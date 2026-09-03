from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from ai_edu_tracker.fetcher import Fetcher

FIXTURES = Path(__file__).parents[1] / "fixtures"


@pytest.mark.asyncio
async def test_explicit_empty_source_selection_is_rejected_without_network() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected network request: {request.url}")

    fetcher = Fetcher(transport=httpx.MockTransport(handler))
    with pytest.raises(ValueError, match="unknown source id"):
        await fetcher.fetch_track("domestic", source_ids=[])


@pytest.mark.asyncio
async def test_today_filters_by_verified_published_date_and_records_undated_article() -> None:
    homepage = (
        '<a href="/industry/insight/2026090218790.shtml">ok</a>'
        '<a href="/industry/insight/2026090218791.shtml">bad</a>'
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(200, text=homepage, headers={"content-type": "text/html"})
        if request.url.path.endswith("18790.shtml"):
            return httpx.Response(
                200,
                text=(
                    '<h1>In window</h1><time datetime="2026-09-02T08:00:00+00:00">'
                    "</time><p>body</p>"
                ),
                headers={"content-type": "text/html"},
            )
        return httpx.Response(
            200, text="<h1>Undated</h1><p>body</p>", headers={"content-type": "text/html"}
        )

    fetcher = Fetcher(
        transport=httpx.MockTransport(handler), clock=lambda: datetime(2026, 9, 2, 12, tzinfo=UTC)
    )
    bundle = await fetcher.fetch_track("domestic", since="today", source_ids=["duozhi"])
    assert [article.title for article in bundle.articles] == ["In window"]
    assert bundle.articles[0].published_at == datetime(2026, 9, 2, 8, tzinfo=UTC)
    assert bundle.source_results[0].status == "partial"
    assert bundle.source_results[0].errors[0].kind == "date"


@pytest.mark.asyncio
async def test_out_of_window_dated_article_is_normal_filter_not_source_error() -> None:
    homepage = (
        '<a href="/industry/insight/2026090218790.shtml">current</a>'
        '<a href="/industry/insight/2026090118789.shtml">old</a>'
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(200, text=homepage, headers={"content-type": "text/html"})
        published = (
            "2026-09-02T08:00:00+00:00"
            if request.url.path.endswith("18790.shtml")
            else "2026-09-01T08:00:00+00:00"
        )
        return httpx.Response(
            200,
            text=f'<h1>Article</h1><time datetime="{published}"></time><p>body</p>',
            headers={"content-type": "text/html"},
        )

    bundle = await Fetcher(
        transport=httpx.MockTransport(handler), clock=lambda: datetime(2026, 9, 2, 12, tzinfo=UTC)
    ).fetch_track("domestic", since="today", source_ids=["duozhi"])
    result = bundle.source_results[0]
    assert len(bundle.articles) == 1
    assert result.status == "success"
    assert result.filtered_count == 1
    assert result.errors == []


@pytest.mark.asyncio
async def test_bundle_contract_contains_normalized_evidence_fields() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(
                200,
                text='<a href="/industry/insight/2026090218790.shtml">one</a>',
                headers={"content-type": "text/html"},
            )
        return httpx.Response(
            200,
            text='<h1>Article</h1><time datetime="2026-09-02T01:00:00+00:00"></time><p>body</p>',
            headers={"content-type": "text/html"},
        )

    bundle = await Fetcher(
        transport=httpx.MockTransport(handler), clock=lambda: datetime(2026, 9, 2, 12, tzinfo=UTC)
    ).fetch_track("domestic", since="today", source_ids=["duozhi"])
    article = bundle.articles[0]
    assert bundle.run_id and bundle.config_digest and bundle.window.start < bundle.window.end
    assert article.article_id and article.canonical_url and article.content_sha256
    assert article.transport_trust.value == "untrusted_http"
    assert article.truncated is False


@pytest.mark.asyncio
async def test_rss_adapter_uses_item_links_and_dates_not_arbitrary_xml_nodes() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/rss.xml":
            return httpx.Response(
                200,
                text=(
                    "<rss><channel><link>https://www.jiemodui.com/about</link><item>"
                    "<link>https://www.jiemodui.com/N/139544.html</link>"
                    "<pubDate>Tue, 02 Sep 2026 08:00:00 +0000</pubDate>"
                    "</item></channel></rss>"
                ),
                headers={"content-type": "application/rss+xml"},
            )
        return httpx.Response(
            200,
            text="<h1>RSS article</h1><p>body</p>",
            headers={"content-type": "text/html"},
        )

    bundle = await Fetcher(
        transport=httpx.MockTransport(handler), clock=lambda: datetime(2026, 9, 2, 12, tzinfo=UTC)
    ).fetch_track("domestic", since="today", source_ids=["jiemodui"])
    assert [article.title for article in bundle.articles] == ["RSS article"]
    assert bundle.source_results[0].discovered_count == 1


@pytest.mark.asyncio
async def test_normalized_article_is_truncated_at_one_hundred_kilobytes() -> None:
    huge_body = "x" * 100_100

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(
                200,
                text='<a href="/industry/insight/2026090218790.shtml">one</a>',
                headers={"content-type": "text/html"},
            )
        return httpx.Response(
            200,
            text=(
                '<h1>Article</h1><time datetime="2026-09-02T01:00:00+00:00">'
                f"</time><p>{huge_body}</p>"
            ),
            headers={"content-type": "text/html"},
        )

    bundle = await Fetcher(
        transport=httpx.MockTransport(handler), clock=lambda: datetime(2026, 9, 2, 12, tzinfo=UTC)
    ).fetch_track("domestic", source_ids=["duozhi"])
    assert bundle.articles[0].truncated is True
    assert len(bundle.articles[0].content.encode("utf-8")) <= 100_000


@pytest.mark.asyncio
async def test_source_candidate_limit_is_fifty_before_source_result_serialization() -> None:
    links = "".join(
        f'<a href="/industry/insight/20260902{index:05d}.shtml">{index}</a>' for index in range(55)
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(200, text=links, headers={"content-type": "text/html"})
        return httpx.Response(
            200,
            text='<h1>Article</h1><time datetime="2026-09-02T01:00:00+00:00"></time><p>body</p>',
            headers={"content-type": "text/html"},
        )

    bundle = await Fetcher(
        transport=httpx.MockTransport(handler), clock=lambda: datetime(2026, 9, 2, 12, tzinfo=UTC)
    ).fetch_track("domestic", source_ids=["duozhi"])
    assert len(bundle.articles) == 50
    assert bundle.source_results[0].discovered_count == 50


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source_id", "homepage_name", "article_name", "expected_title", "expected_published_at"),
    [
        (
            "duozhi",
            "duozhi-discovery.html",
            "duozhi-article.html",
            "多知真实文章",
            datetime(2026, 9, 2, 14, 10, 24, tzinfo=UTC),
        ),
        (
            "duojing",
            "duojing-discovery.html",
            "duojing-article.html",
            "多鲸真实文章",
            datetime(2026, 9, 1, 16, 22, tzinfo=UTC),
        ),
        (
            "jiemodui",
            "jiemodui-rss.xml",
            "jiemodui-article.html",
            "芥末堆真实文章",
            datetime(2026, 9, 2, 8, tzinfo=UTC),
        ),
    ],
)
async def test_observed_production_shapes_produce_dated_article(
    source_id: str,
    homepage_name: str,
    article_name: str,
    expected_title: str,
    expected_published_at: datetime,
) -> None:
    homepage = (FIXTURES / homepage_name).read_text(encoding="utf-8")
    article = (FIXTURES / article_name).read_text(encoding="utf-8")

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path in {"/", "/nr.jsp", "/rss.xml"}:
            mime = "application/rss+xml" if request.url.path == "/rss.xml" else "text/html"
            return httpx.Response(200, text=homepage, headers={"content-type": mime})
        return httpx.Response(200, text=article, headers={"content-type": "text/html"})

    bundle = await Fetcher(
        transport=httpx.MockTransport(handler), clock=lambda: datetime(2026, 9, 2, 12, tzinfo=UTC)
    ).fetch_track("domestic", source_ids=[source_id])
    assert [item.title for item in bundle.articles] == [expected_title]
    assert bundle.articles[0].published_at == expected_published_at


@pytest.mark.asyncio
async def test_jiemodui_json_ld_date_is_used_when_rss_item_has_no_pubdate() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/rss.xml":
            return httpx.Response(
                200,
                text="<rss><channel><item><link>https://www.jiemodui.com/N/139544.html</link></item></channel></rss>",
                headers={"content-type": "application/rss+xml"},
            )
        return httpx.Response(
            200,
            text=(FIXTURES / "jiemodui-article.html").read_text(encoding="utf-8"),
            headers={"content-type": "text/html"},
        )

    bundle = await Fetcher(
        transport=httpx.MockTransport(handler), clock=lambda: datetime(2026, 9, 2, 12, tzinfo=UTC)
    ).fetch_track("domestic", source_ids=["jiemodui"])
    assert bundle.articles[0].published_at == datetime(2026, 9, 2, 8, tzinfo=UTC)


@pytest.mark.asyncio
async def test_nonempty_discovery_without_matching_candidates_is_schema_failure() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text='<html><body><a href="/about">about</a></body></html>',
            headers={"content-type": "text/html"},
        )

    bundle = await Fetcher(transport=httpx.MockTransport(handler)).fetch_track(
        "domestic", source_ids=["duozhi"]
    )
    result = bundle.source_results[0]
    assert result.status == "failed"
    assert result.errors[0].kind == "content"
    assert result.errors[0].message == "discovery schema mismatch: no article candidates"


@pytest.mark.asyncio
async def test_empty_normalized_article_becomes_structured_content_error_not_gather_crash() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(
                200,
                text='<a href="/industry/insight/2026090218790.shtml">article</a>',
                headers={"content-type": "text/html"},
            )
        return httpx.Response(
            200,
            text='<time datetime="2026-09-02T08:00:00+00:00"></time>',
            headers={"content-type": "text/html"},
        )

    bundle = await Fetcher(
        transport=httpx.MockTransport(handler), clock=lambda: datetime(2026, 9, 2, 12, tzinfo=UTC)
    ).fetch_track("domestic", source_ids=["duozhi"])
    result = bundle.source_results[0]
    assert bundle.articles == []
    assert result.status == "failed"
    assert result.errors[0].kind == "content"
    assert "readable" in result.errors[0].message


@pytest.mark.asyncio
async def test_article_redirect_to_non_article_path_is_rejected() -> None:
    article_path = "/industry/insight/2026090218790.shtml"

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(
                200,
                text=f'<a href="{article_path}">article</a>',
                headers={"content-type": "text/html"},
            )
        if request.url.path == article_path:
            return httpx.Response(302, headers={"location": "/login"})
        return httpx.Response(
            200,
            text='<h1>Login</h1><time datetime="2026-09-02T08:00:00+00:00"></time>',
            headers={"content-type": "text/html"},
        )

    bundle = await Fetcher(
        transport=httpx.MockTransport(handler), clock=lambda: datetime(2026, 9, 2, 12, tzinfo=UTC)
    ).fetch_track("domestic", source_ids=["duozhi"])
    result = bundle.source_results[0]
    assert bundle.articles == []
    assert result.status == "failed"
    assert result.errors[0].kind == "security"
    assert "article redirect" in result.errors[0].message
