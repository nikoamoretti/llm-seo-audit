from __future__ import annotations

from dataclasses import dataclass, field

from src.prompts.loader import PromptProfile


REQUIRED_CLUSTERS = (
    "branded",
    "discovery",
    "comparison",
    "urgency",
    "trust",
    "price",
    "symptom_problem",
    "follow_up",
)


@dataclass(frozen=True)
class PromptCoverageReport:
    profile_slug: str
    counts_by_cluster: dict[str, int]
    missing_clusters: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def build_prompt_coverage(profile: PromptProfile) -> PromptCoverageReport:
    counts_by_cluster = {
        cluster: len(prompts)
        for cluster, prompts in profile.clusters.items()
    }
    missing_clusters = [
        cluster for cluster in REQUIRED_CLUSTERS
        if counts_by_cluster.get(cluster, 0) == 0
    ]
    warnings = [
        f"Profile '{profile.slug}' is missing required cluster '{cluster}'."
        for cluster in missing_clusters
    ]
    return PromptCoverageReport(
        profile_slug=profile.slug,
        counts_by_cluster=counts_by_cluster,
        missing_clusters=missing_clusters,
        warnings=warnings,
    )
