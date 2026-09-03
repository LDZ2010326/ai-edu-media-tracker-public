# v1 implementation plan

Scope: a local-only domestic-media tracker with fixed sources, secure retrieval, evidence-bound
validation, and explicitly configured Feishu delivery. No AI analysis provider, network telemetry,
credentials, or persistent state is included.

1. Write failing unit/security/contract tests for URL policy, source-specific discovery, bounded
   streaming retrieval, date windows, validation expiry, and publish gating; run them before implementation.
2. Implement the approved EvidenceBundle v1 fields, fixed RSS/HTML adapters, URL/redirect/DNS policy,
   MIME gate, and normalized-content limits; verify the fetching tests.
3. Implement explicit article-ID citations and a 24-hour artifact bound to evidence path/hash/config;
   verify contract tests.
4. Implement a no-shell, opt-in Feishu publisher with the verified lark-cli arguments and Typer exit
   codes; verify CLI tests.
5. Add public docs, skills, ADR and run lint/type/security/dependency checks.

Assumptions: multi-source web content is hostile input. HTML discovery uses per-source article patterns
and 芥末堆 uses its RSS item links. HTTP origins are deliberately retained for 多知/多鲸 compatibility but
labelled untrusted; redirect host changes are refused. The host agent consumes the resulting
EvidenceBundle and is responsible for interpretation; this package never calls a model or transmits
telemetry.
