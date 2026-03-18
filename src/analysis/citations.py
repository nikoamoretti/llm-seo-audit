from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse


URL_PATTERN = re.compile(
    r"https?://[^\s)>]+|www\.[^\s)>]+",
    re.IGNORECASE,
)
MARKDOWN_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")


@dataclass(frozen=True)
class CitationMatch:
    label: str
    url: str
    domain: str
    is_official_domain: bool
    citation_type: str


def extract_citations(response: str, known_facts: dict | None = None) -> list[CitationMatch]:
    known_facts = known_facts or {}
    official_domain = _domain_from_url(known_facts.get("website", "")) if known_facts else ""

    citations: list[CitationMatch] = []
    seen: set[str] = set()

    for match in MARKDOWN_LINK_PATTERN.findall(response):
        label, url = match
        citation = _build_citation(label=label, url=url, official_domain=official_domain)
        if citation.url not in seen:
            citations.append(citation)
            seen.add(citation.url)

    stripped_response = MARKDOWN_LINK_PATTERN.sub("", response)
    for raw_url in URL_PATTERN.findall(stripped_response):
        citation = _build_citation(label=raw_url, url=raw_url, official_domain=official_domain)
        if citation.url not in seen:
            citations.append(citation)
            seen.add(citation.url)

    return citations


def citation_flags(citations: list[CitationMatch]) -> dict[str, bool]:
    return {
        "cited": bool(citations),
        "cited_official_domain": any(citation.is_official_domain for citation in citations),
        "cited_third_party_domain": any(not citation.is_official_domain for citation in citations),
    }


def _build_citation(label: str, url: str, official_domain: str) -> CitationMatch:
    normalized_url = url if url.startswith("http") else f"https://{url}"
    domain = _domain_from_url(normalized_url)
    is_official = bool(official_domain and domain == official_domain)
    return CitationMatch(
        label=label.strip(),
        url=normalized_url,
        domain=domain,
        is_official_domain=is_official,
        citation_type="official" if is_official else "third_party",
    )


def _domain_from_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url if url.startswith("http") else f"https://{url}")
    return parsed.netloc.lower().removeprefix("www.")
