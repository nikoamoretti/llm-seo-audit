"""
Web Presence Checker - SOTA GEO Blueprint Implementation.
Two-layer readiness checks covering P0/P1/P2 audit items:
  - R_Index: crawlability, robots.txt, canonical, sitemap, noindex
  - R_Schema: JSON-LD, microdata, FAQ schema, LocalBusiness schema
  - R_Trust: SSL and directory presence
  - R_Content: answer blocks, meta desc, OG tags, content freshness
  - R_LocalEntity: GBP signals, NAP consistency, review indicators
"""

import json
import logging
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

from src.crawl.discovery import SiteDiscovery
from src.crawl.fetcher import PageFetcher
from src.entity.extractors import extract_page_facts
from src.entity.reconciler import reconcile_business_entity
from thefuzz import fuzz


logger = logging.getLogger(__name__)


class WebPresenceChecker:
    """Checks a business's web presence for GEO readiness signals."""

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    TIMEOUT = 15

    def __init__(self, session=None, crawl_budget: int = 6):
        self.http_session = session or requests
        self.crawl_budget = crawl_budget
        self.fetcher = PageFetcher(session=self.http_session, headers=self.HEADERS, timeout=self.TIMEOUT)
        self.discovery = SiteDiscovery(fetcher=self.fetcher, crawl_budget=self.crawl_budget)

    def check_all(self, business_name: str, website_url: str, city: str) -> dict:
        """Run all readiness checks. Returns flat dict of check results."""
        results = {}

        if website_url:
            site_results = self._crawl_site_readiness(business_name, website_url, city)
            results.update(site_results)
            index_results = self._check_indexability(website_url)
            results.update(index_results)

        dir_results = self._check_directories(business_name, city)
        results.update(dir_results)

        return results

    def _crawl_site_readiness(self, business_name: str, website_url: str, city: str) -> dict:
        discovery = self.discovery.discover(website_url)
        if not discovery.pages:
            return {
                "has_schema_markup": False,
                "schema_types": [],
                "has_faq_schema": False,
                "has_local_business_schema": False,
                "has_og_tags": False,
                "has_meta_description": False,
                "has_title_tag": False,
                "ssl_valid": False,
                "mobile_friendly_meta": False,
                "fast_load": False,
                "load_time_seconds": None,
                "website_accessible": False,
                "has_canonical": False,
                "has_hreflang": False,
                "has_answer_blocks": False,
                "answer_block_count": 0,
                "word_count": 0,
                "has_faq_section": False,
                "faq_count": 0,
                "has_contact_info": False,
                "has_hours": False,
                "has_address": False,
                "has_booking_cta": False,
                "has_contact_cta": False,
                "discovered_page_count": 0,
                "page_types": [],
                "service_names": [],
                "service_areas": [],
                "trust_signals": [],
                "extracted_entity": {},
            }

        page_facts = [extract_page_facts(page) for page in discovery.pages]
        entity = reconcile_business_entity(
            page_facts,
            business_name=business_name,
            city=city,
            website_url=website_url,
        )
        schema_types = sorted(
            {
                schema_type
                for facts in page_facts
                for schema_type in facts.schema_types
            }
        )
        local_schema_types = {
            "LocalBusiness",
            "Restaurant",
            "CafeOrCoffeeShop",
            "Dentist",
            "Attorney",
            "AutoRepair",
            "HairSalon",
            "Plumber",
            "Store",
            "MedicalBusiness",
            "FinancialService",
            "RealEstateAgent",
            "ProfessionalService",
            "FoodEstablishment",
        }
        homepage = discovery.homepage

        return {
            "has_schema_markup": bool(schema_types),
            "schema_types": schema_types,
            "has_faq_schema": "FAQPage" in schema_types,
            "has_local_business_schema": any(schema_type in local_schema_types for schema_type in schema_types),
            "has_og_tags": any(facts.has_og_tags for facts in page_facts),
            "has_meta_description": any(facts.has_meta_description for facts in page_facts),
            "has_title_tag": any(facts.has_title_tag for facts in page_facts),
            "ssl_valid": bool(homepage and homepage.final_url.startswith("https://")),
            "mobile_friendly_meta": any(facts.has_viewport_meta for facts in page_facts),
            "fast_load": bool(homepage and homepage.load_time_seconds is not None and homepage.load_time_seconds < 3.0),
            "load_time_seconds": homepage.load_time_seconds if homepage else None,
            "website_accessible": homepage is not None,
            "has_canonical": any(facts.has_canonical for facts in page_facts),
            "has_hreflang": any("hreflang" in page.html.lower() for page in discovery.pages),
            "has_answer_blocks": any(facts.has_answer_blocks for facts in page_facts),
            "answer_block_count": sum(len(facts.faq_questions) for facts in page_facts),
            "word_count": sum(facts.word_count for facts in page_facts),
            "has_faq_section": any(facts.faq_questions for facts in page_facts),
            "faq_count": sum(len(facts.faq_questions) for facts in page_facts),
            "has_contact_info": bool(entity.phone),
            "has_hours": bool(entity.hours),
            "has_address": bool(entity.address),
            "has_booking_cta": bool(entity.has_booking_cta),
            "has_contact_cta": bool(entity.has_contact_cta),
            "discovered_page_count": len(discovery.pages),
            "page_types": sorted({page.page_type for page in discovery.pages}),
            "service_names": entity.service_names,
            "service_areas": entity.service_areas,
            "trust_signals": entity.trust_signals,
            "extracted_entity": entity.model_dump(mode="json"),
        }

    def _check_website(self, url: str) -> dict:
        """Core website technical checks."""
        results = {
            "has_schema_markup": False,
            "schema_types": [],
            "has_faq_schema": False,
            "has_local_business_schema": False,
            "has_og_tags": False,
            "has_meta_description": False,
            "has_title_tag": False,
            "ssl_valid": False,
            "mobile_friendly_meta": False,
            "fast_load": False,
            "load_time_seconds": None,
            "website_accessible": False,
            "has_canonical": False,
            "has_hreflang": False,
        }

        if not url.startswith("http"):
            url = "https://" + url

        try:
            start = time.time()
            resp = self.http_session.get(url, headers=self.HEADERS, timeout=self.TIMEOUT,
                                         allow_redirects=True)
            load_time = time.time() - start

            results["website_accessible"] = resp.status_code == 200
            results["load_time_seconds"] = round(load_time, 2)
            results["fast_load"] = load_time < 3.0
            results["ssl_valid"] = resp.url.startswith("https://")

            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")

                # Title tag
                title = soup.find("title")
                results["has_title_tag"] = bool(title and title.string and len(title.string.strip()) > 0)

                # Meta description
                meta_desc = soup.find("meta", attrs={"name": "description"})
                results["has_meta_description"] = bool(meta_desc and meta_desc.get("content"))

                # Open Graph tags
                og_tags = soup.find_all("meta", attrs={"property": re.compile(r"^og:")})
                results["has_og_tags"] = len(og_tags) >= 2

                # Mobile viewport
                viewport = soup.find("meta", attrs={"name": "viewport"})
                results["mobile_friendly_meta"] = bool(viewport)

                # Canonical URL
                canonical = soup.find("link", attrs={"rel": "canonical"})
                results["has_canonical"] = bool(canonical and canonical.get("href"))

                # Hreflang
                hreflang = soup.find("link", attrs={"hreflang": True})
                results["has_hreflang"] = bool(hreflang)

                # Schema.org / JSON-LD
                schema_scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
                if schema_scripts:
                    results["has_schema_markup"] = True
                    for script in schema_scripts:
                        try:
                            data = json.loads(script.string)
                            self._extract_schema_types(data, results)
                        except (json.JSONDecodeError, TypeError):
                            pass

                # Microdata fallback
                if not results["has_schema_markup"]:
                    microdata = soup.find_all(attrs={"itemtype": re.compile(r"schema\.org")})
                    results["has_schema_markup"] = len(microdata) > 0

        except requests.exceptions.SSLError:
            results["ssl_valid"] = False
        except requests.exceptions.RequestException:
            pass

        return results

    def _extract_schema_types(self, data, results):
        """Recursively extract schema types from JSON-LD."""
        if isinstance(data, dict):
            schema_type = data.get("@type", "")
            if schema_type:
                if isinstance(schema_type, list):
                    results["schema_types"].extend(schema_type)
                else:
                    results["schema_types"].append(schema_type)

                type_str = str(schema_type).lower()
                if "faq" in type_str:
                    results["has_faq_schema"] = True
                local_types = [
                    "localbusiness", "restaurant", "cafeorcoffeeshop", "dentist",
                    "attorney", "autorepair", "hairsalon", "plumber", "store",
                    "medicalbusiness", "financialservice", "realestateagent",
                    "professionalservice", "foodestablishment",
                ]
                if any(lt in type_str for lt in local_types):
                    results["has_local_business_schema"] = True

            # Check @graph
            if "@graph" in data:
                for item in data["@graph"]:
                    self._extract_schema_types(item, results)

        elif isinstance(data, list):
            for item in data:
                self._extract_schema_types(item, results)

    def _check_indexability(self, url: str) -> dict:
        """P0 checks: robots.txt, sitemap, noindex."""
        results = {
            "robots_txt_exists": False,
            "robots_allows_crawl": True,
            "sitemap_exists": False,
            "has_noindex": False,
        }

        if not url.startswith("http"):
            url = "https://" + url

        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"

        # Check robots.txt
        try:
            resp = self.http_session.get(f"{base}/robots.txt", headers=self.HEADERS, timeout=10)
            if resp.status_code == 200 and "user-agent" in resp.text.lower():
                results["robots_txt_exists"] = True
                robots_lower = resp.text.lower()
                # Check if our page path is disallowed
                if "disallow: /" in robots_lower:
                    # Check if it's "Disallow: /" (blocks everything) vs "Disallow: /something"
                    for line in robots_lower.split("\n"):
                        line = line.strip()
                        if line == "disallow: /":
                            results["robots_allows_crawl"] = False

                # Check for sitemap in robots.txt
                if "sitemap:" in robots_lower:
                    results["sitemap_exists"] = True
        except requests.exceptions.RequestException:
            pass

        # Check sitemap.xml directly if not found in robots
        if not results["sitemap_exists"]:
            try:
                resp = self.http_session.get(f"{base}/sitemap.xml", headers=self.HEADERS, timeout=10)
                results["sitemap_exists"] = (
                    resp.status_code == 200
                    and ("<?xml" in resp.text[:100] or "<urlset" in resp.text[:500])
                )
            except requests.exceptions.RequestException:
                pass

        # Check for noindex on the page
        try:
            resp = self.http_session.get(url, headers=self.HEADERS, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                robots_meta = soup.find("meta", attrs={"name": "robots"})
                if robots_meta:
                    content = (robots_meta.get("content", "") or "").lower()
                    results["has_noindex"] = "noindex" in content

                # Also check X-Robots-Tag header
                xrobots = resp.headers.get("X-Robots-Tag", "").lower()
                if "noindex" in xrobots:
                    results["has_noindex"] = True
        except requests.exceptions.RequestException:
            pass

        return results

    def _check_content_readiness(self, url: str) -> dict:
        """P1 checks: answer blocks, FAQ sections, content depth."""
        results = {
            "has_answer_blocks": False,
            "answer_block_count": 0,
            "word_count": 0,
            "has_faq_section": False,
            "faq_count": 0,
            "has_contact_info": False,
            "has_hours": False,
            "has_address": False,
        }

        if not url.startswith("http"):
            url = "https://" + url

        try:
            resp = self.http_session.get(url, headers=self.HEADERS, timeout=self.TIMEOUT)
            if resp.status_code != 200:
                return results

            soup = BeautifulSoup(resp.text, "html.parser")

            # Remove script/style
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()

            text = soup.get_text(separator=" ", strip=True)
            results["word_count"] = len(text.split())

            text_lower = text.lower()

            # Detect FAQ sections
            faq_headers = soup.find_all(
                ["h2", "h3", "h4"],
                string=re.compile(r"(?:faq|frequently asked|common question)", re.IGNORECASE)
            )
            results["has_faq_section"] = len(faq_headers) > 0

            # Count question patterns (answer blocks)
            questions = re.findall(r'(?:^|\n)[^.]*\?\s*\n', text)
            q_tags = soup.find_all(string=re.compile(r'.+\?\s*$'))
            answer_count = len(questions) + len(q_tags)
            results["answer_block_count"] = min(answer_count, 50)
            results["has_answer_blocks"] = answer_count >= 2

            # FAQ schema count
            for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict) and data.get("@type") == "FAQPage":
                        entities = data.get("mainEntity", [])
                        results["faq_count"] = len(entities)
                except (json.JSONDecodeError, TypeError):
                    pass

            # Contact info detection
            phone_pattern = r'[\(]?\d{3}[\)]?[\s.-]?\d{3}[\s.-]?\d{4}'
            results["has_contact_info"] = bool(re.search(phone_pattern, text))

            # Hours detection
            hour_patterns = [
                r'\d{1,2}:\d{2}\s*(?:am|pm|AM|PM)',
                r'(?:mon|tue|wed|thu|fri|sat|sun)\w*\s*[-:]\s*\d',
                r'hours?\s*(?:of\s*)?(?:operation|business)',
            ]
            results["has_hours"] = any(re.search(p, text, re.IGNORECASE) for p in hour_patterns)

            # Address detection
            address_pattern = r'\d+\s+[\w\s]+(?:st|street|ave|avenue|blvd|boulevard|rd|road|dr|drive|ln|lane|way|ct|court)'
            results["has_address"] = bool(re.search(address_pattern, text, re.IGNORECASE))

        except requests.exceptions.RequestException:
            pass

        return results

    def _check_directories(self, business_name: str, city: str) -> dict:
        """Directory presence checks using Yelp Fusion API and Google Places API.

        Returns None for fields where the API key is missing or the call failed
        (so the report can say "couldn't check" instead of "not found").
        Returns False only when the API confirmed the business is not listed.
        """
        import os

        results = {
            "google_business_found": None,
            "google_rating": None,
            "google_review_count": None,
            "google_place_id": None,
            "yelp_found": None,
            "yelp_rating": None,
            "yelp_review_count": None,
            "yelp_url": None,
        }

        def fuzzy_score(candidate_name: str) -> int:
            candidate = (candidate_name or "").lower()
            target = business_name.lower()
            return max(
                fuzz.ratio(target, candidate),
                fuzz.partial_ratio(target, candidate),
                fuzz.token_sort_ratio(target, candidate),
            )

        yelp_key = os.environ.get("YELP_API_KEY")
        if not yelp_key:
            logger.warning("YELP_API_KEY is not set; skipping Yelp directory check.")
        else:
            try:
                resp = requests.get(
                    "https://api.yelp.com/v3/businesses/search",
                    headers={**self.HEADERS, "Authorization": f"Bearer {yelp_key}"},
                    params={"term": business_name, "location": city, "limit": 5},
                    timeout=10,
                )
                if resp.status_code != 200:
                    logger.warning(
                        "Yelp directory check failed for %s in %s with status %s.",
                        business_name,
                        city,
                        resp.status_code,
                    )
                else:
                    businesses = resp.json().get("businesses", [])
                    best_match = None
                    best_score = 0
                    for biz in businesses:
                        score = fuzzy_score(biz.get("name", ""))
                        if score >= 80 and score > best_score:
                            best_match = biz
                            best_score = score

                    results["yelp_found"] = best_match is not None
                    if best_match:
                        results["yelp_rating"] = best_match.get("rating")
                        results["yelp_review_count"] = best_match.get("review_count")
                        results["yelp_url"] = best_match.get("url")
            except (requests.exceptions.RequestException, ValueError) as exc:
                logger.warning(
                    "Yelp directory check failed for %s in %s: %s",
                    business_name,
                    city,
                    exc,
                )

        places_key = os.environ.get("GOOGLE_PLACES_API_KEY")
        if not places_key:
            logger.warning(
                "GOOGLE_PLACES_API_KEY is not set; skipping Google Business directory check."
            )
        else:
            try:
                resp = requests.get(
                    "https://maps.googleapis.com/maps/api/place/textsearch/json",
                    params={
                        "query": f"{business_name} {city}",
                        "key": places_key,
                    },
                    headers=self.HEADERS,
                    timeout=10,
                )
                if resp.status_code != 200:
                    logger.warning(
                        "Google Business directory check failed for %s in %s with status %s.",
                        business_name,
                        city,
                        resp.status_code,
                    )
                else:
                    payload = resp.json()
                    status = payload.get("status")
                    if status == "ZERO_RESULTS":
                        results["google_business_found"] = False
                    elif status != "OK":
                        logger.warning(
                            "Google Business directory check failed for %s in %s with API status %s.",
                            business_name,
                            city,
                            status,
                        )
                    else:
                        places = payload.get("results", [])
                        best_match = None
                        best_score = 0
                        for place in places:
                            score = fuzzy_score(place.get("name", ""))
                            if score >= 80 and score > best_score:
                                best_match = place
                                best_score = score

                        results["google_business_found"] = best_match is not None
                        if best_match:
                            results["google_rating"] = best_match.get("rating")
                            results["google_review_count"] = best_match.get("user_ratings_total")
                            results["google_place_id"] = best_match.get("place_id")
            except (requests.exceptions.RequestException, ValueError) as exc:
                logger.warning(
                    "Google Business directory check failed for %s in %s: %s",
                    business_name,
                    city,
                    exc,
                )

        return results
