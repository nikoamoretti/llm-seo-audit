from src.core.models import CheckDimension, ReadinessResult, VisibilityResult
from src.scoring.final import score_final


def _readiness(score: int) -> ReadinessResult:
    return ReadinessResult(
        score=score,
        dimensions={
            "crawlability": CheckDimension(
                label="Crawlability",
                description="Can bots access the site?",
                score=score,
                weight=0.25,
                weighted_score=round(score * 0.25, 2),
            )
        },
    )


def _visibility(score: float) -> VisibilityResult:
    return VisibilityResult(
        score=score,
        dimensions={},
        overall_mention_rate=50,
        per_llm={},
        per_cluster={},
        top_competitors={},
        attributes_cited=[],
        prompt_results=[],
    )


def test_final_score_uses_weighted_base_when_no_penalties_apply():
    score = score_final(
        readiness=_readiness(80),
        visibility=_visibility(71.0),
        web_presence={},
    )

    assert score.formula == "score_v2 final = round((0.45 * readiness) + (0.55 * visibility) - penalties)"
    assert score.final == 75
    assert score.penalties == []


def test_final_score_applies_one_configured_penalty():
    score = score_final(
        readiness=_readiness(80),
        visibility=_visibility(71.0),
        web_presence={"has_noindex": True},
    )

    assert score.final == 55
    assert [penalty["key"] for penalty in score.penalties] == ["noindex"]


def test_final_score_applies_multiple_configured_penalties():
    score = score_final(
        readiness=_readiness(80),
        visibility=_visibility(71.0),
        web_presence={"has_noindex": True, "website_accessible": False},
    )

    assert score.final == 35
    assert [penalty["key"] for penalty in score.penalties] == [
        "noindex",
        "website_inaccessible",
    ]


def test_final_score_rounds_half_point_adjusted_scores_consistently():
    score = score_final(
        readiness=_readiness(3),
        visibility=_visibility(53.0),
        web_presence={},
    )

    assert score.final == 30
