"""Repository-level release controls that must not silently regress."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
FULL_SHA = re.compile(r"^[^\s@]+@[a-f0-9]{40}(?:\s+#.*)?$")


def _workflow(name: str) -> tuple[str, dict[str, object]]:
    text = (WORKFLOWS / name).read_text(encoding="utf-8")
    parsed = yaml.safe_load(text)
    assert isinstance(parsed, dict)
    return text, parsed


def test_workflows_are_least_privilege_and_pin_actions() -> None:
    for path in WORKFLOWS.glob("*.yml"):
        text, workflow = _workflow(path.name)
        assert "pull_request_target" not in workflow
        assert workflow.get("permissions") == {"contents": "read"} or path.name == "codeql.yml"
        if path.name == "codeql.yml":
            assert workflow.get("permissions") == {
                "contents": "read",
                "security-events": "write",
            }
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("uses:"):
                assert FULL_SHA.fullmatch(stripped.removeprefix("uses:").strip())
        assert "${{ secrets." not in text


def test_ci_runs_all_local_release_gates() -> None:
    text, _ = _workflow("ci.yml")
    for command in (
        "pytest -q",
        "ruff check .",
        "mypy src",
        "bandit -q -r src",
        "pip-audit",
        "uv build",
    ):
        assert command in text


def test_publication_uses_node_identifier_names_not_credential_names() -> None:
    publisher = (ROOT / "src" / "ai_edu_tracker" / "publisher.py").read_text(encoding="utf-8")
    assert "FEISHU_WIKI_NODE_TOKEN" in publisher
    assert 'os.environ.get("FEISHU_WIKI_TOKEN"' not in publisher
