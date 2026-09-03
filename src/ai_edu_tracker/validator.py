"""Stable article-ID citation validation with evidence-file binding."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from html import unescape
from pathlib import Path

from markdown_it import MarkdownIt

from .artifact_auth import sign_artifact
from .models import EvidenceBundle, ValidatedArtifact
from .secure_io import MAX_EVIDENCE_BYTES, read_bounded_file

CITATION_RE = re.compile(r"\[@article:([A-Za-z0-9_-]{3,128})\]")
HTML_RE = re.compile(r"<[/!]?[A-Za-z][^>]*>")
URL_RE = re.compile(r"\bhttps?://\S+", re.IGNORECASE)
SECRET_RE = re.compile(
    r"(?:\b(?:api[_ -]?key|password|secret|token)\b\s*[:=]\s*\S+"
    r"|\bsk-[A-Za-z0-9_-]{8,}|\bAKIA[A-Z0-9]{16}\b|\bxox[baprs]-\S+)",
    re.IGNORECASE,
)


def _visible_text(draft_markdown: str) -> tuple[str, str]:
    """Accept only headings/paragraph visible text; citations in code, links, images, and HTML never count."""
    if _contains_url(draft_markdown):
        raise ValueError("draft must not contain URLs")
    if HTML_RE.search(draft_markdown):
        raise ValueError("draft must not contain HTML or script remnants")
    if SECRET_RE.search(draft_markdown):
        raise ValueError("draft appears to contain a secret")
    visible: list[str] = []
    title = "Validated AI education media brief"
    heading_open = False
    allowed_blocks = {
        "heading_open",
        "heading_close",
        "paragraph_open",
        "paragraph_close",
        "inline",
    }
    for token in MarkdownIt("commonmark").parse(draft_markdown):
        if token.type not in allowed_blocks:
            raise ValueError("draft contains unsupported Markdown construct")
        if token.type == "heading_open":
            heading_open = token.tag == "h1"
        elif token.type == "heading_close":
            heading_open = False
        elif token.type == "inline":
            text_parts: list[str] = []
            for child in token.children or []:
                if child.type == "text":
                    text_parts.append(child.content)
                elif child.type not in {"softbreak", "hardbreak"}:
                    raise ValueError("draft contains links, images, code, or unsupported Markdown")
            text = "".join(text_parts)
            visible.append(text)
            if heading_open and text.strip():
                title = text.strip()[:300]
    text = "\n".join(visible)
    if _contains_url(text):
        raise ValueError("draft must not contain URLs")
    return text, title


def _contains_url(value: str) -> bool:
    """Detect direct, Markdown-escaped, and HTML-entity URL spellings."""
    decoded = unescape(value)
    normalized = re.sub(r"\\(?=[:/])", "", decoded)
    return URL_RE.search(normalized) is not None


def validate_draft(
    draft_markdown: str,
    evidence: EvidenceBundle,
    evidence_path: Path,
    now: datetime | None = None,
) -> ValidatedArtifact:
    """Create a 24-hour artifact bound to both evidence bytes and source-registry digest."""
    visible_text, title = _visible_text(draft_markdown)
    article_ids = sorted(set(CITATION_RE.findall(visible_text)))
    if not article_ids:
        raise ValueError("draft requires [@article:<article_id>] citations")
    try:
        evidence_bytes = read_bounded_file(evidence_path, MAX_EVIDENCE_BYTES)
        on_disk = EvidenceBundle.model_validate_json(evidence_bytes)
    except (OSError, ValueError) as error:
        raise ValueError("evidence path is unreadable, invalid, or too large") from error
    if on_disk.sha256() != evidence.sha256():
        raise ValueError("evidence object does not match evidence path")
    known_ids = {article.article_id for article in evidence.articles}
    unknown = sorted(set(article_ids) - known_ids)
    if unknown:
        raise ValueError(f"draft cites article_id absent from evidence: {unknown[0]}")
    validated_at = now or datetime.now(UTC)
    if validated_at.tzinfo is None:
        raise ValueError("validation time must be timezone-aware")
    unsigned = ValidatedArtifact(
        schema_version="validated-artifact/v1",
        title=title,
        draft_markdown=draft_markdown,
        evidence_path=str(evidence_path.resolve()),
        evidence_sha256=sha256(evidence_bytes).hexdigest(),
        config_digest=evidence.config_digest,
        draft_sha256=sha256(draft_markdown.encode("utf-8")).hexdigest(),
        article_ids=article_ids,
        validated_at=validated_at,
        expires_at=validated_at + timedelta(hours=24),
        mac="0" * 64,
    )
    return sign_artifact(unsigned)
