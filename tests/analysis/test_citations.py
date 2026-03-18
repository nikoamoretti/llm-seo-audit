from pathlib import Path

from src.analysis.citations import extract_citations


FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "responses"


def test_citations_distinguish_official_and_third_party_domains():
    response = (FIXTURE_ROOT / "good_response.md").read_text()

    citations = extract_citations(response, {"website": "https://lavetacoffee.com"})

    assert len(citations) >= 2
    assert any(citation.is_official_domain for citation in citations)
    assert any(citation.citation_type == "third_party" for citation in citations)


def test_citations_handle_messy_markdown_and_bare_urls():
    response = (FIXTURE_ROOT / "messy_markdown.md").read_text()

    citations = extract_citations(response, {"website": "https://brightsmiledental.com"})

    assert any("brightsmiledental.com" in citation.url for citation in citations)
    assert any("yelp.com" in citation.url for citation in citations)
