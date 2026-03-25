"""
Deterministic website-resolution module.

Resolves a business's official website URL through a priority chain:
1. User-provided URL (validate reachable)
2. Google Places API (if GOOGLE_PLACES_API_KEY is set)
3. DuckDuckGo search (filter social/directory sites, title-match)
4. Heuristic guess ({slug}.com)
5. Give up -> no_website_identified
"""

import logging
import os
import re
from dataclasses import dataclass
from typing import Literal, Optional
from urllib.parse import parse_qs, unquote, urlparse

import requests

logger = logging.getLogger(__name__)

ResolutionStatus = Literal[
    "user_provided",
    "verified_candidate",
    "no_website_identified",
    "invalid_user_url",
]


@dataclass
class WebsiteResolution:
    url: Optional[str]
    status: ResolutionStatus
    source: str  # "user_input", "google_places", "duckduckgo", "heuristic", "none"
    confidence: float  # 0.0 to 1.0
    notes: str  # human-readable explanation


_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

_SOCIAL_AND_DIRECTORY_DOMAINS = {
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "linkedin.com",
    "yelp.com",
    "bbb.org",
    "glassdoor.com",
    "indeed.com",
    "tripadvisor.com",
    "yellowpages.com",
    "pinterest.com",
    "tiktok.com",
    "youtube.com",
    "reddit.com",
    "nextdoor.com",
    "angi.com",
    "thumbtack.com",
    "mapquest.com",
    "foursquare.com",
    "manta.com",
    "crunchbase.com",
    "zoominfo.com",
    "trustpilot.com",
    "sitejabber.com",
    "google.com",
    "bing.com",
    "duckduckgo.com",
    "yahoo.com",
    "wikipedia.org",
}


def resolve_website(
    business_name: str,
    city: str = "",
    industry: str = "",
    user_url: Optional[str] = None,
) -> WebsiteResolution:
    """Resolve the official website for a business using a priority chain.

    Args:
        business_name: The business name to search for.
        city: Optional city/location context.
        industry: Optional industry context.
        user_url: Optional user-provided URL to validate first.

    Returns:
        WebsiteResolution with the result.
    """
    logger.info(
        "Resolving website for %r (city=%r, industry=%r, user_url=%r)",
        business_name,
        city,
        industry,
        user_url,
    )

    # Strategy 1: User-provided URL
    if user_url:
        result = _try_user_provided(user_url)
        if result is not None:
            return result

    # Strategy 2: Google Places API
    places_key = os.environ.get("GOOGLE_PLACES_API_KEY", "")
    if places_key:
        result = _try_google_places(business_name, city, places_key)
        if result is not None:
            return result

    # Strategy 3: Heuristic {slug}.com — fast, high confidence when it matches
    result = _try_heuristic(business_name)
    if result is not None:
        return result

    # Strategy 4: DuckDuckGo search — broader but noisier
    result = _try_duckduckgo(business_name, city)
    if result is not None:
        return result

    # Strategy 5: Give up
    logger.info("No website found for %r after all strategies.", business_name)
    return WebsiteResolution(
        url=None,
        status="no_website_identified",
        source="none",
        confidence=0.0,
        notes=f"Could not identify an official website for '{business_name}' "
        "after trying all resolution strategies.",
    )


def _try_user_provided(user_url: str) -> Optional[WebsiteResolution]:
    """Validate a user-provided URL. Returns resolution or None to continue."""
    logger.info("Strategy 1: Validating user-provided URL %r", user_url)
    try:
        resp = requests.get(
            user_url,
            timeout=8,
            allow_redirects=True,
            stream=True,
            headers=_REQUEST_HEADERS,
        )
        resp.close()
        if resp.status_code < 400:
            final_url = resp.url or user_url
            logger.info("User-provided URL %r is reachable (status %d).", user_url, resp.status_code)
            return WebsiteResolution(
                url=final_url,
                status="user_provided",
                source="user_input",
                confidence=1.0,
                notes=f"User-provided URL is reachable (HTTP {resp.status_code}).",
            )
        else:
            logger.warning(
                "User-provided URL %r returned status %d; marking invalid.",
                user_url,
                resp.status_code,
            )
            return WebsiteResolution(
                url=None,
                status="invalid_user_url",
                source="user_input",
                confidence=0.0,
                notes=f"User-provided URL returned HTTP {resp.status_code}.",
            )
    except Exception as exc:
        logger.warning("User-provided URL %r is not reachable: %s", user_url, exc)
        return WebsiteResolution(
            url=None,
            status="invalid_user_url",
            source="user_input",
            confidence=0.0,
            notes=f"User-provided URL could not be reached: {exc}",
        )


def _try_google_places(
    business_name: str, city: str, api_key: str
) -> Optional[WebsiteResolution]:
    """Search Google Places for the business and extract websiteUri."""
    logger.info("Strategy 2: Searching Google Places for %r", business_name)
    query = f"{business_name} {city}".strip()
    try:
        resp = requests.post(
            "https://places.googleapis.com/v1/places:searchText",
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": api_key,
                "X-Goog-FieldMask": "places.displayName,places.websiteUri",
            },
            json={"textQuery": query, "maxResultCount": 3},
            timeout=8,
        )
        if resp.status_code != 200:
            logger.warning(
                "Google Places API returned status %d for %r.",
                resp.status_code,
                query,
            )
            return None

        data = resp.json()
        places = data.get("places", [])
        for place in places:
            website_uri = place.get("websiteUri")
            if not website_uri:
                continue
            logger.info("Google Places candidate: %r", website_uri)
            if _validate_url_reachable(website_uri):
                return WebsiteResolution(
                    url=website_uri,
                    status="verified_candidate",
                    source="google_places",
                    confidence=0.9,
                    notes=f"Found via Google Places API for query '{query}'.",
                )
    except Exception as exc:
        logger.warning("Google Places lookup failed for %r: %s", business_name, exc)
    return None


def _try_duckduckgo(
    business_name: str, city: str
) -> Optional[WebsiteResolution]:
    """Search DuckDuckGo for the business and find a matching URL."""
    query = f'"{business_name}" official site'
    if city:
        query = f'"{business_name}" {city} official site'
    logger.info("Strategy 3: DuckDuckGo search for %r", query)

    try:
        resp = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers=_REQUEST_HEADERS,
            timeout=8,
        )
        if resp.status_code != 200:
            logger.warning("DuckDuckGo returned status %d.", resp.status_code)
            return None

        # Extract URLs from uddg= params in result links
        candidate_urls = _extract_ddg_urls(resp.text)
        logger.info("DuckDuckGo returned %d candidate URLs.", len(candidate_urls))

        name_slug = re.sub(r"[^a-z0-9]", "", business_name.lower())

        # Score and sort candidates: prefer domains that contain the business name
        scored: list[tuple[int, str]] = []
        for url in candidate_urls[:10]:
            parsed = urlparse(url)
            domain = parsed.netloc.lower().lstrip("www.")

            # Skip social media and directory sites
            if any(domain.endswith(blocked) for blocked in _SOCIAL_AND_DIRECTORY_DOMAINS):
                logger.debug("Skipping directory/social URL: %s", url)
                continue

            # Skip obvious news/media domains
            if any(kw in domain for kw in ("news", "blog", "article", "press", "media", "wiki")):
                logger.debug("Skipping news/media URL: %s", url)
                continue

            # Score: domain contains business name slug → much higher priority
            domain_base = domain.split(".")[0]
            score = 2 if name_slug and name_slug in domain_base else 0
            scored.append((score, url))

        # Sort by score descending, then try each
        scored.sort(key=lambda x: x[0], reverse=True)

        for _, url in scored:
            if _validate_url_with_title_match(url, business_name):
                parsed = urlparse(url)
                domain_base = parsed.netloc.lower().lstrip("www.").split(".")[0]
                domain_match = name_slug and name_slug in domain_base
                confidence = 0.85 if domain_match else 0.65
                logger.info("DuckDuckGo match: %r (domain_match=%s)", url, domain_match)
                return WebsiteResolution(
                    url=url,
                    status="verified_candidate",
                    source="duckduckgo",
                    confidence=confidence,
                    notes=f"Found via DuckDuckGo search; page title matches business name.",
                )
    except Exception as exc:
        logger.warning("DuckDuckGo search failed for %r: %s", business_name, exc)
    return None


def _try_heuristic(business_name: str) -> Optional[WebsiteResolution]:
    """Try https://{slug}.com where slug is the lowered, alphanumeric business name."""
    slug = re.sub(r"[^a-z0-9]", "", business_name.lower())
    if not slug or len(slug) < 3:
        return None

    url = f"https://{slug}.com"
    logger.info("Strategy 4: Heuristic check for %r", url)

    if _validate_url_with_title_match(url, business_name):
        logger.info("Heuristic match: %r", url)
        return WebsiteResolution(
            url=url,
            status="verified_candidate",
            source="heuristic",
            confidence=0.7,
            notes=f"Heuristic URL {url} is reachable and page title matches business name.",
        )
    return None


def _validate_url_reachable(url: str) -> bool:
    """Check if a URL is reachable (2xx/3xx status)."""
    try:
        resp = requests.get(
            url,
            timeout=8,
            allow_redirects=True,
            stream=True,
            headers=_REQUEST_HEADERS,
        )
        resp.close()
        reachable = resp.status_code < 400
        logger.debug("URL %r reachable=%s (status %d)", url, reachable, resp.status_code)
        return reachable
    except Exception as exc:
        logger.debug("URL %r not reachable: %s", url, exc)
        return False


def _validate_url_with_title_match(url: str, business_name: str) -> bool:
    """Validate URL is reachable AND page title fuzzy-matches the business name."""
    try:
        resp = requests.get(
            url,
            timeout=8,
            allow_redirects=True,
            headers=_REQUEST_HEADERS,
        )
        if resp.status_code >= 400:
            return False

        title = _extract_title(resp.text)
        if not title:
            return False

        if _fuzzy_title_match(title, business_name):
            return True

        logger.debug(
            "Title mismatch for %r: title=%r, business=%r",
            url,
            title,
            business_name,
        )
        return False
    except Exception as exc:
        logger.debug("Title-match validation failed for %r: %s", url, exc)
        return False


def _extract_title(html: str) -> str:
    """Extract the <title> text from HTML."""
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


def _fuzzy_title_match(title: str, business_name: str) -> bool:
    """Check if any significant word from the business name appears in the title.

    A "significant word" is 3+ characters long. The match is case-insensitive.
    """
    title_lower = title.lower()
    words = business_name.lower().split()
    significant_words = [w for w in words if len(w) >= 3]

    if not significant_words:
        # If all words are short, check full name presence
        return business_name.lower() in title_lower

    return any(word in title_lower for word in significant_words)


def _extract_ddg_urls(html: str) -> list[str]:
    """Extract URLs from DuckDuckGo HTML results (uddg= params)."""
    urls = []
    # DuckDuckGo embeds target URLs in uddg= query parameters
    for match in re.finditer(r'uddg=([^&"]+)', html):
        raw = match.group(1)
        decoded = unquote(raw)
        if decoded.startswith("http"):
            urls.append(decoded)
    return urls
