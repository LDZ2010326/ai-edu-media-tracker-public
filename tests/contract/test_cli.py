from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from ai_edu_tracker import cli
from ai_edu_tracker.models import ErrorKind, EvidenceBundle, FetchError, SourceResult, Window
from ai_edu_tracker.secure_io import MAX_DRAFT_BYTES, MAX_EVIDENCE_BYTES
from ai_edu_tracker.sources import source_config_digest

runner = CliRunner()


def _failed_bundle() -> EvidenceBundle:
    return EvidenceBundle(
        run_id="run_failed",
        config_digest=source_config_digest(),
        window=Window(start=datetime(2026, 9, 2, tzinfo=UTC), end=datetime(2026, 9, 3, tzinfo=UTC)),
        source_results=[SourceResult(source_id="duozhi", status="failed")],
    )


def test_fetch_all_sources_failed_returns_four_without_output(
    tmp_path: Path, monkeypatch: object
) -> None:
    class StubFetcher:
        async def fetch_track(self, track: str, since: str) -> EvidenceBundle:
            return _failed_bundle()

    monkeypatch.setattr(cli, "Fetcher", StubFetcher)  # type: ignore[attr-defined]
    output = tmp_path / "evidence.json"
    result = runner.invoke(cli.app, ["fetch", "--output", str(output)])
    assert result.exit_code == 4
    assert not output.exists()


def test_doctor_rejects_non_absolute_or_non_executable_lark_path(monkeypatch: object) -> None:
    monkeypatch.setenv("LARK_CLI_PATH", "not-an-executable")  # type: ignore[attr-defined]
    result = runner.invoke(cli.app, ["doctor"])
    assert result.exit_code == 2
    assert '"lark_cli_valid": false' in result.output


def test_cli_does_not_echo_local_path_from_network_failure(
    tmp_path: Path, monkeypatch: object
) -> None:
    class StubFetcher:
        async def fetch_track(self, track: str, since: str) -> EvidenceBundle:
            bundle = _failed_bundle()
            bundle.source_results[0].errors.append(
                FetchError(
                    kind=ErrorKind.NETWORK,
                    message="permission denied: /" "Users/private/socket",
                )
            )
            return bundle

    monkeypatch.setattr(cli, "Fetcher", StubFetcher)  # type: ignore[attr-defined]
    result = runner.invoke(cli.app, ["fetch", "--output", str(tmp_path / "evidence.json")])
    assert result.exit_code == 4
    assert "/" "Users/private" not in result.output


def test_validate_rejects_oversized_evidence_before_json_parsing(tmp_path: Path) -> None:
    draft = tmp_path / "draft.md"
    draft.write_text("# Report\n\n[@article:a_123]", encoding="utf-8")
    evidence = tmp_path / "evidence.json"
    evidence.write_bytes(b"x" * (MAX_EVIDENCE_BYTES + 1))
    result = runner.invoke(cli.app, ["validate", str(draft), "--evidence", str(evidence)])
    assert result.exit_code == 6
    assert "too large" in result.output


def test_validate_rejects_oversized_draft_before_markdown_parsing(tmp_path: Path) -> None:
    draft = tmp_path / "draft.md"
    draft.write_bytes(b"x" * (MAX_DRAFT_BYTES + 1))
    evidence = tmp_path / "evidence.json"
    evidence.write_text(_failed_bundle().model_dump_json(), encoding="utf-8")
    result = runner.invoke(cli.app, ["validate", str(draft), "--evidence", str(evidence)])
    assert result.exit_code == 6
    assert "too large" in result.output
