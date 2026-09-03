"""Private-by-default local artifact writes."""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

MAX_ARTIFACT_BYTES = 1_100_000
MAX_DRAFT_BYTES = 1_000_000
MAX_EVIDENCE_BYTES = 2_500_000


class BoundedReadError(ValueError):
    """An external file is unsafe to consume as a bounded contract input."""


def read_bounded_file(path: Path, maximum_bytes: int) -> bytes:
    """Read one regular, non-symlink file with pre-read and streaming caps."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise BoundedReadError("external file is unreadable or a symbolic link") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise BoundedReadError("external file is not regular")
        if metadata.st_size > maximum_bytes:
            raise BoundedReadError("external file is too large")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(64 * 1024, maximum_bytes + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > maximum_bytes:
                raise BoundedReadError("external file is too large")
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def atomic_write_private(path: Path, payload: bytes) -> None:
    """Write atomically with 0600 permissions, preserving no partly-written public artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
