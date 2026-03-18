from src.scoring.readiness import score_readiness


def test_readiness_scores_multi_page_site_signals():
    readiness = score_readiness(
        {
            "website_accessible": True,
            "robots_txt_exists": True,
            "robots_allows_crawl": True,
            "sitemap_exists": True,
            "has_canonical": True,
            "has_noindex": False,
            "has_contact_info": True,
            "has_hours": True,
            "has_address": True,
            "service_names": ["espresso", "pastries", "catering"],
            "service_areas": ["Echo Park", "Silver Lake"],
            "has_contact_cta": True,
            "has_booking_cta": True,
            "has_local_business_schema": True,
            "has_meta_description": True,
            "has_title_tag": True,
            "has_answer_blocks": True,
            "has_faq_section": True,
            "word_count": 1400,
            "page_types": ["homepage", "service", "faq", "location", "contact"],
            "ssl_valid": True,
            "fast_load": True,
            "mobile_friendly_meta": True,
            "has_og_tags": True,
            "trust_signals": ["licensed", "family-owned", "5-star reviews"],
            "google_business_found": True,
            "google_review_count": 120,
            "yelp_found": True,
            "yelp_review_count": 42,
        }
    )

    assert readiness.score >= 85
    assert readiness.dimensions["crawlability"].weight > 0
    assert readiness.dimensions["entity_completeness"].score >= 80
    assert readiness.dimensions["listing_presence"].score >= 80


def test_readiness_treats_unchecked_directory_lookups_as_neutral():
    readiness = score_readiness(
        {
            "website_accessible": True,
            "robots_txt_exists": True,
            "robots_allows_crawl": True,
            "sitemap_exists": True,
            "has_canonical": True,
            "has_noindex": False,
            "has_contact_info": True,
            "has_hours": True,
            "has_address": True,
            "service_names": ["espresso"],
            "service_areas": ["Echo Park"],
            "has_contact_cta": True,
            "has_local_business_schema": True,
            "has_meta_description": True,
            "has_title_tag": True,
            "has_answer_blocks": True,
            "has_faq_section": True,
            "word_count": 900,
            "page_types": ["homepage", "service", "contact"],
            "ssl_valid": True,
            "fast_load": True,
            "mobile_friendly_meta": True,
            "trust_signals": ["licensed"],
            "google_business_found": None,
            "yelp_found": None,
        }
    )

    listing_presence = readiness.dimensions["listing_presence"]

    assert listing_presence.checks["Google Business Profile"] is None
    assert listing_presence.checks["Yelp"] is None
    assert listing_presence.score > 0
