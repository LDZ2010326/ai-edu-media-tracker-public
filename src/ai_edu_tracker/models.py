"""Typed, evidence-bound public interchange contracts."""

from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


def digest(value: object) -> str:
    """Canonical JSON digest for files and schema objects."""
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return sha256(encoded.encode("utf-8")).hexdigest()


class TransportTrust(StrEnum):
    TRUSTED_HTTPS = "trusted_https"
    UNTRUSTED_HTTP = "untrusted_http"


class ErrorKind(StrEnum):
    NETWORK = "network"
    SECURITY = "security"
    CONTENT = "content"
    DATE = "date"


class StrictModel(BaseModel):
    """All serialized contracts reject unknown external fields."""

    model_config = ConfigDict(extra="forbid")


class Window(StrictModel):
    start: datetime
    end: datetime


class FetchError(StrictModel):
    kind: ErrorKind
    message: str = Field(min_length=1, max_length=500)
    url: str | None = None
    article_id: str | None = None


class SourceResult(StrictModel):
    source_id: Literal["duozhi", "duojing", "jiemodui"]
    status: Literal["success", "partial", "failed"]
    errors: list[FetchError] = Field(default_factory=list)
    discovered_count: int = Field(default=0, ge=0, le=50)
    filtered_count: int = Field(default=0, ge=0, le=50)
    accepted_count: int = Field(default=0, ge=0, le=50)

    @model_validator(mode="after")
    def validate_counts(self) -> SourceResult:
        if self.accepted_count + self.filtered_count > self.discovered_count:
            raise ValueError("accepted_count + filtered_count exceeds discovered_count")
        return self


class EvidenceArticle(StrictModel):
    article_id: str = Field(pattern=r"^[A-Za-z0-9_-]{3,128}$")
    source_id: Literal["duozhi", "duojing", "jiemodui"]
    canonical_url: HttpUrl
    title: str = Field(min_length=1, max_length=2_000)
    content: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    fetched_at: datetime
    published_at: datetime
    transport_trust: TransportTrust
    truncated: bool

    @model_validator(mode="after")
    def validate_evidence_integrity(self) -> EvidenceArticle:
        if sha256(self.content.encode("utf-8")).hexdigest() != self.content_sha256:
            raise ValueError("content_sha256 does not match content")
        # Runtime import avoids an import cycle while keeping the registry as the single URL policy.
        from .sources import SOURCES

        source = SOURCES[self.source_id]
        canonical = str(self.canonical_url)
        if not source.matches_article(canonical):
            raise ValueError("canonical_url does not match source article pattern")
        expected_trust = (
            TransportTrust.UNTRUSTED_HTTP
            if self.canonical_url.scheme == "http"
            else source.transport_trust
        )
        if self.transport_trust is not expected_trust:
            raise ValueError("transport_trust does not match canonical_url and source")
        return self


class EvidenceBundle(StrictModel):
    schema_version: Literal["evidence-bundle/v1"] = "evidence-bundle/v1"
    run_id: str = Field(pattern=r"^run_[A-Za-z0-9_-]{3,128}$")
    config_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    window: Window
    source_results: list[SourceResult] = Field(min_length=1, max_length=3)
    articles: list[EvidenceArticle] = Field(default_factory=list, max_length=150)

    @model_validator(mode="after")
    def validate_bundle_integrity(self) -> EvidenceBundle:
        result_ids = [result.source_id for result in self.source_results]
        if len(result_ids) != len(set(result_ids)):
            raise ValueError("source_results source_id values must be unique")
        article_ids = [article.article_id for article in self.articles]
        urls = [str(article.canonical_url) for article in self.articles]
        if len(article_ids) != len(set(article_ids)) or len(urls) != len(set(urls)):
            raise ValueError("article_id and canonical_url values must be unique")
        normalized_bytes = sum(len(article.content.encode("utf-8")) for article in self.articles)
        if normalized_bytes > 1_000_000:
            raise ValueError("normalized article content exceeds 1000000 bytes")
        for result in self.source_results:
            accepted = sum(article.source_id == result.source_id for article in self.articles)
            if accepted != result.accepted_count:
                raise ValueError("accepted_count does not match bundle articles")
        return self

    def sha256(self) -> str:
        return digest(self.model_dump(mode="json"))


class ValidatedArtifact(StrictModel):
    schema_version: Literal["validated-artifact/v1"]
    title: str = Field(min_length=1, max_length=300)
    draft_markdown: str = Field(min_length=1, max_length=1_000_000)
    evidence_path: str = Field(min_length=1)
    evidence_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    config_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    draft_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    article_ids: list[str] = Field(min_length=1)
    validated_at: datetime
    expires_at: datetime
    mac: str = Field(pattern=r"^[a-f0-9]{64}$")

    def is_fresh(self, now: datetime) -> bool:
        return self.validated_at <= now < self.expires_at
