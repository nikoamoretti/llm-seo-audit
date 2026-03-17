"""
Web Presence Checker - SOTA GEO Blueprint Implementation.
Two-layer readiness checks covering P0/P1/P2 audit items:
  - R_Index: crawlability, robots.txt, canonical, sitemap, noindex
  - R_Schema: JSON-LD, microdata, FAQ schema, LocalBusiness schema
  - R_Trust: SSL, directories, BBB
  - R_Content: answer blocks, meta desc, OG tags, content freshness
  - R_LocalEntity: GBP signals, NAP consistency, review indicators
"""

import json
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urljoin, urlparse


class WebPresenceChecker:
    """Checks a business's web presence for GEO readiness signals."""

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    TIMEOUT = 15

    def check_all(self, business_name: str, website_url: str, city: str) -> dict:
        """Run all readiness checks. Returns flat dict of check results."""
        results = {}

        if website_url:
            site_results = self._check_website(website_url)
            results.update(site_results)

            index_results = self._check_indexability(website_url)
            results.update(index_results)

            content_results = self._check_content_readiness(website_url)
            results.update(content_results)

        dir_results = self._check_directories(business_name, city)
        results.update(dir_results)

        return results

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
            resp = requests.get(url, headers=self.HEADERS, timeout=self.TIMEOUT,
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
            resp = requests.get(f"{base}/robots.txt", headers=self.HEADERS, timeout=10)
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
                resp = requests.get(f"{base}/sitemap.xml", headers=self.HEADERS, timeout=10)
                results["sitemap_exists"] = (
                    resp.status_code == 200
                    and ("<?xml" in resp.text[:100] or "<urlset" in resp.text[:500])
                )
            except requests.exceptions.RequestException:
                pass

        # Check for noindex on the page
        try:
            resp = requests.get(url, headers=self.HEADERS, timeout=10)
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
            resp = requests.get(url, headers=self.HEADERS, timeout=self.TIMEOUT)
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
        """Directory presence checks."""
        results = {
            "google_business_found": False,
            "yelp_found": False,
            "bbb_found": False,
        }

        query = quote_plus(f"{business_name} {city}")

        # Check Yelp
        try:
            yelp_url = f"https://www.yelp.com/search?find_desc={quote_plus(business_name)}&find_loc={quote_plus(city)}"
            resp = requests.get(yelp_url, headers=self.HEADERS, timeout=self.TIMEOUT)
            if resp.status_code == 200:
                results["yelp_found"] = business_name.lower().split()[0] in resp.text.lower()
        except requests.exceptions.RequestException:
            pass

        # Check BBB
        try:
            bbb_url = f"https://www.bbb.org/search?find_text={quote_plus(business_name)}&find_loc={quote_plus(city)}"
            resp = requests.get(bbb_url, headers=self.HEADERS, timeout=self.TIMEOUT)
            if resp.status_code == 200:
                results["bbb_found"] = business_name.lower().split()[0] in resp.text.lower()
        except requests.exceptions.RequestException:
            pass

        # Check Google
        try:
            google_url = f"https://www.google.com/search?q={query}+reviews"
            resp = requests.get(google_url, headers=self.HEADERS, timeout=self.TIMEOUT)
            if resp.status_code == 200:
                text = resp.text.lower()
                results["google_business_found"] = (
                    "rating" in text or "reviews" in text or "google.com/maps" in text
                ) and business_name.lower().split()[0] in text
        except requests.exceptions.RequestException:
            pass

        return results
