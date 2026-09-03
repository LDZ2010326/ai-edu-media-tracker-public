# Security policy

## Threat boundary

All collected page, feed, title, date, link, and article content is untrusted data. It must never be treated as a command, tool argument, URL to visit, authorization request, or request for a secret. The package does not run embedded content, invoke an AI model, collect telemetry, or publish unless the user explicitly invokes the publisher with an already validated artifact.

The v1 collector permits only the three compile-time source IDs and fixed canonical hosts. It rejects IP literal and credential-bearing URLs, private/mixed DNS answers, host-changing redirects, non-default ports, unsupported content encodings/disallowed MIME responses, and proxy environment routing. It accepts only identity or bounded, strict, single-member gzip: compressed input and decompressed output are each capped at 5 MB, and truncated, trailing, and multi-member gzip streams are rejected. Each production hop resolves to approved public IPs and connects directly to one of those IPs while retaining the canonical Host header and HTTPS SNI. It revalidates redirects and uses a streamed 5 MB response cap before buffering. Limits also include 5-second connect / 20-second total request timing, three redirects, two bounded retries for only retryable failures, three concurrent requests, 50 candidates/source, 100 KB normalized article content, and 1 MB normalized bundle content.

多知 and 多鲸 start from HTTP compatibility endpoints. Their evidence uses `transport_trust: untrusted_http` even if a same-host redirect reaches HTTPS. This is a warning, not an authenticity claim.

## Publisher boundary

Publication requires a fresh `ValidatedArtifact`, an absolute executable `LARK_CLI_PATH`, and `FEISHU_WIKI_NODE_TOKEN`. The node token identifies a destination Wiki node and is not an authentication credential; authentication is managed by the selected lark-cli auth profile, which should be least privilege. Validation signs every artifact field (except its MAC) with a stable local HMAC-SHA256 key before writing it; publication verifies that MAC in constant time before any replay checks. Artifact input is capped at 1.1 MB, draft input at 1 MB, and evidence input at 2.5 MB before parsing; every external Pydantic contract rejects unknown fields. The key and the local `0600` locked publication journal live in a user-stable `0700` application state directory (or an explicitly configured absolute state directory), rather than the current working directory. Key, journal, and lock files reject symbolic links. The journal is capped at 1 MB / 10,000 records. Feishu CLI stdout is streamed from a pipe and capped at 1 MB; an overrun or timeout kills and reaps its dedicated process group. This detects accidental and cross-boundary artifact tampering; it does not protect against a complete compromise of the same user account. The tool never uses a shell. Its child-process environment is an allowlist containing locale, absolute PATH entries needed by script interpreters, and HOME/XDG configuration locations needed by the selected lark-cli auth profile; proxy and credential variables are not forwarded. It verifies raw evidence bytes, re-runs draft validation, re-derives title/citations/expiry, and checks the source-config digest. It rechecks artifact freshness after acquiring the journal lock, immediately before search, and immediately before pending/create effects. The journal records `pending`, `succeeded`, and `reconcile` states to prevent concurrent duplicate publication on one host. A duplicate or unknown result is a failure and is never retried. Parent-scoped duplicate search is only best-effort because the available search command has no parent scope flag.

## Supported versions

| Version | Supported |
| --- | --- |
| Latest tagged `0.1.x` release | Yes |
| Unreleased `main` | Best effort; not a release |
| Older releases | No |

## Reporting

Use this repository's **Security** tab and GitHub Security Advisories “Report a vulnerability” flow for a private report; do not open a public issue first. Repository maintainers must enable private vulnerability reporting before public launch. Until that control is enabled, do not claim that a private reporting channel is available. Do not include credentials, cookies, authentication material, private artifacts, personal paths, or raw production logs in an issue.

The same private form also accepts a sensitive Code of Conduct report. Prefix its title with
`confidential community report`; maintainers will handle it as a confidential community matter,
not require the reporter to characterize it as a software vulnerability. Non-sensitive community
feedback may remain in a public issue or pull request.

Maintainers target acknowledgement within 3 business days, an initial assessment within 7 business days, and coordinated remediation timelines based on severity. These are response targets, not guaranteed service levels.
