# 贡献指南

感谢你帮助改进 AI 教育媒体追踪器。提交代码、文档或数据源反馈前，请先阅读本指南与 [SECURITY.md](SECURITY.md)。

## 本地开发

需要 Python 3.12+ 与 [uv](https://docs.astral.sh/uv/)。

```bash
git clone https://github.com/LDZ2010326/ai-edu-media-tracker-public.git
cd ai-edu-media-tracker
uv sync --locked
uv run --extra dev pytest -q
```

完整质量门禁见 [README](README.md#开发)。新增行为应先写能复现问题的测试，再实现最小修复。

## 分支与 Pull Request

1. 从最新默认分支创建范围明确的功能分支，例如 `fix/source-date-parser`。
2. 保持提交小而可审阅，不要混入证据包、日志、个人路径或本地配置。
3. 同步更新测试和面向用户的文档，并在 Pull Request 中附上实际运行的验证结果。
4. 对真实文章只保留必要的标题、短摘要与原文链接；确认来源与版权边界。

## 反馈分流

- 可复现的软件问题：使用 Bug 表单。
- 新能力建议：使用功能建议表单。
- 公开数据源失效或解析异常：使用数据源异常表单，仅提供公开 URL，不粘贴整篇正文、Cookie 或凭证。
- 安全漏洞：不要创建公开 Issue。请使用 GitHub **Private Vulnerability Reporting**：<https://github.com/LDZ2010326/ai-edu-media-tracker-public/security/advisories/new>。

提交贡献即表示你同意遵守 [社区行为规范](CODE_OF_CONDUCT.md)。
