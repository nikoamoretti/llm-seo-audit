"""Tests that the canonical audit entity name equals the submitted input name."""

from __future__ import annotations

import pytest

from src.core.audit_builder import _build_entity
from src.entity.extractors import ExtractedPageFacts, extract_page_facts
from src.entity.reconciler import reconcile_business_entity
from src.crawl.models import CrawlPage


class TestCanonicalEntityNameFromInput:
    """The displayed business name must always be the user-submitted name."""

    def test_submitted_name_used_even_when_extracted_differs(self):
        """Reconciler uses the submitted name, not the extracted name."""
        facts = ExtractedPageFacts(
            url="https://example.com",
            page_type="homepage",
            business_name="Cloudflare Challenge Page",
        )
        entity = reconcile_business_entity(
            [facts],
            business_name="Joe's Plumbing",
            city="Austin, TX",
        )
        assert entity.business_name == "Joe's Plumbing"

    def test_submitted_name_wins_over_extracted_garbage(self):
        """Even with garbage extracted names, the submitted name is canonical."""
        facts = [
            ExtractedPageFacts(
                url="https://example.com",
                page_type="homepage",
                business_name="Attention Required! | Cloudflare",
            ),
            ExtractedPageFacts(
                url="https://example.com/about",
                page_type="about",
                business_name="Access Denied",
            ),
        ]
        entity = reconcile_business_entity(
            facts,
            business_name="Acme Widgets Inc",
            city="Denver, CO",
        )
        assert entity.business_name == "Acme Widgets Inc"

    def test_extracted_name_used_as_fallback_when_no_input(self):
        """If no submitted name, the extracted name can be used as fallback."""
        facts = ExtractedPageFacts(
            url="https://example.com",
            page_type="homepage",
            business_name="Real Business Name",
        )
        entity = reconcile_business_entity(
            [facts],
            business_name="",
            city="Portland, OR",
        )
        assert entity.business_name == "Real Business Name"


class TestBlockedPageCannotReplaceEntityName:
    """A blocked/interstitial page cannot overwrite the business name."""

    def test_blocked_page_skipped_in_extraction(self):
        """extract_page_facts returns empty facts for blocked pages."""
        page = CrawlPage(
            url="https://example.com",
            final_url="https://example.com",
            page_type="homepage",
            status_code=200,
            html='<html><head><title>Just a moment...</title></head><body>cf-chl</body></html>',
            source="homepage",
            blocked=True,
        )
        facts = extract_page_facts(page)
        assert facts.business_name is None
        assert facts.word_count == 0

    def test_audit_builder_uses_submitted_name(self):
        """_build_entity always uses the submitted business_name."""
        entity = _build_entity(
            business_name="My Real Business",
            industry="plumbing",
            city="Seattle, WA",
            website_url="https://example.com",
            phone=None,
            web_presence={
                "extracted_entity": {
                    "business_name": "Attention Required! | Cloudflare",
                    "industry": "plumbing",
                    "city": "Seattle, WA",
                },
            },
        )
        assert entity.business_name == "My Real Business"

    def test_audit_builder_with_empty_extraction(self):
        """_build_entity works when extracted_entity is empty."""
        entity = _build_entity(
            business_name="My Real Business",
            industry="plumbing",
            city="Seattle, WA",
            website_url="https://example.com",
            phone=None,
            web_presence={"extracted_entity": {}},
        )
        assert entity.business_name == "My Real Business"
