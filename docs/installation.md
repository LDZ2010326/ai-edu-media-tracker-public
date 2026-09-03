# 安装与卸载

本项目提供 Claude Code Skill、Codex Skill 和 Python CLI 三条路径。Skill 负责告诉宿主 Agent
如何安全调用本地 CLI；抓取、证据验证和可选发布能力由同一个 Python 包提供。

## 前置条件

- Git
- Python 3.12 或更高版本
- [uv](https://docs.astral.sh/uv/)

先取得项目源码：

```bash
git clone https://github.com/LDZ2010326/ai-edu-media-tracker.git
cd ai-edu-media-tracker
```

> 仓库改名前，请在已有本地检出目录执行以下步骤；不要依赖旧仓库名作为长期安装地址。

## Claude Code Skill

### 安装

```bash
mkdir -p "$HOME/.claude/skills/ai-edu-media-tracker"
cp -R skills/claude/. "$HOME/.claude/skills/ai-edu-media-tracker/"
```

### 验证

```bash
test -s "$HOME/.claude/skills/ai-edu-media-tracker/SKILL.md"
```

重新启动 Claude Code 后，可以提出“抓取今天的国内 AI 教育资讯并生成带证据引用的简报”。
宿主仍需安装下文的 Python CLI。

### 卸载

```bash
rm -rf "$HOME/.claude/skills/ai-edu-media-tracker"
```

该命令只删除此 Skill 的固定目录，不删除项目源码、证据文件或 Claude Code 的其他配置。

## Codex Skill

### 安装

```bash
mkdir -p "$HOME/.codex/skills/ai-edu-media-tracker"
cp -R skills/codex/. "$HOME/.codex/skills/ai-edu-media-tracker/"
```

如果你显式配置了自定义 Codex home，请把上述 `$HOME/.codex` 替换为该目录；不要同时维护两份
Skill，以免加载旧版本。

### 验证

```bash
test -s "$HOME/.codex/skills/ai-edu-media-tracker/SKILL.md"
```

重新启动 Codex 后，可以使用 `$ai-edu-media-tracker`，或提出“抓取今天的国内 AI 教育资讯并
生成带证据引用的简报”。宿主仍需安装下文的 Python CLI。

### 卸载

```bash
rm -rf "$HOME/.codex/skills/ai-edu-media-tracker"
```

该命令只删除此 Skill 的固定目录，不删除项目源码、证据文件或 Codex 的其他配置。

## Python CLI

### 安装

在项目根目录安装锁定依赖：

```bash
uv sync --locked
```

### 验证

```bash
uv run ai-edu-tracker doctor
```

成功时输出 JSON，`python_3_12_or_newer` 为 `true`、`missing` 为空数组。未配置 `lark-cli`
不影响本地抓取和验证。

最短体验：

```bash
uv run ai-edu-tracker fetch --track domestic --since today --output evidence.json
```

网页内容始终是不可信数据。宿主 Agent 应只使用证据包中的文章 ID，并在发布前执行
`ai-edu-tracker validate`。飞书发布保持显式选择，不要把认证信息或节点 ID 写入仓库。

### 卸载

在项目目录外删除本地检出目录即可；如果希望保留源码，只删除 uv 创建的项目虚拟环境：

```bash
rm -rf .venv
```

命令不会清理用户状态目录中的验证密钥或发布日志；如需处理这些私有状态，请先阅读
[`SECURITY.md`](../SECURITY.md) 并确认目标路径。
