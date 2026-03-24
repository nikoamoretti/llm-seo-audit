import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from report_generator import ReportGenerator
from src.core.models import (
    AuditRun,
    BusinessEntity,
    BusinessInput,
    CheckDimension,
    ReadinessResult,
    VisibilityResult,
)
from src.scoring.final import ScoreIntegrityError, score_final


def _build_audit_run(*, web_presence: dict) -> AuditRun:
    readiness = ReadinessResult(
        score=80,
        dimensions={
            "crawlability": CheckDimension(
                score=80,
                label="Crawlability",
                description="Can bots access the site?",
                weight=0.25,
                weighted_score=20.0,
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
    return AuditRun(
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
        score=score_final(readiness=readiness, visibility=visibility, web_presence=web_presence),
        readiness=readiness,
        visibility=visibility,
        recommendations=[],
        web_presence=web_presence,
    )


def test_report_generator_renders_score_math_and_penalties():
    audit_run = _build_audit_run(web_presence={"has_noindex": True})

    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = ReportGenerator(audit_run, Path(tmpdir)).save_html()
        html = html_path.read_text()

    assert "Score Explanation" in html
    assert "Weighted Base Score" in html
    assert "Penalty Points" in html
    assert "Noindex directive present" in html
    assert "score_v2 final = round((0.45 * readiness) + (0.55 * visibility) - penalties)" in html
    assert "0.55 &times; V" not in html
    assert "0.55 × Visibility + 0.45 × Readiness" not in html


def test_report_generator_fails_fast_when_score_display_does_not_reconcile():
    audit_run = _build_audit_run(web_presence={})
    inconsistent_audit_run = audit_run.model_copy(
        update={
            "score": audit_run.score.model_copy(update={"final": audit_run.score.final + 1}),
        }
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(ScoreIntegrityError):
            ReportGenerator(inconsistent_audit_run, Path(tmpdir)).save_html()
