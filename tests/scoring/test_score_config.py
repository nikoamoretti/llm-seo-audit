from src.scoring.final import load_score_config


def test_score_config_exposes_versioned_weights():
    config = load_score_config()

    assert config["version"] == "score_v2"
    assert set(config["readiness"]["weights"]) == {
        "crawlability",
        "entity_completeness",
        "content_coverage",
        "trust_signals",
        "listing_presence",
    }
    assert set(config["visibility"]["weights"]) == {
        "mention_rate",
        "recommendation_rate",
        "citation_rate",
        "official_citation_share",
        "competitor_gap",
        "discovery_strength",
    }
    assert round(sum(config["readiness"]["weights"].values()), 2) == 1.0
    assert round(sum(config["visibility"]["weights"].values()), 2) == 1.0
    assert round(sum(config["final"]["weights"].values()), 2) == 1.0
    assert "noindex" in config["penalties"]
