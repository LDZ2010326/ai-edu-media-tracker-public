"""Proxy-free HTTP/1.1 retrieval pinned to addresses already approved by DNS policy."""

from __future__ import annotations

import asyncio
import re
import ssl
from collections.abc import Awaitable, Callable, Iterable
from urllib.parse import urljoin, urlsplit

import httpx

from .content_encoding import ContentEncodingError, decode_chunks

CONNECT_SECONDS = 5.0
TOTAL_SECONDS = 20.0
MAX_REDIRECTS = 3
MAX_RESPONSE_BYTES = 5_000_000
MAX_STATUS_LINE_BYTES = 8_192
MAX_HEADER_LINE_BYTES = 8_192
MAX_HEADER_BYTES = 65_536
ALLOWED_MIME_TYPES = frozenset(
    {"text/html", "application/xhtml+xml", "application/rss+xml", "application/xml", "text/xml"}
)

Resolver = Callable[[str], Awaitable[Iterable[str]]]
UrlValidator = Callable[[str], str]


class SafeHTTPError(ValueError):
    """A protocol or resource safety boundary was refused."""


async def get_bytes(url: str, resolver: Resolver, validate_url: UrlValidator) -> bytes:
    """Resolve each hop then connect directly to that IP with canonical Host/SNI; never use env proxies."""
    current = validate_url(url)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + TOTAL_SECONDS
    for attempt in range(3):
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise TimeoutError("total request timeout exceeded")
        try:
            async with asyncio.timeout(remaining):
                for redirect_count in range(MAX_REDIRECTS + 1):
                    parsed = urlsplit(current)
                    addresses = list(await resolver(parsed.hostname or ""))
                    status, headers, body = await _exchange(current, addresses)
                    if status in {301, 302, 303, 307, 308}:
                        location = headers.get("location")
                        if location is None or redirect_count == MAX_REDIRECTS:
                            raise SafeHTTPError("redirect limit or missing location")
                        current = validate_url(urljoin(current, location))
                        continue
                    if status == 429 or status >= 500:
                        raise httpx.HTTPStatusError(
                            "retryable HTTP status",
                            request=httpx.Request("GET", current),
                            response=httpx.Response(status),
                        )
                    if not 200 <= status < 300:
                        raise httpx.HTTPStatusError(
                            "HTTP error",
                            request=httpx.Request("GET", current),
                            response=httpx.Response(status),
                        )
                    _validate_headers(headers)
                    try:
                        return decode_chunks(
                            [body],
                            headers.get("content-encoding", "identity"),
                            max_input_bytes=MAX_RESPONSE_BYTES,
                            max_output_bytes=MAX_RESPONSE_BYTES,
                        )
                    except ContentEncodingError as error:
                        raise SafeHTTPError(str(error)) from error
        except httpx.HTTPStatusError as error:
            if (
                not (error.response.status_code == 429 or error.response.status_code >= 500)
                or attempt == 2
            ):
                raise
        except (
            httpx.ConnectError,
            httpx.ReadError,
            httpx.RemoteProtocolError,
            OSError,
            ssl.SSLError,
        ):
            if attempt == 2:
                raise
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise TimeoutError("total request timeout exceeded")
        await asyncio.sleep(min(0.25 * (2**attempt), remaining))
    raise SafeHTTPError("unreachable retry state")


async def _exchange(raw_url: str, addresses: list[str]) -> tuple[int, dict[str, str], bytes]:
    url = urlsplit(raw_url)
    if url.port not in {None, 80 if url.scheme == "http" else 443}:
        raise SafeHTTPError("non-default ports are forbidden")
    if not addresses:
        raise httpx.ConnectError("hostname resolution failed")
    port = 443 if url.scheme == "https" else 80
    target = url.path or "/"
    if url.query:
        target = f"{target}?{url.query}"
    host = url.hostname or ""
    last_error: OSError | ssl.SSLError | None = None
    for address in addresses:
        writer: asyncio.StreamWriter | None = None
        try:
            context = ssl.create_default_context() if url.scheme == "https" else None
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(
                    host=address,
                    port=port,
                    ssl=context,
                    server_hostname=host if context else None,
                ),
                timeout=CONNECT_SECONDS,
            )
            request = (
                f"GET {target} HTTP/1.1\r\nHost: {host}\r\n"
                "User-Agent: ai-edu-media-tracker/0.1\r\n"
                f"Accept: {', '.join(ALLOWED_MIME_TYPES)}\r\n"
                "Accept-Encoding: identity\r\nConnection: close\r\n\r\n"
            ).encode("ascii")
            if writer is None:
                raise httpx.ConnectError("pinned connection failed")
            writer.write(request)
            await writer.drain()
            status, headers = await _read_headers(reader)
            body = await _read_body(reader, headers)
            return status, headers, body
        except (OSError, ssl.SSLError) as error:
            last_error = error
        finally:
            if writer is not None:
                writer.close()
                try:
                    await writer.wait_closed()
                except OSError:
                    pass
    raise httpx.ConnectError("pinned connection failed") from last_error


async def _read_headers(reader: asyncio.StreamReader) -> tuple[int, dict[str, str]]:
    status_line = await _read_line(reader, MAX_STATUS_LINE_BYTES, "status")
    match = re.fullmatch(rb"HTTP/1\.[01]\s+(\d{3})[^\r\n]*\r?\n", status_line)
    if match is None:
        raise httpx.RemoteProtocolError("invalid HTTP response")
    headers: dict[str, str] = {}
    header_bytes = 0
    while True:
        line = await _read_line(reader, MAX_HEADER_LINE_BYTES, "header")
        header_bytes += len(line)
        if header_bytes > MAX_HEADER_BYTES:
            raise SafeHTTPError("response headers exceed 65536 bytes")
        if line in {b"\r\n", b"\n", b""}:
            return int(match.group(1)), headers
        if b":" not in line:
            raise httpx.RemoteProtocolError("invalid response header")
        key, value = line.split(b":", 1)
        normalized_key = key.decode("ascii", errors="ignore").lower()
        normalized_value = value.decode("latin-1", errors="replace").strip()
        if normalized_key in headers:
            headers[normalized_key] = f"{headers[normalized_key]},{normalized_value}"
        else:
            headers[normalized_key] = normalized_value


async def _read_line(reader: asyncio.StreamReader, maximum: int, label: str) -> bytes:
    try:
        line = await reader.readline()
    except ValueError as error:
        raise SafeHTTPError(f"{label} line exceeds {maximum} bytes") from error
    if len(line) > maximum:
        raise SafeHTTPError(f"{label} line exceeds {maximum} bytes")
    return line


def _validate_headers(headers: dict[str, str]) -> None:
    mime = headers.get("content-type", "").split(";", 1)[0].lower()
    if mime not in ALLOWED_MIME_TYPES:
        raise SafeHTTPError("response MIME type is not allowlisted")


async def _read_body(reader: asyncio.StreamReader, headers: dict[str, str]) -> bytes:
    length = headers.get("content-length")
    if length is not None:
        declared = _parse_content_length(length)
        if declared < 0 or declared > MAX_RESPONSE_BYTES:
            raise SafeHTTPError(f"response exceeds {MAX_RESPONSE_BYTES} bytes")
    else:
        declared = None
    transfer_encoding = headers.get("transfer-encoding")
    if transfer_encoding is not None:
        encodings = [value.strip().lower() for value in transfer_encoding.split(",")]
        if encodings != ["chunked"]:
            raise httpx.RemoteProtocolError("unsupported transfer encoding")
        if declared is not None:
            raise httpx.RemoteProtocolError("ambiguous response framing")
        return await _read_chunked(reader)
    if declared is not None:
        return await _read_exact(reader, declared, "content length body")
    return await _read_to_eof(reader)


def _parse_content_length(value: str) -> int:
    values = [item.strip() for item in value.split(",")]
    if not values or any(re.fullmatch(r"[0-9]+", item) is None for item in values):
        raise httpx.RemoteProtocolError("invalid content length")
    parsed = [int(item) for item in values]
    if len(set(parsed)) != 1:
        raise httpx.RemoteProtocolError("conflicting content length")
    return parsed[0]


async def _read_to_eof(reader: asyncio.StreamReader) -> bytes:
    data = bytearray()
    while chunk := await reader.read(65_536):
        if len(data) + len(chunk) > MAX_RESPONSE_BYTES:
            raise SafeHTTPError(f"response exceeds {MAX_RESPONSE_BYTES} bytes")
        data.extend(chunk)
    return bytes(data)


async def _read_chunked(reader: asyncio.StreamReader) -> bytes:
    data = bytearray()
    while True:
        line = await _read_line(reader, MAX_HEADER_LINE_BYTES, "chunk size")
        try:
            size = int(line.split(b";", 1)[0].strip(), 16)
        except ValueError as error:
            raise httpx.RemoteProtocolError("invalid chunk size") from error
        if size < 0 or len(data) + size > MAX_RESPONSE_BYTES:
            raise SafeHTTPError(f"response exceeds {MAX_RESPONSE_BYTES} bytes")
        if size == 0:
            await _read_trailers(reader)
            return bytes(data)
        data.extend(await _read_exact(reader, size, "chunk body"))
        if await _read_exact(reader, 2, "chunk terminator") != b"\r\n":
            raise httpx.RemoteProtocolError("invalid chunk terminator")


async def _read_trailers(reader: asyncio.StreamReader) -> None:
    trailer_bytes = 0
    while True:
        line = await _read_line(reader, MAX_HEADER_LINE_BYTES, "trailer")
        trailer_bytes += len(line)
        if trailer_bytes > MAX_HEADER_BYTES:
            raise SafeHTTPError("response trailers exceed 65536 bytes")
        if line in {b"\r\n", b"\n", b""}:
            return
        if b":" not in line:
            raise httpx.RemoteProtocolError("invalid response trailer")


async def _read_exact(reader: asyncio.StreamReader, count: int, label: str) -> bytes:
    try:
        return await reader.readexactly(count)
    except asyncio.IncompleteReadError as error:
        raise httpx.RemoteProtocolError(f"truncated {label}") from error
