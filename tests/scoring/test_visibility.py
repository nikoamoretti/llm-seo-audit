from src.core.models import PromptResult
from src.scoring.visibility import score_visibility


def test_visibility_scores_mentions_recommendations_and_official_citations():
    prompt_results = [
        PromptResult(
            provider="openai",
            query="Laveta Coffee Echo Park",
            cluster="branded",
            mentioned=True,
            recommended=True,
            cited=True,
            cited_official_domain=True,
            visibility_score=75,
        ),
        PromptResult(
            provider="openai",
            query="Best coffee shop in Echo Park",
            cluster="discovery",
            mentioned=True,
            recommended=True,
            cited=True,
            cited_official_domain=True,
            competitors=["Woodcat Coffee"],
            visibility_score=82,
        ),
        PromptResult(
            provider="anthropic",
            query="Coffee shop with good espresso in Echo Park",
            cluster="symptom_problem",
            mentioned=True,
            recommended=True,
            cited=True,
            cited_official_domain=True,
            visibility_score=80,
        ),
        PromptResult(
            provider="perplexity",
            query="Most trusted coffee shop in Echo Park",
            cluster="trust",
            mentioned=True,
            recommended=False,
            cited=True,
            cited_official_domain=False,
            cited_third_party_domain=True,
            competitors=["Woodcat Coffee", "Stereoscope Coffee"],
            visibility_score=68,
        ),
    ]

    visibility = score_visibility(prompt_results)

    assert visibility.score >= 70
    assert visibility.dimensions["official_citation_share"].score >= 70
    assert visibility.dimensions["discovery_strength"].metrics["discovery_prompt_count"] == 3
    assert visibility.per_llm["openai"].visibility_score > 0
    assert visibility.per_cluster["discovery"].avg_score > 0


def test_visibility_penalizes_competitor_heavy_discovery_results():
    prompt_results = [
        PromptResult(
            provider="openai",
            query="Best plumber in Austin",
            cluster="discovery",
            mentioned=False,
            recommended=False,
            cited=False,
            competitors=["A-Team Plumbing", "Capital Flow Plumbing", "Austin Rooter"],
            visibility_score=5,
        ),
        PromptResult(
            provider="openai",
            query="Emergency plumber in Austin",
            cluster="urgency",
            mentioned=False,
            recommended=False,
            cited=False,
            competitors=["A-Team Plumbing", "Austin Rooter"],
            visibility_score=0,
        ),
        PromptResult(
            provider="anthropic",
            query="Acme Plumbing Austin",
            cluster="branded",
            mentioned=True,
            recommended=False,
            cited=False,
            visibility_score=25,
        ),
    ]

    visibility = score_visibility(prompt_results)

    assert visibility.score < 40
    assert visibility.dimensions["competitor_gap"].score < 50
    assert visibility.dimensions["discovery_strength"].score < visibility.dimensions["mention_rate"].score
