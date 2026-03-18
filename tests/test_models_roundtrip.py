from datetime import datetime

from src.core.models import (
    AuditRun,
    BusinessEntity,
    BusinessInput,
    CitationRecord,
    CheckDimension,
    PromptResult,
    Recommendation,
    ReadinessResult,
    ScoreBreakdown,
    VisibilityResult,
)


def test_audit_run_round_trips_through_json():
    audit_run = AuditRun(
        mode="demo",
        timestamp=datetime.fromisoformat("2026-03-17T12:00:00"),
        input=BusinessInput(
            business_name="Laveta",
            industry="coffee shop",
            city="Echo Park, Los Angeles",
            website_url="https://lavetacoffee.com",
            demo=True,
        ),
        entity=BusinessEntity(
            business_name="Laveta",
            industry="coffee shop",
            city="Echo Park, Los Angeles",
            website_url="https://lavetacoffee.com",
        ),
        score=ScoreBreakdown(final=72, readiness=61, visibility=81, formula="0.55 × Visibility + 0.45 × Readiness"),
        readiness=ReadinessResult(
            score=61,
            dimensions={
                "R_local_entity": CheckDimension(
                    score=50,
                    label="Online Listings",
                    description="Can AI find your business on core directories?",
                    checks={"Found on Google Business": False, "Found on Yelp": None},
                )
            },
        ),
        visibility=VisibilityResult(
            score=81,
            overall_mention_rate=50.0,
            prompt_results=[
                PromptResult(
                    provider="openai",
                    query="What are the best coffee shops in Echo Park, Los Angeles?",
                    cluster="head",
                    response="Laveta is a strong option.",
                    raw_text="Laveta is a strong option.",
                    latency_ms=18,
                    metadata={"model": "gpt-5.4"},
                    mentioned=True,
                    recommended=True,
                    cited=False,
                    cited_official_domain=False,
                    cited_third_party_domain=True,
                    position=1,
                    visibility_score=81,
                    citations=[
                        CitationRecord(
                            label="Yelp",
                            url="https://www.yelp.com/biz/laveta-coffee-los-angeles",
                            domain="yelp.com",
                            citation_type="third_party",
                            is_official_domain=False,
                        )
                    ],
                )
            ],
        ),
        recommendations=[
            Recommendation(
                priority="P1",
                category="Online Listings",
                title="Claim your Google Business Profile",
                detail="Google Business data is currently missing from the audit.",
                evidence=["web_presence.google_business_found=False"],
            )
        ],
        web_presence={"google_business_found": False},
        api_keys_used=["openai"],
        queries=["What are the best coffee shops in Echo Park, Los Angeles?"],
    )

    round_tripped = AuditRun.model_validate_json(audit_run.model_dump_json())

    assert round_tripped == audit_run
