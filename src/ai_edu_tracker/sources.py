"""The fixed v1 source registry and source-specific discovery adapters."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit

from .models import TransportTrust, digest


@dataclass(frozen=True, slots=True)
class Source:
    id: str
    name: str
    homepage: str
    host: str
    discovery_kind: str
    article_pattern: str
    transport_trust: TransportTrust
    allowed_schemes: tuple[str, ...]

    def matches_article(self, url: str) -> bool:
        parsed = urlsplit(url)
        path_and_query = parsed.path if not parsed.query else f"{parsed.path}?{parsed.query}"
        return (
            parsed.hostname == self.host
            and parsed.scheme in self.allowed_schemes
            and re.search(self.article_pattern, path_and_query) is not None
        )


SOURCES: dict[str, Source] = {
    "duozhi": Source(
        id="duozhi",
        name="多知网",
        homepage="http://www.duozhi.com/",
        host="www.duozhi.com",
        discovery_kind="html",
        article_pattern=r"^/industry/[^/]+/\d{8}\d+\.shtml$",
        transport_trust=TransportTrust.UNTRUSTED_HTTP,
        allowed_schemes=("http", "https"),
    ),
    "duojing": Source(
        id="duojing",
        name="多鲸",
        homepage="http://www.djcapital.net/nr.jsp",
        host="www.djcapital.net",
        discovery_kind="html",
        article_pattern=r"^/nd\.jsp\?(?=[^#]*\bid=)[^#]+$",
        transport_trust=TransportTrust.UNTRUSTED_HTTP,
        allowed_schemes=("http", "https"),
    ),
    "jiemodui": Source(
        id="jiemodui",
        name="芥末堆",
        homepage="https://www.jiemodui.com/rss.xml",
        host="www.jiemodui.com",
        discovery_kind="rss",
        article_pattern=r"^/N/\d+\.html$",
        transport_trust=TransportTrust.TRUSTED_HTTPS,
        allowed_schemes=("https",),
    ),
}


def source_config_digest() -> str:
    """Digest every behaviorally relevant registry field, in a stable order."""
    return digest([asdict(SOURCES[source_id]) for source_id in sorted(SOURCES)])
