"""Stable, private local state used for artifact authentication and publishing."""

from __future__ import annotations

import errno
import os
import stat
import sys
import tempfile
from pathlib import Path


class StateError(ValueError):
    """Private local state is unavailable or does not meet its permission contract."""


def state_dir() -> Path:
    """Return the user-stable state directory, never a current-working-directory path."""
    configured = os.environ.get("AI_EDU_TRACKER_STATE_DIR")
    if configured:
        directory = Path(configured).expanduser()
        if not directory.is_absolute():
            raise StateError("AI_EDU_TRACKER_STATE_DIR must be absolute")
    elif sys.platform == "darwin":
        directory = Path.home() / "Library" / "Application Support" / "ai-edu-media-tracker"
    else:
        xdg_state = os.environ.get("XDG_STATE_HOME")
        base = Path(xdg_state) if xdg_state else Path.home() / ".local" / "state"
        if not base.is_absolute():
            raise StateError("XDG_STATE_HOME must be absolute")
        directory = base / "ai-edu-media-tracker"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    return directory


def artifact_hmac_key() -> bytes:
    """Load or atomically create the stable 256-bit artifact-authentication key."""
    path = state_dir() / "artifact-hmac.key"
    try:
        return _read_key(path)
    except FileNotFoundError:
        return _create_key(path)


def _read_key(path: Path) -> bytes:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as error:
        if error.errno == errno.ENOENT:
            raise FileNotFoundError(path) from error
        raise StateError("artifact authentication key is unreadable") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077:
            raise StateError("artifact authentication key permissions are unsafe")
        key = os.read(descriptor, 33)
        if len(key) != 32:
            raise StateError("artifact authentication key is invalid")
        return key
    finally:
        os.close(descriptor)


def _create_key(path: Path) -> bytes:
    """Publish a fully-written key with link(2), never exposing a partial key file."""
    key = os.urandom(32)
    descriptor, temporary = tempfile.mkstemp(prefix=".artifact-hmac.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(key)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            return _read_key(path)
        return key
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
