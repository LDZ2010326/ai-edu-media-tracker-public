"""Typer commands and their stable public exit-code contract."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import subprocess  # nosec B404
import sys
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from .fetcher import Fetcher
from .models import ErrorKind, EvidenceBundle
from .publisher import PublishError, _cli_environment, publish_artifact
from .secure_io import MAX_DRAFT_BYTES, MAX_EVIDENCE_BYTES, atomic_write_private, read_bounded_file
from .validator import validate_draft

app = typer.Typer(no_args_is_help=True, add_completion=False)
publish = typer.Typer(no_args_is_help=True, add_completion=False)
app.add_typer(publish, name="publish")

EXIT_SUCCESS = 0
EXIT_USAGE_CONFIG = 2
EXIT_PARTIAL_FETCH = 3
EXIT_ALL_SOURCES_FAILED = 4
EXIT_SECURITY_REFUSAL = 5
EXIT_VALIDATION = 6
EXIT_PUBLISH = 7


def _write(path: Path, payload: str) -> None:
    atomic_write_private(path, payload.encode("utf-8"))


@app.command()
def doctor() -> None:
    """Inspect local prerequisites and any configured lark executable; never invokes it."""
    required = ("httpx", "selectolax", "defusedxml", "pydantic", "markdown_it", "typer")
    missing = [name for name in required if importlib.util.find_spec(name) is None]
    configured_cli = os.environ.get("LARK_CLI_PATH")
    cli_valid = None
    cli_version_valid = None
    if configured_cli:
        path = Path(configured_cli)
        cli_valid = path.is_absolute() and path.is_file() and os.access(path, os.X_OK)
        if cli_valid:
            try:
                probe = subprocess.run(  # noqa: S603  # nosec B603
                [str(path), "--version"],
                shell=False,
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                    timeout=5,
                    env=_cli_environment(),
                )
                cli_version_valid = probe.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                cli_version_valid = False
    report = {
        "python": sys.version.split()[0],
        "python_3_12_or_newer": sys.version_info >= (3, 12),
        "missing": missing,
        "lark_cli_configured": bool(configured_cli),
        "lark_cli_valid": cli_valid,
        "lark_cli_version_valid": cli_version_valid,
        "telemetry": False,
    }
    typer.echo(json.dumps(report, ensure_ascii=False, sort_keys=True))
    if (
        missing
        or not report["python_3_12_or_newer"]
        or cli_valid is False
        or cli_version_valid is False
    ):
        raise typer.Exit(EXIT_USAGE_CONFIG)


@app.command()
def fetch(
    track: Annotated[str, typer.Option()] = "domestic",
    since: Annotated[str, typer.Option()] = "today",
    output: Annotated[Path, typer.Option()] = Path("artifacts/evidence.json"),
) -> None:
    """Collect an EvidenceBundle. Never writes a file when all sources fail or safety refuses."""
    try:
        bundle = asyncio.run(Fetcher().fetch_track(track, since=since))
    except ValueError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(EXIT_USAGE_CONFIG) from error
    errors = [error for result in bundle.source_results for error in result.errors]
    if any(error.kind is ErrorKind.SECURITY for error in errors):
        typer.echo("security refusal; evidence was not written", err=True)
        raise typer.Exit(EXIT_SECURITY_REFUSAL)
    if all(result.status == "failed" for result in bundle.source_results):
        typer.echo("all sources failed; evidence was not written", err=True)
        raise typer.Exit(EXIT_ALL_SOURCES_FAILED)
    _write(output, bundle.model_dump_json(indent=2))
    typer.echo(str(output))
    if any(result.status != "success" for result in bundle.source_results):
        raise typer.Exit(EXIT_PARTIAL_FETCH)


@app.command()
def validate(
    draft: Annotated[Path, typer.Argument(exists=True, readable=True)],
    evidence: Annotated[Path, typer.Option(exists=True, readable=True)],
    output: Annotated[Path, typer.Option()] = Path("artifacts/validated-artifact.json"),
) -> None:
    """Bind explicit article-ID citations to the supplied evidence file for 24 hours."""
    try:
        bundle = EvidenceBundle.model_validate_json(read_bounded_file(evidence, MAX_EVIDENCE_BYTES))
        draft_markdown = read_bounded_file(draft, MAX_DRAFT_BYTES).decode("utf-8")
        artifact = validate_draft(draft_markdown, bundle, evidence)
    except (OSError, ValidationError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(EXIT_VALIDATION) from error
    _write(output, artifact.model_dump_json(indent=2))
    typer.echo(str(output))


@publish.command("feishu")
def feishu(artifact: Annotated[Path, typer.Option(exists=True, readable=True)]) -> None:
    """Publish one validated artifact once; all publisher failures use exit code 7."""
    try:
        typer.echo(publish_artifact(artifact))
    except PublishError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(EXIT_PUBLISH) from error


if __name__ == "__main__":
    app()
