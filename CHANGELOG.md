# Changelog

## Unreleased

### Added
- Canonical `AuditRun` models under `src/core/models.py`.
- Legacy adapter that maps current app and CLI payloads into the canonical schema.
- Sprint 1 test scaffolding for boot, model round-tripping, adapter behavior, and report rendering.
- CI, pytest, ruff, and mypy configuration.
- Crawl discovery, fetcher, classifier, and models under `src/crawl/`.
- Multi-page entity extraction and reconciliation under `src/entity/`.
- Fixture-backed SMB site test coverage for discovery, extraction, reconciliation, and the `web_presence` shim.
- YAML prompt profiles under `config/prompt_profiles/` for default, dentist, plumber, and lawyer verticals.
- Prompt profile loading, rendering, and coverage reporting under `src/prompts/`.
- Prompt-system tests for profile selection, rendering, app integration, and coverage warnings.
- Structured engine adapters and runner under `src/engines/`.
- Structured response-analysis modules under `src/analysis/`.
- Golden response fixtures plus engine and analysis contract tests for Sprint 4.
- Versioned score config under `config/score_v2.yaml`.
- Score_v2 modules under `src/scoring/` for readiness, visibility, and final score calculation.
- Evidence-linked recommendation rules and explainer under `src/recommendations/`.
- Sprint 5 test coverage for score config loading, readiness scoring, visibility scoring, final penalties, and recommendation traceability.
- Offline benchmark dataset under `benchmarks/` with 25 SMB fixtures plus expected score and pattern baselines.
- Benchmark and regression reporting helpers under `src/ops/`.
- Canary prompt set under `config/canary_prompts.yaml` for weekly engine-drift monitoring.
- Sprint 6 test coverage for benchmark replay, shipped benchmark stability, regression drift classification, and canary snapshot comparison.
- Presentation-layer models under `src/presentation/` for UI and report shaping.
- Sprint 7 end-to-end tests for demo and live audit presentation flows.
- Playwright-based browser E2E support plus a canary runner under `src/ops/canary_runner.py`.

### Changed
- `/api/audit` now serves the canonical audit data through the active UI-facing response contract instead of legacy score dictionaries.
- `report_generator.py` now renders only from the canonical audit schema.
- Saved report JSON is now emitted from the canonical model instead of the legacy dict shape.
- `web_presence.py` now aggregates multi-page crawl facts while keeping its existing flat compatibility output.
- `app.py` now builds prompts from vertical-specific YAML profiles instead of a hardcoded prompt bank.
- `llm_querier.py` now delegates to normalized provider adapters instead of provider-specific inline query code.
- `analyzer.py` now acts as a facade over dedicated mention, citation, position, competitor, and fact-alignment modules.
- The active app and CLI paths now preserve structured engine metadata and citation objects instead of reducing responses to plain text and boolean citation flags.
- The active app and CLI paths now build `AuditRun` directly through score_v2 instead of routing live scoring through legacy score dictionaries.
- Recommendation copy is now evidence-linked and no longer includes unsupported percentage claims.
- HTML reports now include score explanation tables plus recommendation evidence, impacted components, and implementation hints.
- `src/core/audit_builder.py` now stamps canonical audit timestamps with timezone-aware UTC datetimes.
- The shipped benchmark expectations now include baseline scores so benchmark runs measure real deltas instead of only score-band heuristics.
- Benchmark summaries can now classify external drift directly from saved canary snapshots instead of only injected delta fixtures.
- `/api/audit` now returns a presentation wrapper with the canonical audit plus summary, score cards, prompt-cluster performance, citation breakdown, readiness gaps, top recommendations, and checklist data for the UI.
- `report_generator.py` and `ui.html` now emphasize executive summary, cluster wins/losses, citation mix, competitor gap, top fixes, and implementation checklist sections instead of raw debug-style tables.
- The browser UI render path is now split into section helpers, and CI now installs Chromium, runs the benchmark suite on push, and schedules a weekly canary snapshot job.
