from __future__ import annotations

from collections import Counter, defaultdict
from typing import Iterable

from src.core.models import CheckDimension, ClusterVisibility, PromptResult, ProviderVisibility, VisibilityResult
from src.scoring.config import load_score_config


def score_visibility(prompt_results: list[PromptResult]) -> VisibilityResult:
    config = load_score_config()
    weights = config["visibility"]["weights"]
    prompt_quality_weights = config["visibility"]["prompt_quality_weights"]
    thresholds = config["thresholds"]["visibility"]

    components = _score_components(prompt_results, weights, thresholds)
    score = round(sum(dimension.weighted_score for dimension in components.values()), 1)
    per_llm = _per_provider_visibility(prompt_results, weights, thresholds)
    per_cluster = _per_cluster_visibility(prompt_results, prompt_quality_weights)
    top_competitors = _top_competitors(prompt_results)
    attributes = sorted({attribute for prompt in prompt_results for attribute in prompt.attributes})
    overall_mention_rate = round(_percentage(sum(1 for prompt in prompt_results if prompt.mentioned), len(prompt_results)), 1)

    return VisibilityResult(
        score=score,
        overall_mention_rate=overall_mention_rate,
        dimensions=components,
        per_llm=per_llm,
        per_cluster=per_cluster,
        top_competitors=top_competitors,
        attributes_cited=attributes,
        prompt_results=prompt_results,
    )


def _score_components(
    prompt_results: list[PromptResult],
    weights: dict[str, float],
    thresholds: dict[str, object],
) -> dict[str, CheckDimension]:
    total = len(prompt_results)
    mentioned = sum(1 for prompt in prompt_results if prompt.mentioned)
    recommended = sum(1 for prompt in prompt_results if prompt.recommended)
    cited = sum(1 for prompt in prompt_results if prompt.cited)
    official_citations = sum(1 for prompt in prompt_results if prompt.cited_official_domain)
    prompts_with_competitors = sum(1 for prompt in prompt_results if prompt.competitors)
    raw_discovery_clusters = thresholds.get("discovery_clusters", [])
    discovery_clusters = (
        set(str(cluster) for cluster in raw_discovery_clusters)
        if isinstance(raw_discovery_clusters, list)
        else set()
    )
    branded_cluster_name = str(thresholds.get("branded_cluster_name", "branded"))
    discovery_prompts = [
        prompt for prompt in prompt_results
        if prompt.cluster in discovery_clusters
    ]
    branded_prompts = [
        prompt for prompt in prompt_results
        if prompt.cluster == branded_cluster_name
    ]
    discovery_mentioned = sum(1 for prompt in discovery_prompts if prompt.mentioned)
    discovery_recommended = sum(1 for prompt in discovery_prompts if prompt.recommended)
    branded_mentioned = sum(1 for prompt in branded_prompts if prompt.mentioned)

    mention_rate = round(_percentage(mentioned, total))
    recommendation_rate = round(_percentage(recommended, total))
    citation_rate = round(_percentage(cited, total))
    official_citation_share = round(_percentage(official_citations, cited))
    competitor_gap = round(_percentage(mentioned, mentioned + prompts_with_competitors))
    discovery_mention_rate = _percentage(discovery_mentioned, len(discovery_prompts))
    discovery_recommendation_rate = _percentage(discovery_recommended, len(discovery_prompts))
    branded_mention_rate = _percentage(branded_mentioned, len(branded_prompts))
    if discovery_prompts:
        if branded_prompts:
            balance_score = min(100.0, _percentage(discovery_mentioned, max(branded_mentioned, 1)))
        else:
            balance_score = discovery_mention_rate
        discovery_strength = round((0.7 * discovery_mention_rate) + (0.3 * balance_score))
    else:
        discovery_strength = mention_rate

    return {
        "mention_rate": _dimension(
            key="mention_rate",
            label="Mention Rate",
            description="How often the business appears at all across prompts.",
            score=mention_rate,
            weight=float(weights["mention_rate"]),
            evidence=[f"visibility.mention_rate={mention_rate}"],
            metrics={"mentioned_prompt_count": mentioned, "total_prompt_count": total},
        ),
        "recommendation_rate": _dimension(
            key="recommendation_rate",
            label="Recommendation Rate",
            description="How often the engines actively recommend the business, not just mention it.",
            score=recommendation_rate,
            weight=float(weights["recommendation_rate"]),
            evidence=[f"visibility.recommendation_rate={recommendation_rate}"],
            metrics={"recommended_prompt_count": recommended, "total_prompt_count": total},
        ),
        "citation_rate": _dimension(
            key="citation_rate",
            label="Citation Rate",
            description="How often the business appears with any citation or linked source.",
            score=citation_rate,
            weight=float(weights["citation_rate"]),
            evidence=[f"visibility.citation_rate={citation_rate}"],
            metrics={"cited_prompt_count": cited, "total_prompt_count": total},
        ),
        "official_citation_share": _dimension(
            key="official_citation_share",
            label="Official Citation Share",
            description="How much of the cited visibility points back to the official business site.",
            score=official_citation_share,
            weight=float(weights["official_citation_share"]),
            evidence=[f"visibility.official_citation_share={official_citation_share}"],
            metrics={"official_citation_count": official_citations, "cited_prompt_count": cited},
        ),
        "competitor_gap": _dimension(
            key="competitor_gap",
            label="Competitor Gap",
            description="How often competitors occupy the answer space instead of the business.",
            score=competitor_gap,
            weight=float(weights["competitor_gap"]),
            evidence=[
                f"visibility.prompts_with_business={mentioned}",
                f"visibility.prompts_with_competitors={prompts_with_competitors}",
            ],
            metrics={
                "prompts_with_business": mentioned,
                "prompts_with_competitors": prompts_with_competitors,
            },
        ),
        "discovery_strength": _dimension(
            key="discovery_strength",
            label="Discovery Strength",
            description="How well the business shows up in non-branded discovery prompts compared with branded prompts.",
            score=discovery_strength,
            weight=float(weights["discovery_strength"]),
            evidence=[
                f"visibility.discovery_mention_rate={round(discovery_mention_rate, 1)}",
                f"visibility.discovery_recommendation_rate={round(discovery_recommendation_rate, 1)}",
                f"visibility.branded_mention_rate={round(branded_mention_rate, 1)}",
            ],
            metrics={
                "discovery_prompt_count": len(discovery_prompts),
                "discovery_mention_rate": round(discovery_mention_rate, 1),
                "discovery_recommendation_rate": round(discovery_recommendation_rate, 1),
                "branded_prompt_count": len(branded_prompts),
                "branded_mention_rate": round(branded_mention_rate, 1),
            },
        ),
    }


def _per_provider_visibility(
    prompt_results: list[PromptResult],
    weights: dict[str, float],
    thresholds: dict[str, object],
) -> dict[str, ProviderVisibility]:
    grouped: dict[str, list[PromptResult]] = defaultdict(list)
    for prompt in prompt_results:
        grouped[prompt.provider].append(prompt)

    providers: dict[str, ProviderVisibility] = {}
    for provider, prompts in grouped.items():
        components = _score_components(prompts, weights, thresholds)
        positions = [prompt.position for prompt in prompts if prompt.position is not None]
        competitors = Counter(name for prompt in prompts for name in prompt.competitors)
        attributes = sorted({attribute for prompt in prompts for attribute in prompt.attributes})
        providers[provider] = ProviderVisibility(
            visibility_score=round(sum(component.weighted_score for component in components.values()), 1),
            mention_rate=round(_percentage(sum(1 for prompt in prompts if prompt.mentioned), len(prompts)), 1),
            citation_rate=round(_percentage(sum(1 for prompt in prompts if prompt.cited), len(prompts)), 1),
            avg_position=round(sum(positions) / len(positions), 1) if positions else None,
            total_queries=len(prompts),
            times_mentioned=sum(1 for prompt in prompts if prompt.mentioned),
            times_cited=sum(1 for prompt in prompts if prompt.cited),
            top_competitors=dict(competitors.most_common(10)),
            attributes_cited=attributes,
        )
    return providers


def _per_cluster_visibility(
    prompt_results: list[PromptResult],
    prompt_quality_weights: dict[str, float],
) -> dict[str, ClusterVisibility]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for prompt in prompt_results:
        grouped[prompt.cluster or "unclustered"].append(_prompt_quality(prompt, prompt_quality_weights))

    return {
        cluster: ClusterVisibility(avg_score=round(sum(scores) / len(scores), 1), query_count=len(scores))
        for cluster, scores in grouped.items()
    }


def _prompt_quality(prompt: PromptResult, weights: dict[str, float]) -> float:
    position_signal = 100.0 if prompt.position == 1 else (60.0 if prompt.position and prompt.position <= 3 else 0.0)
    score = (
        (100.0 if prompt.mentioned else 0.0) * float(weights["mentioned"])
        + (100.0 if prompt.recommended else 0.0) * float(weights["recommended"])
        + (100.0 if prompt.cited else 0.0) * float(weights["cited"])
        + (100.0 if prompt.cited_official_domain else 0.0) * float(weights["official_citation"])
        + position_signal * float(weights["position"])
    )
    return round(score, 1)


def _top_competitors(prompt_results: Iterable[PromptResult]) -> dict[str, int]:
    counter = Counter(name for prompt in prompt_results for name in prompt.competitors)
    return dict(counter.most_common(15))


def _dimension(
    *,
    key: str,
    label: str,
    description: str,
    score: float,
    weight: float,
    evidence: list[str],
    metrics: dict[str, object],
) -> CheckDimension:
    del key
    return CheckDimension(
        label=label,
        description=description,
        score=int(round(score)),
        weight=weight,
        weighted_score=round(score * weight, 2),
        evidence=evidence,
        metrics=metrics,
    )


def _percentage(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return (numerator / denominator) * 100.0
