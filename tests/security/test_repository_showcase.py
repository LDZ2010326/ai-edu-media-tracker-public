"""Public-repository presentation contracts that must not silently regress."""

from __future__ import annotations

import re
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).parents[2]

REQUIRED_SHOWCASE_PATHS = (
    "README.md",
    "README_EN.md",
    "examples/sample-report.md",
    "docs/installation.md",
    "docs/roadmap.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "assets/brand/logo.svg",
    "assets/brand/social-preview.png",
    "assets/demo/report-preview.png",
    "assets/demo/workflow.svg",
    ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/feature_request.yml",
    ".github/ISSUE_TEMPLATE/source_issue.yml",
    ".github/ISSUE_TEMPLATE/config.yml",
)


def test_required_showcase_files_exist() -> None:
    missing = [path for path in REQUIRED_SHOWCASE_PATHS if not (ROOT / path).is_file()]
    assert missing == []


def test_readmes_link_languages_demo_example_and_install_routes() -> None:
    chinese = (ROOT / "README.md").read_text(encoding="utf-8")
    english = (ROOT / "README_EN.md").read_text(encoding="utf-8")
    for text in (chinese, english):
        assert "assets/demo/report-preview.png" in text
        assert "examples/sample-report.md" in text
        assert "docs/installation.md" in text
        assert "Claude Code" in text
        assert "Codex" in text
        assert "Python CLI" in text
        assert re.search(r"!\[[^\]]{8,}\]\(assets/", text)
    assert "README_EN.md" in chinese
    assert "README.md" in english


def test_public_showcase_does_not_contain_credential_shaped_values_or_local_paths() -> None:
    checked = [ROOT / "README.md"]
    checked.extend(ROOT / path for path in REQUIRED_SHOWCASE_PATHS if (ROOT / path).is_file())
    content = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in checked
        if path.suffix.lower() not in {".png"}
    )
    forbidden = (
        r"cli_[a-z0-9]{12,}",
        r"(?:wikcn|doccn|shtcn|fldcn|nodcn|doxcn)[A-Za-z0-9]{8,}",
        r"/(?:Users|home)/[A-Za-z0-9._-]+/",
        r"(?:app[_-]?secret|api[_-]?key|access[_-]?token)\s*[:=]\s*\S{8,}",
    )
    for pattern in forbidden:
        assert re.search(pattern, content, flags=re.IGNORECASE) is None


def test_license_is_complete_apache_2_text() -> None:
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "Apache License\n                           Version 2.0, January 2004" in license_text
    assert "END OF TERMS AND CONDITIONS" in license_text
    assert "http://www.apache.org/licenses/LICENSE-2.0" in license_text
    assert "Copyright [yyyy] [name of copyright owner]" in license_text
    assert sha256(license_text.encode()).hexdigest() == (
        "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4"
    )
