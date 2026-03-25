"""Tests for user-facing audit copy when website is inaccessible or missing."""

from __future__ import annotations

from src.core.models import (
    AuditRun,
    BusinessEntity,
    BusinessInput,
    ReadinessResult,
    ScoreBreakdown,
    VisibilityResult,
    CheckDimension,
)
from src.presentation import build_audit_ui_response


def _make_audit_run(
    *,
    website_url: str | None = None,
    website_accessible: bool | None = None,
    readiness_state: str = "unavailable",
    resolution_status: str = "",
) -> AuditRun:
    """Build a minimal AuditRun for copy testing."""
    dim = CheckDimension(
        label="Crawlability",
        description="Whether crawlers can reach the site.",
        score=50,
        weight=0.2,
        state=readiness_state,
    )
    web_presence: dict = {}
    if website_accessible is not None:
        web_presence["website_accessible"] = website_accessible
    if resolution_status:
        web_presence["_resolution_status"] = resolution_status
        web_presence["_resolution_source"] = "test"
        web_presence["_resolution_notes"] = "test note"

    return AuditRun(
        mode="live",
        timestamp="2026-01-01T00:00:00",
        input=BusinessInput(
            business_name="Test Biz",
            industry="consulting",
            city="Austin, TX",
            website_url=website_url,
        ),
        entity=BusinessEntity(
            business_name="Test Biz",
            industry="consulting",
            city="Austin, TX",
            website_url=website_url,
        ),
        score=ScoreBreakdown(
            readiness=50,
            visibility=10.0,
            final=28,
            penalties=[],
        ),
        readiness=ReadinessResult(
            score=50,
            dimensions={"crawlability": dim},
        ),
        visibility=VisibilityResult(
            score=10.0,
            overall_mention_rate=20.0,
        ),
        web_presence=web_presence,
        api_keys_used=["anthropic"],
    )


class TestInaccessibleWebsiteCopy:
    """When website was discovered/provided but could not be accessed."""

    def test_inaccessible_site_note(self):
        audit = _make_audit_run(
            website_url="https://example.com",
            website_accessible=False,
        )
        resp = build_audit_ui_response(audit)
        notes = resp.summary.data_notes
        assert any("could not be accessed" in n for n in notes), notes
        assert any("unavailable rather than estimated" in n for n in notes), notes

    def test_inaccessible_site_none_value(self):
        """website_accessible=None also triggers the inaccessible message."""
        audit = _make_audit_run(
            website_url="https://example.com",
            website_accessible=None,
        )
        resp = build_audit_ui_response(audit)
        notes = resp.summary.data_notes
        assert any("could not be accessed" in n for n in notes), notes

    def test_no_duplicate_readiness_note(self):
        """When site is inaccessible, don't also show the generic readiness note."""
        audit = _make_audit_run(
            website_url="https://example.com",
            website_accessible=False,
        )
        resp = build_audit_ui_response(audit)
        notes = resp.summary.data_notes
        generic = [n for n in notes if "Some readiness signals were unavailable" in n]
        assert len(generic) == 0, f"Generic note should not appear: {notes}"


class TestNoWebsiteCopy:
    """When no website URL was available at all."""

    def test_no_website_note(self):
        audit = _make_audit_run(website_url=None)
        resp = build_audit_ui_response(audit)
        notes = resp.summary.data_notes
        assert any("No website was available" in n for n in notes), notes
        assert any("not included" in n for n in notes), notes

    def test_no_website_still_has_visibility(self):
        """Audit should still present visibility data even without a website."""
        audit = _make_audit_run(website_url=None)
        resp = build_audit_ui_response(audit)
        assert resp.score_explanation.visibility_score == 10.0
        assert resp.score_explanation.final_score == 28


class TestAccessibleWebsiteCopy:
    """When the website is accessible, no partial-data messages should appear."""

    def test_accessible_site_no_inaccessible_note(self):
        audit = _make_audit_run(
            website_url="https://example.com",
            website_accessible=True,
            readiness_state="pass",
        )
        resp = build_audit_ui_response(audit)
        notes = resp.summary.data_notes
        assert not any("could not be accessed" in n for n in notes), notes
        assert not any("No website was available" in n for n in notes), notes


class TestResolutionStatusCopy:
    """Tests for resolution-status-based data notes."""

    def test_no_website_identified_note(self):
        audit = _make_audit_run(
            website_url=None,
            resolution_status="no_website_identified",
        )
        resp = build_audit_ui_response(audit)
        notes = resp.summary.data_notes
        assert any("No official website could be identified" in n for n in notes), notes

    def test_invalid_user_url_note(self):
        audit = _make_audit_run(
            website_url="https://broken.com",
            resolution_status="invalid_user_url",
        )
        resp = build_audit_ui_response(audit)
        notes = resp.summary.data_notes
        assert any("provided website URL could not be reached" in n for n in notes), notes

    def test_no_website_identified_is_different_from_generic_no_website(self):
        """Resolution-based 'no website identified' differs from the generic fallback."""
        audit_resolution = _make_audit_run(
            website_url=None,
            resolution_status="no_website_identified",
        )
        audit_generic = _make_audit_run(website_url=None)
        resp_resolution = build_audit_ui_response(audit_resolution)
        resp_generic = build_audit_ui_response(audit_generic)
        notes_resolution = " ".join(resp_resolution.summary.data_notes)
        notes_generic = " ".join(resp_generic.summary.data_notes)
        # Resolution version uses "No official website could be identified"
        assert "No official website could be identified" in notes_resolution
        # Generic uses "No website was available"
        assert "No website was available" in notes_generic
        assert notes_resolution != notes_generic

    def test_invalid_user_url_is_different_from_site_blocked(self):
        """'invalid_user_url' differs from inaccessible-but-known-site."""
        audit_invalid = _make_audit_run(
            website_url="https://broken.com",
            resolution_status="invalid_user_url",
        )
        audit_blocked = _make_audit_run(
            website_url="https://example.com",
            website_accessible=False,
        )
        resp_invalid = build_audit_ui_response(audit_invalid)
        resp_blocked = build_audit_ui_response(audit_blocked)
        notes_invalid = " ".join(resp_invalid.summary.data_notes)
        notes_blocked = " ".join(resp_blocked.summary.data_notes)
        assert "provided website URL could not be reached" in notes_invalid
        assert "could not be accessed" in notes_blocked
        assert notes_invalid != notes_blocked
