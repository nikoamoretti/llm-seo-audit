from web_presence import WebPresenceChecker
from tests.helpers.fixture_site import FixtureSession


def test_web_presence_uses_multi_page_crawl_facts(monkeypatch):
    checker = WebPresenceChecker(session=FixtureSession("strong_cafe"), crawl_budget=5)
    monkeypatch.setattr(
        checker,
        "_check_directories",
        lambda business_name, city: {
            "google_business_found": True,
            "google_rating": 4.7,
            "google_review_count": 182,
            "google_place_id": "place-123",
            "yelp_found": True,
            "yelp_rating": 4.5,
            "yelp_review_count": 96,
            "yelp_url": "https://yelp.example/laveta",
        },
    )

    results = checker.check_all("Laveta Coffee", "https://strong-cafe.test", "Echo Park, Los Angeles")

    assert results["website_accessible"] is True
    assert results["has_faq_section"] is True
    assert results["has_contact_info"] is True
    assert results["has_hours"] is True
    assert results["has_address"] is True
    assert results["has_schema_markup"] is True
    assert results["has_local_business_schema"] is True
    assert results["has_booking_cta"] is True
    assert results["discovered_page_count"] >= 5
