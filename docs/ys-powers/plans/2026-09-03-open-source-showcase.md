# 开源项目产品化展示升级 Implementation Plan

**Goal:** 将仓库升级为以静态 Demo 和真实示例报告为第一触点、再分流到 Claude Code Skill、Codex Skill 与 Python CLI 的中英双语开源产品入口。

**Architecture:** 以 `examples/sample-report.md` 和经过验证的安装契约作为内容事实源，由静态视觉资产呈现结果，再由同构的中英文 README 编排用户路径。社区文件补齐贡献入口；仓库重命名、Topics、Social Preview 与安全控制回查作为合并后的独立发布阶段，不能用本地文件状态替代 GitHub 实际状态。

**Tech Stack:** GitHub Flavored Markdown、SVG、PNG、Python 3.12、pytest、uv、GitHub Actions、GitHub CLI/API

**Spec:** `docs/ys-powers/specs/2026-09-03-open-source-showcase-design.md`

## Global Constraints

- 仅改变展示、文档、社区文件、测试和 GitHub 仓库元数据；不得改变 `src/ai_edu_tracker/` 的运行时行为。
- 中文 `README.md` 为主入口，`README_EN.md` 为等价英文入口，功能命令和限制必须一致。
- 访客先看到静态 Demo 与示例报告，再选择 Skill 或 CLI 安装路径。
- 示例只使用真实公开来源的标题、时间、原创短摘要、原文链接和抓取日期，不提交抓取正文或 EvidenceBundle。
- 所有公开安装命令必须在 `mktemp -d` 创建的干净目录中实际验证；不稳定协议降级为手工复制，不宣称“一键安装”。
- 图片及其元数据不得包含用户名、本地绝对路径、飞书节点 ID、认证信息、API Key、日志或运行制品。
- 徽章只展示可由 GitHub、Release、LICENSE 或 CI 实际验证的状态，不展示虚构用户数、下载量、Stars、评价或性能指标。
- `main` 的 ruleset、Secret Scanning、Push Protection、CodeQL、Dependency Review 和只读 Actions 权限不得被绕过或弱化。
- 合并 PR、重命名仓库、关闭 Dependabot PR、创建/覆盖 Release 和上传 Social Preview 前必须取得用户明确授权。

## Dependency Map

```text
Task 1 文档安全契约与许可证
  ├──> Task 2 真实示例报告
  ├──> Task 3 安装路径验证
  └──> Task 4 静态视觉资产（同时依赖 Task 2）

Task 2 + Task 3 + Task 4
  └──> Task 5 中英文产品 README

Task 1
  └──> Task 6 社区贡献入口
        └──> Task 7 本地发布候选总验收（同时依赖 Task 5）
              └──> Task 8 GitHub 合并后迁移与公开状态回查
```

## Task 1: 建立展示契约并恢复许可证识别基础

**Status:** Completed

**Description:** 用先失败的仓库契约测试固定双语入口、Demo/示例/安装链接、社区文件、图片可访问性和敏感信息边界，并将 `LICENSE` 恢复为 GitHub 可识别的标准 Apache-2.0 文本。

**Files:**
- Create: `tests/security/test_repository_showcase.py`
- Modify: `LICENSE`
- Test: `tests/security/test_repository_showcase.py`

**Interfaces:**
- Consumes: Spec 中的文件清单、安全边界和 `Apache-2.0` 识别要求
- Produces: `test_repository_showcase.py` 仓库展示契约；标准 Apache-2.0 根许可证文本

**Acceptance criteria:**
- [ ] 测试明确要求 `README.md`、`README_EN.md`、`examples/sample-report.md`、`docs/installation.md`、社区文件与必需图片路径存在。
- [ ] 测试检查 README 语言互链、三个安装入口、完整示例入口、非空图片 `alt` 和禁止的凭证/本地路径形态。
- [ ] `LICENSE` 与 Apache-2.0 官方标准文本一致，不保留自定义缩写或替换字段。
- [ ] 本任务不修改任何 `src/ai_edu_tracker/` 文件。

**Verification:**
- [ ] RED: `uv run --extra dev pytest -q tests/security/test_repository_showcase.py` 因尚缺展示文件而按预期失败
- [ ] GREEN: `uv run --extra dev pytest -q tests/security/test_repository_showcase.py -k license` 通过
- [ ] Regression: `uv run --extra dev pytest -q tests/security/test_repository_security.py` 通过
- [ ] Manual: 对比官方 Apache-2.0 文本来源，并记录来源 URL 与获取日期

**Dependencies:** None

**Estimated scope:** S

## Task 2: 提供可核验的真实示例报告

**Status:** Completed

**Description:** 创建一份面向访客的短篇示例报告，以真实公开文章证明输出形态，同时维持版权、安全与来源可追溯边界。

**Files:**
- Create: `examples/sample-report.md`
- Modify: `tests/security/test_repository_showcase.py`
- Test: `tests/security/test_repository_showcase.py`

**Interfaces:**
- Consumes: 固定来源 `duozhi`、`duojing`、`jiemodui` 的公开文章元数据与 Spec 的示例字段约束
- Produces: 每条均含 `来源`、`发布时间`、`抓取日期`、`短摘要`、`原文链接` 的公开示例报告

**Acceptance criteria:**
- [ ] 示例至少覆盖两个可访问的固定来源，且不因某一来源临时不可用而伪造第三条内容。
- [ ] 每条记录包含来源、发布时间、抓取日期、HTTPS/HTTP 原文链接和原创短摘要。
- [ ] 摘要不包含大段原文、用户数据、飞书信息、EvidenceBundle、内部日志或本地路径。
- [ ] 对检查时失效的链接显式标注检查日期和状态，不静默替换。

**Verification:**
- [ ] RED: `uv run --extra dev pytest -q tests/security/test_repository_showcase.py -k sample_report` 在示例缺失或字段不完整时失败
- [ ] GREEN: `uv run --extra dev pytest -q tests/security/test_repository_showcase.py -k sample_report` 通过
- [ ] Regression: `uv run --extra dev pytest -q tests/security/test_repository_security.py tests/security/test_repository_showcase.py` 通过
- [ ] Manual: 匿名打开每个原文链接，逐条核对标题、来源、发布时间、抓取日期和摘要原创性

**Dependencies:** Task 1

**Estimated scope:** S

## Task 3: 交付三条经过验证的安装路径

**Status:** Completed

**Description:** 为 Claude Code Skill、Codex Skill 和 Python CLI 编写安装、最短体验与卸载说明，且只公开在干净环境中实际成功的命令。

**Files:**
- Create: `docs/installation.md`
- Modify: `tests/security/test_repository_showcase.py`
- Test: `tests/security/test_repository_showcase.py`

**Interfaces:**
- Consumes: `skills/claude/SKILL.md`、`skills/codex/SKILL.md`、`pyproject.toml` 的真实目录和入口点
- Produces: 三个标题明确的安装契约：`Claude Code Skill`、`Codex Skill`、`Python CLI`

**Acceptance criteria:**
- [ ] 每条路径包含前置条件、安装、验证、最短体验和卸载步骤。
- [ ] Claude Code 与 Codex 使用各平台当前可验证的本地安装方式；没有稳定远程协议时使用复制目录方式。
- [ ] CLI 路径从 GitHub 仓库安装或检出，不声称包已发布到 PyPI。
- [ ] 所有命令使用仓库重命名后的目标 URL `LDZ2010326/ai-edu-media-tracker`，并在重命名前通过本地路径完成等价验证。
- [ ] 文档明确飞书发布为可选行为，且不要求用户把认证值写入仓库。

**Verification:**
- [ ] RED: `uv run --extra dev pytest -q tests/security/test_repository_showcase.py -k installation` 在安装章节或卸载步骤缺失时失败
- [ ] GREEN: `uv run --extra dev pytest -q tests/security/test_repository_showcase.py -k installation` 通过
- [ ] Regression: `uv run --extra dev pytest -q tests/contract/test_cli.py tests/security/test_repository_showcase.py` 通过
- [ ] Manual: 分别在三个独立 `mktemp -d` 目录执行 Claude Code、Codex 和 CLI 安装、验证与卸载命令，并保存不含本地绝对路径或凭证的结果摘要

**Dependencies:** Task 1

**Estimated scope:** M

## Checkpoint: 内容事实源

- [ ] Task 1–3 的全部验收标准通过
- [ ] `tests/security/test_repository_security.py` 与 `tests/security/test_repository_showcase.py` 通过
- [ ] 示例报告和三条安装路径可以独立演示
- [ ] 人工复核示例版权边界、安装命令证据和 LICENSE 标准文本后再制作视觉资产

## Task 4: 创建静态 Demo 与品牌资产

**Status:** Completed

**Description:** 根据同版示例报告创建报告预览、文字等价流程图、最小 Logo 和 Social Preview，使图片加载成功时增强理解、加载失败时不阻断主路径。

**Files:**
- Create: `assets/brand/logo.svg`
- Create: `assets/brand/social-preview.png`
- Create: `assets/demo/report-preview.png`
- Create: `assets/demo/workflow.svg`
- Modify: `tests/security/test_repository_showcase.py`

**Interfaces:**
- Consumes: Task 2 的 `examples/sample-report.md` 字段和已批准的数据流
- Produces: 1280×640 `social-preview.png`；报告预览 PNG；`sources -> EvidenceBundle -> report -> optional Feishu` SVG；可复用 Logo SVG

**Acceptance criteria:**
- [ ] `social-preview.png` 精确为 1280×640，标题与核心图形处于中央安全区域。
- [ ] `report-preview.png` 与当前示例报告的来源、日期和摘要一致，不展示额外虚构数据。
- [ ] `workflow.svg` 不加载远程脚本、字体或图片，且与 Spec 的文字数据流一致。
- [ ] 所有资产均不包含 EXIF、本地路径、用户名、令牌、节点 ID、浏览器账户或无关窗口内容。
- [ ] 视觉风格保持结果优先和低噪声，不使用虚构指标徽章。

**Verification:**
- [ ] RED: `uv run --extra dev pytest -q tests/security/test_repository_showcase.py -k assets` 因尺寸、文件或安全约束未满足而失败
- [ ] GREEN: `uv run --extra dev pytest -q tests/security/test_repository_showcase.py -k assets` 通过
- [ ] Regression: `uv run --extra dev pytest -q tests/security/test_repository_showcase.py` 通过
- [ ] Manual: 原始尺寸查看三项资产，验证报告一致性、中央安全区域、窄屏辨识度和无敏感信息

**Dependencies:** Task 1, Task 2

**Estimated scope:** M

## Task 5: 重构中英文产品入口

**Status:** Completed

**Description:** 将 README 重构为产品结果优先的中文主入口，并提供结构、命令、功能和限制等价的英文版本。

**Files:**
- Modify: `README.md`
- Create: `README_EN.md`
- Modify: `tests/security/test_repository_showcase.py`
- Test: `tests/security/test_repository_showcase.py`

**Interfaces:**
- Consumes: Task 2 示例报告、Task 3 安装契约、Task 4 静态资产、现有 `SECURITY.md`
- Produces: 同构章节顺序的中英文 README；首屏 Demo；三个安装分流；安全、Roadmap 和贡献入口

**Acceptance criteria:**
- [ ] 中文首屏无需滚动即可看到价值主张、报告预览和完整示例入口。
- [ ] 前两个屏幕包含 Claude Code Skill、Codex Skill、Python CLI 三个入口。
- [ ] 两个 README 顶部互链，章节顺序一致，功能代码块和运行限制一致。
- [ ] README 只简述安全边界并链接 `SECURITY.md`，不复制长篇内部实现说明。
- [ ] 图片具有描述内容的 `alt`，流程图附近包含不依赖图片的文本流程。
- [ ] 所有相对链接均指向存在的仓库文件，所有徽章均对应可验证状态。

**Verification:**
- [ ] RED: `uv run --extra dev pytest -q tests/security/test_repository_showcase.py -k 'readme or parity or links'` 在旧 README 结构下失败
- [ ] GREEN: `uv run --extra dev pytest -q tests/security/test_repository_showcase.py -k 'readme or parity or links'` 通过
- [ ] Regression: `uv run --extra dev pytest -q tests/security/test_repository_security.py tests/security/test_repository_showcase.py` 通过
- [ ] Manual: 在 GitHub Markdown 桌面宽屏与窄屏预览中确认首屏顺序、图片清晰度、代码块和表格无明显横向阅读障碍

**Dependencies:** Task 2, Task 3, Task 4

**Estimated scope:** M

## Checkpoint: 产品入口

- [ ] Task 4–5 的全部验收标准通过
- [ ] 静态 Demo、完整示例和三条安装入口形成可演示的端到端访客路径
- [ ] 中英文 README 契约测试和现有仓库安全测试通过
- [ ] 人工审阅首屏、窄屏、图片替代文本和所有公开承诺后再补齐社区入口

## Task 6: 补齐社区贡献入口

**Status:** Completed

**Description:** 提供最小而完整的贡献、行为规范、Roadmap 和结构化 Issue 入口，使新用户可以报告 Bug、建议功能或反馈数据源异常。

**Files:**
- Create: `CONTRIBUTING.md`
- Create: `CODE_OF_CONDUCT.md`
- Create: `docs/roadmap.md`
- Modify: `.github/pull_request_template.md`
- Modify: `tests/security/test_repository_showcase.py`

**Interfaces:**
- Consumes: 当前 `uv` 质量门禁、`SECURITY.md` 私密披露边界、Spec 的近期能力与非目标
- Produces: 公开贡献流程、社区行为规范、有限 Roadmap、与强制检查一致的 PR 清单

**Acceptance criteria:**
- [ ] `CONTRIBUTING.md` 给出安装、测试、分支、PR 和安全漏洞分流流程。
- [ ] `CODE_OF_CONDUCT.md` 包含行为要求、处理方式和有效联系路径，不留下模板占位符。
- [ ] `docs/roadmap.md` 区分近期方向、未来探索和明确非目标，不承诺日期或未实现功能。
- [ ] PR 模板要求测试证据、文档同步、安全影响和真实来源版权检查。
- [ ] 安全漏洞被引导到 Private Vulnerability Reporting，不要求公开 Issue 披露。

**Verification:**
- [ ] RED: `uv run --extra dev pytest -q tests/security/test_repository_showcase.py -k community` 因社区文件缺失而失败
- [ ] GREEN: `uv run --extra dev pytest -q tests/security/test_repository_showcase.py -k community` 通过
- [ ] Regression: `uv run --extra dev pytest -q tests/security/test_repository_security.py tests/security/test_repository_showcase.py` 通过
- [ ] Manual: 从陌生贡献者视角走读 Bug、功能建议、安全漏洞和 PR 四条路径

**Dependencies:** Task 1

**Estimated scope:** S

## Task 7: 提供结构化 Issue 表单并完成本地发布候选验收

**Status:** Completed

**Description:** 增加三类 Issue 表单，随后对完整展示候选运行文档安全、代码回归、依赖审计和构建检查，形成可提交 PR 的发布候选。

**Files:**
- Create: `.github/ISSUE_TEMPLATE/bug_report.yml`
- Create: `.github/ISSUE_TEMPLATE/feature_request.yml`
- Create: `.github/ISSUE_TEMPLATE/source_issue.yml`
- Create: `.github/ISSUE_TEMPLATE/config.yml`
- Modify: `tests/security/test_repository_showcase.py`

**Interfaces:**
- Consumes: Task 6 的贡献分流和 `SECURITY.md` 私密披露入口
- Produces: Bug、功能建议、数据源异常三个表单；禁用空白 Issue 的模板配置；完整本地发布候选证据

**Acceptance criteria:**
- [ ] 三个表单均有唯一名称、描述、labels 和必填复现/需求/来源字段。
- [ ] 数据源异常表单要求 source ID、公开 URL、观察日期和预期/实际行为，不要求粘贴抓取正文或凭证。
- [ ] `config.yml` 禁用空白 Issue，并链接 Private Vulnerability Reporting 或 `SECURITY.md`。
- [ ] 仓库展示契约测试全部通过，现有 73 项测试不回归。
- [ ] Ruff、strict Mypy、Bandit、pip-audit、`uv build` 和 `git diff --check` 全部通过。

**Verification:**
- [ ] RED: `uv run --extra dev pytest -q tests/security/test_repository_showcase.py -k issue_templates` 在表单缺失时失败
- [ ] GREEN: `uv run --extra dev pytest -q tests/security/test_repository_showcase.py` 通过
- [ ] Regression: `uv run --extra dev pytest -q && uv run --extra dev ruff check . && uv run --extra dev mypy src && uv run --extra dev bandit -q -r src && uv run --extra dev pip-audit && uv build && git diff --check` 通过
- [ ] Manual: 在 GitHub 表单预览中确认字段、labels、安全分流和窄屏可用性

**Dependencies:** Task 5, Task 6

**Estimated scope:** M

## Checkpoint: 可合并发布候选

- [ ] Task 6–7 的全部验收标准通过
- [ ] 完整本地门禁和构建通过，仓库无敏感信息或非预期生成文件
- [ ] 功能分支已通过独立五维审查，PR 中 `verify`、`dependency-review`、`analyze` 全部成功
- [ ] 人工批准 PR 合并、仓库重命名和 Social Preview 上传后才进入外部状态变更

## Task 8: 完成 GitHub 品牌迁移并回查公开状态

**Status:** Awaiting explicit external-change authorization

**Description:** 在用户明确批准并合并展示 PR 后，将仓库重命名为 `ai-edu-media-tracker`，设置可发现性元数据和 Social Preview，并逐项验证安全控制、Release 与匿名访问未回归。

**Files:**
- Inspect: `docs/github-release-checklist.md`
- Inspect: `README.md`
- Inspect: `README_EN.md`
- Inspect: `docs/installation.md`
- Inspect: `assets/brand/social-preview.png`

**Interfaces:**
- Consumes: 已合并的展示候选、`assets/brand/social-preview.png`、GitHub 当前 API schema、现有 ruleset ID 和 Release `v0.1.0`
- Produces: `LDZ2010326/ai-edu-media-tracker` 公开仓库；Description；Topics；Social Preview；更新后的 clone/install URL；逐项回查记录

**Acceptance criteria:**
- [ ] 新仓库 URL 为 `https://github.com/LDZ2010326/ai-edu-media-tracker`，旧 URL 匿名访问会重定向到新 URL。
- [ ] Description 清楚说明本地优先的中国 AI 教育媒体追踪用途；Topics 至少包含 `claude-code`、`codex`、`ai-education`、`news-aggregator`、`python` 和 `feishu`。
- [ ] Social Preview 使用已验证的 1280×640 PNG，匿名页面分享预览可辨识。
- [ ] `origin`、README 和安装文档全部使用新 URL，不依赖旧重定向。
- [ ] GitHub API 返回 `visibility=public`、`private=false`、`license.spdx_id=Apache-2.0`。
- [ ] `main` ruleset 仍要求 PR、1 人批准、对话解决、`verify`、`dependency-review`、`analyze`，且禁止删除和强推。
- [ ] Secret Scanning、Push Protection、Dependabot、安全更新、Private Vulnerability Reporting 和只读 Actions 权限均保持启用。
- [ ] `v0.1.0` 标签与制品仍可访问，Secret Scanning 和 Code Scanning 均为 0 个新增开放告警。

**Verification:**
- [ ] RED: 重命名前执行目标 URL 的匿名 HTTP 与 `gh api repos/LDZ2010326/ai-edu-media-tracker` 检查失败，证明验证命令指向新目标
- [ ] GREEN: 重命名和元数据设置后，`gh repo view LDZ2010326/ai-edu-media-tracker`、目标仓库 API、ruleset API 和匿名 HTTP 检查全部通过
- [ ] Regression: 重命名后的 `main` 上 GitHub Actions `verify`、`dependency-review`、`analyze` 保持成功，`git rev-parse HEAD` 与 `git ls-remote origin refs/heads/main` 一致
- [ ] Manual: 在匿名桌面和窄屏页面检查 README 首屏、Issue 表单、Community Profile、Social Preview、旧 URL 重定向和 Release 下载

**Dependencies:** Task 7；用户已明确批准 PR 合并、仓库重命名和 Social Preview 上传

**Estimated scope:** M

## Task 9: 修复 Skill 与 CLI 的端到端安装契约

**Status:** Completed

**Description:** 修复 `uv sync` 仅将命令放入项目虚拟环境、而已安装 Skill 在任意目录调用裸
`ai-edu-tracker` 导致退出 127 的问题。

**Files:**
- Modify: `docs/installation.md`
- Modify: `tests/security/test_repository_showcase.py`

**Acceptance criteria:**
- [ ] CLI 使用 `uv tool install .` 安装为用户工具，不声称已发布到 PyPI。
- [ ] 文档说明并验证 `uv tool dir --bin` 的 PATH 前置条件。
- [ ] 从项目目录外调用裸 `ai-edu-tracker doctor` 成功，与两个 Skill 的实际命令一致。
- [ ] CLI 卸载使用 `uv tool uninstall ai-edu-media-tracker`。

**Verification:**
- [ ] RED: 端到端测试证明当前裸 CLI 不可用。
- [ ] GREEN: 在隔离的 `UV_TOOL_DIR`、`UV_TOOL_BIN_DIR` 和 `HOME` 下完成安装、项目外验证与卸载。
- [ ] Regression: `uv run --extra dev pytest -q tests/security/test_repository_showcase.py`。

**Dependencies:** Task 3

## Task 10: 防止 Skill 安装覆盖和卸载误删

**Status:** Completed

**Description:** 为 Claude Code 与 Codex 的复制安装加入同名目录冲突拒绝和 ownership marker，
卸载仅在 marker 与 Skill 名称同时匹配时执行。

**Files:**
- Create: `scripts/install-skill.sh`
- Modify: `docs/installation.md`
- Modify: `tests/security/test_repository_showcase.py`

**Acceptance criteria:**
- [ ] 已存在同名目录时安装失败且原文件保持不变。
- [ ] 新安装写入项目专用 ownership marker。
- [ ] 缺失 marker 或 Skill 名称不匹配时卸载失败且目录保持不变。
- [ ] 正常安装后的卸载只删除该固定 Skill 目录。

**Verification:**
- [ ] RED: 当前命令覆盖既有目录且无 ownership 验证。
- [ ] GREEN: 在隔离 HOME 中执行两套文档命令，覆盖拒绝、误删拒绝与正常卸载均符合预期。
- [ ] Regression: `uv run --extra dev pytest -q tests/security/test_repository_showcase.py`。

**Dependencies:** Task 9

## Task 11: 扩大公开文件与 Git 历史敏感信息门禁

**Status:** Completed

**Description:** 修复敏感信息测试仅扫描固定展示清单、遗漏 PR 模板、Spec、Plan 与 Git 历史的问题。

**Files:**
- Create: `scripts/scan-public-secrets.py`
- Modify: `tests/security/test_repository_showcase.py`
- Modify: `.github/workflows/ci.yml`

**Acceptance criteria:**
- [ ] 当前检出的全部公开文本文件进入扫描，测试夹具的刻意攻击样例使用明确排除规则。
- [ ] CI 以完整历史检出，并扫描所有可达提交中的凭证形态与个人绝对路径。
- [ ] 扫描不输出匹配到的秘密值，只报告文件或提交标识。

**Verification:**
- [ ] RED: 临时公开文本或历史 fixture 中的凭证形态使门禁失败。
- [ ] GREEN: 当前树和可达历史扫描通过。
- [ ] Regression: 仓库安全测试、workflow 权限测试与 `git diff --check` 通过。

**Dependencies:** Task 10

## Task 12: 提供社区事件私密报告路径

**Status:** Completed

**Description:** 将骚扰、隐私或其他敏感社区事件明确分流到现有私密渠道，避免要求在公开
Issue 或 PR 披露；不发布未经用户授权的个人邮箱。

**Files:**
- Modify: `CODE_OF_CONDUCT.md`
- Modify: `SECURITY.md`
- Modify: `tests/security/test_repository_showcase.py`

**Acceptance criteria:**
- [ ] 非敏感行为问题可以公开反馈，敏感社区事件明确使用私密报告渠道。
- [ ] 私密渠道明确接受 confidential community report，不将其误描述成漏洞。
- [ ] 不新增个人邮箱、凭证或外部服务。

**Verification:**
- [ ] RED: 当前社区文档没有 confidential community report 契约。
- [ ] GREEN: 社区与安全文档测试通过。
- [ ] Regression: 完整测试、Ruff、Mypy、Bandit、pip-audit、build 与 diff check 通过。

**Dependencies:** Task 11

## Task 13: 支持自定义 CODEX_HOME

**Status:** Completed

**Description:** 修复安装器固定写入 `$HOME/.codex`、与安装文档承诺的自定义 Codex home 不一致。

**Files:**
- Modify: `scripts/install-skill.sh`
- Modify: `docs/installation.md`
- Modify: `tests/security/test_repository_showcase.py`

**Acceptance criteria:**
- [ ] 未设置 `CODEX_HOME` 时仍使用 `$HOME/.codex`。
- [ ] 设置绝对 `CODEX_HOME` 时，安装、验证与卸载均使用其 `skills` 子目录。
- [ ] 文档给出与安装器一致的环境变量方式，不再要求替换不存在的命令文本。

**Verification:**
- [ ] RED: 隔离测试证明设置 `CODEX_HOME` 后仍错误写入 `$HOME/.codex`。
- [ ] GREEN: 默认与自定义路径生命周期测试均通过。
- [ ] Regression: Skill 安装安全测试与 Ruff 通过。

**Dependencies:** Task 10

## Task 14: 将用户级 CLI 安装绑定到锁定依赖

**Status:** In progress

**Description:** 修复 `uv tool install .` 独立解析最新依赖、绕过仓库已审计 `uv.lock` 的问题。

**Files:**
- Create: `requirements-cli.lock`
- Modify: `docs/installation.md`
- Modify: `tests/security/test_repository_showcase.py`

**Acceptance criteria:**
- [ ] 从 `uv.lock` 导出不包含项目自身的生产依赖锁文件并提交。
- [ ] `uv tool install` 使用该文件约束/补充全部运行时依赖。
- [ ] 隔离安装后的版本与锁文件一致，裸 CLI 在项目外可用。
- [ ] 锁文件可由明确命令从 `uv.lock` 重建。

**Verification:**
- [ ] RED: 安装文档当前未引用任何锁定 requirements 文件。
- [ ] GREEN: 隔离 tool 安装、版本核对、doctor 与卸载通过。
- [ ] Regression: `uv lock --check`、安装契约测试与依赖审计通过。

**Dependencies:** Task 13

## Task 15: 消除 secret scanner 整文件盲区

**Status:** Pending

**Description:** 移除扫描器对自身和完整契约测试文件的排除，通过拆分刻意假值避免误报。

**Files:**
- Modify: `scripts/scan-public-secrets.py`
- Modify: `tests/contract/test_cli.py`
- Modify: `tests/security/test_repository_showcase.py`

**Acceptance criteria:**
- [ ] 扫描器自身进入当前树和历史扫描。
- [ ] `tests/contract/test_cli.py` 不再整文件排除，刻意路径样例不形成真实匹配串。
- [ ] 测试夹具目录仍以显式前缀排除，且新增任意普通测试文件泄露都会失败。

**Verification:**
- [ ] RED: 测试确认现有 `EXCLUDED_PATHS` 形成盲区。
- [ ] GREEN: 当前树、全部历史和注入测试通过且不回显值。
- [ ] Regression: 完整测试、Ruff、Mypy、Bandit、pip-audit、build 与 diff check 通过。

**Dependencies:** Task 14

## Checkpoint: 公开发布完成

- [ ] Task 8 的全部验收标准通过
- [ ] 新旧 URL、GitHub 元数据、社区入口、Release 和安全设置均有当前状态证据
- [ ] 匿名用户可完成“看 Demo -> 看示例 -> 选择安装路径”的端到端流程
- [ ] 用户确认账户级 MFA；若 GitHub API 仍返回 `null`，明确记录为人工验证项而非自动通过

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| 示例内容的版权或链接有效性变化 | 只保留事实元数据与原创短摘要；发布前逐条匿名核验并记录抓取日期 |
| 安装文档依赖平台易变接口 | 实际执行当前命令；不稳定时采用本地复制；不写未经验证的一键安装承诺 |
| 图片内容与示例报告漂移 | 报告预览以同版 `sample-report.md` 为事实源，变更时契约测试和人工复核同时要求更新 |
| 二进制 PNG 隐藏元数据或敏感信息 | 生成后检查尺寸、metadata 和敏感形态；使用脱敏样例而非真实终端/飞书截图 |
| LICENSE 本地正确但 GitHub 仍不识别 | 使用官方标准文本；将 GitHub API 的 `Apache-2.0` 结果作为 Task 8 硬验收条件 |
| 仓库重命名破坏 URL、ruleset 或 Release | 先合并再改名，按依赖顺序逐项回查；任一关键控制失败即停止宣称完成 |
| Solo maintainer 无法满足 1 人批准 | 不绕过 ruleset；由仓库所有者安排独立 reviewer，合并属于 Ask first 边界 |
| Community Profile 因平台算法未达 100% | 核对缺失文件/API 字段；无法控制的平台项保留返回证据和明确限制 |
| Dependabot PR 让首页显示开放项 | 保留安全更新，不把开放 PR 当作 Bug 数；不得为了展示关闭或自动合并 |

## Open Questions

没有阻塞实施的产品问题。账户级 MFA 无法从当前仓库 API 得到确定状态，必须在最终 Checkpoint 由用户人工确认；该项不能由测试或仓库文件替代。
