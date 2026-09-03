#!/usr/bin/env python3
"""Scan tracked public text and reachable Git blobs without echoing matches."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

PATTERNS = (
    re.compile(rb"cli_[A-Za-z0-9]{20,}"),
    re.compile(rb"(?:wikcn|doccn|shtcn|fldcn|nodcn|doxcn)[A-Za-z0-9]{8,}"),
    re.compile(rb"/(?:Users|home)/[A-Za-z0-9._-]+/"),
    re.compile(
        rb"(?:app[_-]?secret|api[_-]?key|access[_-]?token|client[_-]?secret)"
        rb"\s*[:=]\s*[^$<{\s][^\s]{7,}",
        re.IGNORECASE,
    ),
)
SAFE_LITERAL_REPLACEMENTS = {
    # Historical test fixture retained in old blobs; built in pieces so this scanner scans itself.
    "tests/contract/test_cli.py": (b"/" + b"Users/private/socket",),
}


def _has_secret(path: str, payload: bytes) -> bool:
    for fixture in SAFE_LITERAL_REPLACEMENTS.get(path, ()):
        payload = payload.replace(fixture, b"<known-test-fixture>")
    return any(pattern.search(payload) for pattern in PATTERNS)


def _git(git: str, repo: Path, *arguments: str) -> bytes:
    return subprocess.check_output(  # noqa: S603 - absolute git executable, fixed arguments
        [git, "-C", str(repo), *arguments],
        stderr=subprocess.DEVNULL,
    )


def _current_findings(git: str, repo: Path) -> list[str]:
    findings: list[str] = []
    for raw_path in _git(git, repo, "ls-files", "-z").split(b"\0"):
        if not raw_path:
            continue
        path = raw_path.decode("utf-8", errors="surrogateescape")
        if _has_secret(path, (repo / path).read_bytes()):
            findings.append(f"working tree: {path}")
    return findings


def _history_findings(git: str, repo: Path) -> list[str]:
    findings: list[str] = []
    blobs: set[tuple[str, str]] = set()
    commits = _git(git, repo, "rev-list", "--all").decode().splitlines()
    for commit in commits:
        listing = _git(git, repo, "ls-tree", "-r", "-z", "--full-tree", commit)
        for entry in listing.split(b"\0"):
            if not entry:
                continue
            metadata, raw_path = entry.split(b"\t", 1)
            blob = metadata.split()[2].decode()
            path = raw_path.decode("utf-8", errors="surrogateescape")
            blobs.add((blob, path))
    for blob, path in sorted(blobs):
        if _has_secret(path, _git(git, repo, "cat-file", "blob", blob)):
            findings.append(f"history blob {blob[:12]}: {path}")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--history", action="store_true")
    args = parser.parse_args()
    git = shutil.which("git")
    if git is None:
        print("secret scan could not find git", file=sys.stderr)
        return 2
    repo = args.repo.resolve()
    findings = _current_findings(git, repo)
    if args.history:
        findings.extend(_history_findings(git, repo))
    for finding in findings:
        print(f"secret-like content detected in {finding}", file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
