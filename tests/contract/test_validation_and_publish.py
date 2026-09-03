import json
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest

from ai_edu_tracker.models import (
    EvidenceArticle,
    EvidenceBundle,
    SourceResult,
    TransportTrust,
    Window,
)
from ai_edu_tracker.publisher import PublishError, load_artifact, publish_artifact
from ai_edu_tracker.sources import source_config_digest
from ai_edu_tracker.state import artifact_hmac_key, state_dir
from ai_edu_tracker.validator import validate_draft


@pytest.fixture(autouse=True)
def isolated_stable_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_EDU_TRACKER_STATE_DIR", str(tmp_path / "stable-state"))


def evidence() -> EvidenceBundle:
    article = EvidenceArticle(
        article_id="a_123",
        source_id="duozhi",
        canonical_url="http://www.duozhi.com/industry/insight/2026090218790.shtml",
        title="A",
        content="body",
        content_sha256=sha256(b"body").hexdigest(),
        fetched_at=datetime(2026, 9, 2, tzinfo=UTC),
        published_at=datetime(2026, 9, 2, tzinfo=UTC),
        transport_trust=TransportTrust.UNTRUSTED_HTTP,
        truncated=False,
    )
    return EvidenceBundle(
        run_id="run_123",
        config_digest=source_config_digest(),
        window=Window(start=datetime(2026, 9, 2, tzinfo=UTC), end=datetime(2026, 9, 3, tzinfo=UTC)),
        source_results=[
            SourceResult(source_id="duozhi", status="success", discovered_count=1, accepted_count=1)
        ],
        articles=[article],
    )


def test_validator_requires_stable_article_id_citations_and_binds_evidence_file(
    tmp_path: Path,
) -> None:
    bundle = evidence()
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(bundle.model_dump_json(), encoding="utf-8")
    artifact = validate_draft("# Report\n\nClaim [@article:a_123]", bundle, evidence_path)
    assert artifact.evidence_path == str(evidence_path.resolve())
    assert artifact.evidence_sha256 == sha256(evidence_path.read_bytes()).hexdigest()
    assert artifact.config_digest == bundle.config_digest
    assert artifact.article_ids == ["a_123"]
    assert artifact.expires_at - artifact.validated_at == timedelta(hours=24)


@pytest.mark.parametrize(
    "draft",
    [
        "# x\n<script>x</script> [@article:a_123]",
        "token=abc [@article:a_123]",
        "# x",
        "`[@article:a_123]`",
        "![image](/untrusted.png) [@article:a_123]",
        "https://untrusted.example [@article:a_123]",
    ],
)
def test_validator_rejects_html_secrets_and_missing_citations(tmp_path: Path, draft: str) -> None:
    with pytest.raises(ValueError):
        validate_draft(draft, evidence(), tmp_path / "evidence.json")


def test_publisher_verifies_bound_evidence_still_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = evidence()
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(bundle.model_dump_json(), encoding="utf-8")
    artifact = validate_draft("# Report\n\nClaim [@article:a_123]", bundle, evidence_path)
    artifact_path = tmp_path / "artifact.json"
    artifact_path.write_text(artifact.model_dump_json(), encoding="utf-8")
    evidence_path.write_text('{"tampered": true}', encoding="utf-8")
    monkeypatch.setenv("LARK_CLI_PATH", "/bin/echo")
    monkeypatch.setenv("FEISHU_WIKI_NODE_TOKEN", "wiki-token")
    with pytest.raises(PublishError, match="evidence"):
        publish_artifact(artifact_path)


def test_lark_arguments_match_verified_cli_help(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = evidence()
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(bundle.model_dump_json(), encoding="utf-8")
    artifact = validate_draft("# Report\n\nClaim [@article:a_123]", bundle, evidence_path)
    artifact_path = tmp_path / "artifact.json"
    artifact_path.write_text(artifact.model_dump_json(), encoding="utf-8")
    commands: list[list[str]] = []

    def fake_json_result(command: list[str]) -> object:
        commands.append(command)
        if "markdown" in command:
            return {"url": "https://example.test/doc"}
        return {"items": []}

    monkeypatch.setattr("ai_edu_tracker.publisher._json_result", fake_json_result)
    monkeypatch.setenv("LARK_CLI_PATH", "/bin/echo")
    monkeypatch.setenv("FEISHU_WIKI_NODE_TOKEN", "wiki-token")
    monkeypatch.setenv("AI_EDU_TRACKER_JOURNAL", str(tmp_path / "journal.jsonl"))
    assert publish_artifact(artifact_path) == "https://example.test/doc"
    assert commands[0] == ["/bin/echo", "docs", "+search", "--query", "Report", "--format", "json"]
    assert commands[1][0:4] == ["/bin/echo", "markdown", "+create", "--wiki-token"]
    assert (
        "--name" in commands[1] and "--file" in commands[1] and commands[1][-2:] == ["--as", "bot"]
    )


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("validated_at", "2026-09-01T00:00:00Z"),
        ("expires_at", "2026-09-04T00:00:00Z"),
        ("title", "altered title"),
        ("evidence_path", "/untrusted/other-evidence.json"),
        ("evidence_sha256", "0" * 64),
        ("draft_markdown", "# altered\n\nClaim [@article:a_123]"),
    ],
)
def test_artifact_mac_rejects_any_safety_critical_field_tampering(
    tmp_path: Path, field: str, replacement: str
) -> None:
    bundle = evidence()
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(bundle.model_dump_json(), encoding="utf-8")
    artifact = validate_draft("# Report\n\nClaim [@article:a_123]", bundle, evidence_path)
    payload = artifact.model_dump(mode="json")
    payload[field] = replacement
    artifact_path = tmp_path / "artifact.json"
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PublishError, match="authentication"):
        load_artifact(artifact_path)


def test_default_journal_survives_cwd_changes_and_prevents_second_create(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = evidence()
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(bundle.model_dump_json(), encoding="utf-8")
    artifact = validate_draft("# Report\n\nClaim [@article:a_123]", bundle, evidence_path)
    artifact_path = tmp_path / "artifact.json"
    artifact_path.write_text(artifact.model_dump_json(), encoding="utf-8")
    commands: list[list[str]] = []

    def fake_json_result(command: list[str]) -> object:
        commands.append(command)
        if "markdown" in command:
            return {"url": "https://example.test/doc"}
        return {"items": []}

    first_cwd, second_cwd = tmp_path / "one", tmp_path / "two"
    first_cwd.mkdir()
    second_cwd.mkdir()
    monkeypatch.setattr("ai_edu_tracker.publisher._json_result", fake_json_result)
    monkeypatch.setenv("LARK_CLI_PATH", "/bin/echo")
    monkeypatch.setenv("FEISHU_WIKI_NODE_TOKEN", "wiki-token")
    monkeypatch.delenv("AI_EDU_TRACKER_JOURNAL", raising=False)
    monkeypatch.chdir(first_cwd)
    assert publish_artifact(artifact_path) == "https://example.test/doc"
    monkeypatch.chdir(second_cwd)
    assert publish_artifact(artifact_path) == "https://example.test/doc"
    assert sum("markdown" in command for command in commands) == 1


def test_artifact_authentication_key_uses_private_stable_state_directory(tmp_path: Path) -> None:
    assert artifact_hmac_key() == artifact_hmac_key()
    directory = state_dir()
    assert directory.stat().st_mode & 0o777 == 0o700
    assert (directory / "artifact-hmac.key").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "draft",
    [
        "# Report\n\n[@article:a_123]\n\n[hidden]: https://example.test/path",
        "# Report\n\n<https://example.test/path> [@article:a_123]",
        "# Report\n\nhttps\\://example.test/path [@article:a_123]",
        "# Report\n\nh&#116;tPs://example.test/path [@article:a_123]",
    ],
)
def test_validator_rejects_raw_urls_outside_visible_ast_text(tmp_path: Path, draft: str) -> None:
    evidence_path = tmp_path / "evidence.json"
    bundle = evidence()
    evidence_path.write_text(bundle.model_dump_json(), encoding="utf-8")
    with pytest.raises(ValueError, match="URLs"):
        validate_draft(draft, bundle, evidence_path)


def test_artifact_and_evidence_reads_reject_oversized_external_files(tmp_path: Path) -> None:
    from ai_edu_tracker.secure_io import MAX_ARTIFACT_BYTES, MAX_EVIDENCE_BYTES

    oversized_artifact = tmp_path / "artifact.json"
    oversized_artifact.write_bytes(b"x" * (MAX_ARTIFACT_BYTES + 1))
    with pytest.raises(PublishError, match="too large"):
        load_artifact(oversized_artifact)

    oversized_evidence = tmp_path / "evidence.json"
    oversized_evidence.write_bytes(b"x" * (MAX_EVIDENCE_BYTES + 1))
    with pytest.raises(ValueError, match="too large"):
        validate_draft("# Report\n\nClaim [@article:a_123]", evidence(), oversized_evidence)


def test_external_models_reject_unknown_json_fields(tmp_path: Path) -> None:
    bundle = evidence()
    evidence_path = tmp_path / "evidence.json"
    payload = bundle.model_dump(mode="json")
    payload["unexpected"] = "untrusted"
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid"):
        validate_draft("# Report\n\nClaim [@article:a_123]", bundle, evidence_path)


def test_journal_symlink_and_oversized_cli_output_are_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = evidence()
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(bundle.model_dump_json(), encoding="utf-8")
    artifact = validate_draft("# Report\n\nClaim [@article:a_123]", bundle, evidence_path)
    artifact_path = tmp_path / "artifact.json"
    artifact_path.write_text(artifact.model_dump_json(), encoding="utf-8")
    monkeypatch.setenv("LARK_CLI_PATH", "/bin/echo")
    monkeypatch.setenv("FEISHU_WIKI_NODE_TOKEN", "wiki-token")
    journal = state_dir() / "feishu-journal.jsonl"
    journal.symlink_to(tmp_path / "outside-journal")
    with pytest.raises(PublishError, match="journal"):
        publish_artifact(artifact_path)


def test_lark_runner_terminates_continuous_oversized_output_early() -> None:
    from ai_edu_tracker.publisher import _json_result

    command = [
        sys.executable,
        "-c",
        "import sys,time; sys.stdout.write('x'*1100000); sys.stdout.flush(); time.sleep(2)",
    ]
    started = time.monotonic()
    with pytest.raises(PublishError, match="output exceeds"):
        _json_result(command)
    assert time.monotonic() - started < 1.0


def test_lark_runner_preserves_only_auth_location_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai_edu_tracker.publisher import _bounded_cli_output

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("HTTP_PROXY", "http://untrusted-proxy.test")
    command = [
        sys.executable,
        "-c",
        "import json,os; print(json.dumps({k:os.environ.get(k) for k in "
        "['HOME','XDG_CONFIG_HOME','HTTP_PROXY']}))",
    ]
    result = json.loads(_bounded_cli_output(command, timeout_seconds=2))
    assert result == {
        "HOME": str(tmp_path),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "HTTP_PROXY": None,
    }


def test_journal_writer_does_not_extend_past_total_byte_limit(tmp_path: Path) -> None:
    from ai_edu_tracker.publisher import MAX_JOURNAL_BYTES, _record

    journal = tmp_path / "journal.jsonl"
    journal.write_bytes(b"x" * MAX_JOURNAL_BYTES)
    with pytest.raises(PublishError, match="journal exceeds"):
        _record(journal, "identity", "pending")


def test_publish_rechecks_freshness_after_search_before_creating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = evidence()
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(bundle.model_dump_json(), encoding="utf-8")
    validated_at = datetime(2026, 9, 2, tzinfo=UTC)
    artifact = validate_draft(
        "# Report\n\nClaim [@article:a_123]", bundle, evidence_path, now=validated_at
    )
    artifact_path = tmp_path / "artifact.json"
    artifact_path.write_text(artifact.model_dump_json(), encoding="utf-8")
    now = [artifact.expires_at - timedelta(seconds=0.4)]
    commands: list[list[str]] = []

    def fake_now() -> datetime:
        return now[0]

    def fake_json_result(command: list[str]) -> object:
        commands.append(command)
        if "docs" in command:
            now[0] += timedelta(seconds=0.6)
            return {"items": []}
        return {"url": "https://example.test/doc"}

    monkeypatch.setattr("ai_edu_tracker.publisher._now", fake_now)
    monkeypatch.setattr("ai_edu_tracker.publisher._json_result", fake_json_result)
    monkeypatch.setenv("LARK_CLI_PATH", "/bin/echo")
    monkeypatch.setenv("FEISHU_WIKI_NODE_TOKEN", "wiki-token")
    with pytest.raises(PublishError, match="expired"):
        publish_artifact(artifact_path)
    assert all("markdown" not in command for command in commands)


def test_local_tempfile_failure_does_not_leave_pending_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = evidence()
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(bundle.model_dump_json(), encoding="utf-8")
    artifact = validate_draft("# Report\n\nClaim [@article:a_123]", bundle, evidence_path)
    artifact_path = tmp_path / "artifact.json"
    artifact_path.write_text(artifact.model_dump_json(), encoding="utf-8")
    commands: list[list[str]] = []

    def fake_json_result(command: list[str]) -> object:
        commands.append(command)
        return {"url": "https://example.test/doc"} if "markdown" in command else {"items": []}

    monkeypatch.setattr("ai_edu_tracker.publisher._json_result", fake_json_result)
    monkeypatch.setenv("LARK_CLI_PATH", "/bin/echo")
    monkeypatch.setenv("FEISHU_WIKI_NODE_TOKEN", "wiki-token")
    original = tempfile.NamedTemporaryFile
    monkeypatch.setattr(
        "ai_edu_tracker.publisher.tempfile.NamedTemporaryFile",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk unavailable")),
    )
    with pytest.raises(PublishError, match="temporary publish file"):
        publish_artifact(artifact_path)

    monkeypatch.setattr("ai_edu_tracker.publisher.tempfile.NamedTemporaryFile", original)
    assert publish_artifact(artifact_path) == "https://example.test/doc"
    assert sum("markdown" in command for command in commands) == 1


def test_state_directory_oserror_uses_publish_error_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = evidence()
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(bundle.model_dump_json(), encoding="utf-8")
    artifact = validate_draft("# Report\n\nClaim [@article:a_123]", bundle, evidence_path)
    artifact_path = tmp_path / "artifact.json"
    artifact_path.write_text(artifact.model_dump_json(), encoding="utf-8")
    monkeypatch.setenv("LARK_CLI_PATH", "/bin/echo")
    monkeypatch.setenv("FEISHU_WIKI_NODE_TOKEN", "wiki-token")
    monkeypatch.delenv("AI_EDU_TRACKER_JOURNAL", raising=False)
    monkeypatch.setattr(
        "ai_edu_tracker.publisher.state_dir",
        lambda: (_ for _ in ()).throw(PermissionError("state denied")),
    )
    with pytest.raises(PublishError, match="publisher state"):
        publish_artifact(artifact_path)
