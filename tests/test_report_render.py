import tempfile
from datetime import datetime
from pathlib import Path

from report_generator import ReportGenerator
from src.core.models import (
    AuditRun,
    BusinessEntity,
    BusinessInput,
    CheckDimension,
    Recommendation,
    ReadinessResult,
    ScoreBreakdown,
    VisibilityResult,
)


def test_report_generator_renders_from_canonical_audit_run():
    audit_run = AuditRun(
        mode="live",
        timestamp=datetime.fromisoformat("2026-03-17T12:00:00"),
        input=BusinessInput(
            business_name="Laveta",
            industry="coffee shop",
            city="Echo Park, Los Angeles",
            website_url="https://lavetacoffee.com",
        ),
        entity=BusinessEntity(
            business_name="Laveta",
            industry="coffee shop",
            city="Echo Park, Los Angeles",
            website_url="https://lavetacoffee.com",
        ),
        score=ScoreBreakdown(final=78, readiness=65, visibility=84, formula="0.55 × Visibility + 0.45 × Readiness"),
        readiness=ReadinessResult(
            score=65,
            dimensions={
                "R_local_entity": CheckDimension(
                    score=50,
                    label="Online Listings",
                    description="Can AI find your business on core directories?",
                    checks={"Found on Google Business": None, "Found on Yelp": True},
                )
            },
        ),
        visibility=VisibilityResult(
            score=84,
            overall_mention_rate=50.0,
            per_llm={},
            per_cluster={},
            top_competitors={"Woodcat Coffee": 2},
            attributes_cited=["great coffee"],
            prompt_results=[],
        ),
        recommendations=[
            Recommendation(
                priority="P1",
                category="Online Listings",
                title="Claim your Google Business Profile",
                detail="Google Business data is currently missing from the audit.",
                why_it_matters="Local assistants need an observed listing source before they can confidently recommend the business.",
                evidence=["web_presence.google_business_found=False"],
                impacted_components=["listing_presence", "visibility.official_citation_share"],
                implementation_hint="Claim the profile and fill in hours, categories, and website details.",
            )
        ],
        web_presence={"google_business_found": None, "yelp_found": True},
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = ReportGenerator(audit_run, Path(tmpdir)).save_html()
        html = html_path.read_text()

    assert "78/100" in html
    assert "Executive Summary" in html
    assert "Wins and Losses by Prompt Cluster" in html
    assert "Official Site Citation Share" in html
    assert "Third-Party Authority Picture" in html
    assert "Competitor Gap" in html
    assert "Top 10 Fixes" in html
    assert "Implementation Checklist" in html
    assert "Laveta" in html
    assert "Why it matters" in html
    assert "Implementation hint" in html
    assert "scores.overall_score" not in html
