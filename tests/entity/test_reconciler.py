from src.crawl.models import CrawlPage
from src.entity.extractors import extract_page_facts
from src.entity.reconciler import reconcile_business_entity
from tests.helpers.fixture_site import FIXTURE_ROOT


def test_reconciler_picks_high_confidence_business_facts():
    site_root = FIXTURE_ROOT / "multi_location_law"
    pages = [
        CrawlPage(
            url="https://multi-location-law.test/",
            final_url="https://multi-location-law.test/",
            page_type="homepage",
            status_code=200,
            html=(site_root / "homepage.html").read_text(),
            source="homepage",
        ),
        CrawlPage(
            url="https://multi-location-law.test/contact",
            final_url="https://multi-location-law.test/contact",
            page_type="contact",
            status_code=200,
            html=(site_root / "contact.html").read_text(),
            source="nav",
        ),
        CrawlPage(
            url="https://multi-location-law.test/locations/downtown",
            final_url="https://multi-location-law.test/locations/downtown",
            page_type="location",
            status_code=200,
            html=(site_root / "locations__downtown.html").read_text(),
            source="sitemap",
        ),
    ]

    entity = reconcile_business_entity(
        [extract_page_facts(page) for page in pages],
        city="Los Angeles, CA",
        website_url="https://multi-location-law.test",
    )

    assert entity.business_name == "Parker Law Group"
    assert entity.phone == "(323) 555-0110"
    assert "100 Main Street" in (entity.address or "")
    assert entity.confidence["phone"] > 0.6
    assert entity.confidence["address"] > 0.6

