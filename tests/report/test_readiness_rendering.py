import tempfile
from datetime import datetime
from pathlib import Path

from report_generator import ReportGenerator
from src.core.models import (
    AuditRun,
    BusinessEntity,
    BusinessInput,
    CheckDimension,
    ReadinessCheck,
    ReadinessResult,
    VisibilityResult,
)
from src.scoring.final import score_final


def test_report_generator_renders_readiness_unknown_and_unavailable_states_explicitly():
    readiness = ReadinessResult(
        score=50,
        dimensions={
            "listing_presence": CheckDimension(
                score=50,
                label="Listing Presence",
                description="Whether the business can be verified through core listings and local entity facts.",
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
    visibility = VisibilityResult(
        score=71.0,
        overall_mention_rate=50.0,
        per_llm={},
        per_cluster={},
        top_competitors={},
        attributes_cited=[],
        prompt_results=[],
    )
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
        score=score_final(readiness=readiness, visibility=visibility, web_presence={"google_business_found": None}),
        readiness=readiness,
        visibility=visibility,
        recommendations=[],
        web_presence={"google_business_found": None},
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = ReportGenerator(audit_run, Path(tmpdir)).save_html()
        html = html_path.read_text()

    assert "Readiness Verification Detail" in html
    assert "SOURCE UNAVAILABLE" in html
    assert "UNVERIFIED" in html
    assert "Directory sources were unavailable in this run" in html
    assert "FAIL" not in html
