from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class FactCheckResult:
    score: float
    matches: dict[str, bool | None] = field(default_factory=dict)


def score_fact_alignment(response: str, known_facts: dict | None = None) -> FactCheckResult:
    known_facts = known_facts or {}
    if not known_facts:
        return FactCheckResult(score=0.5, matches={})

    response_lower = response.lower()
    matches: dict[str, bool | None] = {}

    city = known_facts.get("city")
    if city:
        city_token = str(city).lower().split(",")[0].strip()
        matches["city"] = city_token in response_lower

    phone = known_facts.get("phone")
    if phone:
        phone_digits = re.sub(r"\D", "", str(phone))
        response_digits = re.sub(r"\D", "", response)
        matches["phone"] = bool(phone_digits and phone_digits in response_digits)

    website = known_facts.get("website")
    if website:
        clean = str(website).lower().replace("https://", "").replace("http://", "").rstrip("/")
        matches["website"] = clean in response_lower

    industry = known_facts.get("industry")
    if industry:
        matches["industry"] = str(industry).lower() in response_lower

    comparable = [value for value in matches.values() if value is not None]
    if not comparable:
        return FactCheckResult(score=0.5, matches=matches)

    return FactCheckResult(
        score=round(sum(1 for value in comparable if value) / len(comparable), 3),
        matches=matches,
    )
