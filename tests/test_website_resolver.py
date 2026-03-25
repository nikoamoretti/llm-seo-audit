"""Tests for deterministic website resolution."""

import pytest
from unittest.mock import patch, MagicMock, call

from src.discovery.website_resolver import (
    resolve_website,
    WebsiteResolution,
    _fuzzy_title_match,
    _extract_title,
    _extract_ddg_urls,
)


class TestUserProvidedURL:
    def test_valid_user_url(self):
        """User-provided URL that's reachable wins."""
        with patch("src.discovery.website_resolver.requests") as mock_req:
            resp = MagicMock()
            resp.status_code = 200
            resp.url = "https://example.com"
            resp.close = MagicMock()
            mock_req.get.return_value = resp
            result = resolve_website(business_name="Test", user_url="https://example.com")
            assert result.status == "user_provided"
            assert result.url == "https://example.com"
            assert result.confidence == 1.0
            assert result.source == "user_input"

    def test_valid_user_url_redirect(self):
        """User-provided URL that redirects uses the final URL."""
        with patch("src.discovery.website_resolver.requests") as mock_req:
            resp = MagicMock()
            resp.status_code = 200
            resp.url = "https://www.example.com/"
            resp.close = MagicMock()
            mock_req.get.return_value = resp
            result = resolve_website(business_name="Test", user_url="https://example.com")
            assert result.status == "user_provided"
            assert result.url == "https://www.example.com/"

    def test_invalid_user_url_connection_error(self):
        """User-provided URL that fails to connect returns invalid_user_url."""
        with patch("src.discovery.website_resolver.requests") as mock_req:
            mock_req.get.side_effect = Exception("Connection refused")
            result = resolve_website(business_name="Test", user_url="https://broken.example.com")
            assert result.status == "invalid_user_url"
            assert result.url is None
            assert result.confidence == 0.0

    def test_invalid_user_url_4xx(self):
        """User-provided URL that returns 404 is marked invalid."""
        with patch("src.discovery.website_resolver.requests") as mock_req:
            resp = MagicMock()
            resp.status_code = 404
            resp.url = "https://example.com/gone"
            resp.close = MagicMock()
            mock_req.get.return_value = resp
            result = resolve_website(business_name="Test", user_url="https://example.com/gone")
            assert result.status == "invalid_user_url"
            assert result.url is None


class TestNoWebsiteIdentified:
    def test_no_strategies_find_anything(self):
        """When nothing works, return no_website_identified."""
        with patch("src.discovery.website_resolver.requests") as mock_req:
            mock_req.get.side_effect = Exception("fail")
            mock_req.post.side_effect = Exception("fail")
            result = resolve_website(business_name="xyznonexistent12345")
            assert result.status == "no_website_identified"
            assert result.url is None
            assert result.confidence == 0.0
            assert result.source == "none"


class TestGooglePlaces:
    def test_google_places_finds_website(self):
        """Google Places returns a websiteUri that is reachable."""
        with patch("src.discovery.website_resolver.requests") as mock_req, \
             patch.dict("os.environ", {"GOOGLE_PLACES_API_KEY": "test-key"}):
            # Places API returns websiteUri
            places_resp = MagicMock()
            places_resp.status_code = 200
            places_resp.json.return_value = {
                "places": [
                    {
                        "displayName": {"text": "Acme Corp"},
                        "websiteUri": "https://acme.com",
                    }
                ]
            }
            # Validation GET returns 200
            validation_resp = MagicMock()
            validation_resp.status_code = 200
            validation_resp.url = "https://acme.com"
            validation_resp.close = MagicMock()

            mock_req.post.return_value = places_resp
            mock_req.get.return_value = validation_resp

            result = resolve_website(business_name="Acme Corp")
            assert result.status == "verified_candidate"
            assert result.source == "google_places"
            assert result.confidence == 0.9
            assert result.url == "https://acme.com"

    def test_google_places_no_key(self):
        """Without GOOGLE_PLACES_API_KEY, skips to next strategy."""
        with patch("src.discovery.website_resolver.requests") as mock_req, \
             patch.dict("os.environ", {}, clear=True):
            # No Places key -> falls through to DuckDuckGo and heuristic
            mock_req.get.side_effect = Exception("fail")
            result = resolve_website(business_name="xyznotreal")
            assert result.status == "no_website_identified"


class TestDuckDuckGo:
    def test_duckduckgo_finds_matching_site(self):
        """DDG returns a URL whose title matches the business name.
        Note: heuristic runs before DDG in the priority chain, but this test
        uses a name where heuristic won't match (multi-word with spaces)."""
        with patch("src.discovery.website_resolver.requests") as mock_req, \
             patch.dict("os.environ", {}, clear=True):
            # DDG search results HTML — use "Zenith Analytics Group" so heuristic
            # tries zenithanalyticsgroup.com which won't exist
            ddg_resp = MagicMock()
            ddg_resp.status_code = 200
            ddg_resp.text = (
                '<a class="result__a" href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fzenith-analytics.com&amp;rut=abc">'
                "Zenith Analytics Group</a>"
            )

            # Heuristic tries zenithanalyticsgroup.com — fails
            heuristic_fail = MagicMock()
            heuristic_fail.status_code = 404

            # The validation fetch for zenith-analytics.com — succeeds
            validation_resp = MagicMock()
            validation_resp.status_code = 200
            validation_resp.url = "https://zenith-analytics.com"
            validation_resp.text = "<html><head><title>Zenith Analytics Group</title></head></html>"

            def side_effect_get(url, **kwargs):
                if "duckduckgo" in url:
                    return ddg_resp
                if "zenithanalyticsgroup.com" in url:
                    return heuristic_fail
                return validation_resp

            mock_req.get.side_effect = side_effect_get

            result = resolve_website(business_name="Zenith Analytics Group")
            assert result.status == "verified_candidate"
            assert result.source == "duckduckgo"

    def test_duckduckgo_skips_social_sites(self):
        """DDG results that are social/directory sites are skipped."""
        with patch("src.discovery.website_resolver.requests") as mock_req, \
             patch.dict("os.environ", {}, clear=True):
            ddg_resp = MagicMock()
            ddg_resp.status_code = 200
            ddg_resp.text = (
                '<a href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.facebook.com%2Facme">'
                '<a href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.yelp.com%2Fbiz%2Facme">'
                '<a href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.linkedin.com%2Fcompany%2Facme">'
            )

            def side_effect_get(url, **kwargs):
                if "duckduckgo" in url:
                    return ddg_resp
                raise Exception("should not validate social URLs")

            mock_req.get.side_effect = side_effect_get

            # Falls through to heuristic, which also fails
            result = resolve_website(business_name="xyznotreal12345")
            assert result.status == "no_website_identified"


class TestHeuristicDiscovery:
    def test_heuristic_finds_site(self):
        """Heuristic {name}.com that's reachable and title-matches."""
        with patch("src.discovery.website_resolver.requests") as mock_req, \
             patch.dict("os.environ", {}, clear=True):
            # DDG fails
            ddg_resp = MagicMock()
            ddg_resp.status_code = 200
            ddg_resp.text = ""  # No results

            resp = MagicMock()
            resp.status_code = 200
            resp.url = "https://acme.com"
            resp.text = "<html><head><title>Acme Corp</title></head></html>"

            def side_effect_get(url, **kwargs):
                if "duckduckgo" in url:
                    return ddg_resp
                return resp

            mock_req.get.side_effect = side_effect_get

            result = resolve_website(business_name="Acme")
            assert result.status == "verified_candidate"
            assert result.source == "heuristic"
            assert result.confidence == 0.7
            assert result.url == "https://acme.com"

    def test_heuristic_title_mismatch_rejects(self):
        """Heuristic URL that doesn't title-match is rejected."""
        with patch("src.discovery.website_resolver.requests") as mock_req, \
             patch.dict("os.environ", {}, clear=True):
            ddg_resp = MagicMock()
            ddg_resp.status_code = 200
            ddg_resp.text = ""

            resp = MagicMock()
            resp.status_code = 200
            resp.url = "https://acme.com"
            resp.text = "<html><head><title>Completely Different Company</title></head></html>"

            def side_effect_get(url, **kwargs):
                if "duckduckgo" in url:
                    return ddg_resp
                return resp

            mock_req.get.side_effect = side_effect_get

            result = resolve_website(business_name="Acme")
            # "acme" (4 chars, significant) is NOT in "Completely Different Company"
            assert result.status == "no_website_identified"

    def test_heuristic_short_name_skipped(self):
        """Business names that produce slugs < 3 chars skip heuristic."""
        with patch("src.discovery.website_resolver.requests") as mock_req, \
             patch.dict("os.environ", {}, clear=True):
            mock_req.get.side_effect = Exception("fail")
            result = resolve_website(business_name="AB")
            assert result.status == "no_website_identified"


class TestFuzzyTitleMatch:
    def test_exact_match(self):
        assert _fuzzy_title_match("Acme Corp - Home", "Acme Corp") is True

    def test_partial_word_match(self):
        assert _fuzzy_title_match("Welcome to Acme", "Acme Corp") is True

    def test_case_insensitive(self):
        assert _fuzzy_title_match("ACME CORP", "acme corp") is True

    def test_no_match(self):
        assert _fuzzy_title_match("Totally Different Site", "Acme Corp") is False

    def test_short_words_ignored(self):
        """Words < 3 chars are not used for matching individually."""
        # "Al" is only 2 chars, but full name check: "al" is in "Albert Einstein Museum"
        assert _fuzzy_title_match("Albert Einstein Museum", "Al") is True

    def test_significant_word_match(self):
        assert _fuzzy_title_match("Best Pizza in Town - Mario's", "Mario's Pizza") is True


class TestExtractTitle:
    def test_basic_title(self):
        assert _extract_title("<html><head><title>Hello World</title></head></html>") == "Hello World"

    def test_no_title(self):
        assert _extract_title("<html><head></head></html>") == ""

    def test_multiline_title(self):
        html = "<html><head><title>\n  My Site\n</title></head></html>"
        assert _extract_title(html) == "My Site"


class TestExtractDDGUrls:
    def test_extracts_uddg_urls(self):
        html = 'uddg=https%3A%2F%2Fexample.com&rut=abc uddg=https%3A%2F%2Fother.com&rut=def'
        urls = _extract_ddg_urls(html)
        assert urls == ["https://example.com", "https://other.com"]

    def test_no_urls(self):
        assert _extract_ddg_urls("no urls here") == []


class TestPriorityOrder:
    def test_user_url_wins_over_all(self):
        """User-provided URL takes priority even if other strategies would work."""
        with patch("src.discovery.website_resolver.requests") as mock_req, \
             patch.dict("os.environ", {"GOOGLE_PLACES_API_KEY": "test-key"}):
            resp = MagicMock()
            resp.status_code = 200
            resp.url = "https://user-site.com"
            resp.close = MagicMock()
            mock_req.get.return_value = resp
            result = resolve_website(
                business_name="Acme",
                user_url="https://user-site.com",
            )
            assert result.source == "user_input"
            assert result.status == "user_provided"
            # Google Places should NOT have been called
            mock_req.post.assert_not_called()


class TestReportCopyDiffers:
    def test_no_website_vs_blocked_copy_differs(self):
        """The report copy for no-website-identified must differ from blocked."""
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

        dim = CheckDimension(
            label="Crawlability",
            description="Whether crawlers can reach the site.",
            score=50,
            weight=0.2,
            state="unavailable",
        )

        def _make_run(resolution_status, website_url=None, website_accessible=None):
            wp = {}
            if website_accessible is not None:
                wp["website_accessible"] = website_accessible
            wp["_resolution_status"] = resolution_status
            wp["_resolution_source"] = "none"
            wp["_resolution_notes"] = "test"
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
                score=ScoreBreakdown(readiness=50, visibility=10.0, final=28, penalties=[]),
                readiness=ReadinessResult(score=50, dimensions={"crawlability": dim}),
                visibility=VisibilityResult(score=10.0, overall_mention_rate=20.0),
                web_presence=wp,
                api_keys_used=["anthropic"],
            )

        # no_website_identified case
        run_no_site = _make_run("no_website_identified")
        resp_no_site = build_audit_ui_response(run_no_site)
        notes_no_site = resp_no_site.summary.data_notes

        # invalid_user_url case
        run_invalid = _make_run("invalid_user_url", website_url="https://broken.com")
        resp_invalid = build_audit_ui_response(run_invalid)
        notes_invalid = resp_invalid.summary.data_notes

        # blocked/inaccessible case (no resolution status, but site was accessible=False)
        run_blocked = _make_run(
            "", website_url="https://example.com", website_accessible=False
        )
        resp_blocked = build_audit_ui_response(run_blocked)
        notes_blocked = resp_blocked.summary.data_notes

        # All three should have different messaging
        no_site_text = " ".join(notes_no_site)
        invalid_text = " ".join(notes_invalid)
        blocked_text = " ".join(notes_blocked)

        assert "No official website was identified" in no_site_text
        assert "provided website URL could not be reached" in invalid_text
        assert "could not be accessed" in blocked_text

        # Make sure they are distinct
        assert no_site_text != invalid_text
        assert no_site_text != blocked_text
        assert invalid_text != blocked_text
