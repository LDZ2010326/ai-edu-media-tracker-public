"""Fixed-source, streamed and bounded collection for EvidenceBundle v1."""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from email.utils import parsedate_to_datetime
from hashlib import sha256
from typing import Literal, cast
from urllib.parse import urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import httpx
from defusedxml import ElementTree  # type: ignore[import-untyped]
from pydantic import HttpUrl, ValidationError
from selectolax.parser import HTMLParser

from .content_encoding import ContentEncodingError, decode_chunks
from .models import (
    ErrorKind,
    EvidenceArticle,
    EvidenceBundle,
    FetchError,
    SourceResult,
    TransportTrust,
    Window,
)
from .safe_http import SafeHTTPError
from .safe_http import get_bytes as pinned_get_bytes
from .sources import SOURCES, Source, source_config_digest

CONNECT_SECONDS = 5.0
TOTAL_SECONDS = 20.0
MAX_REDIRECTS = 3
MAX_ARTICLES_PER_SOURCE = 50
MAX_RESPONSE_BYTES = 5_000_000
MAX_NORMALIZED_ARTICLE_BYTES = 100_000
MAX_NORMALIZED_BUNDLE_BYTES = 1_000_000
MAX_CONCURRENCY = 3
ALLOWED_MIME_TYPES = frozenset(
    {"text/html", "application/xhtml+xml", "application/rss+xml", "application/xml", "text/xml"}
)
SOURCE_TIME_ZONE = ZoneInfo("Asia/Shanghai")


class SourcePolicyError(ValueError):
    """The request crossed a fixed source or network safety boundary."""


class FetchLimitError(ValueError):
    """A response or normalized evidence limit was hit."""


class DateError(FetchLimitError):
    """A candidate is missing a parseable, source-provided publication date."""


class ContentTypeError(SourcePolicyError):
    """The response advertised a MIME type the parser is not allowed to handle."""


Resolver = Callable[[str], Awaitable[Iterable[str]]]
Clock = Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class ValidatedURL:
    value: httpx.URL
    transport_trust: TransportTrust

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class Candidate:
    url: str
    published_at: datetime | None = None


def validate_url(url: str, source: Source) -> ValidatedURL:
    """Validate host/scheme ownership before any connection or redirect hop."""
    parsed = urlsplit(url)
    host = (parsed.hostname or "").rstrip(".").lower()
    if parsed.scheme not in source.allowed_schemes:
        raise SourcePolicyError("scheme is not allowlisted")
    try:
        port = parsed.port
    except ValueError as error:
        raise SourcePolicyError("invalid URL port") from error
    if port not in {None, 80 if parsed.scheme == "http" else 443}:
        raise SourcePolicyError("non-default ports are forbidden")
    if not host or parsed.username or parsed.password or host != source.host:
        raise SourcePolicyError("host is not the fixed source host")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise SourcePolicyError("IP-literal hosts are forbidden")
    cleaned = parsed._replace(fragment="")
    trust = TransportTrust.UNTRUSTED_HTTP if cleaned.scheme == "http" else source.transport_trust
    return ValidatedURL(httpx.URL(urlunsplit(cleaned)), trust)


async def resolve_public(host: str) -> list[str]:
    try:
        infos = await asyncio.get_running_loop().run_in_executor(
            None, lambda: socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        )
    except OSError as error:
        raise httpx.ConnectError("hostname resolution failed") from error
    addresses = sorted({str(entry[4][0]) for entry in infos})
    if not addresses:
        raise SourcePolicyError("host did not resolve")
    if any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise SourcePolicyError("hostname resolves to non-public address")
    return addresses


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _parse_source_datetime(value: str | None) -> datetime | None:
    """Parse observed local dates only when the source timezone makes them verifiable."""
    parsed = _parse_datetime(value)
    if parsed is not None:
        return parsed
    if not value:
        return None
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            local = datetime.strptime(value.strip(), pattern).replace(tzinfo=SOURCE_TIME_ZONE)
            return local.astimezone(UTC)
        except ValueError:
            continue
    return None


def _window(since: str, now: datetime) -> Window:
    if now.tzinfo is None:
        raise ValueError("clock must return timezone-aware datetime")
    if since == "today":
        day = now.astimezone(SOURCE_TIME_ZONE).date()
    else:
        try:
            day = datetime.fromisoformat(since).date()
        except ValueError as error:
            raise ValueError("--since must be today or YYYY-MM-DD") from error
    start = datetime.combine(day, time.min, tzinfo=SOURCE_TIME_ZONE)
    return Window(start=start, end=start + timedelta(days=1))


class Fetcher:
    def __init__(
        self,
        transport: httpx.AsyncBaseTransport | None = None,
        resolver: Resolver = resolve_public,
        clock: Clock = lambda: datetime.now(UTC),
    ) -> None:
        self._transport = transport
        self._resolver = resolver
        self._clock = clock
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    async def fetch_track(
        self, track: str, since: str = "today", source_ids: list[str] | None = None
    ) -> EvidenceBundle:
        if track != "domestic":
            raise ValueError("v1 supports only the domestic track")
        ids = list(SOURCES) if source_ids is None else source_ids
        if (
            not ids
            or len(set(ids)) != len(ids)
            or any(source_id not in SOURCES for source_id in ids)
        ):
            raise ValueError("unknown source id")
        now = self._clock()
        window = _window(since, now)
        results = await asyncio.gather(
            *(self._fetch_source(SOURCES[source_id], window) for source_id in ids)
        )
        articles: list[EvidenceArticle] = []
        source_results: list[SourceResult] = []
        used_normalized_bytes = 0
        for source_articles, result in results:
            source_results.append(result)
            for article in source_articles:
                content_bytes = len(article.content.encode("utf-8"))
                if used_normalized_bytes + content_bytes > MAX_NORMALIZED_BUNDLE_BYTES:
                    result.errors.append(
                        FetchError(
                            kind=ErrorKind.CONTENT,
                            message=(
                                f"normalized bundle exceeds {MAX_NORMALIZED_BUNDLE_BYTES} bytes"
                            ),
                            url=str(article.canonical_url),
                            article_id=article.article_id,
                        )
                    )
                    result.status = "partial"
                    continue
                used_normalized_bytes += content_bytes
                articles.append(article)
            result.accepted_count = sum(
                article.source_id == result.source_id for article in articles
            )
        run_seed = f"{now.isoformat()}|{source_config_digest()}|{window.start.isoformat()}"
        return EvidenceBundle(
            run_id=f"run_{sha256(run_seed.encode()).hexdigest()[:24]}",
            config_digest=source_config_digest(),
            window=window,
            source_results=source_results,
            articles=articles,
        )

    async def _fetch_source(
        self, source: Source, window: Window
    ) -> tuple[list[EvidenceArticle], SourceResult]:
        errors: list[FetchError] = []
        source_id = cast(Literal["duozhi", "duojing", "jiemodui"], source.id)
        try:
            homepage = await self._get_bytes(source.homepage, source)
            candidates = self._discover(homepage, source)[:MAX_ARTICLES_PER_SOURCE]
        except (
            httpx.HTTPError,
            SourcePolicyError,
            SafeHTTPError,
            ContentEncodingError,
            FetchLimitError,
            TimeoutError,
            OSError,
        ) as error:
            return [], SourceResult(
                source_id=source_id,
                status="failed",
                errors=[self._error(error, source.homepage)],
            )
        if not candidates:
            return [], SourceResult(
                source_id=source_id,
                status="failed",
                errors=[
                    FetchError(
                        kind=ErrorKind.CONTENT,
                        message="discovery schema mismatch: no article candidates",
                        url=source.homepage,
                    )
                ],
            )
        articles: list[EvidenceArticle] = []
        filtered_count = 0
        for candidate in candidates:
            try:
                article = await self._fetch_article(candidate, source)
                if not window.start <= article.published_at < window.end:
                    filtered_count += 1
                    continue
                articles.append(article)
            except (
                httpx.HTTPError,
                SourcePolicyError,
                SafeHTTPError,
                ContentEncodingError,
                FetchLimitError,
                TimeoutError,
                OSError,
                ValidationError,
            ) as error:
                errors.append(self._error(error, candidate.url))
        if errors:
            status: Literal["success", "partial", "failed"] = "partial" if articles else "failed"
        else:
            status = "success"
        return articles, SourceResult(
            source_id=source_id,
            status=status,
            errors=errors,
            discovered_count=len(candidates),
            filtered_count=filtered_count,
            accepted_count=len(articles),
        )

    @staticmethod
    def _error(error: Exception, url: str) -> FetchError:
        kind = (
            ErrorKind.SECURITY
            if isinstance(error, (SourcePolicyError, ContentTypeError, SafeHTTPError))
            else ErrorKind.CONTENT
        )
        if isinstance(error, DateError):
            kind = ErrorKind.DATE
        if isinstance(error, httpx.HTTPError | TimeoutError | OSError):
            kind = ErrorKind.NETWORK
        if isinstance(error, OSError):
            return FetchError(kind=kind, message="network operation failed", url=url)
        return FetchError(kind=kind, message=str(error)[:500] or type(error).__name__, url=url)

    def _discover(self, body: bytes, source: Source) -> list[Candidate]:
        text = body.decode("utf-8", errors="replace")
        candidates: list[Candidate] = []
        seen: set[str] = set()
        if source.discovery_kind == "rss":
            try:
                root = ElementTree.fromstring(body)
            except ElementTree.ParseError as error:
                raise FetchLimitError("invalid RSS XML") from error
            for item in root.findall(".//item"):
                raw_url = (item.findtext("link") or "").strip()
                self._append_candidate(candidates, seen, raw_url, source, item.findtext("pubDate"))
        else:
            parser = HTMLParser(text)
            for node in parser.css("a[href]"):
                self._append_candidate(
                    candidates, seen, node.attributes.get("href") or "", source, None
                )
        return candidates

    @staticmethod
    def _append_candidate(
        candidates: list[Candidate],
        seen: set[str],
        href: str,
        source: Source,
        published: str | None,
    ) -> None:
        candidate = urljoin(source.homepage, href)
        try:
            normalized = str(validate_url(candidate, source))
        except SourcePolicyError:
            return
        if normalized in seen or not source.matches_article(normalized):
            return
        seen.add(normalized)
        candidates.append(Candidate(url=normalized, published_at=_parse_datetime(published)))

    async def _fetch_article(self, candidate: Candidate, source: Source) -> EvidenceArticle:
        body = await self._get_bytes(candidate.url, source, require_article=True)
        title, content, page_date, truncated = self._extract_article(body, source)
        published_at = candidate.published_at or page_date
        if published_at is None:
            raise DateError("article has no verified published_at")
        if not content:
            raise FetchLimitError("article has no readable content")
        canonical = str(validate_url(candidate.url, source))
        content_sha = sha256(content.encode("utf-8")).hexdigest()
        return EvidenceArticle(
            article_id=f"art_{sha256(canonical.encode()).hexdigest()[:24]}",
            source_id=cast(Literal["duozhi", "duojing", "jiemodui"], source.id),
            canonical_url=cast(HttpUrl, canonical),
            title=title or canonical,
            content=content,
            content_sha256=content_sha,
            fetched_at=self._clock(),
            published_at=published_at,
            transport_trust=validate_url(canonical, source).transport_trust,
            truncated=truncated,
        )

    @staticmethod
    def _extract_article(body: bytes, source: Source) -> tuple[str, str, datetime | None, bool]:
        raw_page = body.decode("utf-8", errors="replace")
        parser = HTMLParser(raw_page)
        for node in parser.css("script,style,noscript"):
            node.decompose()
        heading = parser.css_first("h1")
        title = heading.text(strip=True)[:2_000] if heading else ""
        date_node = parser.css_first("time[datetime]")
        published_at = _parse_datetime(date_node.attributes.get("datetime") if date_node else None)
        if published_at is None:
            published_at = Fetcher._source_page_date(raw_page, source)
        text = " ".join(parser.body.text(separator=" ", strip=True).split()) if parser.body else ""
        raw = text.encode("utf-8")
        if len(raw) <= MAX_NORMALIZED_ARTICLE_BYTES:
            return title, text, published_at, False
        clipped = raw[:MAX_NORMALIZED_ARTICLE_BYTES].decode("utf-8", errors="ignore")
        return title, clipped, published_at, True

    @staticmethod
    def _source_page_date(page: str, source: Source) -> datetime | None:
        if source.id == "duozhi":
            match = re.search(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?)\s*发布", page)
            return _parse_source_datetime(match.group(1) if match else None)
        if source.id == "duojing":
            match = re.search(
                r"addMeta_[^(]*\(\s*['\"]PubDate['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)",
                page,
            )
            return _parse_source_datetime(match.group(1) if match else None)
        if source.id == "jiemodui":
            match = re.search(r"['\"]datePublished['\"]\s*:\s*['\"]([^'\"]+)['\"]", page)
            return _parse_source_datetime(match.group(1) if match else None)
        return None

    async def _get_bytes(self, url: str, source: Source, *, require_article: bool = False) -> bytes:
        current = str(validate_url(url, source))
        initial = urlsplit(current)

        def validate_hop(candidate: str) -> str:
            normalized = str(validate_url(candidate, source))
            if require_article:
                target = urlsplit(normalized)
                if not source.matches_article(normalized) or (target.path, target.query) != (
                    initial.path,
                    initial.query,
                ):
                    raise SourcePolicyError("article redirect target is not the original article")
            return normalized

        if self._transport is None:
            return await pinned_get_bytes(
                current,
                self._resolver,
                validate_hop,
            )
        timeout = httpx.Timeout(TOTAL_SECONDS, connect=CONNECT_SECONDS)
        headers = {
            "User-Agent": "ai-edu-media-tracker/0.1",
            "Accept": ", ".join(ALLOWED_MIME_TYPES),
        }
        async with (
            self._semaphore,
            httpx.AsyncClient(
                transport=self._transport,
                follow_redirects=False,
                timeout=timeout,
                headers={**headers, "Accept-Encoding": "identity"},
                trust_env=False,
            ) as client,
        ):
            loop = asyncio.get_running_loop()
            deadline = loop.time() + TOTAL_SECONDS
            for attempt in range(3):
                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise TimeoutError("total request timeout exceeded")
                try:
                    async with asyncio.timeout(remaining):
                        for redirect_count in range(MAX_REDIRECTS + 1):
                            async with client.stream("GET", current) as response:
                                if response.status_code in {301, 302, 303, 307, 308}:
                                    location = response.headers.get("location")
                                    if location is None or redirect_count == MAX_REDIRECTS:
                                        raise SourcePolicyError(
                                            "redirect limit or missing location"
                                        )
                                    current = validate_hop(urljoin(current, location))
                                    if self._transport is None:
                                        await self._resolver(source.host)
                                    continue
                                if response.status_code == 429 or response.status_code >= 500:
                                    raise httpx.HTTPStatusError(
                                        "retryable HTTP status",
                                        request=response.request,
                                        response=response,
                                    )
                                response.raise_for_status()
                                mime = (
                                    response.headers.get("content-type", "")
                                    .split(";", 1)[0]
                                    .lower()
                                )
                                if mime not in ALLOWED_MIME_TYPES:
                                    raise ContentTypeError("response MIME type is not allowlisted")
                                raw_chunks: list[bytes] = []
                                compressed_total = 0
                                try:
                                    async for chunk in response.aiter_raw():
                                        if compressed_total + len(chunk) > MAX_RESPONSE_BYTES:
                                            raise FetchLimitError(
                                                f"response exceeds {MAX_RESPONSE_BYTES} bytes"
                                            )
                                        compressed_total += len(chunk)
                                        raw_chunks.append(chunk)
                                except httpx.StreamConsumed as error:
                                    # httpx.MockTransport commonly supplies eager, already-read
                                    # identity responses.  Production responses always use the
                                    # raw stream above; never apply this seam to encoded bodies.
                                    if response.headers.get("content-encoding", "identity").strip().lower() not in {
                                        "",
                                        "identity",
                                    }:
                                        raise
                                    eager_body = response.content
                                    if len(eager_body) > MAX_RESPONSE_BYTES:
                                        raise FetchLimitError(
                                            f"response exceeds {MAX_RESPONSE_BYTES} bytes"
                                        ) from error
                                    raw_chunks = [eager_body]
                                try:
                                    return decode_chunks(
                                        raw_chunks,
                                        response.headers.get("content-encoding", "identity"),
                                        max_input_bytes=MAX_RESPONSE_BYTES,
                                        max_output_bytes=MAX_RESPONSE_BYTES,
                                    )
                                except ContentEncodingError as error:
                                    raise FetchLimitError(str(error)) from error
                except httpx.HTTPStatusError as error:
                    if (
                        not (error.response.status_code == 429 or error.response.status_code >= 500)
                        or attempt == 2
                    ):
                        raise
                except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError):
                    if attempt == 2:
                        raise
                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise TimeoutError("total request timeout exceeded")
                await asyncio.sleep(min(0.25 * (2**attempt), remaining))
        raise FetchLimitError("unreachable retry state")
