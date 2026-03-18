from __future__ import annotations

from src.prompts.loader import PromptProfile


class _SafeFormatDict(dict):
    def __missing__(self, key):
        return ""


def render_prompt_bank(
    profile: PromptProfile,
    *,
    business_name: str,
    industry: str,
    city: str,
    service_area: str | None = None,
    competitors: list[str] | None = None,
) -> list[dict[str, str]]:
    competitors = competitors or []
    context = _SafeFormatDict(
        business_name=business_name,
        industry=industry,
        category=industry,
        city=city,
        service_area=service_area or city,
        competitor_names=", ".join(competitors[:3]),
        top_competitor=competitors[0] if competitors else "",
    )

    prompts: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for cluster, templates in profile.clusters.items():
        for template in templates:
            if template.requires_competitors and not competitors:
                continue
            text = template.template.format_map(context).strip()
            key = (cluster, text)
            if not text or key in seen:
                continue
            prompts.append(
                {
                    "text": text,
                    "cluster": cluster,
                    "profile": profile.slug,
                }
            )
            seen.add(key)
    return prompts
