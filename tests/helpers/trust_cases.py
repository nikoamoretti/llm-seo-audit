from __future__ import annotations

from datetime import datetime

from src.core.models import (
    AuditRun,
    BusinessEntity,
    BusinessInput,
    CheckDimension,
    PromptResult,
    ReadinessCheck,
    ReadinessResult,
    VisibilityResult,
)
from src.recommendations.rules import build_recommendations
from src.scoring.final import score_final


FIXED_TIMESTAMP = datetime.fromisoformat("2026-03-17T12:00:00")


def prompt_result(
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


def build_base_audit_run(
    *,
    business_name: str = "Laveta",
    industry: str = "coffee shop",
    city: str = "Echo Park, Los Angeles",
    website_url: str = "https://lavetacoffee.com",
    readiness: ReadinessResult | None = None,
    visibility_score: float = 71.0,
    official_citation_share_score: int = 0,
    top_competitors: dict[str, int] | None = None,
    prompt_results: list[PromptResult] | None = None,
    web_presence: dict | None = None,
) -> AuditRun:
    active_web_presence = web_presence or {}
    active_readiness = readiness or ReadinessResult(
        score=80,
        dimensions={
            "crawlability": CheckDimension(
                label="Crawlability",
                description="Can bots access the site?",
                score=80,
                weight=0.25,
                weighted_score=20.0,
            )
        },
    )
    visibility = VisibilityResult(
        score=visibility_score,
        dimensions={
            "official_citation_share": CheckDimension(
                label="Official Citation Share",
                description="How often engines cite the official domain.",
                score=official_citation_share_score,
                weight=0.15,
                weighted_score=round(official_citation_share_score * 0.15, 2),
                evidence=[f"visibility.official_citation_share={official_citation_share_score}"],
            )
        },
        overall_mention_rate=50.0,
        per_llm={},
        per_cluster={},
        top_competitors=top_competitors or {},
        attributes_cited=[],
        prompt_results=prompt_results or [],
    )
    return AuditRun(
        mode="live",
        timestamp=FIXED_TIMESTAMP,
        input=BusinessInput(
            business_name=business_name,
            industry=industry,
            city=city,
            website_url=website_url,
        ),
        entity=BusinessEntity(
            business_name=business_name,
            industry=industry,
            city=city,
            website_url=website_url,
        ),
        score=score_final(
            readiness=active_readiness,
            visibility=visibility,
            web_presence=active_web_presence,
        ),
        readiness=active_readiness,
        visibility=visibility,
        recommendations=[],
        web_presence=active_web_presence,
    )


def score_mismatch_audit_run() -> AuditRun:
    audit_run = build_base_audit_run()
    return audit_run.model_copy(
        update={
            "score": audit_run.score.model_copy(update={"final": audit_run.score.final + 1}),
        }
    )


def no_citations_audit_run() -> AuditRun:
    audit_run = build_base_audit_run(
        prompt_results=[prompt_result(cited=False)],
        official_citation_share_score=0,
    )
    return audit_run.model_copy(update={"recommendations": build_recommendations(audit_run)})


def competitor_noise_audit_run() -> AuditRun:
    return build_base_audit_run(
        business_name="Acme Plumbing",
        industry="plumber",
        city="Austin, TX",
        website_url="https://acmeplumbing.example",
        visibility_score=84.0,
        top_competitors={
            "Warning: Results may vary": 4,
            "Source: Yelp": 3,
            "A-Team Plumbing LLC": 2,
            "A Team Plumbing": 1,
            "Capital Flow Plumbing": 1,
        },
    )


def unknown_listing_audit_run() -> AuditRun:
    readiness = ReadinessResult(
        score=55,
        dimensions={
            "listing_presence": CheckDimension(
                label="Listing Presence",
                description="Whether the business can be verified through core listings and local entity facts.",
                score=50,
                weight=0.2,
                weighted_score=10.0,
                checks={
                    "Google Business Profile": None,
                    "Yelp": None,
                },
                state="unavailable",
                state_label="UNAVAILABLE",
                state_note="Directory sources were unavailable in this run, so listing evidence is incomplete.",
                check_states={
                    "Google Business Profile": ReadinessCheck(
                        state="unavailable",
                        short_label="UNAVAILABLE",
                        detail="Google Business data could not be verified because the external source was unavailable.",
                    ),
                    "Yelp": ReadinessCheck(
                        state="unknown",
                        short_label="UNVERIFIED",
                        detail="Yelp was not checked in this run.",
                    ),
                },
            )
        },
    )
    return build_base_audit_run(
        readiness=readiness,
        web_presence={"google_business_found": None},
    )
