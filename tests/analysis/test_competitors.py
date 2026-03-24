from src.analysis.competitors import (
    extract_competitor_candidates,
    extract_competitors,
    select_report_competitors,
)


def test_extract_competitors_keeps_real_named_entities():
    response = """
    Here are the strongest options:
    1. Woodcat Coffee
    2. Canyon Coffee
    3. Laveta Coffee
    4. Stereoscope Coffee
    """

    competitors = extract_competitors(response, business_variants=["laveta coffee", "laveta"])

    assert competitors == ["Woodcat Coffee", "Canyon Coffee", "Stereoscope Coffee"]


def test_extract_competitor_candidates_reject_source_labels_editorial_and_warning_fragments():
    response = """
    **Sources:**
    1. Warning: Results may vary by neighborhood
    2. Official Website
    3. Read more
    4. Here are a few strong choices
    """

    candidates = extract_competitor_candidates(response, business_variants=["laveta"])
    competitors = extract_competitors(response, business_variants=["laveta"])

    assert competitors == []
    assert [candidate.display_name for candidate in candidates] == [
        "Sources",
        "Warning",
        "Official Website",
        "Read More",
        "Here Are A Few Strong Choices",
    ]
    assert all(candidate.accepted is False for candidate in candidates)


def test_extract_competitors_handles_listicles_and_mixed_prose():
    response = """
    1. A-Team Plumbing - often recommended for emergency work
    2. Capital Flow Plumbing: strong local reviews
    In broader roundups, **Austin Rooter** and **Proven Plumbing Co.** also appear.
    """

    competitors = extract_competitors(response, business_variants=["acme plumbing"])

    assert competitors == [
        "A-Team Plumbing",
        "Capital Flow Plumbing",
        "Austin Rooter",
        "Proven Plumbing Co",
    ]


def test_extract_competitors_dedupes_trivial_variants():
    response = """
    1. A-Team Plumbing
    2. A Team Plumbing LLC
    3. A-Team Plumbing, Inc.
    4. Capital Flow Plumbing
    """

    competitors = extract_competitors(response, business_variants=["acme plumbing"])

    assert competitors == ["A-Team Plumbing", "Capital Flow Plumbing"]


def test_extract_competitors_prefers_empty_over_low_confidence_phrases():
    response = """
    1. Best options in the area
    2. Customer reviews and ratings
    3. Local results may change
    """

    candidates = extract_competitor_candidates(response, business_variants=["laveta"])
    competitors = extract_competitors(response, business_variants=["laveta"])

    assert competitors == []
    assert all(candidate.confidence < 0.6 for candidate in candidates)


def test_select_report_competitors_filters_noisy_aggregates():
    visible = select_report_competitors(
        {
            "Warning: Results may vary": 4,
            "Source: Yelp": 3,
            "A-Team Plumbing LLC": 2,
            "A Team Plumbing": 1,
            "Capital Flow Plumbing": 1,
        },
        business_variants=["acme plumbing"],
    )

    assert visible == [("A-Team Plumbing", 3), ("Capital Flow Plumbing", 1)]
