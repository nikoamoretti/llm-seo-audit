from src.analysis.mentions import analyze_mentions


def test_mentions_distinguish_recommended_from_plain_mention():
    recommended = analyze_mentions(
        "Laveta Coffee",
        "1. Laveta Coffee - highly recommended for espresso drinks in Echo Park.",
    )
    plain = analyze_mentions(
        "Laveta Coffee",
        "Laveta Coffee is located in Echo Park and has been open since 2016.",
    )

    assert recommended.mentioned is True
    assert recommended.recommended is True
    assert plain.mentioned is True
    assert plain.recommended is False


def test_mentions_support_fuzzy_matching():
    result = analyze_mentions(
        "Parker Law Group",
        "Parker Law Gruop is often mentioned for personal injury work.",
    )

    assert result.mentioned is True
    assert result.fuzzy_match is True
    assert result.fuzzy_score >= 80
