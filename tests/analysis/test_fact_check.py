from src.analysis.fact_check import score_fact_alignment


def test_fact_check_scores_known_facts_without_inventing_missing_values():
    score = score_fact_alignment(
        "Laveta Coffee is in Echo Park, Los Angeles. Visit lavetacoffee.com or call (213) 555-0199.",
        {
            "city": "Echo Park, Los Angeles",
            "website": "https://lavetacoffee.com",
            "phone": "(213) 555-0199",
            "industry": "coffee shop",
        },
    )

    assert score.score >= 0.75
    assert score.matches["city"] is True
    assert score.matches["phone"] is True


def test_fact_check_marks_conflicts_when_known_facts_are_wrong():
    score = score_fact_alignment(
        "Parker Law Group is based in San Diego and focuses on criminal defense.",
        {
            "city": "Los Angeles, CA",
            "industry": "personal injury lawyer",
        },
    )

    assert score.score < 0.5
    assert score.matches["city"] is False
    assert score.matches["industry"] is False
