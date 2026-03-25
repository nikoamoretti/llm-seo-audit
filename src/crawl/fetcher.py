from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import requests  # type: ignore[import-untyped]

from src.crawl.models import FetchResult
from src.crawl.remote_browser import (
    BrowserFetchResult,
    browserbase_configured,
    fetch_via_browserbase,
    is_blocked_page,
)

logger = logging.getLogger(__name__)

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
        """Fetch a URL, falling back to Browserbase when the page is blocked."""
        url = self.ensure_url(url)

        # --- Fast direct attempt ---
        result = self._fetch_direct(url)

        # --- Blocked-page detection ---
        if result.ok and is_blocked_page(result.html, result.final_url):
            logger.info("Direct fetch of %s returned a blocked page, trying Browserbase", url)
            result = self._mark_blocked(result)

            # --- Browserbase retry ---
            if browserbase_configured():
                bb_result = fetch_via_browserbase(url)
                if bb_result.status == "success":
                    return self._from_browser(url, bb_result, fetch_method="browserbase")
                elif bb_result.status == "blocked":
                    logger.warning(
                        "Browserbase also returned a blocked page for %s", url
                    )
                else:
                    logger.warning(
                        "Browserbase fetch failed for %s: %s", url, bb_result.error
                    )
            else:
                logger.info("Browserbase not configured; blocked page at %s stays unavailable", url)

            # Both methods failed or Browserbase is not configured -- mark unavailable
            return FetchResult(
                url=url,
                final_url=result.final_url,
                status_code=result.status_code,
                html="",
                content_type=result.content_type,
                load_time_seconds=result.load_time_seconds,
                error="Page is blocked (Cloudflare/WAF); content unavailable",
                fetch_method="unavailable",
                blocked=True,
            )

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_direct(self, url: str) -> FetchResult:
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
                fetch_method="direct",
            )
        except requests.exceptions.RequestException as exc:
            return FetchResult(
                url=url,
                final_url=url,
                status_code=0,
                html="",
                content_type="text/html",
                error=str(exc),
                fetch_method="direct",
            )

    @staticmethod
    def _mark_blocked(result: FetchResult) -> FetchResult:
        """Tag an existing result as blocked without changing other fields."""
        result.blocked = True
        return result

    @staticmethod
    def _from_browser(url: str, bb: BrowserFetchResult, fetch_method: str) -> FetchResult:
        return FetchResult(
            url=url,
            final_url=bb.final_url or url,
            status_code=200,
            html=bb.html,
            content_type="text/html",
            load_time_seconds=bb.elapsed_seconds,
            fetch_method=fetch_method,
        )

    # ------------------------------------------------------------------
    # Robots / sitemap helpers (unchanged)
    # ------------------------------------------------------------------

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
