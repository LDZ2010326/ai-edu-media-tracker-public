# GitHub Open-Source Security Release Review

Review date: 2026-09-03 (Asia/Shanghai)
Target: pre-commit working tree of `ai-edu-media-tracker` 0.1.0
Review type: full greenfield snapshot and release-artifact review (no historical diff exists)

## 1. Executive summary

| Severity | Count |
| --- | ---: |
| Critical | 0 |
| High | 0 |
| Medium | 3 |
| Low | 2 |

**Original overall risk: Medium**
**Original recommendation: CONDITIONAL / do not make the repository public until M-01 and M-02 are completed.**

## Post-review remediation status

Repository-level remediation was completed on 2026-09-03 and must still be anchored to an explicitly
authorized initial commit:

- **M-01 remediated in the working tree:** least-privilege, immutable-SHA-pinned CI, dependency
  review, CodeQL, and Dependabot configurations were added. Their hosted execution remains unverified
  until GitHub is created.
- **M-02 pending user-authorized Git operation:** no commit, remote repository, ruleset, or release was
  created. This is intentionally not represented as fixed.
- **M-03 retracted as a false positive:** direct inspection of `lark-cli markdown +create --help`
  establishes that `--wiki-token` is a destination Wiki node identifier, not an authentication
  credential. Authentication is handled by `lark-cli auth`/profiles. The environment variable was
  renamed to `FEISHU_WIKI_NODE_TOKEN` to remove ambiguity.
- **L-01 remediated in files:** SECURITY.md now defines supported versions, response targets, and the
  prerequisite to enable private vulnerability reporting.
- **L-02 remediated:** README now matches the filtered-date and pinned direct socket/TLS behavior.
- **Follow-up implementation review remediated:** production safety-boundary refusals now retain the
  `security` classification, and an explicitly empty source selection is rejected instead of silently
  expanding to every configured source. A `Content-Length` response now completes without waiting for
  a keep-alive connection to close. Regression tests cover these cases and confirm that a connection
  timeout on one validated address already falls back to the next address (`TimeoutError` is caught by
  the existing `OSError` handler).

**Current recommendation: CONDITIONAL.** Repository files are ready for an initial reviewed commit;
public release remains blocked on M-02 and the GitHub-side checklist.

The runtime security boundary is substantially implemented and adversarially tested. The remaining
release blockers are repository governance and provenance controls, rather than a demonstrated remote
code-execution or data-exfiltration flaw.

Verified positive evidence:

- 73 tests pass; Ruff, strict Mypy, Bandit, `uv lock --check`, and `git diff --check` pass.
- `pip-audit` reported no known vulnerability in third-party dependencies on 2026-09-03. The local,
  unpublished package itself was skipped, as expected.
- A clean sdist and wheel were built. The wheel contains 13 package modules, metadata, entry point,
  README metadata, and Apache-2.0 license only; no tests, environment file, runtime artifacts, or
  detected credential patterns are present.
- The sdist contains source, tests, skills, documentation, lockfile, and a placeholder-only
  `.env.example`; it contains no observed secret.
- Network SSRF/DNS pinning, redirect restrictions, response framing, bounded gzip decoding, Markdown
  injection boundaries, artifact HMAC authentication, bounded file/process IO, and local publish
  idempotency have direct regression tests.

## 2. Assessment dimensions and release standards

These criteria combine practical GitHub controls with OpenSSF Scorecard-style source/build risk
checks. OpenSSF explicitly treats dangerous workflows as critical and branch protection, code review,
and token permissions as high-risk checks. GitHub recommends Dependabot alerts, secret scanning, push
protection, and code scanning for public repositories.

| Dimension | Minimum release standard | Strong target | Current result |
| --- | --- | --- | --- |
| Secrets and privacy | No real credentials, user data, artifacts, absolute personal paths, or logs in the complete Git history and release artifacts | Secret scanning plus push protection | **Pass locally / GitHub setting unverified** |
| Runtime trust boundaries | Fixed outbound destinations, SSRF and redirect defenses, bounded inputs, safe parsing, no implicit publication, least privilege | Adversarial tests for every boundary | **Pass within reviewed scope** |
| Dependency security | Lockfile with hashes; vulnerability audit clean at release time | Dependabot and PR dependency review | **Partial: local controls pass; automation absent** |
| CI/CD security | Tests and security checks required on every PR; workflow token defaults to read-only; third-party actions pinned; no untrusted PR code receives secrets | CodeQL, Scorecard, isolated release environment | **Fail: no workflows exist** |
| Source governance | Protected default branch/ruleset, required review and checks, signed/tagged releases, least-privilege maintainers | Two-person review and CODEOWNERS | **Not verifiable before GitHub creation** |
| Build and provenance | Clean, reproducible package contents built from a reviewed commit | PyPI trusted publishing and artifact/SBOM attestations | **Partial: clean local build; no CI provenance** |
| Secure defaults | Publishing opt-in; generated sensitive files ignored and mode-restricted; no telemetry by default | Sandboxed integration and credential isolation | **Pass, with M-03 exception** |
| Vulnerability response | SECURITY policy, supported versions, private contact path, response expectations | GitHub private vulnerability reporting and advisory process | **Partial** |
| Documentation integrity | Security claims match the code and limitations are prominent | Threat model and security architecture maintained as code | **Partial: two stale statements** |
| Verification | Unit/security/contract tests, static analysis, dependency audit, package smoke/build | Multi-version/multi-OS CI and release verification | **Partial: strong local checks, no hosted enforcement** |

Reference baselines:

- [OpenSSF Scorecard checks](https://www.scorecard.dev/)
- [GitHub security and analysis settings](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-security-and-analysis-settings-for-your-repository)
- [GitHub dependency review](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/manage-your-dependency-security/configure-dependency-review-action)
- [GitHub private vulnerability reporting](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository)
- [GitHub artifact attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations)

## 3. Findings

### M-01: No repository-enforced CI or security scanning

**Evidence:** There is no `.github/` directory or workflow in the reviewed tree. All 61 tests and
security checks currently depend on a maintainer running them locally.

**Attack/failure path:** A contributor opens a PR that weakens URL validation or changes a dependency.
Nothing in the repository requires tests, Bandit, dependency audit, or code scanning before merge.
Once public contribution begins, a maintainer can merge a regression without a machine-enforced gate.

**Required remediation:** Add a least-privilege CI workflow for Python 3.12 that runs tests, Ruff,
Mypy, Bandit, lock validation, build, and package-content checks. Add CodeQL or an equivalent scanner,
Dependabot, and dependency review. Declare `permissions: contents: read` at workflow level and pin
third-party actions to immutable commit SHAs. Do not expose publishing credentials to pull-request
workflows.

### M-02: No immutable, reviewable release baseline exists

**Evidence:** `main` has no commit and every project file is untracked. Consequently there is no commit
SHA, tag, review history, branch protection state, or provenance anchor for the reviewed snapshot.

**Impact:** The exact snapshot reviewed here cannot yet be distinguished from later local edits. A
public push or release could contain files not present during this review, and historical secret
scanning cannot be performed against a nonexistent history.

**Required remediation:** Before public visibility, make one reviewed initial commit from the explicit
file allowlist, rerun all gates against that commit, verify `git status` is clean, create the GitHub
repository, enable a default-branch ruleset with required checks/review, then tag the exact reviewed
commit. Do not use `git add -A` without inspecting the index.

### M-03: Feishu wiki token is passed in process arguments — retracted

**Original evidence:** `publisher.py` invokes `lark-cli markdown +create --wiki-token <token> ...`.

**Disposition:** False positive. The term `token` was incorrectly assumed to mean an API credential.
The installed lark-cli defines this argument as the target Wiki node identifier, while authentication
is held by its auth profile. The variable was renamed to prevent recurrence of this ambiguity.

**Remaining control:** Configure lark-cli authentication separately with a least-privilege profile and
never store its actual credentials in this repository.

### L-01: SECURITY.md assumes a GitHub disclosure feature that may not be enabled

`SECURITY.md` tells researchers to use the repository Security tab, but the repository does not yet
exist and private vulnerability reporting cannot be observed. It also does not state supported
versions or expected acknowledgement/remediation windows.

Enable private vulnerability reporting immediately after repository creation, subscribe maintainers
to security alerts, and add supported-version and response-target sections. Until then, provide a real
private contact that does not require the unavailable feature.

### L-02: README contains stale security/behavior statements

At README line 25, out-of-window articles are described together with undated articles as structured
`date` errors, while the implementation intentionally counts valid out-of-window articles as normal
`filtered_count`. At line 45, production responses are described as using
`httpx.AsyncClient.stream`; the hardened production path now uses pinned direct socket/TLS handling in
`safe_http.py`, while httpx is retained for test-transport handling and model/URL utilities.

Update these statements before publication so users do not make security decisions from an obsolete
architecture description.

## 4. GitHub-side release gate

The following settings cannot be proven from this local repository and must be checked after creating
GitHub but before making it public:

1. Enable secret scanning, push protection, Dependabot alerts/security updates, and private
   vulnerability reporting.
2. Enable CodeQL/default code scanning and verify a successful scan, not merely that setup is toggled.
3. Protect `main` with required PR review, required passing checks, conversation resolution, deletion
   protection, and no routine admin bypass.
4. Restrict Actions to approved actions, use read-only default workflow permissions, and require
   approval for first-time external contributors.
5. If publishing to PyPI, use a PyPI Trusted Publisher/OIDC workflow instead of a long-lived API token;
   protect the release environment and generate provenance/attestation for built artifacts.
6. Run a full-history secret scan after the initial commit and immediately before changing visibility.
7. Verify the release tag points to the reviewed clean commit and publish the recorded SHA-256 digests.

## 5. Test and blast-radius assessment

The codebase is small (13 production Python modules) but high risk because it performs network access,
parses hostile content, authenticates artifacts, and invokes an external publisher. Critical flows are
centralized:

- `Fetcher` / `safe_http`: all three source adapters depend on this network boundary.
- `validate_draft` / artifact HMAC: every publishable document depends on this validation boundary.
- `publish_artifact`: the only external publication mutation path.

All three flows have security and contract coverage. No line/branch coverage percentage was claimed
because no coverage instrument is configured. Passing tests establish the exercised cases, not proof
that every parser or OS behavior is safe.

## 6. Scope and limitations

Reviewed all 13 production modules, 12 test/fixture groups, both Skill files, packaging metadata,
lockfile, README, SECURITY policy, ADR, plan, ignore rules, built wheel, and built sdist. The review
included static pattern checks, package-content/credential-pattern inspection, dependency audit,
runtime tests, static typing/lint/security checks, and adversarial analysis of network, validation,
state, subprocess, and publication boundaries.

Not assessed: GitHub account/organization settings, branch rules, maintainer MFA, external lark-cli
implementation, Feishu permissions, live Feishu publication, PyPI project ownership, legal rights to
redistribute scraped content, or every possible secret format. The repository has no commit history,
so differential review, blame, prior-regression analysis, and full-history secret scanning were not
possible.

Confidence is **high for the reviewed local snapshot**, **medium for the eventual GitHub release**, and
**not established for Feishu/PyPI production deployment** until their external controls are observed.
