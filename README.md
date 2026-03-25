# LLM SEO Audit

This repo audits a business's AI visibility across LLMs and web-presence signals.

## Setup

Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## API keys / Fly secrets

The following environment variables are used. On Fly.io, set them as secrets:

| Variable | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes (or OpenAI) | LLM prompt querying (Claude) |
| `OPENAI_API_KEY` | Yes (or Anthropic) | LLM prompt querying (GPT) |
| `BROWSERBASE_API_KEY` | Optional | Remote browser for Cloudflare-blocked sites |
| `BROWSERBASE_PROJECT_ID` | Optional | Remote browser project ID |
| `GOOGLE_PLACES_API_KEY` | Optional | Google Business directory checks and lookup |
| `YELP_API_KEY` | Optional | Yelp directory checks |

If a key is missing, the audit gracefully degrades:
- Without Browserbase, Cloudflare-blocked sites show as **unavailable** rather than returning fake data from block pages.
- Without directory API keys, those checks show as `NOT CHECKED`.

End users install nothing -- all browser work is server-side via Browserbase's managed Chromium instances. The `connect_over_cdp` approach means no local browser binary is needed in the Docker image.

### Honest fallback behavior

When a site is protected by Cloudflare or another WAF:
1. The direct HTTP fetch detects the block page (Cloudflare markers, captcha, interstitial titles).
2. If Browserbase is configured, the fetch retries through a remote browser session with proxies.
3. If both methods fail or Browserbase is not configured, readiness checks for that site are marked **unavailable** (not failed). This prevents garbage WAF HTML from being parsed as business content.

## Sprint 1 architecture

The active app/report path now centers on one canonical audit object:

- `src/core/models.py` defines the canonical `AuditRun` schema.
- `src/core/legacy_adapter.py` maps the current app/CLI raw payloads into that schema during migration.
- `report_generator.py` consumes only the canonical model.

## Sprint 2 crawl layer

Website readiness is now derived from a small crawl layer instead of homepage-only heuristics:

- `src/crawl/` fetches the homepage, navigation pages, and sitemap-backed internal URLs within a crawl budget.
- `src/entity/` extracts business facts, FAQs, trust signals, schema types, and CTA signals across pages.
- `web_presence.py` remains the compatibility shim that aggregates those multi-page facts into the existing readiness keys.

Fixture-backed crawl coverage lives under `tests/fixtures/sites/` so discovery and extraction stay deterministic.

## Sprint 3 prompt profiles

Prompt generation is now config-driven instead of hardcoded in `app.py`:

- `config/prompt_profiles/` stores the default prompt profile plus vertical overrides for dentists, plumbers, and lawyers.
- `src/prompts/loader.py` selects and merges the right profile for the business category.
- `src/prompts/renderer.py` renders prompts with `business_name`, `industry`, `city`, `service_area`, and optional competitors.
- `src/prompts/coverage.py` reports cluster counts and missing required clusters.

This keeps prompt changes out of the runtime code and makes vertical-specific prompt coverage testable.

## Sprint 4 engine and analysis evidence

LLM query execution and response parsing now use structured adapters and analysis modules:

- `src/engines/` normalizes provider calls into one response shape with `provider`, `prompt`, `raw_text`, `latency_ms`, and `metadata`.
- `llm_querier.py` is now a compatibility wrapper over `src/engines/runner.py` instead of owning provider-specific API logic.
- `src/analysis/` separates mention detection, citation extraction, position detection, competitor extraction, fact alignment, and compatibility visibility scoring.
- `analyzer.py` is now a thin facade that returns structured citation objects and citation-domain flags while preserving the legacy fields still used by scoring and reports.
- `PromptResult` in the canonical `AuditRun` now stores citation records plus engine metadata such as latency and model information when available.

## Sprint 5 scoring and recommendation engine

The active score path now uses one versioned scoring system and one evidence-linked recommendation system:

- `config/score_v2.yaml` stores readiness weights, visibility weights, penalties, and thresholds.
- `src/scoring/` calculates v2 readiness, visibility, and final score breakdowns from observed crawl and response evidence.
- `src/core/audit_builder.py` assembles the canonical `AuditRun` directly for both API and CLI flows, so the active path no longer depends on legacy score shaping.
- `src/recommendations/` generates recommendations only from observed evidence and ties each one to impacted score components plus an implementation hint.
- `report_generator.py` now renders score explanation tables and recommendation evidence instead of only a flat score summary.

## Sprint 6 benchmarks and drift safety

The repo now includes an offline benchmark and regression harness so score and parser changes can be checked before they ship:

- `benchmarks/businesses.json` contains a 25-business SMB benchmark set across multiple verticals and visibility profiles.
- `benchmarks/expected_patterns.json` stores expected score bands, competitor patterns, recommendation keywords, penalties, and baseline scores for those fixtures.
- `src/ops/benchmark_runner.py` replays fixture audits offline through the canonical `AuditRun` builder and flags score or pattern drift.
- `src/ops/regression_report.py` summarizes benchmark deltas and separates fixture regressions from canary-only engine drift.
- `config/canary_prompts.yaml` defines a stable weekly prompt set for monitoring engine-output drift outside the fixture benchmark.
- `src/ops/benchmark_runner.py` also stores and compares canary snapshots so weekly runs can distinguish parser regressions from upstream engine drift.

Run the benchmark harness with:

```bash
python - <<'PY'
from pprint import pprint
from src.ops.benchmark_runner import run_benchmarks

pprint(run_benchmarks()["summary"])
PY
```

## Sprint 7 UI and report productization

The API now returns a presentation wrapper for the browser UI instead of a raw `AuditRun` payload:

- `audit` carries the canonical audit object.
- `summary` provides the executive headline, overview, wins, losses, and partial-data notes.
- `score_cards` exposes the UI-ready top-line metrics.
- `prompt_cluster_performance`, `citation_source_breakdown`, `top_competitors`, `readiness_gaps`, `top_recommendations`, and `implementation_checklist` drive the report and browser presentation layer.

The HTML report and browser UI now focus on:

- executive summary
- wins and losses by prompt cluster
- official-site vs third-party citation picture
- competitor gap
- top fixes and implementation checklist

The new browser/report layer is presentation-only. It does not change score_v2 behavior.

The browser UI renderer in `ui.html` is now split into section helpers instead of one large result builder, and the E2E tests under `tests/e2e/` now run in a real Chromium browser via Playwright.

## Sprint 8 Browserbase integration

Sites behind Cloudflare or other WAFs now get honest handling instead of garbage extraction:

- `src/crawl/remote_browser.py` wraps the Browserbase SDK to fetch pages through a managed remote browser with proxies.
- `src/crawl/fetcher.py` detects blocked/interstitial pages after the direct HTTP fetch and retries through Browserbase when configured.
- `FetchResult` and `CrawlPage` now carry `fetch_method` ("direct", "browserbase", "unavailable") and `blocked` fields.
- `web_presence.py` skips entity extraction from blocked pages and marks all readiness checks as unavailable (None) rather than failing them (False).
- `src/entity/reconciler.py` now uses the user-submitted business name as the canonical name, keeping extracted names in metadata only.
- `src/core/audit_builder.py` and `src/presentation/view_model.py` enforce this so Cloudflare titles never appear in headlines.
- `app.py` adds a `GET /health` endpoint returning `{"status": "ok"}`.

## CI and canaries

- `.github/workflows/ci.yml` now runs the offline benchmark suite on every push and pull request.
- The same workflow schedules a weekly canary job and can also run it manually with `workflow_dispatch`.
- The canary job uses `src/ops/canary_runner.py` and expects `OPENAI_API_KEY` to be configured as a GitHub Actions secret if you want live snapshot generation.
- Local browser E2E requires Chromium once per machine:

```bash
python -m playwright install chromium
```

## Running

CLI:

```bash
python audit.py "Business Name" "industry" "City, State" --url https://example.com
```

API:

```bash
uvicorn app:app --reload
```

## Dev checks

```bash
pytest
ruff check .
mypy
```
