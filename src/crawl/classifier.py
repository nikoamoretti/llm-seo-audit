from __future__ import annotations

from urllib.parse import urljoin, urlparse

from src.crawl.models import PageType


JUNK_SEGMENTS = (
    "privacy",
    "terms",
    "cookie",
    "cart",
    "checkout",
    "login",
    "account",
    "feed",
    "tag",
    "author",
    "wp-content",
)
JUNK_SUFFIXES = (".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".zip")


class PageClassifier:
    def normalize(self, base_url: str, href: str) -> str | None:
        if not href:
            return None
        absolute = urljoin(base_url, href.strip())
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return None
        normalized = parsed._replace(query="", fragment="").geturl()
        return normalized[:-1] if normalized.endswith("/") and parsed.path not in {"", "/"} else normalized

    def is_internal(self, base_url: str, url: str) -> bool:
        return urlparse(base_url).netloc == urlparse(url).netloc

    def is_relevant(self, url: str, anchor_text: str = "", title: str = "") -> bool:
        parsed = urlparse(url)
        path = parsed.path.lower()
        if any(path.endswith(suffix) for suffix in JUNK_SUFFIXES):
            return False
        if any(segment in path for segment in JUNK_SEGMENTS):
            return False
        return self.classify(url, anchor_text=anchor_text, title=title) != "other"

    def classify(self, url: str, anchor_text: str = "", title: str = "") -> PageType:
        parsed = urlparse(url)
        path = parsed.path.lower().strip("/")
        haystack = " ".join(part for part in [path.replace("-", " "), anchor_text.lower(), title.lower()] if part)

        if path == "":
            return "homepage"
        if any(token in haystack for token in ("faq", "frequently asked", "questions")):
            return "faq"
        if any(token in haystack for token in ("contact", "get in touch", "call us")):
            return "contact"
        if any(token in haystack for token in ("services", "service", "menu", "offerings")):
            return "service"
        if any(token in haystack for token in ("location", "locations", "service area", "areas we serve", "find us", "office")):
            return "location"
        if any(token in haystack for token in ("about", "our story", "team")):
            return "about"
        if any(token in haystack for token in ("testimonial", "testimonials", "reviews", "success stories")):
            return "testimonial"
        if any(token in haystack for token in ("book", "schedule", "pricing", "quote", "appointment", "reserve")):
            return "pricing_booking"
        return "other"

