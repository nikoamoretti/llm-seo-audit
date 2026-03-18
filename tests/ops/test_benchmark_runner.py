import json
from pathlib import Path

from src.ops.benchmark_runner import (
    load_canary_prompts,
    run_benchmarks,
    save_canary_snapshot,
)
from src.ops.regression_report import build_regression_report


def test_benchmark_runner_replays_fixture_businesses_offline(tmp_path: Path):
    businesses_path = tmp_path / "businesses.json"
    expected_patterns_path = tmp_path / "expected_patterns.json"
    canary_prompts_path = tmp_path / "canary_prompts.yaml"

    businesses_path.write_text(
        json.dumps(
            [
                {
                    "id": "laveta_echo_park",
                    "business_name": "Laveta Coffee",
                    "industry": "coffee shop",
                    "city": "Echo Park, Los Angeles",
                    "website_url": "https://lavetacoffee.com",
                    "fixture_profile": "strong_local",
                    "competitors": ["Woodcat Coffee", "Stereoscope Coffee"],
                },
                {
                    "id": "acme_plumbing_austin",
                    "business_name": "Acme Plumbing",
                    "industry": "plumber",
                    "city": "Austin, TX",
                    "website_url": "https://acmeplumbing.example",
                    "fixture_profile": "competitor_heavy",
                    "competitors": ["A-Team Plumbing", "Capital Flow Plumbing"],
                },
            ]
        )
    )
    expected_patterns_path.write_text(
        json.dumps(
            {
                "defaults": {"max_score_delta": 8},
                "businesses": {
                    "laveta_echo_park": {
                        "expected_band": "strong",
                        "expected_top_competitors": ["Woodcat Coffee"],
                        "expected_recommendation_keywords": [],
                    },
                    "acme_plumbing_austin": {
                        "expected_band": "weak",
                        "expected_top_competitors": ["A-Team Plumbing"],
                        "expected_recommendation_keywords": ["Expand pages", "Close the answer-space gap"],
                    },
                },
            }
        )
    )
    canary_prompts_path.write_text(
        "version: weekly_v1\nprompts:\n  - id: local_discovery\n    cluster: discovery\n    template: 'What are the best {industry} businesses in {city}?'\n"
    )

    result = run_benchmarks(
        businesses_path=businesses_path,
        expected_patterns_path=expected_patterns_path,
        canary_prompts_path=canary_prompts_path,
    )

    assert result["summary"]["business_count"] == 2
    assert result["summary"]["canary_prompt_count"] == 1
    assert result["summary"]["flagged_count"] == 0
    assert load_canary_prompts(canary_prompts_path)["version"] == "weekly_v1"
    laveta = next(item for item in result["results"] if item["business_id"] == "laveta_echo_park")
    assert laveta["pattern_checks"]["score_band"] is True
    assert laveta["pattern_checks"]["top_competitors"] is True


def test_regression_reporting_flags_score_deltas_and_distinguishes_drift(tmp_path: Path):
    businesses_path = tmp_path / "businesses.json"
    expected_patterns_path = tmp_path / "expected_patterns.json"

    businesses_path.write_text(
        json.dumps(
            [
                {
                    "id": "laveta_echo_park",
                    "business_name": "Laveta Coffee",
                    "industry": "coffee shop",
                    "city": "Echo Park, Los Angeles",
                    "website_url": "https://lavetacoffee.com",
                    "fixture_profile": "strong_local",
                    "competitors": ["Woodcat Coffee", "Stereoscope Coffee"],
                }
            ]
        )
    )
    expected_patterns_path.write_text(
        json.dumps(
            {
                "defaults": {"max_score_delta": 5},
                "businesses": {
                    "laveta_echo_park": {
                        "expected_band": "strong",
                        "baseline_scores": {"final": 25, "readiness": 25, "visibility": 25},
                        "expected_top_competitors": ["Woodcat Coffee"],
                    }
                },
            }
        )
    )

    result = run_benchmarks(
        businesses_path=businesses_path,
        expected_patterns_path=expected_patterns_path,
        delta_threshold=5,
    )
    report = build_regression_report(result["results"], delta_threshold=5, canary_snapshot_deltas={"local_discovery": 12})
    stable_report = build_regression_report(
        [
            {
                "business_id": "stable_fixture",
                "flagged": False,
                "delta_flags": [],
            }
        ],
        delta_threshold=5,
        canary_snapshot_deltas={"local_discovery": 12},
    )

    assert result["summary"]["flagged_count"] == 1
    assert report["drift_classification"] == "parser_regression"
    assert stable_report["drift_classification"] == "external_drift"


def test_shipped_benchmark_dataset_is_stable():
    result = run_benchmarks()

    assert result["summary"]["business_count"] == 25
    assert result["summary"]["flagged_count"] == 0
    assert result["summary"]["drift_classification"] == "stable"


def test_canary_snapshot_drift_is_classified_from_saved_snapshots(tmp_path: Path):
    businesses_path = tmp_path / "businesses.json"
    expected_patterns_path = tmp_path / "expected_patterns.json"
    baseline_snapshot_path = tmp_path / "baseline_canary.json"
    current_snapshot_path = tmp_path / "current_canary.json"

    businesses_path.write_text(
        json.dumps(
            [
                {
                    "id": "laveta_echo_park",
                    "business_name": "Laveta Coffee",
                    "industry": "coffee shop",
                    "city": "Echo Park, Los Angeles",
                    "website_url": "https://lavetacoffee.com",
                    "fixture_profile": "strong_local",
                    "competitors": ["Woodcat Coffee", "Stereoscope Coffee"],
                }
            ]
        )
    )
    expected_patterns_path.write_text(
        json.dumps(
            {
                "defaults": {"max_score_delta": 5},
                "businesses": {
                    "laveta_echo_park": {
                        "expected_band": "strong",
                        "baseline_scores": {"final": 93, "readiness": 96, "visibility": 91.2},
                        "expected_top_competitors": ["Woodcat Coffee"],
                    }
                },
            }
        )
    )
    save_canary_snapshot(
        baseline_snapshot_path,
        version="weekly_v1",
        outputs=[
            {
                "id": "local_discovery",
                "provider": "openai",
                "prompt": "What are the best coffee shops in Echo Park, Los Angeles?",
                "raw_text": "Laveta Coffee is a strong local option with direct citations.",
            }
        ],
    )
    save_canary_snapshot(
        current_snapshot_path,
        version="weekly_v1",
        outputs=[
            {
                "id": "local_discovery",
                "provider": "openai",
                "prompt": "What are the best coffee shops in Echo Park, Los Angeles?",
                "raw_text": "This answer now prefers generic national chains and omits the local citations entirely.",
            }
        ],
    )

    result = run_benchmarks(
        businesses_path=businesses_path,
        expected_patterns_path=expected_patterns_path,
        baseline_canary_snapshot_path=baseline_snapshot_path,
        current_canary_snapshot_path=current_snapshot_path,
        delta_threshold=5,
    )

    assert result["summary"]["flagged_count"] == 0
    assert result["summary"]["max_canary_delta"] > 5
    assert result["summary"]["drift_classification"] == "external_drift"
