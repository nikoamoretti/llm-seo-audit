"""Remote browser fallback via Browserbase.

Connects to Browserbase's managed Chromium instances over CDP to fetch pages
that block direct HTTP requests (Cloudflare, captchas, Shopify password gates).

Env vars:
    BROWSERBASE_API_KEY      – Browserbase API key
    BROWSERBASE_PROJECT_ID   – Browserbase project ID

If either env var is missing the module returns an unavailable result immediately
so callers never need to guard against import errors.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Literal, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Blocked-page detection
# ---------------------------------------------------------------------------

_BLOCKED_MARKERS_LOWER = [
    "attention required",
    "sorry, you have been blocked",
    "cf-ray",
    "cf-chl",
    "turnstile",
    "captcha",
    "verify that you're not a robot",
    "verify you are human",
    "checking your browser",
    "please wait while we verify",
    "just a moment",
    "enable javascript and cookies",
    "access denied",
    "ray id:",
]

_BLOCKED_META_PATTERN = re.compile(
    r'<meta[^>]+content=["\'][^"\']*challenge[^"\']*["\']', re.IGNORECASE
)


def is_blocked_page(html: str, final_url: str = "") -> bool:
    """Return True when the HTML looks like a WAF block, captcha, or interstitial."""
    if not html or len(html.strip()) < 50:
        return False

    lower = html.lower()

    # Cloudflare / generic WAF markers
    for marker in _BLOCKED_MARKERS_LOWER:
        if marker in lower:
            return True

    # Cloudflare meta challenge
    if _BLOCKED_META_PATTERN.search(html):
        return True

    # Shopify password gate — only if the page is actually a password form,
    # not a real business page that happens to have "shopify" in the source
    if "/password" in (final_url or "") and "shopify" in lower:
        # Check if it's truly a password gate (has password input, no real content)
        has_password_input = 'type="password"' in lower or "id=\"password\"" in lower
        has_real_content = '<meta property="og:' in lower or "<article" in lower
        if has_password_input and not has_real_content:
            return True

    # Obvious login / interstitial that is NOT a real business page
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if title_match:
        title_text = title_match.group(1).strip().lower()
        if title_text in (
            "just a moment...",
            "attention required! | cloudflare",
            "access denied",
            "please wait...",
            "security check",
        ):
            return True

    return False


# ---------------------------------------------------------------------------
# Browserbase fetch result
# ---------------------------------------------------------------------------

BrowserFetchStatus = Literal["success", "blocked", "error", "unavailable"]


@dataclass
class BrowserFetchResult:
    status: BrowserFetchStatus
    html: str = ""
    final_url: str = ""
    error: Optional[str] = None
    elapsed_seconds: Optional[float] = None


# ---------------------------------------------------------------------------
# Configuration check
# ---------------------------------------------------------------------------

def browserbase_configured() -> bool:
    """Return True when both required env vars are present."""
    return bool(
        os.environ.get("BROWSERBASE_API_KEY")
        and os.environ.get("BROWSERBASE_PROJECT_ID")
    )


# ---------------------------------------------------------------------------
# Remote browser fetch
# ---------------------------------------------------------------------------

def fetch_via_browserbase(url: str) -> BrowserFetchResult:
    """Fetch *url* through a Browserbase remote browser session.

    Returns a BrowserFetchResult with status:
      - "success"     – page loaded and is not a block page
      - "blocked"     – page loaded but still shows a WAF/captcha
      - "error"       – something went wrong (details in .error)
      - "unavailable" – Browserbase is not configured
    """
    api_key = os.environ.get("BROWSERBASE_API_KEY", "")
    project_id = os.environ.get("BROWSERBASE_PROJECT_ID", "")

    if not api_key or not project_id:
        return BrowserFetchResult(status="unavailable", error="Browserbase not configured")

    try:
        from browserbase import Browserbase  # type: ignore[import-untyped]
        from playwright.sync_api import sync_playwright  # type: ignore[import-untyped]
    except ImportError as exc:
        logger.error("Browserbase/Playwright SDK not installed: %s", exc)
        return BrowserFetchResult(status="error", error=f"SDK not installed: {exc}")

    session = None
    try:
        bb = Browserbase(api_key=api_key)
        session = bb.sessions.create(project_id=project_id)
        connect_url = session.connect_url
        logger.info("Browserbase session %s created for %s", session.id, url)

        start = time.time()

        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(connect_url)
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else context.new_page()

            page.goto(url, wait_until="networkidle", timeout=30_000)
            final_url = page.url
            html = page.content()
            elapsed = round(time.time() - start, 2)

            browser.close()

        if is_blocked_page(html, final_url):
            logger.warning(
                "Browserbase session %s for %s returned a blocked page",
                session.id,
                url,
            )
            return BrowserFetchResult(
                status="blocked",
                html=html,
                final_url=final_url,
                elapsed_seconds=elapsed,
            )

        return BrowserFetchResult(
            status="success",
            html=html,
            final_url=final_url,
            elapsed_seconds=elapsed,
        )

    except Exception as exc:
        logger.error(
            "Browserbase fetch failed for %s (session=%s): %s",
            url,
            getattr(session, "id", "n/a"),
            exc,
        )
        return BrowserFetchResult(status="error", error=str(exc))
