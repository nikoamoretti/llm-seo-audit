import tempfile
import unittest
from pathlib import Path

import audit as audit_module
import app as app_module
from src.core.legacy_adapter import adapt_legacy_result
from report_generator import ReportGenerator


class ReportingBehaviorTest(unittest.TestCase):
    def test_compute_scores_skips_unchecked_directory_values(self):
        llm_results = {
            "openai": [
                {
                    "analysis": {
                        "mentioned": True,
                        "position": 1,
                        "competitors": [],
                        "attributes": [],
                    }
                }
            ]
        }

        web_results = {
            "website_accessible": True,
            "robots_txt_exists": True,
            "robots_allows_crawl": True,
            "sitemap_exists": True,
            "has_canonical": True,
            "has_noindex": False,
            "has_schema_markup": True,
            "has_local_business_schema": True,
            "has_faq_schema": True,
            "has_og_tags": True,
            "ssl_valid": True,
            "fast_load": True,
            "mobile_friendly_meta": True,
            "has_meta_description": True,
            "has_title_tag": True,
            "has_answer_blocks": True,
            "has_faq_section": True,
            "word_count": 500,
            "has_contact_info": True,
            "has_hours": True,
            "has_address": True,
            "google_business_found": None,
            "yelp_found": None,
        }
        scores = audit_module.compute_scores(
            llm_results,
            web_results,
            ["openai"],
        )
        readiness = app_module.compute_readiness_score(web_results)

        self.assertIsNone(readiness["listing_presence"]["checks"]["Google Business Profile"])
        self.assertIsNone(readiness["listing_presence"]["checks"]["Yelp"])
        self.assertGreaterEqual(scores["web_presence_score"], 70)

    def test_compute_scores_matches_app_scoring_engine(self):
        llm_results = {
            "openai": [
                {
                    "query": "What are the best coffee shops in Echo Park, Los Angeles?",
                    "cluster": "head",
                    "response": "Laveta is a strong option.",
                    "analysis": {
                        "mentioned": True,
                        "cited": False,
                        "position": 1,
                        "visibility_score": 84,
                        "sentiment": 0.4,
                        "competitors": ["Woodcat Coffee"],
                        "attributes": ["great coffee"],
                    },
                }
            ]
        }
        web_results = {
            "website_accessible": True,
            "robots_txt_exists": True,
            "robots_allows_crawl": True,
            "sitemap_exists": False,
            "has_canonical": True,
            "has_noindex": False,
            "has_schema_markup": False,
            "has_local_business_schema": False,
            "has_faq_schema": False,
            "has_og_tags": True,
            "ssl_valid": True,
            "fast_load": True,
            "mobile_friendly_meta": True,
            "has_meta_description": True,
            "has_title_tag": True,
            "has_answer_blocks": False,
            "has_faq_section": False,
            "word_count": 250,
            "has_contact_info": True,
            "has_hours": True,
            "has_address": True,
            "google_business_found": True,
            "yelp_found": None,
        }

        scores = audit_module.compute_scores(llm_results, web_results, ["openai"])
        readiness = app_module.compute_readiness_score(web_results)
        visibility = app_module.compute_visibility_score(llm_results)
        canonical_scores = app_module.compute_geo_score(readiness, visibility, bool(web_results))

        self.assertEqual(scores["overall_score"], canonical_scores["geo_score"])
        self.assertEqual(scores["llm_visibility_score"], canonical_scores["visibility_score"])
        self.assertEqual(scores["web_presence_score"], canonical_scores["readiness_score"])

    def test_report_generator_renders_source_unavailable_and_omits_bbb(self):
        raw_result = {
            "mode": "live",
            "business_name": "Laveta",
            "industry": "coffee shop",
            "city": "Echo Park, Los Angeles",
            "timestamp": "2026-03-17T12:00:00",
            "scores": {
                "geo_score": 68,
                "readiness_score": 50,
                "visibility_score": 82,
                "formula": "score_v2 final = round((0.45 * readiness) + (0.55 * visibility) - penalties)",
                "readiness": {
                    "R": 50,
                    "R_local_entity": {
                        "score": 50,
                        "label": "Online Listings",
                        "description": "Can AI find your business on core directories?",
                        "checks": {
                            "Found on Google Business": None,
                            "Found on Yelp": True,
                        },
                    }
                },
                "visibility": {
                    "V": 82,
                    "overall_mention_rate": 50.0,
                    "per_llm": {},
                    "per_cluster": {},
                    "top_competitors": {},
                    "attributes_cited": [],
                },
            },
            "web_presence": {
                "google_business_found": None,
                "yelp_found": True,
            },
            "llm_responses": {},
        }
        audit_run = adapt_legacy_result(raw_result)

        with tempfile.TemporaryDirectory() as tmpdir:
            html_path = ReportGenerator(audit_run, Path(tmpdir)).save_html()
            html = html_path.read_text()

        self.assertIn("SOURCE UNAVAILABLE", html)
        self.assertIn("Google Business Profile", html)
        self.assertNotIn("BBB Listing", html)

    def test_terminal_report_renders_from_canonical_audit_run(self):
        raw_result = {
            "mode": "demo",
            "business_name": "Laveta",
            "industry": "coffee shop",
            "city": "Echo Park, Los Angeles",
            "timestamp": "2026-03-17T12:00:00",
            "scores": {
                "overall_score": 82,
                "llm_visibility_score": 82,
                "web_presence_score": 50,
                "per_llm": {
                    "openai": {
                        "visibility_score": 82,
                        "mention_rate": 50.0,
                        "citation_rate": 0.0,
                        "avg_position": 1.0,
                        "total_queries": 2,
                        "times_mentioned": 1,
                        "times_cited": 0,
                        "top_competitors": {
                            "Woodcat Coffee": 1,
                            "Warning: Results may vary": 2,
                            "Source: Yelp": 1,
                        },
                        "attributes_cited": ["great coffee"],
                    }
                },
                "overall_mention_rate": 50.0,
                "top_competitors": {
                    "Woodcat Coffee": 1,
                    "Warning: Results may vary": 2,
                    "Source: Yelp": 1,
                },
                "attributes_cited": ["great coffee"],
            },
            "web_presence": {
                "google_business_found": None,
                "yelp_found": True,
            },
            "llm_results": {},
        }
        audit_run = adapt_legacy_result(raw_result)

        with audit_module.console.capture() as capture:
            audit_module.print_terminal_report(audit_run)

        output = capture.get()
        normalized_output = " ".join(output.split())
        self.assertIn("Overall GEO Score", output)
        self.assertIn("82/100", output)
        self.assertIn("Google Business Profile", output)
        self.assertIn("Web Presence Score", output)
        self.assertIn("SOURCE UNAVAILABLE", normalized_output)
        self.assertIn("Study what these competitors are doing right: Woodcat Coffee", normalized_output)
        self.assertNotIn("Warning: Results may vary", output)
        self.assertNotIn("Source: Yelp", output)


if __name__ == "__main__":
    unittest.main()
