import gzip
from datetime import UTC, datetime

import httpx
import pytest

from ai_edu_tracker.content_encoding import ContentEncodingError, decode_chunks
from ai_edu_tracker.fetcher import Fetcher


class _RawBytes(httpx.AsyncByteStream):
    """A non-eager stream: aiter_raw must consume these compressed bytes."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    async def __aiter__(self):  # type: ignore[override]
        yield self._body

    async def aclose(self) -> None:
        return None


def test_strict_gzip_decodes_valid_content_with_bounded_input_and_output() -> None:
    source = b"<html><body>safe</body></html>"
    assert decode_chunks([gzip.compress(source)], "gzip") == source
    assert decode_chunks([source], "identity") == source


def test_gzip_bomb_is_stopped_at_output_limit() -> None:
    with pytest.raises(ContentEncodingError, match="decompressed response exceeds"):
        decode_chunks([gzip.compress(b"x" * 100_001)], "gzip", max_input_bytes=200_000, max_output_bytes=100_000)


def test_valid_gzip_that_expands_to_exact_output_limit_is_accepted() -> None:
    source = b"x" * 100_000
    assert decode_chunks([gzip.compress(source)], "gzip", max_output_bytes=len(source)) == source


@pytest.mark.parametrize(
    "payload",
    [gzip.compress(b"one")[:-3], gzip.compress(b"one") + b"trailing", gzip.compress(b"one") + gzip.compress(b"two")],
)
def test_gzip_rejects_truncated_trailing_and_multi_member_payloads(payload: bytes) -> None:
    with pytest.raises(ContentEncodingError):
        decode_chunks([payload], "gzip")


@pytest.mark.asyncio
async def test_fetcher_reads_strict_gzip_from_raw_http_stream() -> None:
    homepage = gzip.compress(b'<a href="/industry/insight/2026090218790.shtml">one</a>')
    article = gzip.compress(
        b'<h1>Article</h1><time datetime="2026-09-02T01:00:00+00:00"></time><p>body</p>'
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        body = homepage if request.url.path == "/" else article
        return httpx.Response(
            200,
            headers={"content-type": "text/html", "content-encoding": "gzip"},
            stream=_RawBytes(body),
        )

    bundle = await Fetcher(
        transport=httpx.MockTransport(handler), clock=lambda: datetime(2026, 9, 2, 12, tzinfo=UTC)
    ).fetch_track("domestic", since="today", source_ids=["duozhi"])
    assert [item.title for item in bundle.articles] == ["Article"]
