from pathlib import Path


def test_ui_template_uses_section_render_helpers():
    html = Path("ui.html").read_text()

    assert "function renderExecutiveSummary(" in html
    assert "function renderScoreCards(" in html
    assert "function renderClusterPerformance(" in html
    assert "function renderCitationSources(" in html
    assert "function renderReadinessGaps(" in html
    assert "function renderCompetitorGap(" in html
    assert "function renderTopFixes(" in html
    assert "function renderImplementationChecklist(" in html
