import app as app_module

from src.prompts.loader import load_prompt_profile
from src.prompts.renderer import render_prompt_bank


def test_renderer_inserts_city_service_area_and_required_clusters():
    profile = load_prompt_profile("plumber")

    prompts = render_prompt_bank(
        profile,
        business_name="Precision Rooter",
        industry="plumber",
        city="Austin, TX",
        service_area="Round Rock, TX",
    )

    texts = [prompt["text"] for prompt in prompts]
    clusters = {prompt["cluster"] for prompt in prompts}

    assert "branded" in clusters
    assert "discovery" in clusters
    assert "comparison" in clusters
    assert "urgency" in clusters
    assert "trust" in clusters
    assert "price" in clusters
    assert "symptom_problem" in clusters
    assert "follow_up" in clusters
    assert any("Precision Rooter" in text for text in texts)
    assert any("Austin, TX" in text for text in texts)
    assert any("Round Rock, TX" in text for text in texts)


def test_renderer_emits_competitor_aware_comparison_prompts():
    profile = load_prompt_profile("lawyer")

    prompts = render_prompt_bank(
        profile,
        business_name="Parker Law Group",
        industry="personal injury lawyer",
        city="Los Angeles, CA",
        service_area="Los Angeles, CA",
        competitors=["Morgan & Morgan", "Sweet James"],
    )

    comparison_texts = [prompt["text"] for prompt in prompts if prompt["cluster"] == "comparison"]

    assert any("Morgan & Morgan" in text and "Sweet James" in text for text in comparison_texts)
    assert any("Parker Law Group" in text for text in comparison_texts)


def test_app_prompt_builder_uses_vertical_profile_selection():
    prompts = app_module.build_prompt_list(
        business_name="Bright Smile Studio",
        industry="dentist",
        city="Phoenix, AZ",
        service_area="Scottsdale, AZ",
    )

    clusters = {prompt["cluster"] for prompt in prompts}
    texts = [prompt["text"] for prompt in prompts]

    assert "symptom_problem" in clusters
    assert any("Bright Smile Studio" in text for text in texts)
    assert any("Scottsdale, AZ" in text for text in texts)
