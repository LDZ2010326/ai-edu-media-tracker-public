"""Public-repository presentation contracts that must not silently regress."""

from __future__ import annotations

import os
import re
import shutil
import struct
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

import yaml

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
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    assert "confidential community report" in conduct
    assert "confidential community report" in security
    assert "敏感社区事件" in conduct
    assert "TODO" not in conduct
    for heading in ("## 近期方向", "## 未来探索", "## 明确非目标"):
        assert heading in roadmap
    assert re.search(r"\b20\d{2}[-/]\d{1,2}[-/]\d{1,2}\b", roadmap) is None
    for item in ("测试证据", "文档", "安全影响", "来源与版权"):
        assert item in pull_request


def test_issue_templates_are_structured_and_route_security_privately() -> None:
    template_dir = ROOT / ".github" / "ISSUE_TEMPLATE"
    forms = [
        yaml.safe_load((template_dir / filename).read_text(encoding="utf-8"))
        for filename in ("bug_report.yml", "feature_request.yml", "source_issue.yml")
    ]
    assert len({form["name"] for form in forms}) == 3
    for form in forms:
        assert form["description"].strip()
        assert form["labels"]
        required_fields = [
            item
            for item in form["body"]
            if item.get("validations", {}).get("required") is True
        ]
        assert len(required_fields) >= 2

    source_form = forms[2]
    source_text = str(source_form)
    for field in ("source ID", "公开 URL", "观察日期", "预期行为", "实际行为"):
        assert field in source_text
    for forbidden in ("粘贴正文", "Cookie", "凭证"):
        assert forbidden in source_text

    config = yaml.safe_load((template_dir / "config.yml").read_text(encoding="utf-8"))
    assert config["blank_issues_enabled"] is False
    contact_urls = [link["about"] + link["url"] for link in config["contact_links"]]
    assert any("Private Vulnerability Reporting" in item for item in contact_urls)
    assert any("security/advisories/new" in item for item in contact_urls)


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
    assert "uv tool install ." in guide
    assert "--with-requirements requirements-cli.lock" in guide
    assert "uv tool dir --bin" in guide
    assert "uv tool uninstall ai-edu-media-tracker" in guide
    assert "uv sync --locked" not in guide
    assert "ai-edu-media-tracker-public" not in guide
    assert "pip install ai-edu-media-tracker" not in guide
    assert "自动发布" not in guide


def test_cli_requirements_are_exported_from_uv_lock() -> None:
    requirements = ROOT / "requirements-cli.lock"
    assert requirements.is_file()
    uv = shutil.which("uv")
    assert uv is not None
    result = subprocess.run(  # noqa: S603 - fixed uv export command
        [
            uv,
            "export",
            "--locked",
            "--no-dev",
            "--no-emit-project",
            "--no-hashes",
            "--format",
            "requirements-txt",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert requirements.read_text(encoding="utf-8") == result.stdout


def test_skill_installer_refuses_collisions_and_requires_ownership_marker(
    tmp_path: Path,
) -> None:
    installer = ROOT / "scripts" / "install-skill.sh"
    assert installer.is_file(), "a shared safe installer must back both documented skill routes"
    environment = {**os.environ, "HOME": str(tmp_path)}

    for host, parent in (("claude", ".claude"), ("codex", ".codex")):
        target = tmp_path / parent / "skills" / "ai-edu-media-tracker"
        target.mkdir(parents=True)
        sentinel = target / "user-owned.txt"
        sentinel.write_text("keep", encoding="utf-8")

        collision = subprocess.run(  # noqa: S603 - fixed repository script and host enum
            ["/bin/sh", str(installer), "install", host],
            cwd=ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        assert collision.returncode != 0
        assert sentinel.read_text(encoding="utf-8") == "keep"

        sentinel.unlink()
        target.rmdir()
        subprocess.run(  # noqa: S603 - fixed repository script and host enum
            ["/bin/sh", str(installer), "install", host],
            cwd=ROOT,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        marker = target / ".ai-edu-media-tracker-install"
        assert marker.read_text(encoding="utf-8").strip() == "ai-edu-media-tracker:v1"

        marker.unlink()
        refused = subprocess.run(  # noqa: S603 - fixed repository script and host enum
            ["/bin/sh", str(installer), "uninstall", host],
            cwd=ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        assert refused.returncode != 0
        assert target.is_dir()
        marker.write_text("ai-edu-media-tracker:v1\n", encoding="utf-8")
        subprocess.run(  # noqa: S603 - fixed repository script and host enum
            ["/bin/sh", str(installer), "uninstall", host],
            cwd=ROOT,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        assert not target.exists()


def test_skill_installer_honors_custom_codex_home(tmp_path: Path) -> None:
    installer = ROOT / "scripts" / "install-skill.sh"
    custom_codex_home = tmp_path / "custom-codex"
    environment = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "CODEX_HOME": str(custom_codex_home),
    }
    subprocess.run(  # noqa: S603 - fixed repository script and host
        ["/bin/sh", str(installer), "install", "codex"],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    target = custom_codex_home / "skills" / "ai-edu-media-tracker"
    assert (target / "SKILL.md").is_file()
    assert not (tmp_path / "home" / ".codex").exists()
    subprocess.run(  # noqa: S603 - fixed repository script and host
        ["/bin/sh", str(installer), "uninstall", "codex"],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    assert not target.exists()


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


def test_secret_scanner_covers_git_history_without_echoing_values(tmp_path: Path) -> None:
    scanner = ROOT / "scripts" / "scan-public-secrets.py"
    assert scanner.is_file(), "repository and history scanning must use a shared release gate"
    git = shutil.which("git")
    assert git is not None

    def run_git(*arguments: str) -> None:
        subprocess.run(  # noqa: S603 - resolved git executable and fixed test arguments
            [git, "-C", str(tmp_path), *arguments], check=True, capture_output=True
        )

    run_git("init", "-q")
    run_git("config", "user.email", "test@example.invalid")
    run_git("config", "user.name", "Test")
    readme = tmp_path / "README.md"
    readme.write_text("clean\n", encoding="utf-8")
    run_git("add", "README.md")
    run_git("commit", "-qm", "clean")
    secret_value = "api" + "_key = " + ("A" * 24)
    readme.write_text(secret_value + "\n", encoding="utf-8")
    sensitive_test = tmp_path / "tests" / "contract" / "test_cli.py"
    sensitive_test.parent.mkdir(parents=True)
    sensitive_test.write_text(secret_value + "\n", encoding="utf-8")
    disguised_binary = tmp_path / "tests" / "fixtures" / "leak.png"
    disguised_binary.parent.mkdir(parents=True)
    disguised_binary.write_bytes(b"\x00binary\x00" + secret_value.encode())
    dangling_link = tmp_path / "leak-link"
    dangling_link.symlink_to(secret_value)
    run_git(
        "add",
        "README.md",
        "tests/contract/test_cli.py",
        "tests/fixtures/leak.png",
        "leak-link",
    )
    run_git("commit", "-qm", "leak")

    result = subprocess.run(  # noqa: S603 - fixed interpreter, scanner, and temp repo
        [sys.executable, str(scanner), "--repo", str(tmp_path), "--history"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "README.md" in result.stderr
    assert "tests/contract/test_cli.py" in result.stderr
    assert "tests/fixtures/leak.png" in result.stderr
    assert "leak-link" in result.stderr
    assert "Traceback" not in result.stderr
    assert secret_value not in result.stdout + result.stderr


def test_license_is_complete_apache_2_text() -> None:
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "Apache License\n                           Version 2.0, January 2004" in license_text
    assert "END OF TERMS AND CONDITIONS" in license_text
    assert "http://www.apache.org/licenses/LICENSE-2.0" in license_text
    assert "Copyright [yyyy] [name of copyright owner]" in license_text
    assert sha256(license_text.encode()).hexdigest() == (
        "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4"
    )
