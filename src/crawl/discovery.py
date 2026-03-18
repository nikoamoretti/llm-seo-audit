from __future__ import annotations

from bs4 import BeautifulSoup
from urllib.parse import urlparse

from src.crawl.classifier import PageClassifier
from src.crawl.fetcher import PageFetcher
from src.crawl.models import CrawlPage, DiscoveryResult, PageType


PAGE_PRIORITY = {
    "contact": 100,
    "service": 95,
    "faq": 90,
    "location": 85,
    "about": 80,
    "pricing_booking": 75,
    "testimonial": 70,
    "homepage": 200,
    "other": 0,
}


class SiteDiscovery:
    def __init__(self, fetcher: PageFetcher | None = None, classifier: PageClassifier | None = None, crawl_budget: int = 6):
        self.fetcher = fetcher or PageFetcher()
        self.classifier = classifier or PageClassifier()
        self.crawl_budget = crawl_budget

    def discover(self, website_url: str) -> DiscoveryResult:
        homepage_result = self.fetcher.fetch(website_url)
        if not homepage_result.ok:
            return DiscoveryResult(homepage=None, pages=[], discovered_urls=[], skipped_urls=[website_url])

        homepage_page = self._build_page(
            homepage_result.url,
            homepage_result,
            page_type="homepage",
            source="homepage",
        )

        candidate_map = self._nav_candidates(homepage_result.final_url, homepage_result.html)
        for sitemap_url in self.fetcher.fetch_sitemap_urls(homepage_result.final_url):
            candidate_map.setdefault(sitemap_url, {"anchor_text": "", "source": "sitemap"})

        relevant_urls = []
        skipped_urls = []
        for url, data in candidate_map.items():
            if not self.classifier.is_internal(homepage_result.final_url, url):
                skipped_urls.append(url)
                continue
            if not self.classifier.is_relevant(url, anchor_text=data["anchor_text"]):
                skipped_urls.append(url)
                continue
            relevant_urls.append((url, data["anchor_text"], data["source"]))

        relevant_urls.sort(
            key=lambda item: (-PAGE_PRIORITY[self.classifier.classify(item[0], anchor_text=item[1])], item[0])
        )
        relevant_urls = relevant_urls[: self.crawl_budget]

        pages = [homepage_page]
        discovered_urls = []
        for url, anchor_text, source in relevant_urls:
            fetched = self.fetcher.fetch(url)
            if not fetched.ok:
                skipped_urls.append(url)
                continue
            discovered_urls.append(url)
            pages.append(
                self._build_page(
                    url,
                    fetched,
                    page_type=self.classifier.classify(url, anchor_text=anchor_text, title=self._title_from_html(fetched.html)),
                    source=source,
                )
            )

        return DiscoveryResult(
            homepage=homepage_page,
            pages=pages,
            discovered_urls=discovered_urls,
            skipped_urls=skipped_urls,
        )

    def _nav_candidates(self, base_url: str, html: str) -> dict[str, dict[str, str]]:
        soup = BeautifulSoup(html, "html.parser")
        candidates: dict[str, dict[str, str]] = {}
        for anchor in soup.select("nav a[href], header a[href], footer a[href]"):
            href = anchor.get("href", "")
            if not isinstance(href, str):
                continue
            normalized = self.classifier.normalize(base_url, href)
            if not normalized or normalized == base_url.rstrip("/"):
                continue
            candidates.setdefault(
                normalized,
                {"anchor_text": anchor.get_text(" ", strip=True), "source": "nav"},
            )
        return candidates

    def _build_page(self, url: str, result, page_type: PageType, source: str) -> CrawlPage:
        text = BeautifulSoup(result.html, "html.parser").get_text(" ", strip=True)
        return CrawlPage(
            url=url.rstrip("/") if url.endswith("/") and urlparse(url).path not in {"", "/"} else url,
            final_url=result.final_url,
            page_type=page_type,
            status_code=result.status_code,
            html=result.html,
            source=source,
            title=self._title_from_html(result.html),
            text=text,
            load_time_seconds=result.load_time_seconds,
        )

    def _title_from_html(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        title = soup.find("title")
        return title.get_text(" ", strip=True) if title else ""
