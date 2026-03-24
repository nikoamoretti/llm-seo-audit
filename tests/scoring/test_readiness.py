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


def test_readiness_distinguishes_verified_missing_directory_from_unavailable_source():
    readiness = score_readiness(
        {
            "has_contact_info": True,
            "has_hours": True,
            "has_address": True,
            "google_business_found": False,
            "yelp_found": None,
        }
    )

    listing_presence = readiness.dimensions["listing_presence"]

    assert listing_presence.state == "mixed"
    assert listing_presence.check_states["Google Business Profile"].state == "fail"
    assert listing_presence.check_states["Google Business Profile"].short_label == "VERIFIED MISSING"
    assert listing_presence.check_states["Yelp"].state == "unavailable"
    assert listing_presence.check_states["Yelp"].short_label == "UNAVAILABLE"


def test_readiness_marks_missing_extraction_signals_as_unknown_instead_of_fail():
    readiness = score_readiness(
        {
            "website_accessible": True,
            "robots_txt_exists": True,
        }
    )

    entity_completeness = readiness.dimensions["entity_completeness"]

    assert entity_completeness.state == "unknown"
    assert entity_completeness.checks["Service names extracted"] is None
    assert entity_completeness.check_states["Service names extracted"].state == "unknown"
    assert entity_completeness.check_states["Service names extracted"].short_label == "UNVERIFIED"
    assert entity_completeness.score == 50


def test_readiness_marks_directory_source_unavailable_without_rendering_it_as_fail():
    readiness = score_readiness(
        {
            "google_business_found": None,
            "yelp_found": None,
        }
    )

    listing_presence = readiness.dimensions["listing_presence"]

    assert listing_presence.state == "unavailable"
    assert listing_presence.check_states["Google Business Profile"].state == "unavailable"
    assert listing_presence.check_states["Yelp"].state == "unavailable"
    assert listing_presence.score == 50


def test_readiness_tracks_partial_verification_as_mixed():
    readiness = score_readiness(
        {
            "has_contact_info": True,
            "has_hours": False,
            "has_address": True,
            "google_business_found": True,
            "google_review_count": 4,
            "yelp_found": None,
        }
    )

    listing_presence = readiness.dimensions["listing_presence"]

    assert listing_presence.state == "mixed"
    assert listing_presence.check_states["Phone on site"].state == "pass"
    assert listing_presence.check_states["Hours on site"].state == "fail"
    assert listing_presence.check_states["Yelp"].state == "unavailable"
    assert listing_presence.check_states["Google reviews above floor"].state == "fail"
