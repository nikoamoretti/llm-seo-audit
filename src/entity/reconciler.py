from __future__ import annotations

import re
from collections import defaultdict

from src.core.models import BusinessEntity
from src.entity.extractors import ExtractedPageFacts


PAGE_WEIGHTS = {
    "homepage": 0.95,
    "contact": 1.0,
    "location": 0.9,
    "about": 0.8,
    "service": 0.65,
    "faq": 0.55,
    "pricing_booking": 0.5,
    "testimonial": 0.4,
    "other": 0.2,
}


def reconcile_business_entity(
    page_facts: list[ExtractedPageFacts],
    *,
    business_name: str | None = None,
    industry: str = "",
    city: str = "",
    website_url: str | None = None,
) -> BusinessEntity:
    # The extracted name is kept for metadata only; the canonical displayed
    # name always equals the user-submitted business_name so that
    # Cloudflare challenge titles, interstitial text, etc. never replace it.
    extracted_name, name_confidence = _pick_scalar(
        page_facts,
        lambda facts: facts.business_name,
    )
    chosen_phone, phone_confidence = _pick_scalar(
        page_facts,
        lambda facts: facts.phones[0] if facts.phones else None,
        normalizer=_normalize_phone,
    )
    chosen_address, address_confidence = _pick_scalar(
        page_facts,
        lambda facts: facts.addresses[0] if facts.addresses else None,
        normalizer=_normalize_address,
    )

    service_areas = _merge_lists(page_facts, lambda facts: facts.service_areas)
    hours = _merge_lists(page_facts, lambda facts: facts.hours)
    service_names = _merge_lists(page_facts, lambda facts: facts.service_names)
    faq_questions = _merge_lists(page_facts, lambda facts: facts.faq_questions)
    trust_signals = _merge_lists(page_facts, lambda facts: facts.trust_signals)
    schema_types = _merge_lists(page_facts, lambda facts: facts.schema_types)

    return BusinessEntity(
        business_name=business_name or extracted_name or "",
        industry=industry,
        city=city,
        website_url=website_url,
        phone=chosen_phone,
        address=chosen_address,
        service_areas=service_areas,
        hours=hours,
        service_names=service_names,
        faq_questions=faq_questions,
        trust_signals=trust_signals,
        schema_types=schema_types,
        has_booking_cta=any(facts.has_booking_cta for facts in page_facts) if page_facts else None,
        has_contact_cta=any(facts.has_contact_cta for facts in page_facts) if page_facts else None,
        confidence={
            "business_name": name_confidence,
            "phone": phone_confidence,
            "address": address_confidence,
        },
    )


def _pick_scalar(page_facts, getter, normalizer=None):
    votes = defaultdict(float)
    display_values = {}
    total_weight = 0.0

    for facts in page_facts:
        value = getter(facts)
        if not value:
            continue
        normalized = normalizer(value) if normalizer else _normalize_text(value)
        if not normalized:
            continue
        weight = PAGE_WEIGHTS.get(facts.page_type, 0.2)
        votes[normalized] += weight
        display_values.setdefault(normalized, value)
        total_weight += weight

    if not votes:
        return None, 0.0

    winner = max(votes.items(), key=lambda item: item[1])[0]
    confidence = round(votes[winner] / total_weight, 2) if total_weight else 0.0
    return display_values[winner], confidence


def _merge_lists(page_facts, getter):
    scored = defaultdict(float)
    display = {}
    for facts in page_facts:
        weight = PAGE_WEIGHTS.get(facts.page_type, 0.2)
        for value in getter(facts):
            normalized = _normalize_text(value)
            if not normalized:
                continue
            scored[normalized] += weight
            display.setdefault(normalized, value)
    ordered = sorted(scored.items(), key=lambda item: (-item[1], item[0]))
    return [display[key] for key, _ in ordered]


def _normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    return digits[-10:] if len(digits) >= 10 else digits


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def _normalize_address(value: str) -> str:
    normalized = _normalize_text(value)
    normalized = re.sub(r"\b\d{5}(?:-\d{4})?\b", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip(" ,")
