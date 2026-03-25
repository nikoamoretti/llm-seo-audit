from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional


PageType = Literal[
    "homepage",
    "service",
    "location",
    "faq",
    "about",
    "contact",
    "testimonial",
    "pricing_booking",
    "other",
]


@dataclass
class FetchResult:
    url: str
    final_url: str
    status_code: int
    html: str
    content_type: str
    load_time_seconds: Optional[float] = None
    error: Optional[str] = None
    fetch_method: str = "direct"        # "direct", "browserbase", or "unavailable"
    blocked: bool = False               # True when the page was a WAF/captcha block

    @property
    def ok(self) -> bool:
        return (
            self.status_code == 200
            and "html" in self.content_type
            and bool(self.html.strip())
            and not self.blocked
        )


@dataclass
class CrawlPage:
    url: str
    final_url: str
    page_type: PageType
    status_code: int
    html: str
    source: str
    title: str = ""
    text: str = ""
    load_time_seconds: Optional[float] = None
    fetch_method: str = "direct"
    blocked: bool = False


@dataclass
class DiscoveryResult:
    homepage: Optional[CrawlPage]
    pages: list[CrawlPage] = field(default_factory=list)
    discovered_urls: list[str] = field(default_factory=list)
    skipped_urls: list[str] = field(default_factory=list)

