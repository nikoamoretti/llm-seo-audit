from __future__ import annotations

from typing import Any

from src.core.models import ReadinessResult, ScoreBreakdown, VisibilityResult
from src.scoring.config import load_score_config as _load_score_config


def load_score_config() -> dict[str, Any]:
    return _load_score_config()


def score_final(
    readiness: ReadinessResult,
    visibility: VisibilityResult,
    web_presence: dict[str, Any],
) -> ScoreBreakdown:
    config = load_score_config()
    weights = config["final"]["weights"]

    base_score = (
        readiness.score * float(weights["readiness"])
        + visibility.score * float(weights["visibility"])
    )
    penalties = _collect_penalties(web_presence, config["penalties"])
    final_score = max(0, round(base_score - sum(float(penalty["points"]) for penalty in penalties)))
    return ScoreBreakdown(
        final=int(final_score),
        readiness=readiness.score,
        visibility=visibility.score,
        version=str(config["version"]),
        formula=(
            f"{config['version']}(readiness={weights['readiness']}, "
            f"visibility={weights['visibility']}) - penalties"
        ),
        penalties=penalties,
    )


def _collect_penalties(web_presence: dict[str, Any], penalty_config: dict[str, int]) -> list[dict[str, Any]]:
    penalties = []
    if web_presence.get("has_noindex") is True:
        penalties.append(
            {
                "key": "noindex",
                "label": "Noindex directive present",
                "points": penalty_config["noindex"],
                "reason": "A noindex directive prevents the site from being treated as a retrievable source.",
                "evidence": ["web_presence.has_noindex=True"],
            }
        )
    if web_presence.get("robots_allows_crawl") is False:
        penalties.append(
            {
                "key": "robots_blocked",
                "label": "Robots rules block crawl access",
                "points": penalty_config["robots_blocked"],
                "reason": "Robots rules block crawlers from accessing site content.",
                "evidence": ["web_presence.robots_allows_crawl=False"],
            }
        )
    if web_presence and web_presence.get("website_accessible") is False:
        penalties.append(
            {
                "key": "website_inaccessible",
                "label": "Website inaccessible",
                "points": penalty_config["website_inaccessible"],
                "reason": "The site could not be accessed during the audit.",
                "evidence": ["web_presence.website_accessible=False"],
            }
        )
    return penalties
