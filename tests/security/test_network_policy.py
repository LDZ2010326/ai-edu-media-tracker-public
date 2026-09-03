import socket

import httpx
import pytest

from ai_edu_tracker import fetcher as fetcher_module
from ai_edu_tracker.fetcher import Fetcher, SourcePolicyError, validate_url
from ai_edu_tracker.models import TransportTrust
from ai_edu_tracker.safe_http import SafeHTTPError
from ai_edu_tracker.sources import SOURCES


def test_source_registry_uses_approved_discovery_endpoints_and_patterns() -> None:
    assert SOURCES["jiemodui"].homepage == "https://www.jiemodui.com/rss.xml"
    assert SOURCES["jiemodui"].discovery_kind == "rss"
    assert SOURCES["duojing"].homepage == "http://www.djcapital.net/nr.jsp"
    assert SOURCES["duozhi"].matches_article(
        "http://www.duozhi.com/industry/insight/2026090218790.shtml"
    )
    assert not SOURCES["duozhi"].matches_article("http://www.duozhi.com/industry/insight")
    assert SOURCES["duojing"].matches_article("http://www.djcapital.net/nd.jsp?id=1646&groupId=-1")
    assert SOURCES["jiemodui"].matches_article("https://www.jiemodui.com/N/139544.html")


def test_rejects_ip_literal_and_private_target() -> None:
    with pytest.raises(SourcePolicyError):
        validate_url("http://127.0.0.1/private", SOURCES["duozhi"])


@pytest.mark.asyncio
async def test_rejects_disallowed_mime_type() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"binary", headers={"content-type": "image/jpeg"})

    bundle = await Fetcher(transport=httpx.MockTransport(handler)).fetch_track(
        "domestic", source_ids=["duozhi"]
    )
    assert bundle.source_results[0].status == "failed"
    assert bundle.source_results[0].errors[0].kind == "security"


def test_production_safe_http_refusal_is_classified_as_security() -> None:
    error = Fetcher._error(SafeHTTPError("response MIME type is not allowlisted"), "https://x")
    assert error.kind == "security"


@pytest.mark.asyncio
async def test_streamed_response_is_capped_at_five_megabytes() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 5_000_001, headers={"content-type": "text/html"})

    bundle = await Fetcher(transport=httpx.MockTransport(handler)).fetch_track(
        "domestic", source_ids=["duozhi"]
    )
    assert "response exceeds 5000000 bytes" in bundle.source_results[0].errors[0].message


def test_http_source_keeps_untrusted_transport() -> None:
    result = validate_url("http://www.duozhi.com/article/1", SOURCES["duozhi"])
    assert result.transport_trust is TransportTrust.UNTRUSTED_HTTP


@pytest.mark.asyncio
async def test_dns_failure_is_structured_network_failure_without_local_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_getaddrinfo(*args: object, **kwargs: object) -> object:
        raise socket.gaierror("temporary resolver failure at /private/host")

    monkeypatch.setattr(fetcher_module.socket, "getaddrinfo", failing_getaddrinfo)
    bundle = await Fetcher().fetch_track("domestic", source_ids=["duozhi"])
    result = bundle.source_results[0]
    assert result.status == "failed"
    assert result.errors[0].kind == "network"
    assert result.errors[0].message == "hostname resolution failed"
    assert "/private/" not in result.errors[0].message
