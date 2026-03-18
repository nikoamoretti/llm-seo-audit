from src.core.models import CheckDimension, ReadinessResult, VisibilityResult
from src.scoring.final import score_final


def test_final_score_applies_configured_penalties():
    readiness = ReadinessResult(
        score=80,
        dimensions={
            "crawlability": CheckDimension(
                label="Crawlability",
                description="Can bots access the site?",
                score=80,
                weight=0.25,
                weighted_score=20,
            )
        },
    )
    visibility = VisibilityResult(
        score=70,
        dimensions={},
        overall_mention_rate=50,
        per_llm={},
        per_cluster={},
        top_competitors={},
        attributes_cited=[],
        prompt_results=[],
    )

    score = score_final(
        readiness=readiness,
        visibility=visibility,
        web_presence={"has_noindex": True, "website_accessible": False},
    )

    assert score.formula.startswith("score_v2")
    assert score.final < 75
    assert any(penalty["key"] == "noindex" for penalty in score.penalties)
    assert any(penalty["key"] == "website_inaccessible" for penalty in score.penalties)
