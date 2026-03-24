from fastapi.testclient import TestClient

import app as app_module


def _demo_raw_result():
    return {
        "business_name": "Laveta",
        "industry": "coffee shop",
        "city": "Echo Park, Los Angeles",
        "website_url": "https://lavetacoffee.com",
        "timestamp": "2026-03-17T12:00:00",
        "api_keys_available": ["anthropic", "openai"],
        "llm_results": {
            "openai": [
                {
                    "query": "What are the best coffee shop businesses in Echo Park, Los Angeles?",
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
        },
        "web_presence": {
            "has_schema_markup": False,
            "has_local_business_schema": False,
            "has_answer_blocks": False,
            "google_business_found": False,
            "yelp_found": None,
            "has_meta_description": True,
            "has_title_tag": True,
            "has_og_tags": True,
            "ssl_valid": True,
            "mobile_friendly_meta": True,
            "fast_load": True,
            "website_accessible": True,
            "robots_txt_exists": True,
            "robots_allows_crawl": True,
            "sitemap_exists": True,
            "has_canonical": True,
            "has_noindex": False,
            "has_faq_schema": False,
            "has_faq_section": False,
            "word_count": 250,
            "has_contact_info": True,
            "has_hours": True,
            "has_address": True,
        },
    }


def test_app_boots_and_serves_ui():
    client = TestClient(app_module.app)

    response = client.get("/")

    assert response.status_code == 200
    assert "GEO Audit" in response.text
    assert "Executive Summary" in response.text
    assert "Top 10 Fixes" in response.text


def test_audit_endpoint_returns_ui_ready_payload(monkeypatch):
    monkeypatch.setattr(app_module.DemoAuditor, "run", lambda self: _demo_raw_result())

    client = TestClient(app_module.app)
    response = client.post(
        "/api/audit",
        json={
            "business_name": "Laveta",
            "industry": "coffee shop",
            "city": "Echo Park, Los Angeles",
            "website_url": "https://lavetacoffee.com",
            "demo": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["audit"]["entity"]["business_name"] == "Laveta"
    assert payload["audit"]["input"]["business_name"] == "Laveta"
    assert payload["audit"]["score"]["final"] >= 0
    assert payload["audit"]["score"]["formula"].startswith("score_v2")
    assert payload["summary"]["headline"]
    assert payload["summary"]["overview"]
    assert payload["score_explanation"]["final_score"] == payload["audit"]["score"]["final"]
    assert "score_cards" in payload
    assert "prompt_cluster_performance" in payload
    assert "top_competitors" in payload
    assert "citation_source_breakdown" in payload
    assert "readiness_gaps" in payload
    assert "top_recommendations" in payload
    assert payload["top_recommendations"][0]["why_it_matters"]
    assert payload["top_recommendations"][0]["implementation_hint"]
    assert "scores" not in payload
