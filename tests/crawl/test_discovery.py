from src.crawl.discovery import SiteDiscovery
from src.crawl.fetcher import PageFetcher
from tests.helpers.fixture_site import FixtureSession


def test_discovery_finds_relevant_pages_from_nav_and_sitemap():
    discovery = SiteDiscovery(
        fetcher=PageFetcher(session=FixtureSession("strong_cafe")),
        crawl_budget=5,
    )

    result = discovery.discover("https://strong-cafe.test")
    page_types = {page.page_type for page in result.pages}
    urls = {page.url for page in result.pages}

    assert result.homepage is not None
    assert len(result.pages) == 6
    assert {"homepage", "service", "faq", "contact", "about", "pricing_booking"} <= page_types
    assert "https://strong-cafe.test/privacy-policy" not in urls


def test_discovery_respects_budget_and_skips_broken_links():
    discovery = SiteDiscovery(
        fetcher=PageFetcher(session=FixtureSession("broken_dentist")),
        crawl_budget=3,
    )

    result = discovery.discover("https://broken-dentist.test")

    assert result.homepage is None
    assert result.pages == []
    assert result.discovered_urls == []

