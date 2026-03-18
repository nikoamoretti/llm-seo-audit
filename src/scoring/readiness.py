from __future__ import annotations

from typing import Any

from src.core.models import CheckDimension, ReadinessResult
from src.scoring.config import load_score_config


def score_readiness(web_results: dict[str, Any]) -> ReadinessResult:
    config = load_score_config()
    weights = config["readiness"]["weights"]
    thresholds = config["thresholds"]

    if not web_results:
        return ReadinessResult(score=0, dimensions={})

    dimensions = {
        "crawlability": _score_crawlability(web_results, float(weights["crawlability"])),
        "entity_completeness": _score_entity_completeness(web_results, float(weights["entity_completeness"])),
        "content_coverage": _score_content_coverage(
            web_results,
            float(weights["content_coverage"]),
            thresholds["content"],
        ),
        "trust_signals": _score_trust_signals(
            web_results,
            float(weights["trust_signals"]),
            thresholds["trust"],
        ),
        "listing_presence": _score_listing_presence(
            web_results,
            float(weights["listing_presence"]),
            thresholds["listings"],
        ),
    }
    total = round(sum(dimension.weighted_score for dimension in dimensions.values()))
    return ReadinessResult(score=int(total), dimensions=dimensions)


def _score_crawlability(web_results: dict[str, Any], weight: float) -> CheckDimension:
    checks = {
        "Website accessible": _optional_bool(web_results, "website_accessible"),
        "Robots file present": _optional_bool(web_results, "robots_txt_exists"),
        "Robots allow crawl": _optional_bool(web_results, "robots_allows_crawl"),
        "Sitemap present": _optional_bool(web_results, "sitemap_exists"),
        "Canonical tags present": _optional_bool(web_results, "has_canonical"),
        "No noindex directive": None if "has_noindex" not in web_results else not bool(web_results.get("has_noindex")),
    }
    score = _average_check_score(checks, neutral=0)
    return CheckDimension(
        label="Crawlability",
        description="Whether crawlers can reach, index, and interpret the site pages.",
        score=score,
        weight=weight,
        weighted_score=round(score * weight, 2),
        checks=checks,
        metrics={"eligible_checks": _eligible_count(checks)},
        evidence=_check_evidence("web_presence", {
            "website_accessible": web_results.get("website_accessible"),
            "robots_txt_exists": web_results.get("robots_txt_exists"),
            "robots_allows_crawl": web_results.get("robots_allows_crawl"),
            "sitemap_exists": web_results.get("sitemap_exists"),
            "has_canonical": web_results.get("has_canonical"),
            "has_noindex": web_results.get("has_noindex"),
        }),
    )


def _score_entity_completeness(web_results: dict[str, Any], weight: float) -> CheckDimension:
    checks = {
        "Service names extracted": bool(web_results.get("service_names")),
        "Service areas extracted": bool(web_results.get("service_areas")),
        "Contact CTA present": _optional_bool(web_results, "has_contact_cta"),
        "Booking CTA present": _optional_bool(web_results, "has_booking_cta"),
        "Local business schema present": _optional_bool(web_results, "has_local_business_schema"),
    }
    score = _average_check_score(checks, neutral=0)
    return CheckDimension(
        label="Entity Completeness",
        description="How completely the site exposes services, service areas, and business facts.",
        score=score,
        weight=weight,
        weighted_score=round(score * weight, 2),
        checks=checks,
        metrics={
            "service_name_count": len(web_results.get("service_names", []) or []),
            "service_area_count": len(web_results.get("service_areas", []) or []),
        },
        evidence=_check_evidence("web_presence", {
            "service_names": bool(web_results.get("service_names")),
            "service_areas": bool(web_results.get("service_areas")),
            "has_contact_cta": web_results.get("has_contact_cta"),
            "has_booking_cta": web_results.get("has_booking_cta"),
            "has_local_business_schema": web_results.get("has_local_business_schema"),
        }),
    )


def _score_content_coverage(web_results: dict[str, Any], weight: float, thresholds: dict[str, Any]) -> CheckDimension:
    word_count = int(web_results.get("word_count", 0) or 0)
    supporting_pages = len(
        [
            page_type
            for page_type in web_results.get("page_types", []) or []
            if page_type in {"service", "location", "faq", "about", "contact", "pricing_booking"}
        ]
    )
    word_score = _ratio_score(word_count, int(thresholds["strong_word_count"]))
    page_score = _ratio_score(supporting_pages, int(thresholds["supporting_page_target"]))
    signals = [
        100 if web_results.get("has_meta_description") else 0,
        100 if web_results.get("has_title_tag") else 0,
        100 if web_results.get("has_answer_blocks") else 0,
        100 if web_results.get("has_faq_section") else 0,
        word_score,
        page_score,
    ]
    score = round(sum(signals) / len(signals))
    checks = {
        "Meta description present": _optional_bool(web_results, "has_meta_description"),
        "Title tag present": _optional_bool(web_results, "has_title_tag"),
        "Answer blocks present": _optional_bool(web_results, "has_answer_blocks"),
        "FAQ section present": _optional_bool(web_results, "has_faq_section"),
    }
    return CheckDimension(
        label="Content Coverage",
        description="Whether the site covers the business with enough crawlable, answer-ready content.",
        score=score,
        weight=weight,
        weighted_score=round(score * weight, 2),
        checks=checks,
        metrics={
            "word_count": word_count,
            "supporting_page_count": supporting_pages,
            "minimum_word_count": int(thresholds["minimum_word_count"]),
        },
        evidence=_check_evidence("web_presence", {
            "has_meta_description": web_results.get("has_meta_description"),
            "has_title_tag": web_results.get("has_title_tag"),
            "has_answer_blocks": web_results.get("has_answer_blocks"),
            "has_faq_section": web_results.get("has_faq_section"),
            "word_count": word_count,
            "page_types": ",".join(web_results.get("page_types", []) or []),
        }),
    )


def _score_trust_signals(web_results: dict[str, Any], weight: float, thresholds: dict[str, Any]) -> CheckDimension:
    trust_signal_count = len(web_results.get("trust_signals", []) or [])
    trust_signal_score = _ratio_score(trust_signal_count, int(thresholds["trust_signal_target"]))
    signals = [
        100 if web_results.get("ssl_valid") else 0,
        100 if web_results.get("fast_load") else 0,
        100 if web_results.get("mobile_friendly_meta") else 0,
        100 if web_results.get("has_og_tags") else 0,
        trust_signal_score,
    ]
    checks = {
        "HTTPS enabled": _optional_bool(web_results, "ssl_valid"),
        "Fast load time": _optional_bool(web_results, "fast_load"),
        "Mobile viewport present": _optional_bool(web_results, "mobile_friendly_meta"),
        "Open Graph tags present": _optional_bool(web_results, "has_og_tags"),
    }
    score = round(sum(signals) / len(signals))
    return CheckDimension(
        label="Trust Signals",
        description="Whether the site demonstrates technical trust and recognizable credibility signals.",
        score=score,
        weight=weight,
        weighted_score=round(score * weight, 2),
        checks=checks,
        metrics={"trust_signal_count": trust_signal_count},
        evidence=_check_evidence("web_presence", {
            "ssl_valid": web_results.get("ssl_valid"),
            "fast_load": web_results.get("fast_load"),
            "mobile_friendly_meta": web_results.get("mobile_friendly_meta"),
            "has_og_tags": web_results.get("has_og_tags"),
            "trust_signals": ",".join(web_results.get("trust_signals", []) or []),
        }),
    )


def _score_listing_presence(web_results: dict[str, Any], weight: float, thresholds: dict[str, Any]) -> CheckDimension:
    review_floor = int(thresholds["review_count_good"])
    google_found = web_results.get("google_business_found")
    yelp_found = web_results.get("yelp_found")
    checks = {
        "Google Business Profile": _optional_bool_value(google_found),
        "Yelp": _optional_bool_value(yelp_found),
        "Phone on site": _optional_bool(web_results, "has_contact_info"),
        "Hours on site": _optional_bool(web_results, "has_hours"),
        "Address on site": _optional_bool(web_results, "has_address"),
        "Google reviews above floor": _review_check(google_found, web_results.get("google_review_count"), review_floor),
        "Yelp reviews above floor": _review_check(yelp_found, web_results.get("yelp_review_count"), review_floor),
    }
    score = _average_check_score(checks, neutral=50)
    return CheckDimension(
        label="Listing Presence",
        description="Whether the business can be verified through core listings and local entity facts.",
        score=score,
        weight=weight,
        weighted_score=round(score * weight, 2),
        checks=checks,
        metrics={
            "google_review_count": web_results.get("google_review_count"),
            "yelp_review_count": web_results.get("yelp_review_count"),
        },
        evidence=_check_evidence("web_presence", {
            "google_business_found": google_found,
            "yelp_found": yelp_found,
            "has_contact_info": web_results.get("has_contact_info"),
            "has_hours": web_results.get("has_hours"),
            "has_address": web_results.get("has_address"),
            "google_review_count": web_results.get("google_review_count"),
            "yelp_review_count": web_results.get("yelp_review_count"),
        }),
    )


def _optional_bool(payload: dict[str, Any], key: str) -> bool | None:
    if key not in payload:
        return None
    value = payload.get(key)
    if value is None:
        return None
    return bool(value)


def _optional_bool_value(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _review_check(found_value: Any, review_count: Any, review_floor: int) -> bool | None:
    if found_value is None:
        return None
    if found_value is False:
        return None
    if review_count is None:
        return None
    return int(review_count) >= review_floor


def _average_check_score(checks: dict[str, bool | None], neutral: int) -> int:
    eligible = [value for value in checks.values() if value is not None]
    if not eligible:
        return neutral
    return round(sum(1 for value in eligible if value) / len(eligible) * 100)


def _ratio_score(value: int, target: int) -> int:
    if target <= 0:
        return 0
    return round(min(1.0, value / target) * 100)


def _eligible_count(checks: dict[str, bool | None]) -> int:
    return sum(1 for value in checks.values() if value is not None)


def _check_evidence(prefix: str, values: dict[str, Any]) -> list[str]:
    evidence = []
    for key, value in values.items():
        evidence.append(f"{prefix}.{key}={value}")
    return evidence
