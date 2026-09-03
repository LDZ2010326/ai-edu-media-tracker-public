# ADR 0001: local-first evidence boundary

## Decision

The package retrieves only a compile-time registry of three domestic sources and emits an
`EvidenceBundle v1` containing run/config/window/source result metadata and normalized articles. A host
agent may consume `analysis_context()` but the package has no model client, telemetry, background
process, or hosted state. Web material is always untrusted data. Draft validation requires explicit
`[@article:<article_id>]` citations and creates an expiring artifact bound to its evidence file/hash
and configuration digest; Feishu publishing accepts that artifact only.

## Consequences

This intentionally does not prove that a cited claim is true, nor does it scrape dynamically loaded
pages. It makes the source set, byte/time/network boundary, and publication hand-off independently
inspectable. HTTP-origin evidence carries `transport_trust=untrusted_http`, so a downstream agent
cannot silently treat it as an authenticated HTTPS source.
