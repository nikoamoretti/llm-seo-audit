from pathlib import Path


def test_ui_template_uses_section_render_helpers():
    html = Path("ui.html").read_text()

    assert "function assertScoreExplanationIntegrity(" in html
    assert "function renderExecutiveSummary(" in html
    assert "function renderScoreCards(" in html
    assert "function renderScoreExplanation(" in html
    assert "function renderClusterPerformance(" in html
    assert "function renderCitationSources(" in html
    assert "function renderReadinessGaps(" in html
    assert "function renderCompetitorGap(" in html
    assert "function renderTopFixes(" in html
    assert "function renderImplementationChecklist(" in html
    assert "0.55 × Visibility + 0.45 × Readiness" not in html
