from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml  # type: ignore[import-untyped]


PROMPT_PROFILE_DIR = Path(__file__).resolve().parents[2] / "config" / "prompt_profiles"


@dataclass(frozen=True)
class PromptTemplate:
    template: str
    requires_competitors: bool = False


@dataclass(frozen=True)
class PromptProfile:
    slug: str
    display_name: str
    aliases: list[str] = field(default_factory=list)
    clusters: dict[str, list[PromptTemplate]] = field(default_factory=dict)


def available_prompt_profiles() -> list[str]:
    return sorted(path.stem for path in PROMPT_PROFILE_DIR.glob("*.yaml"))


def select_prompt_profile(industry: str) -> str:
    normalized = industry.strip().lower()
    best_match = "default"
    best_length = 0

    for slug in available_prompt_profiles():
        if slug == "default":
            continue
        profile = load_prompt_profile(slug)
        candidates = [slug, *profile.aliases]
        for candidate in candidates:
            candidate_normalized = candidate.lower()
            if candidate_normalized in normalized and len(candidate_normalized) > best_length:
                best_match = slug
                best_length = len(candidate_normalized)
    return best_match


@lru_cache(maxsize=None)
def load_prompt_profile(slug: str) -> PromptProfile:
    default_data = _load_profile_data("default")
    if slug == "default":
        return _profile_from_data("default", default_data)

    profile_data = _load_profile_data(slug)
    merged_clusters = {
        cluster: list(templates)
        for cluster, templates in _clusters_from_data(default_data).items()
    }
    for cluster, templates in _clusters_from_data(profile_data).items():
        merged_clusters.setdefault(cluster, [])
        merged_clusters[cluster].extend(templates)

    return PromptProfile(
        slug=slug,
        display_name=str(profile_data.get("display_name", slug.title())),
        aliases=[str(alias).lower() for alias in profile_data.get("aliases", [])],
        clusters=merged_clusters,
    )


def _profile_from_data(slug: str, data: dict) -> PromptProfile:
    return PromptProfile(
        slug=slug,
        display_name=str(data.get("display_name", slug.title())),
        aliases=[str(alias).lower() for alias in data.get("aliases", [])],
        clusters=_clusters_from_data(data),
    )


def _clusters_from_data(data: dict) -> dict[str, list[PromptTemplate]]:
    clusters: dict[str, list[PromptTemplate]] = {}
    for cluster, raw_prompts in data.get("clusters", {}).items():
        cluster_prompts = []
        for raw_prompt in raw_prompts:
            if isinstance(raw_prompt, str):
                cluster_prompts.append(PromptTemplate(template=raw_prompt))
            else:
                cluster_prompts.append(
                    PromptTemplate(
                        template=str(raw_prompt["template"]),
                        requires_competitors=bool(raw_prompt.get("requires_competitors", False)),
                    )
                )
        clusters[str(cluster)] = cluster_prompts
    return clusters


def _load_profile_data(slug: str) -> dict:
    path = PROMPT_PROFILE_DIR / f"{slug}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Prompt profile not found: {slug}")

    data = yaml.safe_load(path.read_text()) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Prompt profile {slug} must contain a YAML mapping.")
    return data
