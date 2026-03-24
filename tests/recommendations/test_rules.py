from datetime import datetime

from src.core.models import (
    AuditRun,
    BusinessEntity,
    BusinessInput,
    CheckDimension,
    PromptResult,
    ReadinessResult,
    ScoreBreakdown,
    VisibilityResult,
)
from src.recommendations.rules import build_recommendations


def _prompt_result(
    *,
    cited: bool,
    cited_official_domain: bool = False,
    cited_third_party_domain: bool = False,
    metadata: dict | None = None,
) -> PromptResult:
    return PromptResult(
        provider="openai",
        query="Best coffee shops in Echo Park",
        cluster="discovery",
        mentioned=True,
        recommended=True,
        cited=cited,
        cited_official_domain=cited_official_domain,
        cited_third_party_domain=cited_third_party_domain,
        metadata=metadata or {},
    )


def _audit_run(
    *,
    official_share_score: int,
    prompt_results: list[PromptResult],
) -> AuditRun:
    return AuditRun(
        mode="live",
        timestamp=datetime.fromisoformat("2026-03-17T12:00:00"),
        input=BusinessInput(
            business_name="Laveta Coffee",
            industry="coffee shop",
            city="Echo Park, Los Angeles",
            website_url="https://lavetacoffee.com",
        ),
        entity=BusinessEntity(
            business_name="Laveta Coffee",
            industry="coffee shop",
            city="Echo Park, Los Angeles",
            website_url="https://lavetacoffee.com",
        ),
        score=ScoreBreakdown(
            final=60,
            readiness=80,
            visibility=44,
            formula="score_v2 final = round((0.45 * readiness) + (0.55 * visibility) - penalties)",
        ),
        readiness=ReadinessResult(score=80, dimensions={}),
        visibility=VisibilityResult(
            score=44,
            dimensions={
                "official_citation_share": CheckDimension(
                    label="Official Citation Share",
                    description="How often engines cite the official domain.",
                    score=official_share_score,
                    weight=0.15,
                    weighted_score=round(official_share_score * 0.15, 2),
                    evidence=[f"visibility.official_citation_share={official_share_score}"],
                ),
                "discovery_strength": CheckDimension(
                    label="Discovery Strength",
                    description="How often the business appears in non-branded prompts.",
                    score=80,
                    weight=0.1,
                    weighted_score=8,
                    evidence=["visibility.discovery_mention_rate=0.8"],
                ),
            },
            overall_mention_rate=75,
            per_llm={},
            per_cluster={},
            top_competitors={},
            attributes_cited=[],
            prompt_results=prompt_results,
        ),
        web_presence={},
    )


def _citation_recommendation(audit_run: AuditRun):
    recommendations = build_recommendations(audit_run)
    return next(
        (
            recommendation
            for recommendation in recommendations
            if recommendation.category == "On-Site Evidence"
        ),
        None,
    )


def test_recommendations_do_not_claim_the_business_is_being_cited_when_no_citations_exist():
    recommendation = _citation_recommendation(
        _audit_run(
            official_share_score=0,
            prompt_results=[_prompt_result(cited=False)],
        )
    )

    assert recommendation is not None
    assert recommendation.why_it_matters == (
        "No citations were captured in this run, so the audit cannot yet confirm which sources "
        "answer engines rely on for this business."
    )
    assert "being cited" not in recommendation.why_it_matters
    assert "visibility.citation_evidence_state=no_citations" in recommendation.evidence


def test_recommendations_flag_third_party_only_citations_as_missing_official_support():
    recommendation = _citation_recommendation(
        _audit_run(
            official_share_score=0,
            prompt_results=[_prompt_result(cited=True, cited_third_party_domain=True)],
        )
    )

    assert recommendation is not None
    assert recommendation.why_it_matters == (
        "Third-party sources were cited, but the official site was not, so first-party support is "
        "currently weak."
    )
    assert "visibility.citation_evidence_state=third_party_only" in recommendation.evidence


def test_recommendations_distinguish_mixed_citations_with_weak_official_support():
    recommendation = _citation_recommendation(
        _audit_run(
            official_share_score=25,
            prompt_results=[
                _prompt_result(cited=True, cited_official_domain=True),
                _prompt_result(cited=True, cited_third_party_domain=True),
                _prompt_result(cited=True, cited_third_party_domain=True),
            ],
        )
    )

    assert recommendation is not None
    assert recommendation.why_it_matters == (
        "Both official and third-party sources were cited, but official-domain support is still "
        "weak relative to third-party sources."
    )
    assert "visibility.citation_evidence_state=mixed" in recommendation.evidence


def test_recommendations_skip_missing_official_support_warning_when_official_citations_dominate():
    recommendation = _citation_recommendation(
        _audit_run(
            official_share_score=100,
            prompt_results=[_prompt_result(cited=True, cited_official_domain=True)],
        )
    )

    assert recommendation is None


def test_recommendations_mark_unavailable_citation_evidence_as_inconclusive():
    recommendation = _citation_recommendation(
        _audit_run(
            official_share_score=0,
            prompt_results=[
                _prompt_result(
                    cited=False,
                    metadata={"citation_parser_status": "unavailable"},
                )
            ],
        )
    )

    assert recommendation is not None
    assert recommendation.why_it_matters == (
        "Citation diagnosis is inconclusive because citation evidence was unavailable or incomplete "
        "in this run."
    )
    assert "visibility.citation_evidence_state=unavailable" in recommendation.evidence
