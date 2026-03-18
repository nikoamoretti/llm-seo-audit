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


def test_recommendations_are_evidence_linked_and_skip_unchecked_directory_claims():
    audit_run = AuditRun(
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
            final=46,
            readiness=58,
            visibility=37,
            formula="score_v2(readiness, visibility) - penalties",
            penalties=[{"key": "noindex", "points": 20}],
        ),
        readiness=ReadinessResult(
            score=58,
            dimensions={
                "listing_presence": CheckDimension(
                    label="Listing Presence",
                    description="Can AI verify core directory listings?",
                    score=45,
                    weight=0.2,
                    weighted_score=9,
                    checks={
                        "Google Business Profile": False,
                        "Yelp": None,
                    },
                    evidence=[
                        "web_presence.google_business_found=False",
                        "web_presence.yelp_found=None",
                    ],
                )
            },
        ),
        visibility=VisibilityResult(
            score=37,
            dimensions={
                "official_citation_share": CheckDimension(
                    label="Official Citation Share",
                    description="How often engines cite the official domain.",
                    score=0,
                    weight=0.15,
                    weighted_score=0,
                    evidence=["visibility.official_citation_share=0.0"],
                ),
                "discovery_strength": CheckDimension(
                    label="Discovery Strength",
                    description="How often the business appears in non-branded prompts.",
                    score=20,
                    weight=0.1,
                    weighted_score=2,
                    evidence=["visibility.discovery_mention_rate=0.25"],
                ),
            },
            overall_mention_rate=25,
            per_llm={},
            per_cluster={},
            top_competitors={"Woodcat Coffee": 4},
            attributes_cited=[],
            prompt_results=[
                PromptResult(
                    provider="openai",
                    query="Best coffee shops in Echo Park",
                    cluster="discovery",
                    mentioned=False,
                    recommended=False,
                    cited=False,
                    competitors=["Woodcat Coffee", "Stereoscope Coffee"],
                )
            ],
        ),
        web_presence={
            "has_noindex": True,
            "google_business_found": False,
            "yelp_found": None,
            "has_schema_markup": False,
        },
    )

    recommendations = build_recommendations(audit_run)

    assert recommendations
    assert all(rec.why_it_matters for rec in recommendations)
    assert all(rec.evidence for rec in recommendations)
    assert all(rec.impacted_components for rec in recommendations)
    assert all(rec.implementation_hint for rec in recommendations)
    assert all("%" not in rec.why_it_matters for rec in recommendations)
    assert not any(rec.title == "You're not on Yelp" for rec in recommendations)
    assert any("web_presence.has_noindex=True" in rec.evidence for rec in recommendations)
