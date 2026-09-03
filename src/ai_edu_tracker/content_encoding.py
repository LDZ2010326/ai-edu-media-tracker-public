"""Strict, bounded content-encoding decoding for hostile HTTP bodies."""

from __future__ import annotations

import zlib
from collections.abc import Iterable


class ContentEncodingError(ValueError):
    """Compressed input was malformed, unsupported, or exceeded a configured limit."""


def decode_chunks(
    chunks: Iterable[bytes],
    content_encoding: str,
    *,
    max_input_bytes: int = 5_000_000,
    max_output_bytes: int = 5_000_000,
) -> bytes:
    """Decode identity or one strict gzip member without allocating beyond either ceiling."""
    encoding = content_encoding.strip().lower() or "identity"
    if encoding not in {"identity", "gzip"}:
        raise ContentEncodingError("response content encoding is unsupported")
    compressed_total = 0
    output = bytearray()
    decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS) if encoding == "gzip" else None
    for chunk in chunks:
        compressed_total += len(chunk)
        if compressed_total > max_input_bytes:
            raise ContentEncodingError("compressed response exceeds input limit")
        if decompressor is None:
            _append_limited(output, chunk, max_output_bytes)
            continue
        pending = chunk
        while pending:
            remaining = max_output_bytes - len(output)
            if remaining <= 0:
                raise ContentEncodingError("decompressed response exceeds output limit")
            try:
                decoded = decompressor.decompress(pending, remaining)
            except zlib.error as error:
                raise ContentEncodingError("invalid gzip response") from error
            _append_limited(output, decoded, max_output_bytes)
            if decompressor.unconsumed_tail:
                if len(output) >= max_output_bytes:
                    raise ContentEncodingError("decompressed response exceeds output limit")
                pending = decompressor.unconsumed_tail
            else:
                pending = b""
            if decompressor.unused_data:
                raise ContentEncodingError("gzip response has trailing or multi-member data")
    if decompressor is not None:
        try:
            remaining = max_output_bytes - len(output)
            # zlib rejects flush(0).  One byte is sufficient to prove that a
            # stream which exactly filled the output budget has no hidden tail.
            tail = decompressor.flush(max(1, remaining))
        except zlib.error as error:
            raise ContentEncodingError("invalid gzip response") from error
        _append_limited(output, tail, max_output_bytes)
        if len(output) == max_output_bytes and not decompressor.eof:
            try:
                overflow = decompressor.flush(1)
            except zlib.error as error:
                raise ContentEncodingError("invalid gzip response") from error
            if overflow:
                raise ContentEncodingError("decompressed response exceeds output limit")
        if not decompressor.eof:
            raise ContentEncodingError("truncated gzip response")
        if decompressor.unused_data or decompressor.unconsumed_tail:
            raise ContentEncodingError("gzip response has trailing or multi-member data")
    return bytes(output)


def _append_limited(output: bytearray, chunk: bytes, limit: int) -> None:
    if len(output) + len(chunk) > limit:
        raise ContentEncodingError("decompressed response exceeds output limit")
    output.extend(chunk)
