from src.prompts.loader import load_prompt_profile, select_prompt_profile


def test_select_prompt_profile_uses_vertical_aliases():
    assert select_prompt_profile("emergency plumber") == "plumber"
    assert select_prompt_profile("cosmetic dentist") == "dentist"
    assert select_prompt_profile("personal injury lawyer") == "lawyer"
    assert select_prompt_profile("coffee shop") == "default"


def test_load_prompt_profile_merges_default_and_vertical_clusters():
    profile = load_prompt_profile("dentist")

    assert profile.slug == "dentist"
    assert set(profile.clusters) >= {
        "branded",
        "discovery",
        "comparison",
        "urgency",
        "trust",
        "price",
        "symptom_problem",
        "follow_up",
    }
    assert any("tooth pain" in prompt.template.lower() for prompt in profile.clusters["symptom_problem"])
    assert any(prompt.requires_competitors for prompt in profile.clusters["comparison"])
    assert len(profile.clusters["follow_up"]) >= 1
