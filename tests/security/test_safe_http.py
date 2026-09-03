import asyncio
import time

import httpx
import pytest

from ai_edu_tracker.safe_http import (
    SafeHTTPError,
    _exchange,
    _read_body,
    _read_headers,
)


def _reader(payload: bytes, *, limit: int = 100_000) -> asyncio.StreamReader:
    reader = asyncio.StreamReader(limit=limit)
    reader.feed_data(payload)
    reader.feed_eof()
    return reader


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        b"HTTP/1.1 200 " + b"x" * 70_000 + b"\r\n\r\n",
        b"HTTP/1.1 200 OK\r\nX-Test: " + b"x" * 70_000 + b"\r\n\r\n",
    ],
)
async def test_status_and_each_header_line_have_independent_bounded_protocol_errors(
    payload: bytes,
) -> None:
    with pytest.raises(SafeHTTPError, match="line exceeds"):
        await _read_headers(_reader(payload))


@pytest.mark.asyncio
async def test_streamreader_line_limit_is_converted_to_structured_protocol_error() -> None:
    payload = b"HTTP/1.1 200 OK\r\nX-Test: " + b"x" * 100 + b"\r\n\r\n"
    with pytest.raises(SafeHTTPError, match="line exceeds"):
        await _read_headers(_reader(payload, limit=32))


@pytest.mark.asyncio
async def test_content_length_short_read_invalid_conflicting_and_ambiguous_framing_are_rejected() -> None:
    with pytest.raises(httpx.RemoteProtocolError, match="truncated"):
        await _read_body(_reader(b"abc"), {"content-length": "4"})
    with pytest.raises(httpx.RemoteProtocolError, match="invalid content length"):
        await _read_body(_reader(b""), {"content-length": "abc"})
    with pytest.raises(httpx.RemoteProtocolError, match="conflicting content length"):
        await _read_body(_reader(b""), {"content-length": "1,2"})
    with pytest.raises(httpx.RemoteProtocolError, match="ambiguous response framing"):
        await _read_body(
            _reader(b"0\r\n\r\n"), {"content-length": "0", "transfer-encoding": "chunked"}
        )
    with pytest.raises(SafeHTTPError, match="response exceeds"):
        await _read_body(_reader(b""), {"content-length": "5000001"})


@pytest.mark.asyncio
async def test_content_length_returns_without_waiting_for_connection_close() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(b"abc")
    assert await asyncio.wait_for(
        _read_body(reader, {"content-length": "3"}), timeout=0.05
    ) == b"abc"


@pytest.mark.asyncio
async def test_connection_timeout_falls_back_to_next_validated_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class Writer:
        def write(self, data: bytes) -> None:
            pass

        async def drain(self) -> None:
            pass

        def close(self) -> None:
            pass

        async def wait_closed(self) -> None:
            pass

    async def open_connection(**kwargs: object) -> tuple[asyncio.StreamReader, Writer]:
        address = str(kwargs["host"])
        calls.append(address)
        if address == "2001:db8::1":
            raise TimeoutError("unreachable address")
        reader = asyncio.StreamReader()
        reader.feed_data(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")
        reader.feed_eof()
        return reader, Writer()

    monkeypatch.setattr(asyncio, "open_connection", open_connection)
    status, _, body = await _exchange(
        "https://example.test/", ["2001:db8::1", "93.184.216.34"]
    )
    assert (status, body) == (200, b"")
    assert calls == ["2001:db8::1", "93.184.216.34"]


@pytest.mark.asyncio
async def test_total_timeout_covers_retries_and_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_edu_tracker import safe_http

    async def resolver(host: str) -> list[str]:
        return ["93.184.216.34"]

    async def failing_exchange(url: str, addresses: list[str]) -> tuple[int, dict[str, str], bytes]:
        raise httpx.ConnectError("retry")

    monkeypatch.setattr(safe_http, "TOTAL_SECONDS", 0.05)
    monkeypatch.setattr(safe_http, "_exchange", failing_exchange)
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        await safe_http.get_bytes("https://example.test/a", resolver, lambda value: value)
    assert time.monotonic() - started < 0.2
