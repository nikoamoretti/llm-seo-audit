from __future__ import annotations

from collections import Counter
from typing import Literal

from pydantic import Field

from src.core.models import AuditRun, CanonicalModel, Recommendation


CLUSTER_LABELS = {
    "branded": "Branded Search",
    "discovery": "Discovery",
    "comparison": "Comparison",
    "urgency": "Urgency",
    "trust": "Trust",
    "price": "Price",
    "symptom_problem": "Problem/Symptom",
    "follow_up": "Follow-up",
    "head": '"Best of" Questions',
    "mid_tail": "Specific Needs",
}


class AuditSummary(CanonicalModel):
    headline: str
    overview: str
    wins: list[str] = Field(default_factory=list)
    losses: list[str] = Field(default_factory=list)
    data_notes: list[str] = Field(default_factory=list)


class ScoreCard(CanonicalModel):
    key: str
    label: str
    score: float
    status: Literal["strong", "mixed", "weak", "unknown"]
    detail: str


class PromptClusterPerformance(CanonicalModel):
    cluster: str
    label: str
    score: float
    query_count: int
    status: Literal["strong", "mixed", "weak", "unknown"]
    summary: str


class CompetitorEntry(CanonicalModel):
    name: str
    mentions: int


class DomainCitationEntry(CanonicalModel):
    domain: str
    citations: int


class CitationSourceBreakdown(CanonicalModel):
    official_site_share: int
    official_citation_count: int
    third_party_citation_count: int
    uncited_prompt_count: int
    top_third_party_domains: list[DomainCitationEntry] = Field(default_factory=list)
    note: str = ""


class ReadinessGap(CanonicalModel):
    key: str
    label: str
    score: int
    summary: str
    missing_checks: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class ChecklistItem(CanonicalModel):
    priority: Literal["P0", "P1", "P2"]
    category: str
    title: str
    implementation_hint: str
    evidence: list[str] = Field(default_factory=list)


class AuditUIResponse(CanonicalModel):
    audit: AuditRun
    summary: AuditSummary
    score_cards: list[ScoreCard] = Field(default_factory=list)
    prompt_cluster_performance: list[PromptClusterPerformance] = Field(default_factory=list)
    top_competitors: list[CompetitorEntry] = Field(default_factory=list)
    citation_source_breakdown: CitationSourceBreakdown
    readiness_gaps: list[ReadinessGap] = Field(default_factory=list)
    top_recommendations: list[Recommendation] = Field(default_factory=list)
    implementation_checklist: list[ChecklistItem] = Field(default_factory=list)


def build_audit_ui_response(audit_run: AuditRun) -> AuditUIResponse:
    citation_breakdown = _build_citation_breakdown(audit_run)
    cluster_performance = _build_cluster_performance(audit_run)
    readiness_gaps = _build_readiness_gaps(audit_run)
    top_competitors = [
        CompetitorEntry(name=name, mentions=mentions)
        for name, mentions in list(audit_run.visibility.top_competitors.items())[:10]
    ]
    top_recommendations = audit_run.recommendations[:10]
    implementation_checklist = [
        ChecklistItem(
            priority=recommendation.priority,
            category=recommendation.category,
            title=recommendation.title,
            implementation_hint=recommendation.implementation_hint,
            evidence=recommendation.evidence,
        )
        for recommendation in top_recommendations
    ]

    return AuditUIResponse(
        audit=audit_run,
        summary=_build_summary(
            audit_run,
            citation_breakdown=citation_breakdown,
            cluster_performance=cluster_performance,
            readiness_gaps=readiness_gaps,
        ),
        score_cards=_build_score_cards(audit_run, citation_breakdown),
        prompt_cluster_performance=cluster_performance,
        top_competitors=top_competitors,
        citation_source_breakdown=citation_breakdown,
        readiness_gaps=readiness_gaps,
        top_recommendations=top_recommendations,
        implementation_checklist=implementation_checklist,
    )


def _build_summary(
    audit_run: AuditRun,
    *,
    citation_breakdown: CitationSourceBreakdown,
    cluster_performance: list[PromptClusterPerformance],
    readiness_gaps: list[ReadinessGap],
) -> AuditSummary:
    final_score = audit_run.score.final
    readiness_score = audit_run.score.readiness
    visibility_score = round(audit_run.score.visibility)
    mention_rate = round(audit_run.visibility.overall_mention_rate)

    strong_clusters = [cluster.label for cluster in cluster_performance if cluster.status == "strong"][:2]
    weak_clusters = [cluster.label for cluster in cluster_performance if cluster.status == "weak"][:2]
    weakest_gaps = [gap.label for gap in readiness_gaps[:2]]

    wins = strong_clusters or _dimension_wins(audit_run)
    losses = weak_clusters or weakest_gaps or ["No major prompt-cluster losses observed in this run."]

    data_notes: list[str] = []
    if audit_run.mode == "demo":
        data_notes.append("Demo mode uses simulated prompt and website inputs.")
    if any(audit_run.web_presence.get(key) is None for key in ("google_business_found", "yelp_found")):
        data_notes.append("Some directory checks were unavailable, so listing presence is only partially verified.")
    if not audit_run.visibility.prompt_results:
        data_notes.append("No prompt results were captured, so visibility insights are limited.")
    if (
        citation_breakdown.official_citation_count == 0
        and citation_breakdown.third_party_citation_count == 0
    ):
        data_notes.append("No citations were captured in this run, so source-authority insights are limited.")

    headline = f"{audit_run.entity.business_name} scores {final_score}/100 for AI visibility."
    overview = (
        f"Readiness is {readiness_score}/100, visibility is {visibility_score}/100, and the business is "
        f"mentioned in {mention_rate}% of prompts. Official-site citation share is "
        f"{citation_breakdown.official_site_share}%."
    )
    return AuditSummary(
        headline=headline,
        overview=overview,
        wins=wins,
        losses=losses,
        data_notes=data_notes,
    )


def _build_score_cards(
    audit_run: AuditRun,
    citation_breakdown: CitationSourceBreakdown,
) -> list[ScoreCard]:
    competitor_gap = audit_run.visibility.dimensions.get("competitor_gap")
    official_share = audit_run.visibility.dimensions.get("official_citation_share")
    return [
        ScoreCard(
            key="overall",
            label="Overall Score",
            score=float(audit_run.score.final),
            status=_status(audit_run.score.final),
            detail="Composite score built from readiness and visibility.",
        ),
        ScoreCard(
            key="readiness",
            label="Readiness",
            score=float(audit_run.score.readiness),
            status=_status(audit_run.score.readiness),
            detail="How well the site and listings expose crawlable business facts.",
        ),
        ScoreCard(
            key="visibility",
            label="Visibility",
            score=float(audit_run.score.visibility),
            status=_status(audit_run.score.visibility),
            detail="How often the business is mentioned, recommended, and cited across prompts.",
        ),
        ScoreCard(
            key="mention_rate",
            label="Mention Rate",
            score=float(round(audit_run.visibility.overall_mention_rate, 1)),
            status=_status(audit_run.visibility.overall_mention_rate),
            detail=f"The business appears in {round(audit_run.visibility.overall_mention_rate, 1)}% of prompts.",
        ),
        ScoreCard(
            key="official_citation_share",
            label="Official Citation Share",
            score=float(citation_breakdown.official_site_share),
            status=_status(official_share.score if official_share else citation_breakdown.official_site_share),
            detail=(
                f"{citation_breakdown.official_citation_count} prompts cited the official site and "
                f"{citation_breakdown.third_party_citation_count} cited third-party sources."
            ),
        ),
        ScoreCard(
            key="competitor_gap",
            label="Competitor Gap",
            score=float(competitor_gap.score if competitor_gap else 0),
            status=_status(competitor_gap.score if competitor_gap else 0),
            detail=(
                "Higher scores mean the business holds more of the answer space when competitors are also present."
            ),
        ),
    ]


def _build_cluster_performance(audit_run: AuditRun) -> list[PromptClusterPerformance]:
    items: list[PromptClusterPerformance] = []
    for cluster, data in audit_run.visibility.per_cluster.items():
        items.append(
            PromptClusterPerformance(
                cluster=cluster,
                label=CLUSTER_LABELS.get(cluster, cluster.replace("_", " ").title()),
                score=float(data.avg_score),
                query_count=data.query_count,
                status=_status(data.avg_score),
                summary=f"Average prompt quality score {data.avg_score} across {data.query_count} prompts.",
            )
        )
    return sorted(items, key=lambda item: item.score, reverse=True)


def _build_citation_breakdown(audit_run: AuditRun) -> CitationSourceBreakdown:
    prompt_results = audit_run.visibility.prompt_results
    official_citation_count = sum(1 for prompt in prompt_results if prompt.cited_official_domain)
    third_party_citation_count = sum(1 for prompt in prompt_results if prompt.cited_third_party_domain)
    uncited_prompt_count = sum(1 for prompt in prompt_results if not prompt.cited)
    third_party_domains = Counter(
        citation.domain
        for prompt in prompt_results
        for citation in prompt.citations
        if citation.domain and not citation.is_official_domain
    )
    official_share_dimension = audit_run.visibility.dimensions.get("official_citation_share")
    official_site_share = official_share_dimension.score if official_share_dimension else 0

    note = ""
    if official_citation_count == 0 and third_party_citation_count == 0:
        note = "No cited answers were captured in this run."
    elif official_citation_count == 0:
        note = "Answers cite third-party sources, but not the official site yet."
    elif third_party_citation_count == 0:
        note = "Citations currently point only to the official site."

    return CitationSourceBreakdown(
        official_site_share=official_site_share,
        official_citation_count=official_citation_count,
        third_party_citation_count=third_party_citation_count,
        uncited_prompt_count=uncited_prompt_count,
        top_third_party_domains=[
            DomainCitationEntry(domain=domain, citations=count)
            for domain, count in third_party_domains.most_common(5)
        ],
        note=note,
    )


def _build_readiness_gaps(audit_run: AuditRun) -> list[ReadinessGap]:
    gaps: list[ReadinessGap] = []
    for key, dimension in audit_run.readiness.dimensions.items():
        if dimension.score >= 80:
            continue
        missing_checks = [name for name, passed in dimension.checks.items() if passed is False]
        gaps.append(
            ReadinessGap(
                key=key,
                label=dimension.label,
                score=dimension.score,
                summary=dimension.description,
                missing_checks=missing_checks[:5],
                evidence=dimension.evidence,
            )
        )
    return sorted(gaps, key=lambda gap: gap.score)


def _dimension_wins(audit_run: AuditRun) -> list[str]:
    strong_dimensions = [
        dimension.label
        for dimension in audit_run.readiness.dimensions.values()
        if dimension.score >= 80
    ]
    return strong_dimensions[:2] or ["No major wins surfaced in the current prompt mix."]


def _status(score: float) -> Literal["strong", "mixed", "weak", "unknown"]:
    if score is None:
        return "unknown"
    if score >= 70:
        return "strong"
    if score >= 40:
        return "mixed"
    return "weak"
