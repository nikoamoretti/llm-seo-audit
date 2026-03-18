from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, cast

from src.core.models import (
    AuditRun,
    BusinessEntity,
    BusinessInput,
    CheckDimension,
    ClusterVisibility,
    CitationRecord,
    PromptResult,
    ProviderVisibility,
    ReadinessResult,
    Recommendation,
    ScoreBreakdown,
    VisibilityResult,
)


RECOMMENDATION_TEMPLATES = {
    "has_noindex": (
        "P0",
        "Website Access",
        "Your website is telling AI to ignore it",
        "A noindex directive is present on the site, so AI systems may skip this page entirely.",
        lambda _: ["web_presence.has_noindex=True"],
    ),
    "robots_blocked": (
        "P0",
        "Website Access",
        "Your website is blocking AI from reading it",
        "The current robots rules block crawlers from accessing the site content.",
        lambda _: ["web_presence.robots_allows_crawl=False"],
    ),
    "site_down": (
        "P0",
        "Website Access",
        "Your website is down or inaccessible",
        "The site did not load successfully during the audit, so AI systems cannot reliably read it.",
        lambda _: ["web_presence.website_accessible=False"],
    ),
    "google_missing": (
        "P0",
        "Online Listings",
        "You're not on Google Business Profile",
        "Google Business data was not found for this business in the audit.",
        lambda _: ["web_presence.google_business_found=False"],
    ),
    "visibility_low": (
        "P0",
        "AI Visibility",
        "AI assistants almost never mention your business",
        "The current visibility score is very low, so the business rarely appears in AI answers.",
        lambda audit_run: [f"score.visibility={audit_run.score.visibility}"],
    ),
    "schema_missing": (
        "P1",
        "Machine-Readable Info",
        "Add structured data so AI understands your business",
        "Structured data is missing, which makes it harder for machines to identify the business type and key details.",
        lambda _: ["web_presence.has_schema_markup=False"],
    ),
    "local_schema_missing": (
        "P1",
        "Machine-Readable Info",
        "Your structured data doesn't identify your business type",
        "The site has structured data, but it does not clearly label the business as a local entity type.",
        lambda _: [
            "web_presence.has_schema_markup=True",
            "web_presence.has_local_business_schema=False",
        ],
    ),
    "answer_blocks_missing": (
        "P1",
        "AI-Ready Content",
        "Add a Q&A section that AI can quote directly",
        "The site does not currently expose clear answer-style blocks that AI systems can quote back.",
        lambda _: ["web_presence.has_answer_blocks=False"],
    ),
    "yelp_missing": (
        "P1",
        "Online Listings",
        "You're not on Yelp",
        "Yelp data was not found for this business in the audit.",
        lambda _: ["web_presence.yelp_found=False"],
    ),
    "sitemap_missing": (
        "P1",
        "Website Access",
        "No sitemap found",
        "A sitemap was not detected, which limits how easily crawlers can discover the site's pages.",
        lambda _: ["web_presence.sitemap_exists=False"],
    ),
    "canonical_missing": (
        "P1",
        "Website Access",
        "Pages don't have a canonical URL set",
        "Canonical URLs were not detected, so duplicate URLs may dilute crawl signals.",
        lambda _: ["web_presence.has_canonical=False"],
    ),
    "ssl_missing": (
        "P1",
        "Trust & Speed",
        "Your site isn't secure (no HTTPS)",
        "HTTPS was not detected during the audit.",
        lambda _: ["web_presence.ssl_valid=False"],
    ),
    "meta_missing": (
        "P1",
        "AI-Ready Content",
        "Your site has no meta description",
        "A meta description was not detected on the site.",
        lambda _: ["web_presence.has_meta_description=False"],
    ),
    "faq_schema_missing": (
        "P2",
        "AI-Ready Content",
        "Add FAQ markup so AI can read your Q&As",
        "FAQ schema is missing, so question-and-answer content is less explicit to crawlers.",
        lambda _: ["web_presence.has_faq_schema=False"],
    ),
}


def adapt_legacy_result(result: dict[str, Any]) -> AuditRun:
    """Map the current app.py or audit.py dict payload into the canonical AuditRun."""
    if "scores" not in result:
        raise ValueError("Expected a legacy result with a 'scores' field.")

    if "geo_score" in result["scores"]:
        return _adapt_app_result(result)
    if "overall_score" in result["scores"]:
        return _adapt_audit_result(result)

    raise ValueError("Unsupported legacy result shape.")


def _adapt_app_result(result: dict[str, Any]) -> AuditRun:
    score_data = result["scores"]
    readiness = _adapt_readiness(score_data.get("readiness", {}), score_data.get("readiness_score", 0))
    visibility = _adapt_visibility_from_app(
        score_data.get("visibility", {}),
        result.get("llm_responses", {}),
    )
    audit_run = AuditRun(
        mode=result.get("mode", "live"),
        timestamp=_parse_timestamp(result.get("timestamp")),
        input=_business_input_from_result(result),
        entity=_business_entity_from_result(result),
        score=ScoreBreakdown(
            final=score_data.get("geo_score", 0),
            readiness=score_data.get("readiness_score", 0),
            visibility=score_data.get("visibility_score", 0),
            formula=score_data.get("formula"),
        ),
        readiness=readiness,
        visibility=visibility,
        recommendations=[],
        web_presence=result.get("web_presence", {}),
        api_keys_used=result.get("api_keys_used", result.get("api_keys_available", [])),
        queries=_collect_queries(result),
    )
    audit_run.recommendations = _build_recommendations(audit_run)
    return audit_run


def _adapt_audit_result(result: dict[str, Any]) -> AuditRun:
    score_data = result["scores"]
    readiness = ReadinessResult(score=score_data.get("web_presence_score", 0), dimensions={})
    visibility = _adapt_visibility_from_audit(
        score_data,
        result.get("llm_results", {}),
    )
    audit_run = AuditRun(
        mode=result.get("mode", "live"),
        timestamp=_parse_timestamp(result.get("timestamp")),
        input=_business_input_from_result(result),
        entity=_business_entity_from_result(result),
        score=ScoreBreakdown(
            final=score_data.get("overall_score", 0),
            readiness=score_data.get("web_presence_score", 0),
            visibility=score_data.get("llm_visibility_score", 0),
            formula="0.70 × Visibility + 0.30 × Web Presence",
        ),
        readiness=readiness,
        visibility=visibility,
        recommendations=[],
        web_presence=result.get("web_presence", {}),
        api_keys_used=result.get("api_keys_used", result.get("api_keys_available", [])),
        queries=_collect_queries(result),
    )
    audit_run.recommendations = _build_recommendations(audit_run)
    return audit_run


def _business_input_from_result(result: dict[str, Any]) -> BusinessInput:
    return BusinessInput(
        business_name=result.get("business_name", ""),
        industry=result.get("industry", ""),
        city=result.get("city", ""),
        website_url=result.get("website_url"),
        phone=result.get("phone"),
        demo=result.get("mode") == "demo",
    )


def _business_entity_from_result(result: dict[str, Any]) -> BusinessEntity:
    return BusinessEntity(
        business_name=result.get("business_name", ""),
        industry=result.get("industry", ""),
        city=result.get("city", ""),
        website_url=result.get("website_url"),
        phone=result.get("phone"),
        address=result.get("address"),
    )


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return datetime.utcnow()


def _adapt_readiness(readiness_data: dict[str, Any], score: int) -> ReadinessResult:
    dimensions = {}
    for key, value in readiness_data.items():
        if key == "R":
            continue
        if isinstance(value, dict):
            dimensions[key] = CheckDimension(
                score=value.get("score", 0),
                label=value.get("label", key),
                description=value.get("description", ""),
                checks=value.get("checks", {}),
            )
    return ReadinessResult(score=score, dimensions=dimensions)


def _adapt_visibility_from_app(
    visibility_data: dict[str, Any],
    llm_responses: dict[str, list[dict[str, Any]]],
) -> VisibilityResult:
    per_llm = {
        provider: ProviderVisibility.model_validate(data)
        for provider, data in visibility_data.get("per_llm", {}).items()
    }
    per_cluster = {
        cluster: ClusterVisibility.model_validate(data)
        for cluster, data in visibility_data.get("per_cluster", {}).items()
    }
    return VisibilityResult(
        score=visibility_data.get("V", 0),
        overall_mention_rate=visibility_data.get("overall_mention_rate", 0),
        per_llm=per_llm,
        per_cluster=per_cluster,
        top_competitors=visibility_data.get("top_competitors", {}),
        attributes_cited=visibility_data.get("attributes_cited", []),
        prompt_results=_prompt_results_from_app(llm_responses),
    )


def _adapt_visibility_from_audit(
    score_data: dict[str, Any],
    llm_results: dict[str, list[dict[str, Any]]],
) -> VisibilityResult:
    per_llm = {
        provider: ProviderVisibility(
            visibility_score=data.get("score", 0),
            mention_rate=data.get("mention_rate", 0),
            citation_rate=0,
            avg_position=data.get("avg_position"),
            total_queries=data.get("total_queries", 0),
            times_mentioned=data.get("times_mentioned", 0),
            times_cited=0,
            top_competitors=data.get("top_competitors", {}),
            attributes_cited=data.get("attributes_cited", []),
        )
        for provider, data in score_data.get("per_llm", {}).items()
    }
    return VisibilityResult(
        score=score_data.get("llm_visibility_score", 0),
        overall_mention_rate=score_data.get("overall_mention_rate", 0),
        per_llm=per_llm,
        per_cluster={},
        top_competitors=score_data.get("top_competitors", {}),
        attributes_cited=score_data.get("attributes_cited", []),
        prompt_results=_prompt_results_from_audit(llm_results),
    )


def _prompt_results_from_app(llm_responses: dict[str, list[dict[str, Any]]]) -> list[PromptResult]:
    prompt_results = []
    for provider, responses in llm_responses.items():
        for response in responses:
            analysis = _analysis_payload(response)
            engine_response = _engine_response_payload(response, provider=provider)
            prompt_results.append(
                PromptResult(
                    provider=provider,
                    query=response.get("query", engine_response.get("prompt", "")),
                    cluster=response.get("cluster"),
                    response=response.get("response") or engine_response.get("raw_text"),
                    raw_text=engine_response.get("raw_text") or response.get("response"),
                    latency_ms=engine_response.get("latency_ms"),
                    metadata=engine_response.get("metadata", {}),
                    mentioned=analysis.get("mentioned", False),
                    recommended=analysis.get("recommended", False),
                    cited=analysis.get("cited", False),
                    cited_official_domain=analysis.get("cited_official_domain", False),
                    cited_third_party_domain=analysis.get("cited_third_party_domain", False),
                    position=analysis.get("position"),
                    visibility_score=analysis.get("visibility_score", 0),
                    sentiment=analysis.get("sentiment"),
                    competitors=analysis.get("competitors", []),
                    attributes=analysis.get("attributes", []),
                    citations=_citation_records(analysis.get("citations", [])),
                )
            )
    return prompt_results


def _prompt_results_from_audit(llm_results: dict[str, list[dict[str, Any]]]) -> list[PromptResult]:
    prompt_results = []
    for provider, responses in llm_results.items():
        for response in responses:
            analysis = _analysis_payload(response)
            engine_response = _engine_response_payload(response, provider=provider)
            prompt_results.append(
                PromptResult(
                    provider=provider,
                    query=response.get("query", engine_response.get("prompt", "")),
                    cluster=response.get("cluster"),
                    response=response.get("response") or engine_response.get("raw_text"),
                    raw_text=engine_response.get("raw_text") or response.get("response"),
                    latency_ms=engine_response.get("latency_ms"),
                    metadata=engine_response.get("metadata", {}),
                    mentioned=analysis.get("mentioned", False),
                    recommended=analysis.get("recommended", False),
                    cited=analysis.get("cited", False),
                    cited_official_domain=analysis.get("cited_official_domain", False),
                    cited_third_party_domain=analysis.get("cited_third_party_domain", False),
                    position=analysis.get("position"),
                    visibility_score=analysis.get("visibility_score", 0),
                    sentiment=analysis.get("sentiment"),
                    competitors=analysis.get("competitors", []),
                    attributes=analysis.get("attributes", []),
                    citations=_citation_records(analysis.get("citations", [])),
                )
            )
    return prompt_results


def _analysis_payload(response: dict[str, Any]) -> dict[str, Any]:
    analysis = response.get("analysis")
    if isinstance(analysis, dict):
        return analysis
    return response


def _engine_response_payload(response: dict[str, Any], provider: str) -> dict[str, Any]:
    engine_response = response.get("engine_response")
    if isinstance(engine_response, dict):
        return engine_response
    return {
        "provider": provider,
        "prompt": response.get("query", ""),
        "raw_text": response.get("response"),
        "metadata": {},
    }


def _citation_records(citations: list[dict[str, Any]]) -> list[CitationRecord]:
    records = []
    for citation in citations:
        if not isinstance(citation, dict):
            continue
        records.append(
            CitationRecord(
                label=str(citation.get("label", "")),
                url=citation.get("url"),
                domain=citation.get("domain"),
                citation_type=citation.get("citation_type"),
                is_official_domain=citation.get("is_official_domain"),
            )
        )
    return records


def _collect_queries(result: dict[str, Any]) -> list[str]:
    if result.get("queries"):
        return list(result["queries"])

    if "llm_responses" in result:
        queries = []
        for responses in result["llm_responses"].values():
            for response in responses:
                query = response.get("query")
                if query and query not in queries:
                    queries.append(query)
        return queries

    if "llm_results" in result:
        queries = []
        for responses in result["llm_results"].values():
            for response in responses:
                query = response.get("query")
                if query and query not in queries:
                    queries.append(query)
        return queries

    return []


def _build_recommendations(audit_run: AuditRun) -> list[Recommendation]:
    web_presence = audit_run.web_presence
    recommendations = []

    def add(template_key: str):
        priority, category, title, detail, evidence_fn = RECOMMENDATION_TEMPLATES[template_key]
        recommendations.append(
            Recommendation(
                priority=cast(Literal["P0", "P1", "P2"], priority),
                category=category,
                title=title,
                detail=detail,
                evidence=evidence_fn(audit_run),
            )
        )

    if web_presence.get("has_noindex"):
        add("has_noindex")
    if web_presence.get("robots_allows_crawl") is False:
        add("robots_blocked")
    if web_presence and web_presence.get("website_accessible") is False:
        add("site_down")
    if web_presence.get("google_business_found") is False:
        add("google_missing")
    if audit_run.score.visibility < 15:
        add("visibility_low")
    if web_presence.get("has_schema_markup") is False:
        add("schema_missing")
    if web_presence.get("has_local_business_schema") is False and web_presence.get("has_schema_markup"):
        add("local_schema_missing")
    if web_presence and web_presence.get("has_answer_blocks") is False:
        add("answer_blocks_missing")
    if web_presence.get("yelp_found") is False:
        add("yelp_missing")
    if web_presence and web_presence.get("sitemap_exists") is False:
        add("sitemap_missing")
    if web_presence and web_presence.get("has_canonical") is False:
        add("canonical_missing")
    if web_presence and web_presence.get("ssl_valid") is False:
        add("ssl_missing")
    if web_presence and web_presence.get("has_meta_description") is False:
        add("meta_missing")
    if web_presence and web_presence.get("has_faq_schema") is False:
        add("faq_schema_missing")

    if audit_run.visibility.top_competitors:
        top = list(audit_run.visibility.top_competitors.keys())[:3]
        recommendations.append(
            Recommendation(
                priority="P2",
                category="AI Visibility",
                title=f"Study what these competitors are doing right: {', '.join(top)}",
                detail="These competitors are appearing in AI answers more often than your business.",
                evidence=[f"visibility.top_competitors={', '.join(top)}"],
            )
        )

    weak_cluster = None
    weak_score = None
    for cluster_name, cluster in audit_run.visibility.per_cluster.items():
        if weak_score is None or cluster.avg_score < weak_score:
            weak_cluster = cluster_name
            weak_score = cluster.avg_score
    if weak_cluster and weak_score is not None and weak_score < 30:
        recommendations.append(
            Recommendation(
                priority="P1",
                category="AI Visibility",
                title=f"You're weakest when people ask {weak_cluster.replace('_', ' ')} questions",
                detail="One query cluster is consistently underperforming, which signals a visibility gap for that intent.",
                evidence=[f"visibility.per_cluster.{weak_cluster}.avg_score={weak_score}"],
            )
        )

    return recommendations
