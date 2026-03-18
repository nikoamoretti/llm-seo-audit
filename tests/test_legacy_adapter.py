from src.core.legacy_adapter import adapt_legacy_result


def test_legacy_adapter_maps_current_app_shape_to_canonical_audit_run():
    raw_result = {
        "mode": "demo",
        "business_name": "Laveta",
        "industry": "coffee shop",
        "city": "Echo Park, Los Angeles",
        "website_url": "https://lavetacoffee.com",
        "timestamp": "2026-03-17T12:00:00",
        "scores": {
            "geo_score": 74,
            "readiness_score": 62,
            "visibility_score": 83,
            "formula": "0.55 × Visibility + 0.45 × Readiness",
            "readiness": {
                "R": 62,
                "R_local_entity": {
                    "score": 50,
                    "label": "Online Listings",
                    "description": "Can AI find your business on core directories?",
                    "checks": {"Found on Google Business": False, "Found on Yelp": None},
                },
            },
            "visibility": {
                "V": 83,
                "overall_mention_rate": 50.0,
                "per_llm": {
                    "openai": {
                        "visibility_score": 83,
                        "mention_rate": 50.0,
                        "citation_rate": 0.0,
                        "avg_position": 1.0,
                        "total_queries": 2,
                        "times_mentioned": 1,
                        "times_cited": 0,
                        "top_competitors": {"Woodcat Coffee": 1},
                        "attributes_cited": ["great coffee"],
                    }
                },
                "per_cluster": {"head": {"avg_score": 83, "query_count": 1}},
                "top_competitors": {"Woodcat Coffee": 1},
                "attributes_cited": ["great coffee"],
            },
        },
        "web_presence": {"google_business_found": False, "has_schema_markup": False},
        "recommendations": [
            {
                "priority": "P1",
                "category": "Machine-Readable Info",
                "title": "Add structured data so AI understands your business",
                "detail": "Sites with this are 78% more likely to be recommended by AI.",
            }
        ],
        "llm_responses": {
            "openai": [
                {
                    "query": "What are the best coffee shops in Echo Park, Los Angeles?",
                    "cluster": "head",
                    "response": "Laveta is a strong option.",
                    "engine_response": {
                        "provider": "openai",
                        "prompt": "What are the best coffee shops in Echo Park, Los Angeles?",
                        "raw_text": "Laveta is a strong option.",
                        "latency_ms": 22,
                        "metadata": {"model": "gpt-5.4"},
                    },
                    "analysis": {
                        "mentioned": True,
                        "recommended": True,
                        "cited": True,
                        "cited_official_domain": True,
                        "cited_third_party_domain": False,
                        "position": 1,
                        "visibility_score": 83,
                        "sentiment": 0.4,
                        "citations": [
                            {
                                "label": "Laveta Coffee",
                                "url": "https://lavetacoffee.com",
                                "domain": "lavetacoffee.com",
                                "citation_type": "official",
                                "is_official_domain": True,
                            }
                        ],
                    },
                }
            ]
        },
    }

    audit_run = adapt_legacy_result(raw_result)

    assert audit_run.entity.business_name == "Laveta"
    assert audit_run.score.final == 74
    assert audit_run.score.readiness == 62
    assert audit_run.score.visibility == 83
    assert audit_run.readiness.dimensions["R_local_entity"].checks["Found on Google Business"] is False
    assert audit_run.visibility.prompt_results[0].provider == "openai"
    assert audit_run.visibility.prompt_results[0].latency_ms == 22
    assert audit_run.visibility.prompt_results[0].recommended is True
    assert audit_run.visibility.prompt_results[0].cited_official_domain is True
    assert audit_run.visibility.prompt_results[0].citations[0].domain == "lavetacoffee.com"
    assert any(rec.evidence == ["web_presence.has_schema_markup=False"] for rec in audit_run.recommendations)
    assert all("%" not in rec.detail for rec in audit_run.recommendations)
