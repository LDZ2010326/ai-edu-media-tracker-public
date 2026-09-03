# AI Education Media Tracker

An Apache-2.0, local-first Python 3.12+ collector for domestic AI-education media. It emits a typed `EvidenceBundle v1`; it does not call an LLM, upload data, or emit telemetry. A host agent may analyze the bundle, but all collected web material remains untrusted data.

## Fixed v1 sources

| ID | Discovery endpoint | Adapter | Transport trust |
| --- | --- | --- | --- |
| `duozhi` | `http://www.duozhi.com/` | only `/industry/<category>/YYYYMMDD<n>.shtml` links | `untrusted_http` |
| `duojing` | `http://www.djcapital.net/nr.jsp` | only `/nd.jsp?id=...` links | `untrusted_http` |
| `jiemodui` | `https://www.jiemodui.com/rss.xml` | RSS `<item>` links matching `/N/<id>.html` | `trusted_https` |

HTTP-origin records are never silently upgraded: every redirect must remain on the fixed host, and the resulting article retains `untrusted_http`.

## Quick start

```bash
uv sync --extra dev
uv run ai-edu-tracker doctor
uv run ai-edu-tracker fetch --track domestic --since today --output evidence.json
# Drafts cite stable article IDs, for example: Claim [@article:art_abc123...]
uv run ai-edu-tracker validate draft.md --evidence evidence.json --output artifact.json
```

`--since today` is a real Asia/Shanghai calendar window. Sources must provide a parseable publication date. Undated articles produce structured `date` errors; valid out-of-window articles are normal exclusions recorded in `filtered_count`. For reproducible tests, the fetcher accepts an injectable clock.

`EvidenceBundle v1` contains `run_id`, `config_digest`, `window`, per-source results (including normal window `filtered_count`), and normalized articles. Every article contains `article_id`, `canonical_url`, `content_sha256`, `transport_trust`, and `truncated`. Content is normalized to 100 KB/article and 1 MB/bundle.

## Validation and optional publication

Validator citations use exactly `[@article:<article_id>]`. It rejects raw Markdown URLs (including reference definitions and autolinks), HTML/script remnants, and likely secrets; it binds the artifact to the resolved evidence path, evidence hash, and source configuration digest for 24 hours. It HMAC-authenticates all artifact fields with a private, stable local key. This detects accidental and cross-boundary tampering, not a full compromise of the same local account. The publisher verifies the MAC before rereading the bound evidence path and hashes/digest.

Publishing is opt-in and accepts only an artifact:

```bash
export LARK_CLI_PATH=/absolute/path/to/lark-cli
export FEISHU_WIKI_NODE_TOKEN=your-wiki-node-token
uv run ai-edu-tracker publish feishu --artifact artifact.json
```

`FEISHU_WIKI_NODE_TOKEN` identifies the destination Wiki node; it is not an API credential. Authenticate separately with `lark-cli auth` and use a least-privilege lark-cli profile. The publisher invokes no shell. It runs `docs +search --query` once, then (only if no exact-title match is found) runs `markdown +create --wiki-token ... --name ... --file ... --as bot` once. The search interface does not provide a parent-scope option; an optional `FEISHU_PARENT_NODE_TOKEN` is used only to filter results that expose `parent_token` metadata, so duplicate detection is best-effort. Unknown results are never retried. Do not commit configuration values, artifacts, or logs.

## Security boundary

Requests are limited to the fixed source IDs and hosts. The production retriever pins validated public DNS answers to direct socket/TLS connections while retaining the canonical Host and SNI, rejects IP-literal URLs, credential-bearing URLs, disallowed schemes, cross-host redirects, and mixed/non-global DNS answers, and applies strict HTTP framing and response-size limits. The injectable httpx transport is reserved for deterministic tests. It applies 5-second connect and 20-second total timeouts, at most three redirects, a maximum of two retries only for 429/5xx/transient connection failures, and a concurrency limit of three. See [SECURITY.md](SECURITY.md).

## Repository security

Pull requests are checked by least-privilege, commit-SHA-pinned CI, dependency review, and CodeQL workflows. See [SECURITY.md](SECURITY.md) and [the pre-publication checklist](docs/github-release-checklist.md) before creating a public mirror or release.

## Exit codes

| Code | Meaning |
| ---: | --- |
| 0 | Success |
| 2 | Usage or local configuration problem |
| 3 | Partial fetch; usable evidence was written |
| 4 | All sources failed; no bundle was written |
| 5 | Security refusal; no bundle was written |
| 6 | Validation failure |
| 7 | Publishing failure, duplicate, or unknown result |

## Development

```bash
uv run --extra dev pytest -q
uv run --extra dev ruff check .
uv run --extra dev mypy src
uv run --extra dev bandit -q -r src
uv run --extra dev pip-audit
```

The `skills/codex` and `skills/claude` folders describe the same safe host-agent boundary.
