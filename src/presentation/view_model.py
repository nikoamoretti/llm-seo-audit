from __future__ import annotations

from collections import Counter
from typing import Literal

from pydantic import Field

from src.analysis.competitors import select_report_competitors
from src.core.models import AuditRun, CanonicalModel, ReadinessState, Recommendation
from src.scoring.final import (
    FinalScoreMath,
    final_score_formula,
    format_score_value,
    validate_score_breakdown,
)
from src.scoring.visibility import CitationEvidenceState, CitationEvidenceSummary, summarize_citation_evidence


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
    evidence_state: CitationEvidenceState
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
    state: ReadinessState
    state_label: str
    state_note: str = ""
    summary: str
    missing_checks: list[str] = Field(default_factory=list)
    verified_missing_checks: list[str] = Field(default_factory=list)
    partial_checks: list[str] = Field(default_factory=list)
    unknown_checks: list[str] = Field(default_factory=list)
    unavailable_checks: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class ChecklistItem(CanonicalModel):
    priority: Literal["P0", "P1", "P2"]
    category: str
    title: str
    implementation_hint: str
    evidence: list[str] = Field(default_factory=list)


class ScorePenalty(CanonicalModel):
    key: str
    label: str
    points: int
    reason: str = ""


class ScoreExplanation(CanonicalModel):
    readiness_score: int
    visibility_score: float
    weighted_base_score: float
    penalties_total: float
    final_score: int
    penalties_applied: list[ScorePenalty] = Field(default_factory=list)
    formula: str
    rounding_note: str


class AuditUIResponse(CanonicalModel):
    audit: AuditRun
    summary: AuditSummary
    score_explanation: ScoreExplanation
    score_cards: list[ScoreCard] = Field(default_factory=list)
    prompt_cluster_performance: list[PromptClusterPerformance] = Field(default_factory=list)
    top_competitors: list[CompetitorEntry] = Field(default_factory=list)
    citation_source_breakdown: CitationSourceBreakdown
    readiness_gaps: list[ReadinessGap] = Field(default_factory=list)
    top_recommendations: list[Recommendation] = Field(default_factory=list)
    implementation_checklist: list[ChecklistItem] = Field(default_factory=list)


def build_audit_ui_response(audit_run: AuditRun) -> AuditUIResponse:
    score_explanation = _build_score_explanation(audit_run)
    citation_breakdown = _build_citation_breakdown(audit_run)
    cluster_performance = _build_cluster_performance(audit_run)
    readiness_gaps = _build_readiness_gaps(audit_run)
    business_variants = _business_variants(audit_run)
    top_competitors = [
        CompetitorEntry(name=name, mentions=mentions)
        for name, mentions in select_report_competitors(
            audit_run.visibility.top_competitors,
            business_variants=business_variants,
        )
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
            score_explanation=score_explanation,
            citation_breakdown=citation_breakdown,
            cluster_performance=cluster_performance,
            readiness_gaps=readiness_gaps,
        ),
        score_explanation=score_explanation,
        score_cards=_build_score_cards(audit_run, citation_breakdown, score_explanation),
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
    score_explanation: ScoreExplanation,
    citation_breakdown: CitationSourceBreakdown,
    cluster_performance: list[PromptClusterPerformance],
    readiness_gaps: list[ReadinessGap],
) -> AuditSummary:
    final_score = audit_run.score.final
    readiness_score = audit_run.score.readiness
    visibility_score = format_score_value(score_explanation.visibility_score)
    mention_rate = round(audit_run.visibility.overall_mention_rate)

    strong_clusters = [cluster.label for cluster in cluster_performance if cluster.status == "strong"][:2]
    weak_clusters = [cluster.label for cluster in cluster_performance if cluster.status == "weak"][:2]
    weakest_gaps = [gap.label for gap in readiness_gaps if gap.state in {"fail", "mixed"}][:2]

    wins = strong_clusters or _dimension_wins(audit_run)
    losses = weak_clusters or weakest_gaps or ["No major prompt-cluster losses observed in this run."]

    data_notes: list[str] = []
    if audit_run.mode == "demo":
        data_notes.append("Demo mode uses simulated prompt and website inputs.")

    # --- Website accessibility messaging ---
    website_url = audit_run.input.website_url or audit_run.entity.website_url
    web_presence = audit_run.web_presence or {}
    site_accessible = web_presence.get("website_accessible")

    if not website_url:
        data_notes.append(
            "No website was available for this business, so website-readiness "
            "checks were not included. The audit still evaluated other verifiable signals."
        )
    elif site_accessible is False or site_accessible is None:
        data_notes.append(
            "This audit completed with partial data. The business website could "
            "not be accessed, so website-based checks were marked unavailable "
            "rather than estimated. Remaining results are based on other verifiable signals."
        )

    readiness_states = [dimension.state for dimension in audit_run.readiness.dimensions.values()]
    if any(state == "unavailable" for state in readiness_states):
        # Only add the generic readiness note if we haven't already explained why
        if website_url and site_accessible is not False and site_accessible is not None:
            data_notes.append(
                "Some readiness signals were unavailable, so incomplete evidence "
                "is shown separately from verified gaps."
            )
    elif any(state == "unknown" for state in readiness_states):
        data_notes.append(
            "Some readiness signals were not fully checked, so incomplete evidence "
            "is shown separately from verified gaps."
        )
    if not audit_run.visibility.prompt_results:
        data_notes.append("No prompt results were captured, so visibility insights are limited.")
    if citation_breakdown.evidence_state == "no_citations":
        data_notes.append("No citations were captured in this run, so source-authority insights are limited.")
    elif citation_breakdown.evidence_state == "unavailable":
        data_notes.append(
            "Citation evidence was unavailable or incomplete, so source-authority insights are inconclusive."
        )

    # Always use the submitted (input) business name for the headline so
    # that Cloudflare challenge page titles or extracted garbage never appear.
    display_name = audit_run.input.business_name or audit_run.entity.business_name
    headline = f"{display_name} scores {final_score}/100 on the GEO audit."
    overview = (
        f"Readiness is {readiness_score}/100, visibility is {visibility_score}/100, and the business is "
        f"mentioned in {mention_rate}% of prompts. {_citation_overview(citation_breakdown)}"
    )
    if score_explanation.penalties_total > 0:
        overview += (
            f" Penalties reduced the score by "
            f"{format_score_value(score_explanation.penalties_total)} points."
        )
    else:
        overview += " No penalties were applied."
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
    score_explanation: ScoreExplanation,
) -> list[ScoreCard]:
    competitor_gap = audit_run.visibility.dimensions.get("competitor_gap")
    official_share = audit_run.visibility.dimensions.get("official_citation_share")
    overall_detail = (
        "Weighted base "
        f"{format_score_value(score_explanation.weighted_base_score)} minus penalties "
        f"{format_score_value(score_explanation.penalties_total)} yields "
        f"{score_explanation.final_score} after rounding."
    )
    return [
        ScoreCard(
            key="overall",
            label="Overall Score",
            score=float(audit_run.score.final),
            status=_status(audit_run.score.final),
            detail=overall_detail,
        ),
        ScoreCard(
            key="readiness",
            label="Readiness",
            score=float(audit_run.score.readiness),
            status=_status(audit_run.score.readiness),
            detail=_readiness_score_card_detail(audit_run),
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
            detail=_citation_score_card_detail(citation_breakdown),
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


def _build_score_explanation(audit_run: AuditRun) -> ScoreExplanation:
    score_math = validate_score_breakdown(audit_run.score)
    penalties = [
        ScorePenalty(
            key=str(penalty.get("key", "")),
            label=str(penalty.get("label", penalty.get("key", ""))),
            points=int(penalty.get("points", 0)),
            reason=str(penalty.get("reason", "")),
        )
        for penalty in audit_run.score.penalties
    ]
    return _score_explanation_from_math(score_math, penalties=penalties)


def _score_explanation_from_math(
    score_math: FinalScoreMath,
    *,
    penalties: list[ScorePenalty],
) -> ScoreExplanation:
    return ScoreExplanation(
        readiness_score=score_math.readiness_score,
        visibility_score=score_math.visibility_score,
        weighted_base_score=score_math.weighted_base_score,
        penalties_total=score_math.penalties_total,
        final_score=score_math.final_score,
        penalties_applied=penalties,
        formula=final_score_formula(),
        rounding_note="The weighted base is reduced by penalties, then rounded to a whole point.",
    )


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
    citation_evidence = summarize_citation_evidence(prompt_results)
    third_party_domains = Counter(
        citation.domain
        for prompt in prompt_results
        for citation in prompt.citations
        if citation.domain and not citation.is_official_domain
    )
    official_share_dimension = audit_run.visibility.dimensions.get("official_citation_share")
    official_site_share = official_share_dimension.score if official_share_dimension else 0

    return CitationSourceBreakdown(
        evidence_state=citation_evidence.state,
        official_site_share=official_site_share,
        official_citation_count=citation_evidence.official_citation_count,
        third_party_citation_count=citation_evidence.third_party_citation_count,
        uncited_prompt_count=citation_evidence.uncited_prompt_count,
        top_third_party_domains=[
            DomainCitationEntry(domain=domain, citations=count)
            for domain, count in third_party_domains.most_common(5)
        ],
        note=_citation_breakdown_note(citation_evidence),
    )


def _build_readiness_gaps(audit_run: AuditRun) -> list[ReadinessGap]:
    gaps: list[ReadinessGap] = []
    for key, dimension in audit_run.readiness.dimensions.items():
        if dimension.score >= 80 and dimension.state == "pass":
            continue
        check_groups = _group_readiness_checks(dimension)
        gaps.append(
            ReadinessGap(
                key=key,
                label=dimension.label,
                score=dimension.score,
                state=dimension.state,
                state_label=dimension.state_label or _readiness_state_label(dimension.state),
                state_note=dimension.state_note or _readiness_state_note(dimension.state),
                summary=dimension.description,
                missing_checks=check_groups["fail"][:5],
                verified_missing_checks=check_groups["fail"][:5],
                partial_checks=check_groups["mixed"][:5],
                unknown_checks=check_groups["unknown"][:5],
                unavailable_checks=check_groups["unavailable"][:5],
                evidence=dimension.evidence,
            )
        )
    return sorted(gaps, key=_readiness_gap_sort_key)


def _business_variants(audit_run: AuditRun) -> list[str]:
    variants = [
        audit_run.entity.business_name,
        audit_run.input.business_name,
    ]
    seen: set[str] = set()
    unique: list[str] = []
    for variant in variants:
        normalized = variant.strip().lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique.append(variant)
    return unique


def _dimension_wins(audit_run: AuditRun) -> list[str]:
    strong_dimensions = [
        dimension.label
        for dimension in audit_run.readiness.dimensions.values()
        if dimension.score >= 80 and dimension.state == "pass"
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


def _readiness_score_card_detail(audit_run: AuditRun) -> str:
    states = [dimension.state for dimension in audit_run.readiness.dimensions.values()]
    if any(state == "unavailable" for state in states):
        return (
            "Some readiness signals were unavailable in this run, so the score uses neutral placeholders where "
            "evidence is incomplete."
        )
    if any(state == "unknown" for state in states):
        return (
            "Some readiness signals were not fully checked in this run, so the score keeps incomplete evidence "
            "separate from verified weaknesses."
        )
    return "How well the site and listings expose crawlable business facts."


def _group_readiness_checks(dimension) -> dict[str, list[str]]:
    groups = {
        "fail": [],
        "mixed": [],
        "unknown": [],
        "unavailable": [],
    }
    if dimension.check_states:
        for name, check in dimension.check_states.items():
            if check.state in groups:
                groups[check.state].append(name)
        return groups

    for name, passed in dimension.checks.items():
        if passed is False:
            groups["fail"].append(name)
        elif passed is None:
            groups["unknown"].append(name)
    return groups


def _readiness_gap_sort_key(gap: ReadinessGap) -> tuple[int, int, str]:
    priority = {
        "fail": 0,
        "mixed": 1,
        "unknown": 2,
        "unavailable": 3,
        "pass": 4,
    }
    return (priority.get(gap.state, 5), gap.score, gap.label)


def _readiness_state_label(state: ReadinessState) -> str:
    return {
        "pass": "VERIFIED",
        "fail": "VERIFIED GAP",
        "mixed": "PARTIAL",
        "unknown": "UNVERIFIED",
        "unavailable": "UNAVAILABLE",
    }[state]


def _readiness_state_note(state: ReadinessState) -> str:
    if state == "fail":
        return "Verified evidence shows this area is missing or weak."
    if state == "mixed":
        return "This area includes a mix of verified signals and incomplete evidence."
    if state == "unknown":
        return "This area was not fully checked in this run."
    if state == "unavailable":
        return "Some sources were unavailable in this run."
    return "All checks in this area were verified."


def _citation_overview(citation_breakdown: CitationSourceBreakdown) -> str:
    if citation_breakdown.evidence_state == "unavailable":
        return "Citation diagnosis is inconclusive because citation evidence was unavailable or incomplete."
    if citation_breakdown.evidence_state == "no_citations":
        return "No citations were captured in this run."
    if citation_breakdown.evidence_state == "official_only":
        return (
            f"Captured citations pointed only to the official site; official-site share was "
            f"{citation_breakdown.official_site_share}%."
        )
    if citation_breakdown.evidence_state == "third_party_only":
        return "Captured citations came from third-party sources only; the official site was not cited."
    return (
        f"Captured citations included both the official site and third-party sources; official-site "
        f"share was {citation_breakdown.official_site_share}%."
    )


def _citation_score_card_detail(citation_breakdown: CitationSourceBreakdown) -> str:
    if citation_breakdown.evidence_state == "unavailable":
        return "Citation evidence was unavailable or incomplete in this run, so official-site support is inconclusive."
    if citation_breakdown.evidence_state == "no_citations":
        return "No citations were captured in this run."
    if citation_breakdown.evidence_state == "official_only":
        return (
            f"{citation_breakdown.official_citation_count} prompts cited the official site and no "
            "third-party citations were captured."
        )
    if citation_breakdown.evidence_state == "third_party_only":
        return (
            f"0 prompts cited the official site and {citation_breakdown.third_party_citation_count} "
            "cited third-party sources."
        )
    return (
        f"{citation_breakdown.official_citation_count} prompts cited the official site and "
        f"{citation_breakdown.third_party_citation_count} cited third-party sources."
    )


def _citation_breakdown_note(citation_evidence: CitationEvidenceSummary) -> str:
    if citation_evidence.state == "unavailable":
        return "Citation evidence was unavailable or incomplete, so source-support diagnosis is inconclusive."
    if citation_evidence.state == "no_citations":
        return "No cited answers were captured in this run."
    if citation_evidence.state == "official_only":
        return "Citations currently point only to the official site."
    if citation_evidence.state == "third_party_only":
        return "Answers cite third-party sources, but not the official site yet."
    return "Answers cite both the official site and third-party sources."
