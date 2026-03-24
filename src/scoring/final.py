from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Any

from src.core.models import ReadinessResult, ScoreBreakdown, VisibilityResult
from src.scoring.config import load_score_config as _load_score_config


DISPLAY_SCORE_QUANTUM = Decimal("0.001")
FINAL_SCORE_QUANTUM = Decimal("1")


class ScoreIntegrityError(ValueError):
    pass


@dataclass(frozen=True)
class FinalScoreMath:
    readiness_score: int
    visibility_score: float
    weighted_base_score: float
    penalties_total: float
    adjusted_score: float
    final_score: int


def load_score_config() -> dict[str, Any]:
    return _load_score_config()


def final_score_formula(*, version: str | None = None, weights: dict[str, Any] | None = None) -> str:
    config = load_score_config()
    active_version = version or str(config["version"])
    active_weights = weights or config["final"]["weights"]
    return (
        f"{active_version} final = round(("
        f"{active_weights['readiness']} * readiness) + "
        f"({active_weights['visibility']} * visibility) - penalties)"
    )


def calculate_final_score_math(
    *,
    readiness_score: int,
    visibility_score: float,
    penalties: list[dict[str, Any]] | None = None,
    weights: dict[str, Any] | None = None,
) -> FinalScoreMath:
    active_weights = weights or load_score_config()["final"]["weights"]
    active_penalties = penalties or []

    weighted_base = (
        _decimal(readiness_score) * _decimal(active_weights["readiness"])
        + _decimal(visibility_score) * _decimal(active_weights["visibility"])
    )
    penalties_total = sum(
        (_decimal(penalty.get("points", 0)) for penalty in active_penalties),
        Decimal("0"),
    )
    adjusted_score = weighted_base - penalties_total

    return FinalScoreMath(
        readiness_score=int(readiness_score),
        visibility_score=float(_quantize_display(_decimal(visibility_score))),
        weighted_base_score=float(_quantize_display(weighted_base)),
        penalties_total=float(_quantize_display(penalties_total)),
        adjusted_score=float(_quantize_display(adjusted_score)),
        final_score=max(0, _round_final_score(adjusted_score)),
    )


def validate_score_breakdown(
    score: ScoreBreakdown,
    *,
    weights: dict[str, Any] | None = None,
) -> FinalScoreMath:
    score_math = calculate_final_score_math(
        readiness_score=score.readiness,
        visibility_score=score.visibility,
        penalties=score.penalties,
        weights=weights,
    )
    if score.final != score_math.final_score:
        raise ScoreIntegrityError(
            "Final score mismatch: "
            f"expected {score_math.final_score} from weighted base "
            f"{format_score_value(score_math.weighted_base_score)} and penalties "
            f"{format_score_value(score_math.penalties_total)}, received {score.final}."
        )
    return score_math


def format_score_value(value: float | int | Decimal) -> str:
    quantized = _quantize_display(_decimal(value))
    if quantized == quantized.to_integral():
        return str(int(quantized))
    return format(quantized.normalize(), "f")


def score_final(
    readiness: ReadinessResult,
    visibility: VisibilityResult,
    web_presence: dict[str, Any],
) -> ScoreBreakdown:
    config = load_score_config()
    weights = config["final"]["weights"]
    penalties = _collect_penalties(web_presence, config["penalties"])
    score_math = calculate_final_score_math(
        readiness_score=readiness.score,
        visibility_score=visibility.score,
        penalties=penalties,
        weights=weights,
    )
    return ScoreBreakdown(
        final=score_math.final_score,
        readiness=readiness.score,
        visibility=visibility.score,
        version=str(config["version"]),
        formula=final_score_formula(version=str(config["version"]), weights=weights),
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


def _decimal(value: float | int | Decimal | str) -> Decimal:
    return Decimal(str(value))


def _quantize_display(value: Decimal) -> Decimal:
    return value.quantize(DISPLAY_SCORE_QUANTUM, rounding=ROUND_HALF_EVEN)


def _round_final_score(value: Decimal) -> int:
    return int(value.quantize(FINAL_SCORE_QUANTUM, rounding=ROUND_HALF_EVEN))
