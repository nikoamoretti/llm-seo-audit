from __future__ import annotations

import re


def extract_competitors(response: str, business_variants: list[str]) -> list[str]:
    competitors: list[str] = []
    lines = response.split("\n")

    for line in lines:
        bold_matches = re.findall(r"\*\*([^*]+)\*\*", line)
        for match in bold_matches:
            name = _clean_candidate(match)
            if _is_competitor_name(name, business_variants) and name not in competitors:
                competitors.append(name)

        numbered = re.match(r"\s*\d+[.)]\s*\*?\*?([^*\n:]+)", line)
        if numbered:
            name = _clean_candidate(numbered.group(1))
            if _is_competitor_name(name, business_variants) and name not in competitors:
                competitors.append(name)

    return competitors[:15]


def _clean_candidate(value: str) -> str:
    return value.strip().rstrip(":").strip(" -")


def _is_competitor_name(value: str, business_variants: list[str]) -> bool:
    if len(value) <= 2 or len(value) >= 60 or len(value.split()) > 8:
        return False
    value_lower = value.lower()
    if any(variant in value_lower for variant in business_variants):
        return False
    generic = [
        "here are", "top rated", "best", "recommend", "option",
        "important", "however", "also", "consider", "please",
    ]
    return not any(token in value_lower for token in generic)
