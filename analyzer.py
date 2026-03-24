"""
Compatibility facade for structured response analysis.
"""

from __future__ import annotations

import re
from dataclasses import asdict

from src.analysis.citations import citation_flags, extract_citations
from src.analysis.competitors import extract_competitor_candidates, filter_competitor_candidates
from src.analysis.fact_check import score_fact_alignment
from src.analysis.mentions import analyze_mentions
from src.analysis.positions import PositionResult, detect_position
from src.analysis.recommendation_strength import (
    compute_legacy_visibility_score,
    score_sentiment,
)


class ResponseAnalyzer:
    """Compatibility shim over the structured analysis modules."""

    def __init__(self, business_name: str, known_facts: dict | None = None):
        self.business_name = business_name
        self.known_facts = known_facts or {}

    def analyze_response(self, response: str, query: str) -> dict:
        del query

        if response.startswith("ERROR:"):
            return self.empty_analysis()

        mention = analyze_mentions(self.business_name, response)
        citation_evidence_state: str | None = None
        try:
            citations = extract_citations(response, self.known_facts)
            citation_state = citation_flags(citations)
        except Exception:
            citations = []
            citation_state = {
                "cited": False,
                "cited_official_domain": False,
                "cited_third_party_domain": False,
            }
            citation_evidence_state = "unavailable"
        position = self._position_for_response(response, mention)
        sentiment = score_sentiment(response, mention.name_variants, mention.mentioned)
        fact_check = score_fact_alignment(response, self.known_facts)
        competitor_candidates = extract_competitor_candidates(response, mention.name_variants)
        competitors = filter_competitor_candidates(competitor_candidates)
        attributes = self._extract_attributes(response)
        visibility_score = compute_legacy_visibility_score(
            mentioned=mention.mentioned,
            cited=citation_state["cited"],
            position_normalized=position.position_normalized,
            sentiment=sentiment,
            accuracy=fact_check.score,
        )

        return {
            "mentioned": mention.mentioned,
            "recommended": mention.recommended,
            "exact_match": mention.exact_match,
            "fuzzy_match": mention.fuzzy_match,
            "fuzzy_score": mention.fuzzy_score,
            "cited": citation_state["cited"],
            "cited_official_domain": citation_state["cited_official_domain"],
            "cited_third_party_domain": citation_state["cited_third_party_domain"],
            "citation_evidence_state": citation_evidence_state,
            "citations": [
                {
                    "label": citation.label,
                    "url": citation.url,
                    "domain": citation.domain,
                    "citation_type": citation.citation_type,
                    "is_official_domain": citation.is_official_domain,
                }
                for citation in citations
            ],
            "position": position.position,
            "total_items": position.total_items,
            "position_normalized": position.position_normalized,
            "sentiment": round(sentiment, 3),
            "accuracy": round(fact_check.score, 3),
            "fact_matches": fact_check.matches,
            "visibility_score": visibility_score,
            "competitors": competitors,
            "competitor_candidates": [asdict(candidate) for candidate in competitor_candidates],
            "attributes": attributes,
        }

    def _position_for_response(self, response: str, mention) -> PositionResult:
        if not mention.mentioned:
            return PositionResult(position=None, total_items=0, position_normalized=0.0)

        detected = detect_position(response, mention.name_variants)
        if detected.position is not None:
            return detected

        return PositionResult(position=None, total_items=detected.total_items, position_normalized=0.5)

    def _extract_attributes(self, response: str) -> list[str]:
        attributes: list[str] = []
        patterns = [
            r"known for\s+(?:their\s+)?([^.,\n]+)",
            r"specializ(?:es?|ing) in\s+([^.,\n]+)",
            r"offers?\s+([^.,\n]+)",
            r"(?:excellent|great|outstanding|exceptional)\s+([^.,\n]+)",
            r"(?:highly rated|well-known|popular|trusted)\s+(?:for\s+)?([^.,\n]+)",
            r"reputation for\s+([^.,\n]+)",
        ]
        for pattern in patterns:
            for match in re.findall(pattern, response, re.IGNORECASE):
                attribute = match.strip()
                if 3 < len(attribute) < 60 and attribute not in attributes:
                    attributes.append(attribute)
        return attributes[:10]

    def empty_analysis(self) -> dict:
        return {
            "mentioned": False,
            "recommended": False,
            "exact_match": False,
            "fuzzy_match": False,
            "fuzzy_score": 0,
            "cited": False,
            "cited_official_domain": False,
            "cited_third_party_domain": False,
            "citation_evidence_state": "unavailable",
            "citations": [],
            "position": None,
            "total_items": 0,
            "position_normalized": 0.0,
            "sentiment": 0.0,
            "accuracy": 0.0,
            "fact_matches": {},
            "visibility_score": 0.0,
            "competitors": [],
            "competitor_candidates": [],
            "attributes": [],
        }
