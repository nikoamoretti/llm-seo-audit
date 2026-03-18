from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

from src.crawl.models import CrawlPage


LOCAL_SCHEMA_TYPES = {
    "LocalBusiness",
    "Restaurant",
    "CafeOrCoffeeShop",
    "Dentist",
    "Attorney",
    "AutoRepair",
    "HairSalon",
    "Plumber",
    "Store",
    "MedicalBusiness",
    "FinancialService",
    "RealEstateAgent",
    "ProfessionalService",
    "FoodEstablishment",
}


@dataclass
class ExtractedPageFacts:
    url: str
    page_type: str
    business_name: str | None = None
    phones: list[str] = field(default_factory=list)
    addresses: list[str] = field(default_factory=list)
    service_areas: list[str] = field(default_factory=list)
    hours: list[str] = field(default_factory=list)
    service_names: list[str] = field(default_factory=list)
    faq_questions: list[str] = field(default_factory=list)
    trust_signals: list[str] = field(default_factory=list)
    schema_types: list[str] = field(default_factory=list)
    has_booking_cta: bool = False
    has_contact_cta: bool = False
    has_meta_description: bool = False
    has_title_tag: bool = False
    has_og_tags: bool = False
    has_canonical: bool = False
    has_viewport_meta: bool = False
    has_answer_blocks: bool = False
    word_count: int = 0


def extract_page_facts(page: CrawlPage) -> ExtractedPageFacts:
    soup = BeautifulSoup(page.html, "html.parser")
    text = soup.get_text("\n", strip=True)
    schema_payloads = _schema_payloads(soup)
    schema_types = _unique(_collect_schema_types(payload) for payload in schema_payloads)

    facts = ExtractedPageFacts(
        url=page.url,
        page_type=page.page_type,
        business_name=_extract_business_name(soup, schema_payloads),
        phones=_extract_phones(soup, text),
        addresses=_extract_addresses(text, schema_payloads),
        service_areas=_extract_service_areas(text, schema_payloads),
        hours=_extract_hours(text, schema_payloads),
        service_names=_extract_service_names(soup, page.page_type),
        faq_questions=_extract_faq_questions(soup, schema_payloads),
        trust_signals=_extract_trust_signals(text),
        schema_types=schema_types,
        has_booking_cta=_has_cta(soup, ("book", "schedule", "appointment", "reserve")),
        has_contact_cta=_has_cta(soup, ("contact", "call", "message", "quote")),
        has_meta_description=bool(soup.find("meta", attrs={"name": "description"})),
        has_title_tag=bool(soup.find("title")),
        has_og_tags=len(soup.find_all("meta", attrs={"property": re.compile(r"^og:")})) >= 2,
        has_canonical=bool(soup.find("link", attrs={"rel": "canonical"})),
        has_viewport_meta=bool(soup.find("meta", attrs={"name": "viewport"})),
        word_count=len(text.split()),
    )
    facts.has_answer_blocks = len(facts.faq_questions) >= 2
    return facts


def _schema_payloads(soup: BeautifulSoup) -> list[object]:
    payloads = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            payload = json.loads(script.string or "")
        except (TypeError, json.JSONDecodeError):
            continue
        payloads.append(payload)
    return payloads


def _collect_schema_types(payload: object) -> list[str]:
    types: list[str] = []
    if isinstance(payload, dict):
        schema_type = payload.get("@type")
        if isinstance(schema_type, list):
            types.extend(str(item) for item in schema_type)
        elif schema_type:
            types.append(str(schema_type))
        if "@graph" in payload:
            for item in payload["@graph"]:
                types.extend(_collect_schema_types(item))
    elif isinstance(payload, list):
        for item in payload:
            types.extend(_collect_schema_types(item))
    return types


def _extract_business_name(soup: BeautifulSoup, schema_payloads: list[object]) -> str | None:
    for payload in schema_payloads:
        for item in _walk_payloads(payload):
            if isinstance(item, dict) and item.get("name"):
                return str(item["name"]).strip()

    h1 = soup.find("h1")
    if h1:
        heading = _clean_business_name_candidate(h1.get_text(" ", strip=True))
        if heading:
            return heading

    for paragraph in soup.find_all(["p", "strong"]):
        candidate = _clean_business_name_candidate(paragraph.get_text(" ", strip=True))
        if candidate and len(candidate.split()) <= 5:
            return candidate

    title = soup.find("title")
    if title:
        parts = [part.strip() for part in re.split(r"\s+[|\-]\s+", title.get_text(" ", strip=True)) if part.strip()]
        for part in parts:
            candidate = _clean_business_name_candidate(part)
            if candidate:
                return candidate
    return None


def _extract_phones(soup: BeautifulSoup, text: str) -> list[str]:
    phones: list[str] = []
    for link in soup.select("a[href^='tel:']"):
        href = link.get("href", "")
        href_text = href if isinstance(href, str) else ""
        label = link.get_text(" ", strip=True) or href_text.replace("tel:", "")
        phones.append(label.strip())
    phones.extend(re.findall(r"\(\d{3}\)\s*\d{3}-\d{4}", text))
    phones.extend(re.findall(r"\d{3}[-.]\d{3}[-.]\d{4}", text))
    return _dedupe_preserve(phones)


def _extract_addresses(text: str, schema_payloads: list[object]) -> list[str]:
    addresses: list[str] = []
    for payload in schema_payloads:
        for item in _walk_payloads(payload):
            if isinstance(item, dict) and item.get("@type") == "PostalAddress":
                parts = [
                    item.get("streetAddress"),
                    item.get("addressLocality"),
                    item.get("addressRegion"),
                    item.get("postalCode"),
                ]
                addresses.append(", ".join(part for part in parts if part))

    pattern = re.compile(
        r"^\d{1,5}\s+[A-Za-z0-9.\s]+(?:Street|St|Avenue|Ave|Boulevard|Blvd|Road|Rd|Drive|Dr|Lane|Ln)"
        r"(?:,\s*[A-Za-z.\s]+,\s*[A-Z]{2}\s*\d{5})?$",
        re.IGNORECASE,
    )
    for line in text.splitlines():
        cleaned = " ".join(line.split()).strip()
        if cleaned and pattern.match(cleaned):
            addresses.append(cleaned)
    return _dedupe_preserve(addresses)


def _extract_service_areas(text: str, schema_payloads: list[object]) -> list[str]:
    areas: list[str] = []
    for payload in schema_payloads:
        for item in _walk_payloads(payload):
            if isinstance(item, dict) and item.get("areaServed"):
                area_served = item["areaServed"]
                if isinstance(area_served, list):
                    areas.extend(str(value) for value in area_served)
                else:
                    areas.append(str(area_served))

    for match in re.findall(r"serving\s+([^.]+)", text, re.IGNORECASE):
        pieces = re.split(r",| and ", match)
        areas.extend(piece.strip() for piece in pieces if piece.strip())
    return _dedupe_preserve(areas)


def _extract_hours(text: str, schema_payloads: list[object]) -> list[str]:
    hours: list[str] = []
    for payload in schema_payloads:
        for item in _walk_payloads(payload):
            if isinstance(item, dict) and item.get("openingHours"):
                opening_hours = item["openingHours"]
                if isinstance(opening_hours, list):
                    hours.extend(str(value) for value in opening_hours)
                else:
                    hours.append(str(opening_hours))

    hours.extend(
        match.strip()
        for match in re.findall(
            r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[A-Za-z\-]*:\s*\d{1,2}:\d{2}\s*[AP]M\s*-\s*\d{1,2}:\d{2}\s*[AP]M",
            text,
        )
    )
    return _dedupe_preserve(hours)


def _extract_service_names(soup: BeautifulSoup, page_type: str) -> list[str]:
    names: list[str] = []
    if page_type == "service":
        names.extend(li.get_text(" ", strip=True) for li in soup.find_all("li"))
        names.extend(
            header.get_text(" ", strip=True)
            for header in soup.find_all(["h2", "h3"])
            if "service" not in header.get_text(" ", strip=True).lower()
        )
    return [name for name in _dedupe_preserve(names) if name and len(name.split()) <= 5]


def _extract_faq_questions(soup: BeautifulSoup, schema_payloads: list[object]) -> list[str]:
    questions = [
        element.get_text(" ", strip=True)
        for element in soup.find_all(["h2", "h3", "summary"])
        if element.get_text(" ", strip=True).endswith("?")
    ]
    for payload in schema_payloads:
        for item in _walk_payloads(payload):
            if isinstance(item, dict) and item.get("@type") == "Question" and item.get("name"):
                questions.append(str(item["name"]).strip())
    return _dedupe_preserve(questions)


def _extract_trust_signals(text: str) -> list[str]:
    lowered = text.lower()
    signals = []
    if "family-owned" in lowered or "family owned" in lowered:
        signals.append("family-owned")
    if "award-winning" in lowered or "award winning" in lowered:
        signals.append("award-winning")
    if "licensed" in lowered:
        signals.append("licensed")
    if "insured" in lowered:
        signals.append("insured")
    if "certified" in lowered:
        signals.append("certified")
    if "five-star" in lowered or "5-star" in lowered:
        signals.append("five-star reviews")
    return signals


def _has_cta(soup: BeautifulSoup, keywords: tuple[str, ...]) -> bool:
    for element in soup.find_all(["a", "button"]):
        label = element.get_text(" ", strip=True).lower()
        if any(keyword in label for keyword in keywords):
            return True
    return False


def _walk_payloads(payload: object):
    if isinstance(payload, dict):
        yield payload
        if "@graph" in payload:
            for item in payload["@graph"]:
                yield from _walk_payloads(item)
        for key, value in payload.items():
            if key == "@graph":
                continue
            if isinstance(value, (dict, list)):
                yield from _walk_payloads(value)
    elif isinstance(payload, list):
        for item in payload:
            yield from _walk_payloads(item)


def _dedupe_preserve(values: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for value in values:
        cleaned = value.strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(cleaned)
    return deduped


def _unique(type_lists) -> list[str]:
    values: list[str] = []
    for type_list in type_lists:
        values.extend(type_list)
    return _dedupe_preserve(values)


def _clean_business_name_candidate(value: str) -> str | None:
    candidate = value.strip()
    if not candidate:
        return None

    for prefix in ("contact ", "about ", "faq ", "book ", "schedule "):
        if candidate.lower().startswith(prefix):
            candidate = candidate[len(prefix):].strip(" :-|")

    generic = {
        "contact",
        "services",
        "faq",
        "frequently asked questions",
        "about",
        "service area",
        "downtown office",
        "book now",
    }
    if candidate.lower() in generic:
        return None
    return candidate
