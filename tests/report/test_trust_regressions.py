import tempfile
from pathlib import Path

import pytest

from report_generator import ReportGenerator
from src.presentation.view_model import build_audit_ui_response
from src.scoring.final import ScoreIntegrityError
from tests.helpers.trust_cases import score_mismatch_audit_run, unknown_listing_audit_run


def test_trust_regression_score_mismatch_fails_fast_before_render():
    audit_run = score_mismatch_audit_run()

    with pytest.raises(ScoreIntegrityError):
        build_audit_ui_response(audit_run)

    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(ScoreIntegrityError):
            ReportGenerator(audit_run, Path(tmpdir)).save_html()


def test_trust_regression_unknown_listing_state_stays_incomplete_in_report_copy():
    audit_run = unknown_listing_audit_run()

    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = ReportGenerator(audit_run, Path(tmpdir)).save_html()
        html = html_path.read_text()

    assert "Overall GEO Score" in html
    assert "Overall LLM Visibility Score" not in html
    assert "scores 64/100 on the GEO audit." in html
    assert "Readiness Verification Detail" in html
    assert "SOURCE UNAVAILABLE" in html
    assert "UNAVAILABLE" in html
    assert "UNVERIFIED" in html
    assert "VERIFIED GAP" not in html
    assert "FAIL" not in html
