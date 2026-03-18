from __future__ import annotations

import re
from dataclasses import dataclass

from thefuzz import fuzz


RECOMMENDATION_WORDS = {
    "recommend",
    "recommended",
    "top",
    "best",
    "favorite",
    "go with",
    "consider",
    "try",
    "first choice",
}


@dataclass(frozen=True)
class MentionAnalysis:
    mentioned: bool
    recommended: bool
    exact_match: bool
    fuzzy_match: bool
    fuzzy_score: int
    name_variants: list[str]


def analyze_mentions(business_name: str, response: str) -> MentionAnalysis:
    variants = _generate_variants(business_name)
    exact_variants = _generate_exact_variants(business_name)
    response_lower = response.lower()
    exact_match = any(
        re.search(rf"\b{re.escape(variant)}\b", response_lower)
        for variant in exact_variants
    )

    fuzzy_match = False
    fuzzy_score = 0
    if not exact_match:
        words = response_lower.split()
        for variant in variants:
            variant_words = variant.split()
            for index in range(len(words) - len(variant_words) + 1):
                chunk = " ".join(words[index:index + len(variant_words)])
                score = fuzz.ratio(variant, chunk)
                if score > fuzzy_score:
                    fuzzy_score = score
                if score >= 80:
                    fuzzy_match = True

    mentioned = exact_match or fuzzy_match
    recommended = False
    if mentioned:
        sentences = re.split(r"[.\n!?]", response_lower)
        for sentence in sentences:
            if any(variant in sentence or fuzz.partial_ratio(variant, sentence) >= 80 for variant in variants):
                if any(token in sentence for token in RECOMMENDATION_WORDS):
                    recommended = True
                    break
        if not recommended and re.search(r"^\s*\d+[.)]\s", response, re.MULTILINE):
            recommended = True

    return MentionAnalysis(
        mentioned=mentioned,
        recommended=recommended,
        exact_match=exact_match,
        fuzzy_match=fuzzy_match and not exact_match,
        fuzzy_score=fuzzy_score,
        name_variants=variants,
    )


def _generate_variants(name: str) -> list[str]:
    variants = [name.lower()]
    variants.append(re.sub(r"'s\b", "", name.lower()))
    for suffix in [" llc", " inc", " corp", " co", " company", " group", " services"]:
        if name.lower().endswith(suffix):
            variants.append(name.lower().replace(suffix, "").strip())
    variants.append(re.sub(r"[^\w\s]", "", name.lower()))
    deduped = []
    for variant in variants:
        if variant not in deduped:
            deduped.append(variant)
    return deduped


def _generate_exact_variants(name: str) -> list[str]:
    exact = [name.lower(), re.sub(r"[^\w\s]", "", name.lower())]
    deduped = []
    for variant in exact:
        if variant not in deduped:
            deduped.append(variant)
    return deduped
