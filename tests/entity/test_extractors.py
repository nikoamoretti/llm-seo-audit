from src.crawl.models import CrawlPage
from src.entity.extractors import extract_page_facts
from tests.helpers.fixture_site import FIXTURE_ROOT


def test_extractors_capture_business_facts_and_ctas():
    site_root = FIXTURE_ROOT / "strong_cafe"

    contact_page = CrawlPage(
        url="https://strong-cafe.test/contact",
        final_url="https://strong-cafe.test/contact",
        page_type="contact",
        status_code=200,
        html=(site_root / "contact.html").read_text(),
        source="nav",
    )
    faq_page = CrawlPage(
        url="https://strong-cafe.test/faq",
        final_url="https://strong-cafe.test/faq",
        page_type="faq",
        status_code=200,
        html=(site_root / "faq.html").read_text(),
        source="nav",
    )

    contact_facts = extract_page_facts(contact_page)
    faq_facts = extract_page_facts(faq_page)

    assert contact_facts.business_name == "Laveta Coffee"
    assert "(213) 555-0199" in contact_facts.phones
    assert any("Sunset Boulevard" in address for address in contact_facts.addresses)
    assert any("Mon-Fri" in hours for hours in contact_facts.hours)
    assert contact_facts.has_contact_cta is True
    assert faq_facts.faq_questions


def test_extractors_capture_services_trust_signals_and_schema():
    site_root = FIXTURE_ROOT / "strong_cafe"

    homepage = CrawlPage(
        url="https://strong-cafe.test/",
        final_url="https://strong-cafe.test/",
        page_type="homepage",
        status_code=200,
        html=(site_root / "homepage.html").read_text(),
        source="homepage",
    )
    services = CrawlPage(
        url="https://strong-cafe.test/services",
        final_url="https://strong-cafe.test/services",
        page_type="service",
        status_code=200,
        html=(site_root / "services.html").read_text(),
        source="nav",
    )

    homepage_facts = extract_page_facts(homepage)
    service_facts = extract_page_facts(services)

    assert "CafeOrCoffeeShop" in homepage_facts.schema_types
    assert homepage_facts.has_booking_cta is True
    assert "family-owned" in homepage_facts.trust_signals
    assert "Espresso Catering" in service_facts.service_names
    assert "Private Events" in service_facts.service_names

