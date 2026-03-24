from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Literal, Mapping


MIN_COMPETITOR_CONFIDENCE = 0.6
MAX_COMPETITORS = 15
COMPETITOR_SOURCE = Literal["bold", "numbered", "aggregate"]

PUNCTUATION_TRANSLATION = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2010": "-",
        "\u2011": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u00a0": " ",
    }
)
LEGAL_SUFFIXES = {"llc", "inc", "incorporated", "corp", "corporation", "ltd", "pllc"}
ENTITY_HINT_WORDS = {
    "advisors",
    "attorneys",
    "auto",
    "bakery",
    "bar",
    "barber",
    "bbq",
    "brewery",
    "builders",
    "burger",
    "cafe",
    "care",
    "clinic",
    "coffee",
    "cooling",
    "dental",
    "electric",
    "electricians",
    "espresso",
    "florist",
    "garage",
    "grill",
    "heating",
    "hotel",
    "hvac",
    "kitchen",
    "law",
    "legal",
    "market",
    "medical",
    "partners",
    "pharmacy",
    "pizza",
    "plumbing",
    "restaurant",
    "roofing",
    "rooter",
    "salon",
    "service",
    "services",
    "shop",
    "spa",
    "studio",
    "sushi",
    "tacos",
}
LOW_SIGNAL_TERMS = {
    "and",
    "are",
    "area",
    "best",
    "by",
    "choice",
    "choices",
    "few",
    "for",
    "here",
    "in",
    "local",
    "may",
    "more",
    "options",
    "ratings",
    "read",
    "results",
    "reviews",
    "strong",
    "the",
    "vary",
}
SOURCE_LABELS = {
    "citation",
    "citations",
    "official website",
    "review sites",
    "source",
    "source label",
    "source labels",
    "sources",
    "website",
}
WARNING_PREFIXES = {"caution", "disclaimer", "important", "note", "warning"}
EDITORIAL_PREFIXES = {
    "based on",
    "best options",
    "here are",
    "here's",
    "other notable",
    "recommended options",
    "top picks",
}
GENERIC_UI_TERMS = {
    "book now",
    "click here",
    "contact us",
    "learn more",
    "official website",
    "open now",
    "read more",
    "view more",
}
REJECT_SUBSTRINGS = {
    "results may vary",
    "reviews and ratings",
}
DOMAIN_PATTERN = re.compile(r"(?:https?://)?(?:www\.)?([a-z0-9-]+\.[a-z]{2,})", re.IGNORECASE)


@dataclass(frozen=True)
class CompetitorCandidate:
    raw_text: str
    display_name: str
    normalized_name: str
    confidence: float
    source: COMPETITOR_SOURCE
    accepted: bool
    rejection_reason: str = ""


def extract_competitors(response: str, business_variants: list[str]) -> list[str]:
    candidates = extract_competitor_candidates(response, business_variants)
    return filter_competitor_candidates(candidates, limit=MAX_COMPETITORS)


def extract_competitor_candidates(response: str, business_variants: list[str]) -> list[CompetitorCandidate]:
    normalized_variants = [_normalized_lookup_key(variant) for variant in business_variants if variant]
    candidates: list[CompetitorCandidate] = []

    for source, raw_candidate, line in _iter_candidate_fragments(response):
        candidates.append(
            _assess_candidate(
                raw_candidate,
                source=source,
                line_context=line,
                business_variants=normalized_variants,
            )
        )

    return candidates


def filter_competitor_candidates(
    candidates: Iterable[CompetitorCandidate],
    *,
    limit: int = MAX_COMPETITORS,
    min_confidence: float = MIN_COMPETITOR_CONFIDENCE,
) -> list[str]:
    grouped: dict[str, tuple[int, CompetitorCandidate]] = {}

    for index, candidate in enumerate(candidates):
        if not candidate.accepted or candidate.confidence < min_confidence:
            continue

        current = grouped.get(candidate.normalized_name)
        if current is None or _prefer_candidate(candidate, current[1]):
            grouped[candidate.normalized_name] = (index, candidate)

    ordered = sorted(grouped.values(), key=lambda item: item[0])
    return [candidate.display_name for _, candidate in ordered[:limit]]


def select_report_competitors(
    competitor_counts: Mapping[str, int],
    *,
    business_variants: list[str],
    limit: int = 10,
    min_confidence: float = MIN_COMPETITOR_CONFIDENCE,
) -> list[tuple[str, int]]:
    normalized_variants = [_normalized_lookup_key(variant) for variant in business_variants if variant]
    grouped: dict[str, tuple[str, int, float]] = {}

    for raw_name, count in competitor_counts.items():
        candidate = _assess_candidate(
            raw_name,
            source="aggregate",
            line_context=raw_name,
            business_variants=normalized_variants,
        )
        if not candidate.accepted or candidate.confidence < min_confidence:
            continue

        display_name, total_count, best_confidence = grouped.get(
            candidate.normalized_name,
            (candidate.display_name, 0, candidate.confidence),
        )
        total_count += count
        if candidate.confidence > best_confidence or (
            candidate.confidence == best_confidence and len(candidate.display_name) < len(display_name)
        ):
            display_name = candidate.display_name
            best_confidence = candidate.confidence
        grouped[candidate.normalized_name] = (display_name, total_count, best_confidence)

    ordered = sorted(
        grouped.values(),
        key=lambda item: (-item[1], -item[2], item[0].lower()),
    )
    return [(display_name, total_count) for display_name, total_count, _ in ordered[:limit]]


def _iter_candidate_fragments(response: str) -> Iterable[tuple[COMPETITOR_SOURCE, str, str]]:
    for line in response.splitlines():
        for match in re.findall(r"\*\*([^*]+)\*\*", line):
            yield "bold", match, line

        numbered = re.match(r"\s*\d+[.)]\s*(.+)$", line)
        if numbered:
            yield "numbered", numbered.group(1), line


def _assess_candidate(
    raw_candidate: str,
    *,
    source: COMPETITOR_SOURCE,
    line_context: str,
    business_variants: list[str],
) -> CompetitorCandidate:
    cleaned = _clean_candidate(raw_candidate)
    display_name = _display_name(cleaned)
    normalized_name = _normalized_lookup_key(display_name)

    if not normalized_name:
        return CompetitorCandidate(
            raw_text=raw_candidate,
            display_name=display_name,
            normalized_name=normalized_name,
            confidence=0.0,
            source=source,
            accepted=False,
            rejection_reason="empty_candidate",
        )

    rejection_reason = _rejection_reason(cleaned, normalized_name, business_variants)
    confidence = _candidate_confidence(cleaned, source=source, line_context=line_context)
    accepted = rejection_reason == "" and confidence >= MIN_COMPETITOR_CONFIDENCE

    return CompetitorCandidate(
        raw_text=raw_candidate,
        display_name=display_name,
        normalized_name=normalized_name,
        confidence=confidence,
        source=source,
        accepted=accepted,
        rejection_reason=rejection_reason,
    )


def _clean_candidate(value: str) -> str:
    cleaned = value.translate(PUNCTUATION_TRANSLATION).strip()
    cleaned = re.sub(r"^\*+", "", cleaned)
    cleaned = re.split(r"\s[-|]\s|:\s", cleaned, maxsplit=1)[0]
    cleaned = re.split(r"\s+\(", cleaned, maxsplit=1)[0]
    cleaned = cleaned.strip().strip('"\''"[]{}()")
    cleaned = cleaned.rstrip(".,;:!?")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def _display_name(value: str) -> str:
    value = _strip_display_suffixes(value)
    words = value.split()
    if _entity_token_count(words) >= 2 or any(token.isupper() for token in words):
        return value
    return " ".join(token.capitalize() for token in value.split())


def _strip_display_suffixes(value: str) -> str:
    tokens = value.split()
    while len(tokens) > 2 and tokens and tokens[-1].lower().rstrip(".") in LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def _normalized_lookup_key(value: str) -> str:
    normalized = value.translate(PUNCTUATION_TRANSLATION).lower()
    normalized = normalized.replace("&", " and ")
    normalized = re.sub(r"[\"'`]", "", normalized)
    normalized = re.sub(
        r"\b(?:llc|inc|incorporated|corp|corporation|ltd|pllc)\b\.?",
        "",
        normalized,
    )
    normalized = re.sub(r"[^a-z0-9]+", "", normalized)
    return normalized


def _rejection_reason(value: str, normalized_name: str, business_variants: list[str]) -> str:
    value_lower = value.lower()
    words = value.split()

    if len(value) <= 2 or len(value) >= 70:
        return "invalid_length"
    if len(words) > 8:
        return "too_many_words"
    if any(variant and variant in normalized_name for variant in business_variants):
        return "same_as_business"
    if value_lower in GENERIC_UI_TERMS:
        return "generic_ui_term"
    if value_lower in SOURCE_LABELS or any(value_lower.startswith(f"{prefix}:") for prefix in SOURCE_LABELS):
        return "source_label"
    if value_lower in WARNING_PREFIXES or any(value_lower.startswith(f"{prefix}:") for prefix in WARNING_PREFIXES):
        return "warning_phrase"
    if any(value_lower.startswith(prefix) for prefix in EDITORIAL_PREFIXES):
        return "editorial_fragment"
    if any(fragment in value_lower for fragment in REJECT_SUBSTRINGS):
        return "editorial_fragment"
    if len(words) >= 3 and _entity_token_count(words) < 2 and not _has_entity_hint(words):
        return "low_signal_phrase"
    return ""


def _candidate_confidence(value: str, *, source: COMPETITOR_SOURCE, line_context: str) -> float:
    words = value.split()
    confidence = 0.15 if source == "aggregate" else (0.35 if source == "numbered" else 0.25)

    if _entity_token_count(words) >= 2:
        confidence += 0.35
    elif len(words) == 1 and _is_title_token(words[0]):
        confidence += 0.25

    if _has_entity_hint(words):
        confidence += 0.2
    if _has_domain_support(line_context, value):
        confidence += 0.15
    if len(words) == 1:
        confidence -= 0.05
    if len(words) >= 5:
        confidence -= 0.15
    if sum(1 for word in words if word.lower() in LOW_SIGNAL_TERMS) >= 2:
        confidence -= 0.25

    return round(max(0.0, min(1.0, confidence)), 2)


def _entity_token_count(words: list[str]) -> int:
    return sum(1 for word in words if _is_title_token(word))


def _has_entity_hint(words: list[str]) -> bool:
    return any(word.lower().rstrip(".") in ENTITY_HINT_WORDS for word in words)


def _is_title_token(word: str) -> bool:
    token = word.strip(".,")
    if not token:
        return False
    if token.isupper() and len(token) > 1:
        return True
    head = token.split("-", 1)[0]
    return head[:1].isupper() and any(char.isalpha() for char in token)


def _has_domain_support(line_context: str, candidate: str) -> bool:
    candidate_key = _normalized_lookup_key(candidate)
    if not candidate_key:
        return False

    for domain in DOMAIN_PATTERN.findall(line_context.lower()):
        domain_key = re.sub(r"[^a-z0-9]+", "", domain.split(".", 1)[0])
        if domain_key and (domain_key in candidate_key or candidate_key.startswith(domain_key)):
            return True
    return False


def _prefer_candidate(candidate: CompetitorCandidate, current: CompetitorCandidate) -> bool:
    if candidate.confidence != current.confidence:
        return candidate.confidence > current.confidence
    return len(candidate.display_name) < len(current.display_name)
