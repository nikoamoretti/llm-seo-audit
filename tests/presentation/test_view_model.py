from datetime import datetime

import pytest

from src.core.models import (
    AuditRun,
    BusinessEntity,
    BusinessInput,
    CheckDimension,
    ReadinessCheck,
    PromptResult,
    ReadinessResult,
    VisibilityResult,
)
from src.presentation.view_model import build_audit_ui_response
from src.recommendations.rules import build_recommendations
from src.scoring.final import ScoreIntegrityError, score_final
from tests.helpers.trust_cases import competitor_noise_audit_run, no_citations_audit_run


def _prompt_result(
    *,
    cited: bool,
    cited_official_domain: bool = False,
    cited_third_party_domain: bool = False,
    metadata: dict | None = None,
) -> PromptResult:
    return PromptResult(
        provider="openai",
        query="Best coffee shops in Echo Park",
        cluster="discovery",
        mentioned=True,
        recommended=True,
        cited=cited,
        cited_official_domain=cited_official_domain,
        cited_third_party_domain=cited_third_party_domain,
        metadata=metadata or {},
    )


def _build_audit_run(
    *,
    visibility_score: float,
    web_presence: dict,
    prompt_results: list[PromptResult] | None = None,
    official_citation_share_score: int = 0,
) -> AuditRun:
    readiness = ReadinessResult(
        score=80,
        dimensions={
            "crawlability": CheckDimension(
                label="Crawlability",
                description="Can bots access the site?",
                score=80,
                weight=0.25,
                weighted_score=20.0,
            )
        },
    )
    visibility = VisibilityResult(
        score=visibility_score,
        dimensions={
            "official_citation_share": CheckDimension(
                label="Official Citation Share",
                description="How often engines cite the official domain.",
                score=official_citation_share_score,
                weight=0.15,
                weighted_score=round(official_citation_share_score * 0.15, 2),
                evidence=[f"visibility.official_citation_share={official_citation_share_score}"],
            )
        },
        overall_mention_rate=50.0,
        per_llm={},
        per_cluster={},
        top_competitors={},
        attributes_cited=[],
        prompt_results=prompt_results or [],
    )
    score = score_final(readiness=readiness, visibility=visibility, web_presence=web_presence)
    return AuditRun(
        mode="live",
        timestamp=datetime.fromisoformat("2026-03-17T12:00:00"),
        input=BusinessInput(
            business_name="Laveta",
            industry="coffee shop",
            city="Echo Park, Los Angeles",
            website_url="https://lavetacoffee.com",
        ),
        entity=BusinessEntity(
            business_name="Laveta",
            industry="coffee shop",
            city="Echo Park, Los Angeles",
            website_url="https://lavetacoffee.com",
        ),
        score=score,
        readiness=readiness,
        visibility=visibility,
        recommendations=[],
        web_presence=web_presence,
    )


def test_build_audit_ui_response_exposes_score_explanation_without_penalties():
    response = build_audit_ui_response(
        _build_audit_run(visibility_score=71.0, web_presence={})
    )

    assert response.score_explanation.readiness_score == 80
    assert response.score_explanation.visibility_score == 71.0
    assert response.score_explanation.weighted_base_score == 75.05
    assert response.score_explanation.penalties_total == 0.0
    assert response.score_explanation.final_score == 75
    assert response.score_explanation.penalties_applied == []


def test_build_audit_ui_response_exposes_penalty_totals_and_copy():
    response = build_audit_ui_response(
        _build_audit_run(
            visibility_score=71.0,
            web_presence={"has_noindex": True, "website_accessible": False},
        )
    )

    assert response.score_explanation.weighted_base_score == 75.05
    assert response.score_explanation.penalties_total == 40.0
    assert response.score_explanation.final_score == 35
    assert [penalty.key for penalty in response.score_explanation.penalties_applied] == [
        "noindex",
        "website_inaccessible",
    ]
    assert "penalties reduced the score by 40" in response.summary.overview.lower()

    overall_card = next(card for card in response.score_cards if card.key == "overall")
    assert "Weighted base" in overall_card.detail
    assert "penalties" in overall_card.detail


def test_build_audit_ui_response_fails_fast_on_score_integrity_mismatch():
    audit_run = _build_audit_run(visibility_score=71.0, web_presence={})
    inconsistent_audit_run = audit_run.model_copy(
        update={
            "score": audit_run.score.model_copy(update={"final": audit_run.score.final + 1}),
        }
    )

    with pytest.raises(ScoreIntegrityError):
        build_audit_ui_response(inconsistent_audit_run)


def test_build_audit_ui_response_uses_no_citation_state_in_summary_and_recommendations():
    audit_run = _build_audit_run(
        visibility_score=71.0,
        web_presence={},
        prompt_results=[_prompt_result(cited=False)],
        official_citation_share_score=0,
    )
    audit_run.recommendations = build_recommendations(audit_run)

    response = build_audit_ui_response(audit_run)

    assert response.citation_source_breakdown.evidence_state == "no_citations"
    assert response.citation_source_breakdown.note == "No cited answers were captured in this run."
    assert "No citations were captured in this run." in response.summary.overview
    assert response.top_recommendations[0].why_it_matters.startswith("No citations were captured")


def test_build_audit_ui_response_marks_unavailable_citation_diagnosis_as_inconclusive():
    audit_run = _build_audit_run(
        visibility_score=71.0,
        web_presence={},
        prompt_results=[
            _prompt_result(
                cited=False,
                metadata={"citation_parser_status": "unavailable"},
            )
        ],
        official_citation_share_score=0,
    )
    audit_run.recommendations = build_recommendations(audit_run)

    response = build_audit_ui_response(audit_run)

    assert response.citation_source_breakdown.evidence_state == "unavailable"
    assert response.citation_source_breakdown.note == (
        "Citation evidence was unavailable or incomplete, so source-support diagnosis is inconclusive."
    )
    assert "Citation diagnosis is inconclusive" in response.summary.overview
    assert "inconclusive" in response.top_recommendations[0].why_it_matters


def test_build_audit_ui_response_preserves_readiness_unknown_and_unavailable_states():
    audit_run = _build_audit_run(visibility_score=71.0, web_presence={"google_business_found": None})
    audit_run = audit_run.model_copy(
        update={
            "readiness": ReadinessResult(
                score=55,
                dimensions={
                    "listing_presence": CheckDimension(
                        label="Listing Presence",
                        description="Whether the business can be verified through core listings and local entity facts.",
                        score=50,
                        weight=0.2,
                        weighted_score=10.0,
                        checks={
                            "Google Business Profile": None,
                            "Yelp": None,
                        },
                        state="unavailable",
                        state_label="UNAVAILABLE",
                        state_note="Directory sources were unavailable in this run, so listing evidence is incomplete.",
                        check_states={
                            "Google Business Profile": ReadinessCheck(
                                state="unavailable",
                                short_label="UNAVAILABLE",
                                detail="Google Business data could not be verified because the external source was unavailable.",
                            ),
                            "Yelp": ReadinessCheck(
                                state="unknown",
                                short_label="UNVERIFIED",
                                detail="Yelp was not checked in this run.",
                            ),
                        },
                    )
                },
            ),
            "score": score_final(
                readiness=ReadinessResult(
                    score=55,
                    dimensions={},
                ),
                visibility=audit_run.visibility,
                web_presence={"google_business_found": None},
            ),
        }
    )

    response = build_audit_ui_response(audit_run)

    gap = response.readiness_gaps[0]
    assert gap.state == "unavailable"
    assert gap.state_label == "UNAVAILABLE"
    assert gap.unavailable_checks == ["Google Business Profile"]
    assert gap.unknown_checks == ["Yelp"]
    assert "incomplete" in gap.state_note.lower()
    assert any("unavailable" in note.lower() for note in response.summary.data_notes)


def test_build_audit_ui_response_keeps_verified_missing_readiness_checks_separate_from_unknown():
    audit_run = _build_audit_run(visibility_score=71.0, web_presence={"google_business_found": False})
    audit_run = audit_run.model_copy(
        update={
            "readiness": ReadinessResult(
                score=45,
                dimensions={
                    "listing_presence": CheckDimension(
                        label="Listing Presence",
                        description="Whether the business can be verified through core listings and local entity facts.",
                        score=40,
                        weight=0.2,
                        weighted_score=8.0,
                        checks={
                            "Google Business Profile": False,
                            "Yelp": None,
                        },
                        state="mixed",
                        state_label="PARTIAL",
                        state_note="Some listing signals were verified missing, while others remain incomplete.",
                        check_states={
                            "Google Business Profile": ReadinessCheck(
                                state="fail",
                                short_label="VERIFIED MISSING",
                                detail="The directory lookup ran and did not find a matching Google Business Profile.",
                            ),
                            "Yelp": ReadinessCheck(
                                state="unknown",
                                short_label="UNVERIFIED",
                                detail="Yelp was not checked in this run.",
                            ),
                        },
                    )
                },
            ),
            "score": score_final(
                readiness=ReadinessResult(
                    score=45,
                    dimensions={},
                ),
                visibility=audit_run.visibility,
                web_presence={"google_business_found": False},
            ),
        }
    )

    response = build_audit_ui_response(audit_run)

    gap = response.readiness_gaps[0]
    assert gap.state == "mixed"
    assert gap.verified_missing_checks == ["Google Business Profile"]
    assert gap.unknown_checks == ["Yelp"]
    assert gap.missing_checks == ["Google Business Profile"]


def test_trust_regression_no_citations_fixture_keeps_summary_and_recommendation_in_sync():
    response = build_audit_ui_response(no_citations_audit_run())

    assert response.summary.headline == "Laveta scores 75/100 on the GEO audit."
    assert response.citation_source_breakdown.evidence_state == "no_citations"
    assert response.citation_source_breakdown.note == "No cited answers were captured in this run."
    assert "No citations were captured in this run." in response.summary.overview
    assert response.top_recommendations[0].why_it_matters.startswith("No citations were captured")
    assert "being cited" not in response.top_recommendations[0].why_it_matters


def test_trust_regression_competitor_fixture_filters_junk_from_top_competitors():
    response = build_audit_ui_response(competitor_noise_audit_run())

    assert [(entry.name, entry.mentions) for entry in response.top_competitors] == [
        ("A-Team Plumbing", 3),
        ("Capital Flow Plumbing", 1),
    ]
    assert all("Warning" not in entry.name for entry in response.top_competitors)
    assert all("Source:" not in entry.name for entry in response.top_competitors)
