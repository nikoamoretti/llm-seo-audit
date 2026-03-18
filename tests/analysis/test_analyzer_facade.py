from pathlib import Path

from analyzer import ResponseAnalyzer


FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "responses"


def test_response_analyzer_returns_structured_citations_and_flags():
    response = (FIXTURE_ROOT / "good_response.md").read_text()
    analyzer = ResponseAnalyzer(
        "Laveta Coffee",
        known_facts={"website": "https://lavetacoffee.com", "city": "Echo Park, Los Angeles"},
    )

    analysis = analyzer.analyze_response(response, "Who are the best coffee shops in Echo Park?")

    assert analysis["mentioned"] is True
    assert analysis["cited"] is True
    assert analysis["cited_official_domain"] is True
    assert analysis["cited_third_party_domain"] is True
    assert analysis["citations"]
    assert analysis["citations"][0]["url"].startswith("http")
