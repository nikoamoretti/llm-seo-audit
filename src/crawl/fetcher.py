from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import requests  # type: ignore[import-untyped]

from src.crawl.models import FetchResult


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


class PageFetcher:
    def __init__(self, session=None, headers=None, timeout: int = 15):
        self.session = session or requests
        self.headers = headers or DEFAULT_HEADERS
        self.timeout = timeout

    def ensure_url(self, url: str) -> str:
        return url if url.startswith("http") else f"https://{url}"

    def fetch(self, url: str) -> FetchResult:
        url = self.ensure_url(url)
        try:
            start = time.time()
            response = self.session.get(
                url,
                headers=self.headers,
                timeout=self.timeout,
                allow_redirects=True,
            )
            elapsed = round(time.time() - start, 2)
            return FetchResult(
                url=url,
                final_url=getattr(response, "url", url),
                status_code=response.status_code,
                html=getattr(response, "text", "") or "",
                content_type=(getattr(response, "headers", {}) or {}).get("Content-Type", "text/html"),
                load_time_seconds=elapsed,
            )
        except requests.exceptions.RequestException as exc:
            return FetchResult(
                url=url,
                final_url=url,
                status_code=0,
                html="",
                content_type="text/html",
                error=str(exc),
            )

    def fetch_robots_txt(self, website_url: str) -> str | None:
        parsed = urlparse(self.ensure_url(website_url))
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        response = self.fetch(f"{base_url}/robots.txt")
        if response.status_code == 200 and response.html:
            return response.html
        return None

    def fetch_sitemap_urls(self, website_url: str) -> list[str]:
        parsed = urlparse(self.ensure_url(website_url))
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        robots_text = self.fetch_robots_txt(base_url) or ""

        sitemap_urls = [
            line.split(":", 1)[1].strip()
            for line in robots_text.splitlines()
            if line.lower().startswith("sitemap:")
        ]
        if not sitemap_urls:
            sitemap_urls = [f"{base_url}/sitemap.xml"]

        discovered: list[str] = []
        seen: set[str] = set()
        for sitemap_url in sitemap_urls:
            self._collect_sitemap_urls(sitemap_url, base_url, discovered, seen)
        return discovered

    def _collect_sitemap_urls(
        self,
        sitemap_url: str,
        base_url: str,
        discovered: list[str],
        seen: set[str],
    ) -> None:
        response = self.fetch(sitemap_url)
        if response.status_code != 200 or "xml" not in response.content_type and "<urlset" not in response.html:
            return

        try:
            root = ET.fromstring(response.html)
        except ET.ParseError:
            return

        namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
        for loc in root.findall(f".//{namespace}loc"):
            value = (loc.text or "").strip()
            if not value:
                continue
            if value.endswith(".xml"):
                self._collect_sitemap_urls(value, base_url, discovered, seen)
                continue
            if urlparse(value).netloc != urlparse(base_url).netloc or value in seen:
                continue
            discovered.append(value)
            seen.add(value)
