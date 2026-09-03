# GitHub release hardening plan

## Problem and root cause

The runtime implementation has security tests, but the repository has no hosted enforcement. A
future pull request could bypass local-only checks, and the reviewed pre-commit snapshot has no commit
SHA that can anchor a release. Two documentation statements also describe behavior that changed
during hardening. Finally, `FEISHU_WIKI_TOKEN` is a misleading name: lark-cli defines
`--wiki-token` as a target Wiki node identifier, while authentication is managed by lark-cli's auth
profile. Treating the node identifier as an API credential produced an incorrect review finding.

## Remediation

1. Add least-privilege, SHA-pinned GitHub Actions for deterministic CI, dependency review, and CodeQL.
2. Add Dependabot configuration for Python and GitHub Actions dependencies.
3. Correct the README network/date semantics and expand SECURITY.md with supported versions,
   disclosure prerequisites, response targets, and GitHub-side controls.
4. Rename the Feishu resource identifier to `FEISHU_WIKI_NODE_TOKEN` and
   `FEISHU_PARENT_NODE_TOKEN`; keep authentication exclusively in lark-cli's configured profile.
5. Add an explicit pre-publication checklist for settings that cannot be configured or verified in a
   local checkout.
6. Build and inspect wheel/sdist, rerun all deterministic gates, and obtain a fresh security review.
7. Preserve security error semantics across both mock and production transports, and reject an
   explicitly empty source selection so caller intent can never broaden into a fetch-all operation.
8. Treat `Content-Length` as the HTTP message boundary rather than waiting for connection close;
   retain and regression-test fallback across multiple validated DNS addresses.

Creating the initial commit, GitHub repository, branch rules, tags, or releases remains a separate Git
mutation and requires explicit user authorization.
