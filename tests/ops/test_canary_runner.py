import json
from pathlib import Path

from src.engines.base import EngineResponse


def test_run_canary_check_skips_without_provider_key(tmp_path: Path):
    from src.ops.canary_runner import run_canary_check

    result = run_canary_check(
        provider="openai",
        api_keys={},
        snapshot_path=tmp_path / "snapshot.json",
    )

    assert result["status"] == "skipped"
    assert result["snapshot_path"] is None


def test_run_canary_check_saves_snapshot_and_compares_baseline(monkeypatch, tmp_path: Path):
    from src.ops import canary_runner

    prompts_path = tmp_path / "canary_prompts.yaml"
    prompts_path.write_text(
        "version: weekly_v1\nprompts:\n"
        "  - id: local_discovery\n"
        "    cluster: discovery\n"
        "    template: 'What are the best {industry} businesses in {city}?'\n"
    )

    outputs = iter(
        [
            "Laveta Coffee is a strong local option with direct citations.",
            "This answer now prefers generic national chains and omits the local citations entirely.",
        ]
    )

    class StubQuerier:
        def __init__(self, api_keys):
            self.api_keys = api_keys

        def query_structured(self, provider, prompt):
            return EngineResponse(
                provider=provider,
                prompt=prompt,
                raw_text=next(outputs),
                latency_ms=120,
                metadata={"model": "stub"},
            )

    monkeypatch.setattr(canary_runner, "LLMQuerier", StubQuerier)

    baseline_path = tmp_path / "baseline.json"
    current_path = tmp_path / "current.json"

    baseline = canary_runner.run_canary_check(
        provider="openai",
        api_keys={"openai": "test-key"},
        snapshot_path=baseline_path,
        canary_prompts_path=prompts_path,
        business_name="Laveta Coffee",
        industry="coffee shop",
        city="Echo Park, Los Angeles",
    )
    current = canary_runner.run_canary_check(
        provider="openai",
        api_keys={"openai": "test-key"},
        snapshot_path=current_path,
        baseline_snapshot_path=baseline_path,
        canary_prompts_path=prompts_path,
        business_name="Laveta Coffee",
        industry="coffee shop",
        city="Echo Park, Los Angeles",
        delta_threshold=5,
    )

    assert baseline["status"] == "completed"
    assert json.loads(baseline_path.read_text())["version"] == "weekly_v1"
    assert current["status"] == "completed"
    assert current["comparison"]["drift_classification"] == "external_drift"
    assert current["comparison"]["max_canary_delta"] > 5
