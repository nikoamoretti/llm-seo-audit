from __future__ import annotations

from typing import Any


def build_regression_report(
    results: list[dict[str, Any]],
    *,
    delta_threshold: int,
    canary_snapshot_deltas: dict[str, int] | None = None,
) -> dict[str, Any]:
    flagged = [result for result in results if result.get("flagged")]
    canary_snapshot_deltas = canary_snapshot_deltas or {}
    max_score_delta = max(
        [
            max((abs(float(delta)) for delta in result.get("score_deltas", {}).values()), default=0.0)
            for result in results
        ]
        or [0.0]
    )
    max_canary_delta = max((abs(delta) for delta in canary_snapshot_deltas.values()), default=0)

    if flagged:
        drift_classification = "parser_regression"
    elif max_canary_delta > delta_threshold:
        drift_classification = "external_drift"
    else:
        drift_classification = "stable"

    return {
        "business_count": len(results),
        "flagged_count": len(flagged),
        "flagged_business_ids": [result.get("business_id") for result in flagged],
        "max_score_delta": round(max_score_delta, 1),
        "max_canary_delta": max_canary_delta,
        "drift_classification": drift_classification,
    }
