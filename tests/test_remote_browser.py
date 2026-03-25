"""Tests for the Browserbase remote browser integration and blocked page detection."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from src.crawl.remote_browser import (
    BrowserFetchResult,
    browserbase_configured,
    fetch_via_browserbase,
    is_blocked_page,
)
from src.crawl.fetcher import PageFetcher
from src.crawl.models import FetchResult


# ---------------------------------------------------------------------------
# is_blocked_page detection
# ---------------------------------------------------------------------------

class TestBlockedPageDetection:
    """Verify that blocked page detection correctly identifies various block types."""

    def test_cloudflare_attention_required(self):
        html = "<html><head><title>Attention Required! | Cloudflare</title></head><body>Attention Required</body></html>"
        assert is_blocked_page(html) is True

    def test_cloudflare_blocked_message(self):
        html = "<html><body><p>Sorry, you have been blocked</p><span class='cf-ray'>abc123</span></body></html>"
        assert is_blocked_page(html) is True

    def test_cf_ray_marker(self):
        html = "<html><body>Something with cf-ray identifier in the page</body></html>"
        assert is_blocked_page(html) is True

    def test_cf_chl_marker(self):
        html = "<html><body>Challenge page with cf-chl token</body></html>"
        assert is_blocked_page(html) is True

    def test_turnstile_marker(self):
        html = "<html><body>Please complete the turnstile challenge</body></html>"
        assert is_blocked_page(html) is True

    def test_captcha_marker(self):
        html = "<html><body>Please solve the captcha below</body></html>"
        assert is_blocked_page(html) is True

    def test_verify_not_robot(self):
        html = "<html><body>Please verify that you're not a robot</body></html>"
        assert is_blocked_page(html) is True

    def test_verify_you_are_human(self):
        html = "<html><body>We need to verify you are human before proceeding</body></html>"
        assert is_blocked_page(html) is True

    def test_shopify_password_page(self):
        html = '<html><body>This store is powered by Shopify. <input type="password" id="password"></body></html>'
        assert is_blocked_page(html, final_url="https://example.com/password") is True

    def test_shopify_password_url_with_real_content_not_blocked(self):
        """Shopify /password URL with OG tags and real content should NOT be blocked."""
        html = '<html><head><meta property="og:title" content="My Store"></head><body>Shopify store content</body></html>'
        assert is_blocked_page(html, final_url="https://example.com/password") is False

    def test_shopify_without_password_url(self):
        """Shopify marker alone without /password URL should not trigger."""
        html = "<html><body>Powered by Shopify. Great products here.</body></html>"
        assert is_blocked_page(html, final_url="https://example.com/products") is False

    def test_just_a_moment_title(self):
        html = "<html><head><title>Just a moment...</title></head><body>Checking browser</body></html>"
        assert is_blocked_page(html) is True

    def test_access_denied_title(self):
        html = "<html><head><title>Access Denied</title></head><body>You do not have access.</body></html>"
        assert is_blocked_page(html) is True

    def test_normal_business_page(self):
        html = """<html><head><title>Joe's Plumbing - Best Plumber in Town</title></head>
        <body><h1>Joe's Plumbing</h1><p>We provide quality plumbing services.</p></body></html>"""
        assert is_blocked_page(html) is False

    def test_empty_html(self):
        assert is_blocked_page("") is False
        assert is_blocked_page("   ") is False

    def test_short_html(self):
        assert is_blocked_page("<html></html>") is False

    def test_challenge_meta_tag(self):
        html = '<html><head><meta content="cloudflare-challenge-page"></head><body></body></html>'
        assert is_blocked_page(html) is True


# ---------------------------------------------------------------------------
# browserbase_configured
# ---------------------------------------------------------------------------

class TestBrowserbaseConfigured:
    def test_not_configured_when_no_env(self):
        with patch.dict(os.environ, {}, clear=True):
            assert browserbase_configured() is False

    def test_not_configured_when_only_api_key(self):
        with patch.dict(os.environ, {"BROWSERBASE_API_KEY": "key"}, clear=True):
            assert browserbase_configured() is False

    def test_not_configured_when_only_project_id(self):
        with patch.dict(os.environ, {"BROWSERBASE_PROJECT_ID": "pid"}, clear=True):
            assert browserbase_configured() is False

    def test_configured_when_both_present(self):
        with patch.dict(os.environ, {
            "BROWSERBASE_API_KEY": "key",
            "BROWSERBASE_PROJECT_ID": "pid",
        }, clear=True):
            assert browserbase_configured() is True


# ---------------------------------------------------------------------------
# fetch_via_browserbase returns unavailable immediately when not configured
# ---------------------------------------------------------------------------

class TestFetchViaBrowserbaseUnconfigured:
    def test_returns_unavailable_when_no_env(self):
        with patch.dict(os.environ, {}, clear=True):
            result = fetch_via_browserbase("https://example.com")
            assert result.status == "unavailable"
            assert "not configured" in (result.error or "").lower()


# ---------------------------------------------------------------------------
# Fetcher retry flow: direct blocked -> Browserbase retry
# ---------------------------------------------------------------------------

class TestFetcherRetryFlow:
    """Test the fetcher retry flow: direct fetch blocked -> retry through Browserbase."""

    def _make_blocked_response(self, url):
        """Create a mock requests response that looks blocked."""
        resp = MagicMock()
        resp.url = url
        resp.status_code = 200
        resp.text = "<html><head><title>Attention Required! | Cloudflare</title></head><body>Sorry, you have been blocked</body></html>"
        resp.headers = {"Content-Type": "text/html"}
        return resp

    def _make_ok_response(self, url, html="<html><body>Real page</body></html>"):
        resp = MagicMock()
        resp.url = url
        resp.status_code = 200
        resp.text = html
        resp.headers = {"Content-Type": "text/html"}
        return resp

    def test_direct_ok_returns_direct(self):
        """A normal page goes through without Browserbase."""
        session = MagicMock()
        session.get.return_value = self._make_ok_response("https://example.com")
        fetcher = PageFetcher(session=session)
        result = fetcher.fetch("https://example.com")
        assert result.ok is True
        assert result.fetch_method == "direct"
        assert result.blocked is False

    @patch("src.crawl.fetcher.browserbase_configured", return_value=True)
    @patch("src.crawl.fetcher.fetch_via_browserbase")
    def test_blocked_then_browserbase_success(self, mock_bb_fetch, mock_bb_configured):
        """Blocked direct fetch retries through Browserbase and succeeds."""
        session = MagicMock()
        session.get.return_value = self._make_blocked_response("https://blocked.com")
        mock_bb_fetch.return_value = BrowserFetchResult(
            status="success",
            html="<html><body>Real content via browser</body></html>",
            final_url="https://blocked.com",
            elapsed_seconds=2.5,
        )

        fetcher = PageFetcher(session=session)
        result = fetcher.fetch("https://blocked.com")
        assert result.ok is True
        assert result.fetch_method == "browserbase"
        assert result.blocked is False
        assert "Real content" in result.html

    @patch("src.crawl.fetcher.browserbase_configured", return_value=True)
    @patch("src.crawl.fetcher.fetch_via_browserbase")
    def test_blocked_then_browserbase_also_blocked(self, mock_bb_fetch, mock_bb_configured):
        """Both direct and Browserbase blocked -> unavailable."""
        session = MagicMock()
        session.get.return_value = self._make_blocked_response("https://blocked.com")
        mock_bb_fetch.return_value = BrowserFetchResult(
            status="blocked",
            html="<html><body>Still blocked</body></html>",
            final_url="https://blocked.com",
        )

        fetcher = PageFetcher(session=session)
        result = fetcher.fetch("https://blocked.com")
        assert result.ok is False
        assert result.fetch_method == "unavailable"
        assert result.blocked is True

    @patch("src.crawl.fetcher.browserbase_configured", return_value=False)
    def test_blocked_no_browserbase_config(self, mock_bb_configured):
        """Blocked but Browserbase not configured -> unavailable."""
        session = MagicMock()
        session.get.return_value = self._make_blocked_response("https://blocked.com")

        fetcher = PageFetcher(session=session)
        result = fetcher.fetch("https://blocked.com")
        assert result.ok is False
        assert result.fetch_method == "unavailable"
        assert result.blocked is True
        assert result.html == ""
