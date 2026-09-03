# GitHub pre-publication security checklist

Repository files cannot prove GitHub account or repository settings. A maintainer must complete and
record this checklist after repository creation and before changing visibility to public.

- [ ] The exact reviewed initial commit was created from an explicit staged-file allowlist; the worktree is clean.
- [ ] Secret scanning and push protection are enabled; a full-history scan has no unresolved findings.
- [ ] Dependabot alerts/security updates and dependency graph are enabled.
- [ ] CodeQL completed successfully at least once.
- [ ] Private vulnerability reporting is enabled and maintainers receive security-alert notifications.
- [ ] `main` has a ruleset requiring pull requests, one approval, conversation resolution, and the CI,
      dependency-review, and CodeQL checks; branch deletion and force pushes are blocked.
- [ ] Default Actions workflow permissions are read-only; first-time external contributors require approval.
- [ ] Maintainers use phishing-resistant MFA and the minimum repository role needed.
- [ ] No Feishu authentication credentials, lark-cli profiles, `.env`, evidence, artifacts, or logs are committed.
- [ ] The release tag points to the reviewed commit and release artifact SHA-256 values are published.
- [ ] If PyPI publishing is added, it uses Trusted Publisher/OIDC and a protected release environment,
      not a long-lived API token.
