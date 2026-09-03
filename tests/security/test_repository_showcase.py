"""Public-repository presentation contracts that must not silently regress."""

from __future__ import annotations

import re
import struct
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
    section_pattern = re.compile(r"<!-- section:([a-z-]+) -->")
    assert section_pattern.findall(chinese) == section_pattern.findall(english)
    command_pattern = re.compile(r"```bash\n(.*?)```", re.DOTALL)
    assert command_pattern.findall(chinese) == command_pattern.findall(english)


def test_community_docs_define_safe_contribution_routes() -> None:
    contribution = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    conduct = (ROOT / "CODE_OF_CONDUCT.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "docs" / "roadmap.md").read_text(encoding="utf-8")
    pull_request = (ROOT / ".github" / "pull_request_template.md").read_text(
        encoding="utf-8"
    )

    for marker in ("uv sync --locked", "uv run --extra dev pytest -q", "Pull Request"):
        assert marker in contribution
    assert "Private Vulnerability Reporting" in contribution
    assert "security/advisories/new" in contribution
    assert "公开 Issue" in contribution
    assert "security/advisories/new" in conduct
    assert "TODO" not in conduct
    for heading in ("## 近期方向", "## 未来探索", "## 明确非目标"):
        assert heading in roadmap
    assert re.search(r"\b20\d{2}[-/]\d{1,2}[-/]\d{1,2}\b", roadmap) is None
    for item in ("测试证据", "文档", "安全影响", "来源与版权"):
        assert item in pull_request


def test_sample_report_has_traceable_short_entries() -> None:
    report_path = ROOT / "examples" / "sample-report.md"
    assert report_path.is_file(), "sample report must be published"
    report = report_path.read_text(encoding="utf-8")
    assert report.count("### ") >= 2
    for field in ("来源：", "发布时间：", "抓取日期：", "短摘要：", "原文链接："):
        assert report.count(field) >= 2
    assert len(report.encode("utf-8")) <= 12_000
    assert "正文内容" not in report
    assert len(re.findall(r"https?://(?:www\.)?(?:duozhi\.com|djcapital\.net|jiemodui\.com)/", report)) >= 2


def test_installation_guide_has_three_verified_routes_and_uninstall_steps() -> None:
    guide_path = ROOT / "docs" / "installation.md"
    assert guide_path.is_file(), "installation guide must be published"
    guide = guide_path.read_text(encoding="utf-8")
    for heading in ("## Claude Code Skill", "## Codex Skill", "## Python CLI"):
        assert heading in guide
    assert guide.count("### 验证") == 3
    assert guide.count("### 卸载") == 3
    assert "ai-edu-media-tracker-public" not in guide
    assert "pip install ai-edu-media-tracker" not in guide
    assert "自动发布" not in guide


def test_assets_have_expected_dimensions_and_no_remote_dependencies() -> None:
    social = ROOT / "assets" / "brand" / "social-preview.png"
    report = ROOT / "assets" / "demo" / "report-preview.png"
    logo = ROOT / "assets" / "brand" / "logo.svg"
    workflow = ROOT / "assets" / "demo" / "workflow.svg"
    for path in (social, report, logo, workflow):
        assert path.is_file(), f"missing showcase asset: {path.relative_to(ROOT)}"

    def png_size(path: Path) -> tuple[int, int]:
        payload = path.read_bytes()
        assert payload.startswith(b"\x89PNG\r\n\x1a\n")
        return struct.unpack(">II", payload[16:24])

    assert png_size(social) == (1280, 640)
    report_width, report_height = png_size(report)
    assert report_width >= 1200
    assert report_height >= 700
    for path in (logo, workflow):
        svg = path.read_text(encoding="utf-8")
        assert "<script" not in svg.lower()
        assert re.search(r"(?:href|src)=[\"']https?://", svg, flags=re.IGNORECASE) is None
    for path in (social, report):
        payload = path.read_bytes()
        for marker in (b"/Users/", b"/home/", b"FEISHU_", b"cli_"):
            assert marker not in payload


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
