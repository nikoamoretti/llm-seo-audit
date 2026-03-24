from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from src.core.models import CheckDimension, ReadinessCheck, ReadinessResult, ReadinessState
from src.scoring.config import load_score_config


NEUTRAL_CHECK_SCORE = 50


@dataclass(frozen=True)
class _ScoredCheck:
    state: ReadinessState
    detail: str
    score: int

    @property
    def legacy_value(self) -> bool | None:
        if self.state == "pass":
            return True
        if self.state == "fail":
            return False
        return None


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
        "Website accessible": _bool_check(
            web_results,
            "website_accessible",
            pass_detail="The site responded successfully in this run.",
            fail_detail="The site could not be reached in this run.",
            missing_detail="Site accessibility was not checked in this run.",
            unavailable_detail="Site accessibility could not be verified in this run.",
        ),
        "Robots file present": _bool_check(
            web_results,
            "robots_txt_exists",
            pass_detail="A robots.txt file was found.",
            fail_detail="No robots.txt file was found.",
            missing_detail="Robots.txt presence was not checked in this run.",
            unavailable_detail="Robots.txt presence could not be verified in this run.",
        ),
        "Robots allow crawl": _bool_check(
            web_results,
            "robots_allows_crawl",
            pass_detail="The robots rules allow crawler access.",
            fail_detail="The robots rules restrict crawler access.",
            missing_detail="Crawler access rules were not checked in this run.",
            unavailable_detail="Crawler access rules could not be verified in this run.",
        ),
        "Sitemap present": _bool_check(
            web_results,
            "sitemap_exists",
            pass_detail="A sitemap was found.",
            fail_detail="No sitemap was found.",
            missing_detail="Sitemap presence was not checked in this run.",
            unavailable_detail="Sitemap presence could not be verified in this run.",
        ),
        "Canonical tags present": _bool_check(
            web_results,
            "has_canonical",
            pass_detail="Canonical tags were found on the site.",
            fail_detail="Canonical tags were not found on the checked pages.",
            missing_detail="Canonical tags were not checked in this run.",
            unavailable_detail="Canonical tags could not be verified in this run.",
        ),
        "No noindex directive": _bool_check(
            web_results,
            "has_noindex",
            pass_detail="No noindex directive was detected.",
            fail_detail="A noindex directive was detected.",
            missing_detail="Noindex status was not checked in this run.",
            unavailable_detail="Noindex status could not be verified in this run.",
            invert=True,
        ),
    }
    return _dimension(
        label="Crawlability",
        description="Whether crawlers can reach, index, and interpret the site pages.",
        weight=weight,
        checks=checks,
        metrics={"eligible_checks": _scored_check_count(checks)},
        evidence=_check_evidence(
            "web_presence",
            {
                "website_accessible": web_results.get("website_accessible"),
                "robots_txt_exists": web_results.get("robots_txt_exists"),
                "robots_allows_crawl": web_results.get("robots_allows_crawl"),
                "sitemap_exists": web_results.get("sitemap_exists"),
                "has_canonical": web_results.get("has_canonical"),
                "has_noindex": web_results.get("has_noindex"),
            },
        ),
    )


def _score_entity_completeness(web_results: dict[str, Any], weight: float) -> CheckDimension:
    checks = {
        "Service names extracted": _list_presence_check(
            web_results,
            "service_names",
            label="service names",
        ),
        "Service areas extracted": _list_presence_check(
            web_results,
            "service_areas",
            label="service areas",
        ),
        "Contact CTA present": _bool_check(
            web_results,
            "has_contact_cta",
            pass_detail="A contact call-to-action was found.",
            fail_detail="A contact call-to-action was not found.",
            missing_detail="Contact CTA coverage was not checked in this run.",
            unavailable_detail="Contact CTA coverage could not be verified in this run.",
        ),
        "Booking CTA present": _bool_check(
            web_results,
            "has_booking_cta",
            pass_detail="A booking call-to-action was found.",
            fail_detail="A booking call-to-action was not found.",
            missing_detail="Booking CTA coverage was not checked in this run.",
            unavailable_detail="Booking CTA coverage could not be verified in this run.",
        ),
        "Local business schema present": _bool_check(
            web_results,
            "has_local_business_schema",
            pass_detail="Local business schema was found.",
            fail_detail="Local business schema was not found.",
            missing_detail="Local business schema was not checked in this run.",
            unavailable_detail="Local business schema could not be verified in this run.",
        ),
    }
    return _dimension(
        label="Entity Completeness",
        description="How completely the site exposes services, service areas, and business facts.",
        weight=weight,
        checks=checks,
        metrics={
            "service_name_count": len(web_results.get("service_names", []) or []),
            "service_area_count": len(web_results.get("service_areas", []) or []),
        },
        evidence=_check_evidence(
            "web_presence",
            {
                "service_names": bool(web_results.get("service_names")),
                "service_areas": bool(web_results.get("service_areas")),
                "has_contact_cta": web_results.get("has_contact_cta"),
                "has_booking_cta": web_results.get("has_booking_cta"),
                "has_local_business_schema": web_results.get("has_local_business_schema"),
            },
        ),
    )


def _score_content_coverage(web_results: dict[str, Any], weight: float, thresholds: dict[str, Any]) -> CheckDimension:
    word_count = _int_or_none(web_results, "word_count")
    supporting_pages = _supporting_page_count(web_results)
    reported_word_count = _reported_value(word_count)
    reported_supporting_pages = _reported_value(supporting_pages)
    checks = {
        "Meta description present": _bool_check(
            web_results,
            "has_meta_description",
            pass_detail="A meta description was found.",
            fail_detail="A meta description was not found.",
            missing_detail="Meta description coverage was not checked in this run.",
            unavailable_detail="Meta description coverage could not be verified in this run.",
        ),
        "Title tag present": _bool_check(
            web_results,
            "has_title_tag",
            pass_detail="A title tag was found.",
            fail_detail="A title tag was not found.",
            missing_detail="Title tag coverage was not checked in this run.",
            unavailable_detail="Title tag coverage could not be verified in this run.",
        ),
        "Answer blocks present": _bool_check(
            web_results,
            "has_answer_blocks",
            pass_detail="Answer-ready content blocks were found.",
            fail_detail="Answer-ready content blocks were not found.",
            missing_detail="Answer block coverage was not checked in this run.",
            unavailable_detail="Answer block coverage could not be verified in this run.",
        ),
        "FAQ section present": _bool_check(
            web_results,
            "has_faq_section",
            pass_detail="An FAQ section was found.",
            fail_detail="An FAQ section was not found.",
            missing_detail="FAQ coverage was not checked in this run.",
            unavailable_detail="FAQ coverage could not be verified in this run.",
        ),
        "Word count meets target": _ratio_check(
            value=word_count,
            target=int(thresholds["strong_word_count"]),
            label="word count",
            pass_detail=f"The site meets the {int(thresholds['strong_word_count'])}-word target.",
            progress_detail=f"The site has {{value}} words; the target is {int(thresholds['strong_word_count'])}.",
            fail_detail="No usable word count was captured from the checked pages.",
            missing_detail="Word count was not measured in this run.",
            unavailable_detail="Word count was unavailable in this run.",
        ),
        "Supporting pages meet target": _ratio_check(
            value=supporting_pages,
            target=int(thresholds["supporting_page_target"]),
            label="supporting pages",
            pass_detail=f"The site meets the {int(thresholds['supporting_page_target'])}-page support target.",
            progress_detail=f"The crawl found {{value}} supporting pages; the target is {int(thresholds['supporting_page_target'])}.",
            fail_detail="No supporting service, location, FAQ, about, contact, or pricing pages were found.",
            missing_detail="Supporting page coverage was not checked in this run.",
            unavailable_detail="Supporting page coverage was unavailable in this run.",
        ),
    }
    return _dimension(
        label="Content Coverage",
        description="Whether the site covers the business with enough crawlable, answer-ready content.",
        weight=weight,
        checks=checks,
        metrics={
            "word_count": reported_word_count,
            "supporting_page_count": reported_supporting_pages,
            "minimum_word_count": int(thresholds["minimum_word_count"]),
        },
        evidence=_check_evidence(
            "web_presence",
            {
                "has_meta_description": web_results.get("has_meta_description"),
                "has_title_tag": web_results.get("has_title_tag"),
                "has_answer_blocks": web_results.get("has_answer_blocks"),
                "has_faq_section": web_results.get("has_faq_section"),
                "word_count": reported_word_count,
                "page_types": ",".join(web_results.get("page_types", []) or []) if "page_types" in web_results else None,
            },
        ),
    )


def _score_trust_signals(web_results: dict[str, Any], weight: float, thresholds: dict[str, Any]) -> CheckDimension:
    trust_signal_count = _list_count(web_results, "trust_signals")
    reported_trust_signal_count = _reported_value(trust_signal_count)
    checks = {
        "HTTPS enabled": _bool_check(
            web_results,
            "ssl_valid",
            pass_detail="HTTPS was verified.",
            fail_detail="HTTPS was not verified.",
            missing_detail="HTTPS status was not checked in this run.",
            unavailable_detail="HTTPS status could not be verified in this run.",
        ),
        "Fast load time": _bool_check(
            web_results,
            "fast_load",
            pass_detail="Page speed met the audit threshold.",
            fail_detail="Page speed did not meet the audit threshold.",
            missing_detail="Page speed was not checked in this run.",
            unavailable_detail="Page speed could not be verified in this run.",
        ),
        "Mobile viewport present": _bool_check(
            web_results,
            "mobile_friendly_meta",
            pass_detail="A mobile viewport tag was found.",
            fail_detail="A mobile viewport tag was not found.",
            missing_detail="Mobile viewport coverage was not checked in this run.",
            unavailable_detail="Mobile viewport coverage could not be verified in this run.",
        ),
        "Open Graph tags present": _bool_check(
            web_results,
            "has_og_tags",
            pass_detail="Open Graph tags were found.",
            fail_detail="Open Graph tags were not found.",
            missing_detail="Open Graph coverage was not checked in this run.",
            unavailable_detail="Open Graph coverage could not be verified in this run.",
        ),
        "Trust signals meet target": _ratio_check(
            value=trust_signal_count,
            target=int(thresholds["trust_signal_target"]),
            label="trust signals",
            pass_detail=f"The site meets the {int(thresholds['trust_signal_target'])}-signal trust target.",
            progress_detail=f"The crawl found {{value}} trust signals; the target is {int(thresholds['trust_signal_target'])}.",
            fail_detail="No trust signals were extracted from the checked pages.",
            missing_detail="Trust signal extraction was not run in this audit.",
            unavailable_detail="Trust signal extraction was unavailable in this audit.",
        ),
    }
    return _dimension(
        label="Trust Signals",
        description="Whether the site demonstrates technical trust and recognizable credibility signals.",
        weight=weight,
        checks=checks,
        metrics={"trust_signal_count": reported_trust_signal_count},
        evidence=_check_evidence(
            "web_presence",
            {
                "ssl_valid": web_results.get("ssl_valid"),
                "fast_load": web_results.get("fast_load"),
                "mobile_friendly_meta": web_results.get("mobile_friendly_meta"),
                "has_og_tags": web_results.get("has_og_tags"),
                "trust_signals": ",".join(web_results.get("trust_signals", []) or []) if "trust_signals" in web_results else None,
            },
        ),
    )


def _score_listing_presence(web_results: dict[str, Any], weight: float, thresholds: dict[str, Any]) -> CheckDimension:
    review_floor = int(thresholds["review_count_good"])
    checks = {
        "Google Business Profile": _directory_presence_check(
            web_results,
            "google_business_found",
            label="Google Business Profile",
        ),
        "Yelp": _directory_presence_check(
            web_results,
            "yelp_found",
            label="Yelp listing",
        ),
        "Phone on site": _bool_check(
            web_results,
            "has_contact_info",
            pass_detail="Phone information was found on the site.",
            fail_detail="Phone information was not found on the site.",
            missing_detail="Phone information was not checked in this run.",
            unavailable_detail="Phone information could not be verified in this run.",
        ),
        "Hours on site": _bool_check(
            web_results,
            "has_hours",
            pass_detail="Business hours were found on the site.",
            fail_detail="Business hours were not found on the site.",
            missing_detail="Business hours were not checked in this run.",
            unavailable_detail="Business hours could not be verified in this run.",
        ),
        "Address on site": _bool_check(
            web_results,
            "has_address",
            pass_detail="A business address was found on the site.",
            fail_detail="A business address was not found on the site.",
            missing_detail="Address coverage was not checked in this run.",
            unavailable_detail="Address coverage could not be verified in this run.",
        ),
        "Google reviews above floor": _review_floor_check(
            web_results,
            found_key="google_business_found",
            review_key="google_review_count",
            source_label="Google Business Profile",
            review_floor=review_floor,
        ),
        "Yelp reviews above floor": _review_floor_check(
            web_results,
            found_key="yelp_found",
            review_key="yelp_review_count",
            source_label="Yelp listing",
            review_floor=review_floor,
        ),
    }
    return _dimension(
        label="Listing Presence",
        description="Whether the business can be verified through core listings and local entity facts.",
        weight=weight,
        checks=checks,
        metrics={
            "google_review_count": web_results.get("google_review_count"),
            "yelp_review_count": web_results.get("yelp_review_count"),
        },
        evidence=_check_evidence(
            "web_presence",
            {
                "google_business_found": web_results.get("google_business_found"),
                "yelp_found": web_results.get("yelp_found"),
                "has_contact_info": web_results.get("has_contact_info"),
                "has_hours": web_results.get("has_hours"),
                "has_address": web_results.get("has_address"),
                "google_review_count": web_results.get("google_review_count"),
                "yelp_review_count": web_results.get("yelp_review_count"),
            },
        ),
    )


def _dimension(
    *,
    label: str,
    description: str,
    weight: float,
    checks: dict[str, _ScoredCheck],
    metrics: dict[str, Any],
    evidence: list[str],
) -> CheckDimension:
    score = round(sum(check.score for check in checks.values()) / len(checks)) if checks else NEUTRAL_CHECK_SCORE
    state_counts = Counter(check.state for check in checks.values())
    state = _dimension_state(state_counts)
    return CheckDimension(
        label=label,
        description=description,
        score=score,
        weight=weight,
        weighted_score=round(score * weight, 2),
        state=state,
        state_label=_dimension_state_label(state),
        state_note=_dimension_state_note(state, state_counts),
        checks={name: check.legacy_value for name, check in checks.items()},
        check_states={
            name: ReadinessCheck(
                state=check.state,
                short_label=_check_state_label(check.state),
                detail=check.detail,
            )
            for name, check in checks.items()
        },
        metrics={
            **metrics,
            "scored_check_count": _scored_check_count(checks),
            "unknown_check_count": state_counts["unknown"],
            "unavailable_check_count": state_counts["unavailable"],
        },
        evidence=evidence,
    )


def _bool_check(
    payload: dict[str, Any],
    key: str,
    *,
    pass_detail: str,
    fail_detail: str,
    missing_detail: str,
    unavailable_detail: str,
    invert: bool = False,
) -> _ScoredCheck:
    if key not in payload:
        return _ScoredCheck(state="unknown", detail=missing_detail, score=NEUTRAL_CHECK_SCORE)

    value = payload.get(key)
    if value is None:
        return _ScoredCheck(state="unavailable", detail=unavailable_detail, score=NEUTRAL_CHECK_SCORE)

    passed = (not bool(value)) if invert else bool(value)
    return _ScoredCheck(
        state="pass" if passed else "fail",
        detail=pass_detail if passed else fail_detail,
        score=100 if passed else 0,
    )


def _list_presence_check(payload: dict[str, Any], key: str, *, label: str) -> _ScoredCheck:
    if key not in payload:
        return _ScoredCheck(
            state="unknown",
            detail=f"{label.title()} were not checked in this run.",
            score=NEUTRAL_CHECK_SCORE,
        )

    value = payload.get(key)
    if value is None:
        return _ScoredCheck(
            state="unavailable",
            detail=f"{label.title()} could not be verified in this run.",
            score=NEUTRAL_CHECK_SCORE,
        )

    items = list(value) if isinstance(value, list) else []
    if items:
        return _ScoredCheck(
            state="pass",
            detail=f"{len(items)} {label} were extracted from the site.",
            score=100,
        )

    return _ScoredCheck(
        state="unknown",
        detail=f"No {label} were detected in this run, so this signal remains unverified.",
        score=0,
    )


def _ratio_check(
    *,
    value: int | None,
    target: int,
    label: str,
    pass_detail: str,
    progress_detail: str,
    fail_detail: str,
    missing_detail: str,
    unavailable_detail: str,
) -> _ScoredCheck:
    if value is _MISSING:
        return _ScoredCheck(state="unknown", detail=missing_detail, score=NEUTRAL_CHECK_SCORE)
    if value is None:
        return _ScoredCheck(state="unavailable", detail=unavailable_detail, score=NEUTRAL_CHECK_SCORE)

    numeric_value = int(value)
    ratio = _ratio_score(numeric_value, target)
    if target <= 0 or numeric_value >= target:
        return _ScoredCheck(state="pass", detail=pass_detail, score=100)
    if numeric_value > 0:
        return _ScoredCheck(
            state="mixed",
            detail=progress_detail.format(value=numeric_value, label=label),
            score=ratio,
        )
    return _ScoredCheck(state="fail", detail=fail_detail, score=0)


def _directory_presence_check(payload: dict[str, Any], key: str, *, label: str) -> _ScoredCheck:
    if key not in payload:
        return _ScoredCheck(
            state="unknown",
            detail=f"{label} was not checked in this run.",
            score=NEUTRAL_CHECK_SCORE,
        )

    value = payload.get(key)
    if value is None:
        return _ScoredCheck(
            state="unavailable",
            detail=f"{label} could not be verified because the external source was unavailable.",
            score=NEUTRAL_CHECK_SCORE,
        )

    if bool(value):
        return _ScoredCheck(
            state="pass",
            detail=f"A matching {label} was found.",
            score=100,
        )

    return _ScoredCheck(
        state="fail",
        detail=f"The lookup ran and did not find a matching {label}.",
        score=0,
    )


def _review_floor_check(
    payload: dict[str, Any],
    *,
    found_key: str,
    review_key: str,
    source_label: str,
    review_floor: int,
) -> _ScoredCheck:
    if found_key not in payload:
        return _ScoredCheck(
            state="unknown",
            detail=f"{source_label} review volume was not checked in this run.",
            score=NEUTRAL_CHECK_SCORE,
        )

    found_value = payload.get(found_key)
    if found_value is None:
        return _ScoredCheck(
            state="unavailable",
            detail=f"{source_label} review volume could not be verified because the source was unavailable.",
            score=NEUTRAL_CHECK_SCORE,
        )
    if found_value is False:
        return _ScoredCheck(
            state="unknown",
            detail=f"{source_label} review volume could not be verified because no matching listing was found.",
            score=NEUTRAL_CHECK_SCORE,
        )

    if review_key not in payload:
        return _ScoredCheck(
            state="unknown",
            detail=f"{source_label} review volume was not checked in this run.",
            score=NEUTRAL_CHECK_SCORE,
        )

    review_count = payload.get(review_key)
    if review_count is None:
        return _ScoredCheck(
            state="unavailable",
            detail=f"{source_label} review volume could not be verified because the source did not return review counts.",
            score=NEUTRAL_CHECK_SCORE,
        )

    numeric_review_count = int(review_count)
    if numeric_review_count >= review_floor:
        return _ScoredCheck(
            state="pass",
            detail=f"{source_label} review volume meets the {review_floor}-review floor.",
            score=100,
        )
    if numeric_review_count > 0:
        return _ScoredCheck(
            state="fail",
            detail=f"{source_label} has {numeric_review_count} reviews, below the {review_floor}-review floor.",
            score=0,
        )
    return _ScoredCheck(
        state="fail",
        detail=f"{source_label} has no captured reviews in this run.",
        score=0,
    )


def _dimension_state(state_counts: Counter[str]) -> ReadinessState:
    active_states = {state for state, count in state_counts.items() if count > 0}

    if active_states <= {"unknown"}:
        return "unknown"
    if active_states <= {"unknown", "unavailable"}:
        return "unavailable" if "unavailable" in active_states else "unknown"
    if active_states <= {"pass"}:
        return "pass"
    if active_states <= {"fail"}:
        return "fail"
    return "mixed"


def _dimension_state_label(state: ReadinessState) -> str:
    return {
        "pass": "VERIFIED",
        "fail": "VERIFIED GAP",
        "mixed": "PARTIAL",
        "unknown": "UNVERIFIED",
        "unavailable": "UNAVAILABLE",
    }[state]


def _check_state_label(state: ReadinessState) -> str:
    return {
        "pass": "VERIFIED",
        "fail": "VERIFIED MISSING",
        "mixed": "PARTIAL",
        "unknown": "UNVERIFIED",
        "unavailable": "UNAVAILABLE",
    }[state]


def _dimension_state_note(state: ReadinessState, state_counts: Counter[str]) -> str:
    if state == "pass":
        return "All scored signals in this area were verified."
    if state == "fail":
        return "Verified evidence shows this area is missing or weak."
    if state == "unknown":
        return "This area was not fully checked in this run, so the score uses neutral placeholders for missing evidence."
    if state == "unavailable":
        return "Some sources were unavailable in this run, so the score uses neutral placeholders where evidence is incomplete."

    parts: list[str] = []
    if state_counts["fail"]:
        parts.append(f"{state_counts['fail']} verified gap{'s' if state_counts['fail'] != 1 else ''}")
    if state_counts["mixed"]:
        parts.append(f"{state_counts['mixed']} partial signal{'s' if state_counts['mixed'] != 1 else ''}")
    if state_counts["unknown"]:
        parts.append(f"{state_counts['unknown']} unverified signal{'s' if state_counts['unknown'] != 1 else ''}")
    if state_counts["unavailable"]:
        parts.append(
            f"{state_counts['unavailable']} unavailable signal{'s' if state_counts['unavailable'] != 1 else ''}"
        )
    if not parts:
        return "This area includes a mix of verified and incomplete signals."
    return "This area includes " + ", ".join(parts) + "."


def _int_or_none(payload: dict[str, Any], key: str) -> int | None | object:
    if key not in payload:
        return _MISSING
    value = payload.get(key)
    if value is None:
        return None
    return int(value)


def _list_count(payload: dict[str, Any], key: str) -> int | None | object:
    if key not in payload:
        return _MISSING
    value = payload.get(key)
    if value is None:
        return None
    return len(value or [])


def _supporting_page_count(payload: dict[str, Any]) -> int | None | object:
    if "page_types" not in payload:
        return _MISSING
    page_types = payload.get("page_types")
    if page_types is None:
        return None
    return len(
        [
            page_type
            for page_type in page_types or []
            if page_type in {"service", "location", "faq", "about", "contact", "pricing_booking"}
        ]
    )


def _scored_check_count(checks: dict[str, _ScoredCheck]) -> int:
    return sum(1 for check in checks.values() if check.state in {"pass", "fail", "mixed"})


def _ratio_score(value: int, target: int) -> int:
    if target <= 0:
        return 0
    return round(min(1.0, value / target) * 100)


def _check_evidence(prefix: str, values: dict[str, Any]) -> list[str]:
    evidence = []
    for key, value in values.items():
        evidence.append(f"{prefix}.{key}={value}")
    return evidence


def _reported_value(value: Any) -> Any:
    return None if value is _MISSING else value


class _Missing:
    pass


_MISSING = _Missing()
