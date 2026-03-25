"""Tests for the full fetch chain and unavailable-page handling."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from src.crawl.fetcher import PageFetcher
from src.crawl.models import FetchResult, CrawlPage
from src.crawl.remote_browser import BrowserFetchResult
from web_presence import WebPresenceChecker


class TestUnavailableChecksStayUnavailable:
    """Unavailable directory / browser checks remain marked unavailable, not failed."""

    def test_unavailable_site_results_returns_none_checks(self):
        """When a site is fully blocked, boolean checks are None (unavailable)."""
        results = WebPresenceChecker._unavailable_site_results()
        # Should be None (unavailable), not False (verified missing)
        assert results["has_schema_markup"] is None
        assert results["has_faq_schema"] is None
        assert results["has_og_tags"] is None
        assert results["has_meta_description"] is None
        assert results["has_title_tag"] is None
        assert results["ssl_valid"] is None
        assert results["has_canonical"] is None
        assert results["website_accessible"] is False
        assert results["site_blocked"] is True

    def test_unavailable_checks_not_marked_false(self):
        """None signals 'we could not check' vs False which means 'verified missing'."""
        results = WebPresenceChecker._unavailable_site_results()
        for key in [
            "has_schema_markup", "has_faq_schema", "has_local_business_schema",
            "has_og_tags", "has_meta_description", "has_title_tag",
            "has_canonical", "has_hreflang", "has_answer_blocks",
            "has_faq_section", "has_contact_info", "has_hours", "has_address",
            "has_booking_cta", "has_contact_cta", "mobile_friendly_meta",
            "fast_load", "ssl_valid",
        ]:
            assert results[key] is None, f"{key} should be None (unavailable), got {results[key]}"


class TestFullFetchChain:
    """Test the complete fetch chain: direct -> blocked detection -> browserbase -> unavailable."""

    def _make_blocked_response(self, url):
        resp = MagicMock()
        resp.url = url
        resp.status_code = 200
        resp.text = (
            "<html><head><title>Just a moment...</title></head>"
            "<body>checking your browser before accessing</body></html>"
        )
        resp.headers = {"Content-Type": "text/html"}
        return resp

    def _make_good_response(self, url):
        resp = MagicMock()
        resp.url = url
        resp.status_code = 200
        resp.text = "<html><head><title>Real Business</title></head><body><h1>Welcome</h1></body></html>"
        resp.headers = {"Content-Type": "text/html"}
        return resp

    def test_direct_success_skips_browserbase(self):
        """Happy path: direct fetch succeeds, no Browserbase call."""
        session = MagicMock()
        session.get.return_value = self._make_good_response("https://example.com")
        fetcher = PageFetcher(session=session)
        result = fetcher.fetch("https://example.com")
        assert result.ok is True
        assert result.fetch_method == "direct"

    @patch("src.crawl.fetcher.browserbase_configured", return_value=True)
    @patch("src.crawl.fetcher.fetch_via_browserbase")
    def test_blocked_triggers_browserbase_retry(self, mock_bb, mock_configured):
        """Blocked direct -> triggers Browserbase retry."""
        session = MagicMock()
        session.get.return_value = self._make_blocked_response("https://example.com")
        mock_bb.return_value = BrowserFetchResult(
            status="success",
            html="<html><body>Real content</body></html>",
            final_url="https://example.com",
            elapsed_seconds=3.0,
        )

        fetcher = PageFetcher(session=session)
        result = fetcher.fetch("https://example.com")
        assert result.ok is True
        assert result.fetch_method == "browserbase"
        mock_bb.assert_called_once_with("https://example.com")

    @patch("src.crawl.fetcher.browserbase_configured", return_value=True)
    @patch("src.crawl.fetcher.fetch_via_browserbase")
    def test_blocked_browserbase_error_returns_unavailable(self, mock_bb, mock_configured):
        """Blocked direct + Browserbase error -> unavailable."""
        session = MagicMock()
        session.get.return_value = self._make_blocked_response("https://example.com")
        mock_bb.return_value = BrowserFetchResult(
            status="error",
            error="Session timeout",
        )

        fetcher = PageFetcher(session=session)
        result = fetcher.fetch("https://example.com")
        assert result.ok is False
        assert result.fetch_method == "unavailable"
        assert result.blocked is True

    @patch("src.crawl.fetcher.browserbase_configured", return_value=False)
    def test_blocked_no_browserbase_returns_unavailable(self, mock_configured):
        """Blocked direct + no Browserbase config -> unavailable."""
        session = MagicMock()
        session.get.return_value = self._make_blocked_response("https://example.com")

        fetcher = PageFetcher(session=session)
        result = fetcher.fetch("https://example.com")
        assert result.ok is False
        assert result.fetch_method == "unavailable"
        assert result.blocked is True
        # HTML should be cleared so blocked content is never parsed
        assert result.html == ""

    def test_connection_error_stays_as_error(self):
        """A connection error should NOT look like a blocked page."""
        import requests
        session = MagicMock()
        session.get.side_effect = requests.exceptions.ConnectionError("DNS failed")

        fetcher = PageFetcher(session=session)
        result = fetcher.fetch("https://example.com")
        assert result.ok is False
        assert result.fetch_method == "direct"
        assert result.blocked is False
        assert "DNS failed" in result.error
