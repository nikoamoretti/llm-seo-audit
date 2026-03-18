from __future__ import annotations

from pathlib import Path
from typing import Any

from analyzer import ResponseAnalyzer
from llm_querier import LLMQuerier
from src.ops.benchmark_runner import (
    compare_canary_snapshots,
    load_canary_prompts,
    load_canary_snapshot,
    save_canary_snapshot,
)
from src.ops.regression_report import build_regression_report


def build_canary_prompts(
    canary_prompts_path: Path,
    *,
    business_name: str,
    industry: str,
    city: str,
) -> tuple[str, list[dict[str, str]]]:
    config = load_canary_prompts(canary_prompts_path)
    prompts = []
    for prompt in config.get("prompts", []):
        if not isinstance(prompt, dict):
            continue
        template = str(prompt.get("template", ""))
        prompts.append(
            {
                "id": str(prompt.get("id", "")),
                "cluster": str(prompt.get("cluster", "")),
                "prompt": template.format(
                    business_name=business_name,
                    industry=industry,
                    city=city,
                ),
            }
        )
    return str(config.get("version", "unknown")), prompts


def run_canary_check(
    *,
    provider: str,
    api_keys: dict[str, str],
    snapshot_path: Path,
    baseline_snapshot_path: Path | None = None,
    canary_prompts_path: Path | None = None,
    business_name: str = "Laveta Coffee",
    industry: str = "coffee shop",
    city: str = "Echo Park, Los Angeles",
    delta_threshold: int = 8,
) -> dict[str, Any]:
    if provider not in api_keys:
        return {
            "status": "skipped",
            "reason": f"Missing API key for provider '{provider}'.",
            "snapshot_path": None,
        }

    if canary_prompts_path is None:
        raise ValueError("canary_prompts_path is required.")

    version, prompts = build_canary_prompts(
        canary_prompts_path,
        business_name=business_name,
        industry=industry,
        city=city,
    )
    known_facts = {
        "city": city,
        "industry": industry,
    }
    analyzer = ResponseAnalyzer(business_name, known_facts=known_facts)
    querier = LLMQuerier(api_keys)

    outputs = []
    for prompt in prompts:
        engine_response = querier.query_structured(provider, prompt["prompt"])
        analysis = analyzer.analyze_response(engine_response.raw_text, prompt["prompt"])
        outputs.append(
            {
                "id": prompt["id"],
                "cluster": prompt["cluster"],
                "provider": provider,
                "prompt": prompt["prompt"],
                "raw_text": engine_response.raw_text,
                "latency_ms": engine_response.latency_ms,
                "metadata": engine_response.metadata,
                "analysis": analysis,
            }
        )

    save_canary_snapshot(snapshot_path, version=version, outputs=outputs)

    comparison: dict[str, Any] | None = None
    if baseline_snapshot_path and baseline_snapshot_path.exists():
        deltas = compare_canary_snapshots(
            load_canary_snapshot(baseline_snapshot_path),
            load_canary_snapshot(snapshot_path),
        )
        comparison = build_regression_report(
            [],
            delta_threshold=delta_threshold,
            canary_snapshot_deltas=deltas,
        )

    return {
        "status": "completed",
        "snapshot_path": str(snapshot_path),
        "prompt_count": len(outputs),
        "comparison": comparison,
    }
