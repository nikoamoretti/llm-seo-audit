from __future__ import annotations

from src.core.models import Recommendation


def explain_recommendation(
    *,
    priority: str,
    category: str,
    title: str,
    why_it_matters: str,
    evidence: list[str],
    impacted_components: list[str],
    implementation_hint: str,
) -> Recommendation:
    return Recommendation(
        priority=priority,  # type: ignore[arg-type]
        category=category,
        title=title,
        detail=why_it_matters,
        why_it_matters=why_it_matters,
        evidence=evidence,
        impacted_components=impacted_components,
        implementation_hint=implementation_hint,
    )
