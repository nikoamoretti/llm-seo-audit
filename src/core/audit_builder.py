from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from src.core.models import (
    AuditRun,
    BusinessEntity,
    BusinessInput,
    CitationRecord,
    PromptResult,
)
from src.recommendations.rules import build_recommendations
from src.scoring.final import score_final
from src.scoring.readiness import score_readiness
from src.scoring.visibility import score_visibility


def build_audit_run(
    *,
    mode: str,
    business_name: str,
    industry: str,
    city: str,
    website_url: str | None,
    phone: str | None,
    web_presence: dict[str, Any],
    llm_results: dict[str, list[dict[str, Any]]],
    api_keys_used: list[str] | None = None,
    timestamp: str | datetime | None = None,
) -> AuditRun:
    prompt_results = prompt_results_from_llm_results(llm_results)
    readiness = score_readiness(web_presence)
    visibility = score_visibility(prompt_results)
    score = score_final(readiness, visibility, web_presence)

    audit_run = AuditRun(
        mode="demo" if mode == "demo" else "live",
        timestamp=_coerce_timestamp(timestamp),
        input=BusinessInput(
            business_name=business_name,
            industry=industry,
            city=city,
            website_url=website_url,
            phone=phone,
            demo=mode == "demo",
        ),
        entity=_build_entity(
            business_name=business_name,
            industry=industry,
            city=city,
            website_url=website_url,
            phone=phone,
            web_presence=web_presence,
        ),
        score=score,
        readiness=readiness,
        visibility=visibility,
        recommendations=[],
        web_presence=web_presence,
        api_keys_used=api_keys_used or [],
        queries=_collect_queries(prompt_results),
    )
    audit_run.recommendations = build_recommendations(audit_run)
    return audit_run


def prompt_results_from_llm_results(llm_results: dict[str, list[dict[str, Any]]]) -> list[PromptResult]:
    prompt_results: list[PromptResult] = []
    for provider, responses in llm_results.items():
        for response in responses:
            analysis = response.get("analysis", {})
            engine_response = response.get("engine_response", {})
            prompt_results.append(
                PromptResult(
                    provider=provider,
                    query=response.get("query", engine_response.get("prompt", "")),
                    cluster=response.get("cluster"),
                    response=response.get("response") or engine_response.get("raw_text"),
                    raw_text=engine_response.get("raw_text") or response.get("response"),
                    latency_ms=engine_response.get("latency_ms"),
                    metadata=_prompt_metadata(engine_response.get("metadata", {}), analysis),
                    mentioned=analysis.get("mentioned", False),
                    recommended=analysis.get("recommended", False),
                    cited=analysis.get("cited", False),
                    cited_official_domain=analysis.get("cited_official_domain", False),
                    cited_third_party_domain=analysis.get("cited_third_party_domain", False),
                    position=analysis.get("position"),
                    visibility_score=analysis.get("visibility_score", 0.0),
                    sentiment=analysis.get("sentiment"),
                    competitors=analysis.get("competitors", []),
                    attributes=analysis.get("attributes", []),
                    citations=[
                        CitationRecord(
                            label=str(citation.get("label", "")),
                            url=citation.get("url"),
                            domain=citation.get("domain"),
                            citation_type=citation.get("citation_type"),
                            is_official_domain=citation.get("is_official_domain"),
                        )
                        for citation in analysis.get("citations", [])
                        if isinstance(citation, dict)
                    ],
                )
            )
    return prompt_results


def _build_entity(
    *,
    business_name: str,
    industry: str,
    city: str,
    website_url: str | None,
    phone: str | None,
    web_presence: dict[str, Any],
) -> BusinessEntity:
    extracted = web_presence.get("extracted_entity")
    if isinstance(extracted, dict):
        payload = dict(extracted)
        # The submitted business_name is authoritative -- never let
        # web-extracted names (which may be Cloudflare titles) override it.
        payload["business_name"] = business_name
        payload.setdefault("industry", industry)
        payload.setdefault("city", city)
        payload.setdefault("website_url", website_url)
        payload.setdefault("phone", phone)
        return BusinessEntity.model_validate(payload)
    return BusinessEntity(
        business_name=business_name,
        industry=industry,
        city=city,
        website_url=website_url,
        phone=phone,
        service_areas=web_presence.get("service_areas", []) or [],
        service_names=web_presence.get("service_names", []) or [],
        trust_signals=web_presence.get("trust_signals", []) or [],
        has_booking_cta=web_presence.get("has_booking_cta"),
        has_contact_cta=web_presence.get("has_contact_cta"),
    )


def _collect_queries(prompt_results: list[PromptResult]) -> list[str]:
    queries: list[str] = []
    for prompt in prompt_results:
        if prompt.query and prompt.query not in queries:
            queries.append(prompt.query)
    return queries


def _prompt_metadata(engine_metadata: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(engine_metadata)
    for key in ("citation_evidence_state", "citation_parser_status", "citation_status", "competitor_candidates"):
        value = analysis.get(key)
        if value:
            metadata[key] = value
    return metadata


def _coerce_timestamp(timestamp: str | datetime | None) -> datetime:
    if isinstance(timestamp, datetime):
        return timestamp
    if isinstance(timestamp, str):
        return datetime.fromisoformat(timestamp)
    return datetime.now(UTC)
