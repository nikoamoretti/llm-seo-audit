from pathlib import Path

import yaml


def test_ci_workflow_runs_benchmarks_and_scheduled_canary():
    workflow = yaml.safe_load(Path(".github/workflows/ci.yml").read_text())

    assert "schedule" in workflow["on"]
    assert workflow["on"]["schedule"]

    jobs = workflow["jobs"]
    assert "test" in jobs
    assert "canary" in jobs

    test_steps = jobs["test"]["steps"]
    test_runs = "\n".join(step.get("run", "") for step in test_steps)
    assert "playwright install --with-deps chromium" in test_runs
    assert "run_benchmarks" in test_runs

    canary_steps = jobs["canary"]["steps"]
    canary_runs = "\n".join(step.get("run", "") for step in canary_steps)
    assert "run_canary_check" in canary_runs
