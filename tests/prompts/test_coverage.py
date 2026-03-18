from src.prompts.coverage import REQUIRED_CLUSTERS, build_prompt_coverage
from src.prompts.loader import PromptProfile, PromptTemplate, load_prompt_profile


def test_coverage_counts_prompts_per_cluster():
    report = build_prompt_coverage(load_prompt_profile("lawyer"))

    assert report.profile_slug == "lawyer"
    assert report.missing_clusters == []
    assert report.counts_by_cluster["comparison"] >= 2
    assert set(report.counts_by_cluster) >= set(REQUIRED_CLUSTERS)


def test_coverage_warns_when_required_clusters_are_missing():
    profile = PromptProfile(
        slug="incomplete",
        display_name="Incomplete",
        aliases=[],
        clusters={
            "branded": [PromptTemplate(template="What do people say about {business_name}?")],
        },
    )

    report = build_prompt_coverage(profile)

    assert "comparison" in report.missing_clusters
    assert report.warnings
