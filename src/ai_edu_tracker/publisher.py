"""Artifact-only Feishu publishing with local idempotency and no shell execution."""

from __future__ import annotations

import fcntl
import json
import os
import select
import signal
import subprocess  # nosec B404
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .artifact_auth import verify_artifact
from .models import EvidenceBundle, ValidatedArtifact
from .secure_io import MAX_ARTIFACT_BYTES, MAX_EVIDENCE_BYTES, read_bounded_file
from .sources import source_config_digest
from .state import StateError, state_dir
from .validator import validate_draft


class PublishError(RuntimeError):
    """All publisher errors are exit-code 7 failures."""


MAX_CLI_OUTPUT_BYTES = 1_000_000
MAX_JOURNAL_BYTES = 1_000_000
MAX_JOURNAL_RECORDS = 10_000


def _now() -> datetime:
    return datetime.now(UTC)


def _configured_cli() -> tuple[str, str]:
    cli = os.environ.get("LARK_CLI_PATH", "")
    wiki_token = os.environ.get("FEISHU_WIKI_NODE_TOKEN", "")
    executable = Path(cli)
    if (
        not cli
        or not wiki_token
        or not executable.is_absolute()
        or not executable.is_file()
        or not os.access(executable, os.X_OK)
    ):
        raise PublishError(
            "LARK_CLI_PATH must be an absolute executable and FEISHU_WIKI_NODE_TOKEN must be set"
        )
    return cli, wiki_token


def load_artifact(path: Path) -> ValidatedArtifact:
    try:
        artifact = ValidatedArtifact.model_validate_json(read_bounded_file(path, MAX_ARTIFACT_BYTES))
    except (OSError, ValidationError, ValueError) as error:
        raise PublishError("artifact is unreadable, invalid, or too large") from error
    try:
        authenticated = verify_artifact(artifact)
    except (StateError, OSError) as error:
        raise PublishError("artifact authentication state is unavailable") from error
    if not authenticated:
        raise PublishError("artifact authentication failed")
    if sha256(
        artifact.draft_markdown.encode()
    ).hexdigest() != artifact.draft_sha256 or not artifact.is_fresh(_now()):
        raise PublishError("artifact hash does not match or validation has expired")
    evidence_path = Path(artifact.evidence_path)
    try:
        raw_evidence = read_bounded_file(evidence_path, MAX_EVIDENCE_BYTES)
        evidence = EvidenceBundle.model_validate_json(raw_evidence)
    except (OSError, ValidationError, ValueError) as error:
        raise PublishError("bound evidence file is unreadable, invalid, or too large") from error
    if sha256(raw_evidence).hexdigest() != artifact.evidence_sha256:
        raise PublishError("bound evidence file hash does not match artifact")
    if (
        evidence.config_digest != artifact.config_digest
        or artifact.config_digest != source_config_digest()
    ):
        raise PublishError("bound evidence config digest does not match current source registry")
    try:
        derived = validate_draft(
            artifact.draft_markdown, evidence, evidence_path, now=artifact.validated_at
        )
    except ValueError as error:
        raise PublishError("artifact draft no longer passes validation") from error
    if any(
        left != right
        for left, right in (
            (derived.title, artifact.title),
            (derived.article_ids, artifact.article_ids),
            (derived.draft_sha256, artifact.draft_sha256),
            (derived.evidence_sha256, artifact.evidence_sha256),
            (derived.config_digest, artifact.config_digest),
            (derived.expires_at, artifact.expires_at),
        )
    ):
        raise PublishError("artifact derived fields do not match evidence and draft")
    return artifact


def _json_result(command: list[str]) -> Any:
    raw_output = _bounded_cli_output(command, timeout_seconds=30)
    try:
        return json.loads(raw_output.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PublishError("Feishu CLI result is unknown; refusing to retry") from error


def _bounded_cli_output(command: list[str], *, timeout_seconds: float) -> bytes:
    """Read a child stdout pipe incrementally and kill its process group on any limit."""
    try:
        process = subprocess.Popen(  # noqa: S603  # nosec B603
            command,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=_cli_environment(),
        )
    except OSError as error:
        raise PublishError("Feishu CLI result is unknown; refusing to retry") from error
    output = process.stdout
    if output is None:
        _terminate_process(process)
        raise PublishError("Feishu CLI result is unknown; refusing to retry")
    collected = bytearray()
    deadline = time.monotonic() + timeout_seconds
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _terminate_process(process)
                raise PublishError("Feishu CLI result is unknown; refusing to retry")
            readable, _, _ = select.select([output], [], [], remaining)
            if not readable:
                _terminate_process(process)
                raise PublishError("Feishu CLI result is unknown; refusing to retry")
            chunk = os.read(
                output.fileno(), min(64 * 1024, MAX_CLI_OUTPUT_BYTES + 1 - len(collected))
            )
            if not chunk:
                try:
                    returncode = process.wait(timeout=max(0.01, deadline - time.monotonic()))
                except subprocess.TimeoutExpired as error:
                    _terminate_process(process)
                    raise PublishError("Feishu CLI result is unknown; refusing to retry") from error
                if returncode != 0:
                    raise PublishError("Feishu CLI result is unknown; refusing to retry")
                return bytes(collected)
            collected.extend(chunk)
            if len(collected) > MAX_CLI_OUTPUT_BYTES:
                _terminate_process(process)
                raise PublishError("Feishu CLI output exceeds configured limit")
    except OSError as error:
        _terminate_process(process)
        raise PublishError("Feishu CLI result is unknown; refusing to retry") from error
    finally:
        output.close()


def _cli_environment() -> dict[str, str]:
    """Preserve only executable/config discovery; never forward proxies or credential variables."""
    environment = {"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    path_entries = [entry for entry in os.environ.get("PATH", "").split(os.pathsep) if Path(entry).is_absolute()]
    environment["PATH"] = os.pathsep.join(path_entries) or "/usr/bin:/bin"
    for name in ("HOME", "XDG_CONFIG_HOME"):
        value = os.environ.get(name)
        if value and Path(value).is_absolute():
            environment[name] = value
    return environment


def _terminate_process(process: subprocess.Popen[bytes]) -> None:
    """Terminate a dedicated process group and reap the leader before returning."""
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            process.kill()
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _journal_path() -> Path:
    configured = os.environ.get("AI_EDU_TRACKER_JOURNAL")
    if configured:
        journal = Path(configured).expanduser()
        if not journal.is_absolute():
            raise PublishError("AI_EDU_TRACKER_JOURNAL must be absolute")
        return journal
    try:
        return state_dir() / "feishu-journal.jsonl"
    except (StateError, OSError) as error:
        raise PublishError("publisher state is unavailable") from error


@contextmanager
def _locked_journal() -> Iterator[Path]:
    journal = _journal_path()
    try:
        journal.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(
            journal.with_suffix(f"{journal.suffix}.lock"),
            os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except OSError as error:
        raise PublishError("journal lock is unavailable or a symbolic link") from error
    try:
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield journal
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _identity(artifact: ValidatedArtifact, wiki_token: str) -> str:
    material = "|".join(
        (
            artifact.title,
            artifact.draft_sha256,
            artifact.evidence_sha256,
            artifact.config_digest,
            sha256(wiki_token.encode()).hexdigest(),
        )
    )
    return sha256(material.encode()).hexdigest()


def _last_record(journal: Path, identity: str) -> dict[str, Any] | None:
    if journal.is_symlink():
        raise PublishError("journal path must not be a symbolic link")
    if not journal.exists():
        return None
    try:
        records = [
            json.loads(line)
            for line in read_bounded_file(journal, MAX_JOURNAL_BYTES).splitlines()
            if line.strip()
        ]
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise PublishError("journal is invalid or exceeds configured limits") from error
    if len(records) > MAX_JOURNAL_RECORDS:
        raise PublishError("journal exceeds configured record limit")
    return next((item for item in reversed(records) if item.get("identity") == identity), None)


def _record(journal: Path, identity: str, status: str, url: str | None = None) -> None:
    payload: dict[str, str] = {
        "identity": identity,
        "status": status,
        "at": datetime.now(UTC).isoformat(),
    }
    if url:
        payload["url"] = url
    encoded = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
    try:
        descriptor = os.open(
            journal,
            os.O_CREAT | os.O_APPEND | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except OSError as error:
        raise PublishError("journal is unavailable or a symbolic link") from error
    os.fchmod(descriptor, 0o600)
    if os.fstat(descriptor).st_size + len(encoded) > MAX_JOURNAL_BYTES:
        os.close(descriptor)
        raise PublishError("journal exceeds configured byte limit")
    with os.fdopen(descriptor, "ab") as file:
        file.write(encoded)
        file.flush()
        os.fsync(file.fileno())


def _duplicate(items: list[Any], title: str) -> bool:
    parent = os.environ.get("FEISHU_PARENT_NODE_TOKEN")
    return any(
        isinstance(item, dict)
        and item.get("title") == title
        and (not parent or item.get("parent_token") in {None, parent})
        for item in items
    )


def publish_artifact(path: Path) -> str:
    """Search/create at most once per locally locked identity; pending results require reconciliation."""
    artifact = load_artifact(path)
    cli, wiki_token = _configured_cli()
    identity = _identity(artifact, wiki_token)
    with _locked_journal() as journal:
        _require_fresh(artifact)
        prior = _last_record(journal, identity)
        prior_url = prior.get("url") if prior else None
        if prior and prior.get("status") == "succeeded" and isinstance(prior_url, str):
            return prior_url
        if prior and prior.get("status") in {"pending", "reconcile"}:
            raise PublishError("publication requires reconciliation; refusing to duplicate")
        _require_fresh(artifact)
        search = _json_result(
            [cli, "docs", "+search", "--query", artifact.title, "--format", "json"]
        )
        items = (
            search.get("items")
            if isinstance(search, dict)
            else search
            if isinstance(search, list)
            else None
        )
        if not isinstance(items, list):
            raise PublishError("Feishu duplicate-check result is unknown; refusing to publish")
        if _duplicate(items, artifact.title):
            _record(journal, identity, "reconcile")
            raise PublishError("exact-title duplicate found; refusing to publish")
        temporary: str | None = None
        try:
            _require_fresh(artifact)
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", suffix=".md", delete=False
                ) as file:
                    os.chmod(file.name, 0o600)
                    file.write(artifact.draft_markdown)
                    file.flush()
                    os.fsync(file.fileno())
                    temporary = file.name
            except OSError as error:
                raise PublishError("temporary publish file could not be prepared") from error
            _require_fresh(artifact)
            _record(journal, identity, "pending")
            _require_fresh(artifact)
            created = _json_result(
                [
                    cli,
                    "markdown",
                    "+create",
                    "--wiki-token",
                    wiki_token,
                    "--name",
                    artifact.title,
                    "--file",
                    temporary,
                    "--as",
                    "bot",
                ]
            )
        finally:
            if temporary:
                Path(temporary).unlink(missing_ok=True)
        if not isinstance(created, dict):
            raise PublishError("Feishu create result is unknown; refusing to retry")
        url = created.get("url")
        if not isinstance(url, str):
            raise PublishError("Feishu create result is unknown; refusing to retry")
        _record(journal, identity, "succeeded", url)
        return url


def _require_fresh(artifact: ValidatedArtifact) -> None:
    if not artifact.is_fresh(_now()):
        raise PublishError("artifact validation has expired")
