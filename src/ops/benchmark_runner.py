from __future__ import annotations

import difflib
import json
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from src.core.audit_builder import build_audit_run
from src.ops.regression_report import build_regression_report


BENCHMARKS_DIR = Path(__file__).resolve().parents[2] / "benchmarks"
DEFAULT_BUSINESSES_PATH = BENCHMARKS_DIR / "businesses.json"
DEFAULT_EXPECTED_PATTERNS_PATH = BENCHMARKS_DIR / "expected_patterns.json"
DEFAULT_CANARY_PROMPTS_PATH = Path(__file__).resolve().parents[2] / "config" / "canary_prompts.yaml"
DEFAULT_DELTA_THRESHOLD = 8


def run_benchmarks(
    *,
    businesses_path: Path | None = None,
    expected_patterns_path: Path | None = None,
    canary_prompts_path: Path | None = None,
    baseline_canary_snapshot_path: Path | None = None,
    current_canary_snapshot_path: Path | None = None,
    delta_threshold: int | None = None,
) -> dict[str, Any]:
    businesses = load_benchmark_businesses(businesses_path or DEFAULT_BUSINESSES_PATH)
    expected_patterns = load_expected_patterns(expected_patterns_path or DEFAULT_EXPECTED_PATTERNS_PATH)
    canary_prompts = load_canary_prompts(canary_prompts_path or DEFAULT_CANARY_PROMPTS_PATH)
    threshold = delta_threshold or int(expected_patterns.get("defaults", {}).get("max_score_delta", DEFAULT_DELTA_THRESHOLD))

    results = []
    for business in businesses:
        fixture = build_fixture_payload(business)
        audit_run = build_audit_run(
            mode="demo",
            business_name=business["business_name"],
            industry=business["industry"],
            city=business["city"],
            website_url=business.get("website_url"),
            phone=business.get("phone"),
            web_presence=fixture["web_presence"],
            llm_results=fixture["llm_results"],
            api_keys_used=["fixture"],
        )
        expected = expected_patterns.get("businesses", {}).get(business["id"], {})
        results.append(compare_audit_to_expected(business["id"], audit_run, expected, threshold))

    canary_snapshot_deltas: dict[str, int] = {}
    if baseline_canary_snapshot_path and current_canary_snapshot_path:
        canary_snapshot_deltas = compare_canary_snapshots(
            load_canary_snapshot(baseline_canary_snapshot_path),
            load_canary_snapshot(current_canary_snapshot_path),
        )

    summary = build_regression_report(
        results,
        delta_threshold=threshold,
        canary_snapshot_deltas=canary_snapshot_deltas,
    )
    summary["canary_prompt_count"] = len(canary_prompts.get("prompts", []))
    return {
        "summary": summary,
        "results": results,
    }


def load_benchmark_businesses(path: Path) -> list[dict[str, Any]]:
    with open(path) as file_obj:
        data = json.load(file_obj)
    if not isinstance(data, list):
        raise ValueError("benchmarks/businesses.json must be a list.")
    return data


def load_expected_patterns(path: Path) -> dict[str, Any]:
    with open(path) as file_obj:
        data = json.load(file_obj)
    if not isinstance(data, dict):
        raise ValueError("benchmarks/expected_patterns.json must be a mapping.")
    return data


def load_canary_prompts(path: Path) -> dict[str, Any]:
    with open(path) as file_obj:
        data = yaml.safe_load(file_obj)
    if not isinstance(data, dict):
        raise ValueError("config/canary_prompts.yaml must be a mapping.")
    return data


def load_canary_snapshot(path: Path) -> dict[str, Any]:
    with open(path) as file_obj:
        data = json.load(file_obj)
    if not isinstance(data, dict):
        raise ValueError("canary snapshot must be a mapping.")
    return data


def save_canary_snapshot(
    path: Path,
    *,
    version: str,
    outputs: list[dict[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": version,
                "outputs": outputs,
            },
            indent=2,
        )
    )


def compare_canary_snapshots(
    baseline_snapshot: dict[str, Any],
    current_snapshot: dict[str, Any],
) -> dict[str, int]:
    baseline_outputs = _snapshot_output_index(baseline_snapshot)
    current_outputs = _snapshot_output_index(current_snapshot)
    deltas: dict[str, int] = {}

    for prompt_id in sorted(set(baseline_outputs) | set(current_outputs)):
        deltas[prompt_id] = _canary_output_delta(
            baseline_outputs.get(prompt_id),
            current_outputs.get(prompt_id),
        )
    return deltas


def compare_audit_to_expected(
    business_id: str,
    audit_run,
    expected: dict[str, Any],
    delta_threshold: int,
) -> dict[str, Any]:
    baseline = expected.get("baseline_scores", {})
    score_deltas = {
        "final": _score_delta(audit_run.score.final, baseline.get("final")),
        "readiness": _score_delta(audit_run.score.readiness, baseline.get("readiness")),
        "visibility": _score_delta(audit_run.score.visibility, baseline.get("visibility")),
    }
    delta_flags = [
        key
        for key, delta in score_deltas.items()
        if delta is not None and abs(delta) > delta_threshold
    ]

    expected_keywords = expected.get("expected_recommendation_keywords", [])
    recommendation_titles = [recommendation.title for recommendation in audit_run.recommendations]
    top_competitors = list(audit_run.visibility.top_competitors)
    pattern_checks = {
        "score_band": _score_band(audit_run.score.final) == expected.get("expected_band", _score_band(audit_run.score.final)),
        "top_competitors": all(
            competitor in top_competitors
            for competitor in expected.get("expected_top_competitors", [])
        ),
        "recommendations": all(
            any(keyword in title for title in recommendation_titles)
            for keyword in expected_keywords
        ),
        "penalties": all(
            penalty_key in {penalty["key"] for penalty in audit_run.score.penalties}
            for penalty_key in expected.get("expected_penalties", [])
        ),
    }
    flagged = bool(delta_flags) or not all(pattern_checks.values())

    return {
        "business_id": business_id,
        "score": {
            "final": audit_run.score.final,
            "readiness": audit_run.score.readiness,
            "visibility": audit_run.score.visibility,
        },
        "baseline": baseline,
        "score_deltas": {key: delta for key, delta in score_deltas.items() if delta is not None},
        "delta_flags": delta_flags,
        "pattern_checks": pattern_checks,
        "flagged": flagged,
    }


def _snapshot_output_index(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    outputs = snapshot.get("outputs", [])
    if not isinstance(outputs, list):
        raise ValueError("canary snapshot outputs must be a list.")
    index: dict[str, dict[str, Any]] = {}
    for output in outputs:
        if isinstance(output, dict) and output.get("id"):
            index[str(output["id"])] = output
    return index


def _canary_output_delta(
    baseline_output: dict[str, Any] | None,
    current_output: dict[str, Any] | None,
) -> int:
    if baseline_output is None or current_output is None:
        return 100

    baseline_text = str(baseline_output.get("raw_text", ""))
    current_text = str(current_output.get("raw_text", ""))
    if not baseline_text and not current_text:
        return 0

    similarity = difflib.SequenceMatcher(None, baseline_text, current_text).ratio()
    return int(round((1 - similarity) * 100))


def build_fixture_payload(business: dict[str, Any]) -> dict[str, Any]:
    profile = business["fixture_profile"]
    competitors = business.get("competitors", [])
    return {
        "web_presence": _web_presence_fixture(profile),
        "llm_results": _llm_results_fixture(profile, business["business_name"], business["industry"], business["city"], competitors),
    }


def _web_presence_fixture(profile: str) -> dict[str, Any]:
    base = {
        "has_schema_markup": True,
        "has_local_business_schema": True,
        "has_answer_blocks": True,
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
        "has_faq_schema": True,
        "has_faq_section": True,
        "word_count": 1400,
        "has_contact_info": True,
        "has_hours": True,
        "has_address": True,
        "has_contact_cta": True,
        "has_booking_cta": False,
        "service_names": ["Primary service", "Secondary service"],
        "service_areas": ["Core city"],
        "page_types": ["homepage", "service", "faq", "location", "contact"],
        "trust_signals": ["licensed", "family-owned", "5-star reviews"],
        "google_business_found": True,
        "google_review_count": 120,
        "yelp_found": True,
        "yelp_review_count": 45,
    }
    if profile == "balanced":
        base.update(
            {
                "fast_load": False,
                "word_count": 850,
                "trust_signals": ["licensed", "5-star reviews"],
                "google_review_count": 40,
                "yelp_review_count": 18,
            }
        )
    elif profile == "weak_visibility":
        base.update(
            {
                "has_answer_blocks": False,
                "has_faq_section": False,
                "word_count": 420,
                "service_areas": [],
                "trust_signals": ["licensed"],
                "google_review_count": 12,
                "yelp_review_count": 8,
            }
        )
    elif profile == "competitor_heavy":
        base.update(
            {
                "has_answer_blocks": False,
                "has_faq_section": False,
                "word_count": 350,
                "service_names": ["Primary service"],
                "service_areas": [],
                "trust_signals": [],
                "google_review_count": 15,
                "yelp_review_count": 5,
            }
        )
    elif profile == "listing_gap":
        base.update(
            {
                "google_business_found": False,
                "google_review_count": None,
                "yelp_found": False,
                "yelp_review_count": None,
            }
        )
    elif profile == "crawl_blocked":
        base.update(
            {
                "robots_allows_crawl": False,
                "has_noindex": True,
                "website_accessible": False,
                "fast_load": False,
                "word_count": 200,
            }
        )
    return base


def _llm_results_fixture(
    profile: str,
    business_name: str,
    industry: str,
    city: str,
    competitors: list[str],
) -> dict[str, list[dict[str, Any]]]:
    competitor_a = competitors[0] if competitors else f"{city.split(',')[0]} Top {industry.title()}"
    competitor_b = competitors[1] if len(competitors) > 1 else f"{city.split(',')[0]} Trusted {industry.title()}"
    prompt_templates = [
        ("branded", f"{business_name} {city}"),
        ("discovery", f"What are the best {industry} businesses in {city}?"),
        ("comparison", f"Compare the best {industry} options in {city}"),
        ("trust", f"Who is the most trusted {industry} in {city}?"),
    ]
    if profile == "strong_local":
        states = [
            _prompt_state(True, True, True, True, 1, [competitor_a]),
            _prompt_state(True, True, True, True, 2, [competitor_a]),
            _prompt_state(True, True, True, False, 2, [competitor_a, competitor_b]),
            _prompt_state(True, True, True, True, 1, [competitor_a]),
        ]
    elif profile == "balanced":
        states = [
            _prompt_state(True, True, True, True, 1, [competitor_a]),
            _prompt_state(True, True, True, False, 2, [competitor_a]),
            _prompt_state(True, False, True, False, 3, [competitor_a, competitor_b]),
            _prompt_state(False, False, False, False, None, [competitor_a, competitor_b]),
        ]
    elif profile == "weak_visibility":
        states = [
            _prompt_state(True, False, False, False, 2, [competitor_a]),
            _prompt_state(False, False, False, False, None, [competitor_a, competitor_b]),
            _prompt_state(False, False, False, False, None, [competitor_a, competitor_b]),
            _prompt_state(False, False, False, False, None, [competitor_a]),
        ]
    elif profile == "competitor_heavy":
        states = [
            _prompt_state(True, False, False, False, 3, [competitor_a, competitor_b]),
            _prompt_state(False, False, False, False, None, [competitor_a, competitor_b]),
            _prompt_state(False, False, False, False, None, [competitor_a, competitor_b]),
            _prompt_state(False, False, False, False, None, [competitor_a]),
        ]
    elif profile == "listing_gap":
        states = [
            _prompt_state(True, True, True, False, 1, [competitor_a]),
            _prompt_state(True, True, True, False, 2, [competitor_a, competitor_b]),
            _prompt_state(True, False, True, False, 3, [competitor_a, competitor_b]),
            _prompt_state(True, True, False, False, 2, [competitor_a]),
        ]
    elif profile == "crawl_blocked":
        states = [
            _prompt_state(True, False, False, False, 2, [competitor_a]),
            _prompt_state(False, False, False, False, None, [competitor_a, competitor_b]),
            _prompt_state(False, False, False, False, None, [competitor_a, competitor_b]),
            _prompt_state(False, False, False, False, None, [competitor_a]),
        ]
    else:
        raise ValueError(f"Unknown fixture profile: {profile}")

    provider_results = [_build_prompt_result(cluster, query, state, business_name) for (cluster, query), state in zip(prompt_templates, states, strict=True)]
    return {
        "openai": provider_results,
        "perplexity": provider_results,
    }


def _build_prompt_result(cluster: str, query: str, state: dict[str, Any], business_name: str) -> dict[str, Any]:
    response = (
        f"{business_name} appears in the results for {query}."
        if state["mentioned"]
        else f"{query} focuses on other businesses."
    )
    return {
        "query": query,
        "cluster": cluster,
        "response": response,
        "analysis": {
            "mentioned": state["mentioned"],
            "recommended": state["recommended"],
            "cited": state["cited"],
            "cited_official_domain": state["cited_official_domain"],
            "cited_third_party_domain": state["cited"] and not state["cited_official_domain"],
            "position": state["position"],
            "competitors": state["competitors"],
            "attributes": ["strong reputation"] if state["mentioned"] else [],
            "citations": [
                {
                    "label": business_name,
                    "url": "https://official.example",
                    "domain": "official.example",
                    "citation_type": "official" if state["cited_official_domain"] else "third_party",
                    "is_official_domain": state["cited_official_domain"],
                }
            ] if state["cited"] else [],
        },
    }


def _prompt_state(
    mentioned: bool,
    recommended: bool,
    cited: bool,
    cited_official_domain: bool,
    position: int | None,
    competitors: list[str],
) -> dict[str, Any]:
    return {
        "mentioned": mentioned,
        "recommended": recommended,
        "cited": cited,
        "cited_official_domain": cited_official_domain,
        "position": position,
        "competitors": competitors,
    }


def _score_delta(actual: float, baseline: Any) -> float | None:
    if baseline is None:
        return None
    return round(float(actual) - float(baseline), 1)


def _score_band(score: float) -> str:
    if score >= 70:
        return "strong"
    if score >= 40:
        return "moderate"
    return "weak"
