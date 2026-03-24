#!/usr/bin/env python3
"""Generate JSON and HTML audit reports from the canonical AuditRun model."""

import json
from pathlib import Path

from jinja2 import Template

from src.core.models import AuditRun
from src.presentation import build_audit_ui_response
from src.scoring.final import format_score_value


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LLM Visibility Audit — {{ audit_run.entity.business_name }}</title>
    <style>
        :root {
            --bg: #0f1117; --surface: #1a1d27; --border: #2a2d3a;
            --text: #e4e4e7; --muted: #9ca3af; --accent: #6366f1;
            --green: #22c55e; --yellow: #eab308; --red: #ef4444;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); padding: 2rem; max-width: 900px; margin: 0 auto; }
        h1 { font-size: 1.8rem; margin-bottom: 0.5rem; }
        h2 { font-size: 1.3rem; margin: 2rem 0 1rem; color: var(--accent); }
        .subtitle { color: var(--muted); margin-bottom: 2rem; }
        .card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem; }
        .score-hero { text-align: center; padding: 2.5rem; }
        .score-number { font-size: 4rem; font-weight: 800; }
        .score-label { font-size: 1.2rem; color: var(--muted); margin-top: 0.5rem; }
        .score-green { color: var(--green); }
        .score-yellow { color: var(--yellow); }
        .score-red { color: var(--red); }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 1rem; }
        .metric { text-align: center; padding: 1rem; }
        .metric-value { font-size: 2rem; font-weight: 700; }
        .metric-label { color: var(--muted); font-size: 0.85rem; margin-top: 0.3rem; }
        table { width: 100%; border-collapse: collapse; }
        th, td { text-align: left; padding: 0.75rem 1rem; border-bottom: 1px solid var(--border); }
        th { color: var(--muted); font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; }
        .pass { color: var(--green); font-weight: 600; }
        .fail { color: var(--red); font-weight: 600; }
        .unknown { color: var(--yellow); font-weight: 600; }
        .tag { display: inline-block; background: var(--border); border-radius: 6px; padding: 0.25rem 0.6rem; margin: 0.2rem; font-size: 0.8rem; }
        .rec { padding: 0.75rem 1rem; border-left: 3px solid var(--accent); margin-bottom: 0.75rem; background: rgba(99,102,241,0.05); border-radius: 0 8px 8px 0; }
        .rec-high { border-left-color: var(--red); }
        .rec-med { border-left-color: var(--yellow); }
        .rec-label { color: var(--muted); font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.04em; margin-top: 0.65rem; }
        .badge { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }
        .badge-demo { background: rgba(234,179,8,0.2); color: var(--yellow); }
        .split { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem; }
        .list-card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 1.25rem; }
        .list-card h3 { font-size: 0.95rem; margin-bottom: 0.8rem; color: var(--text); }
        .stack { display: flex; flex-direction: column; gap: 0.8rem; }
        .stack-item { padding-bottom: 0.8rem; border-bottom: 1px solid var(--border); }
        .stack-item:last-child { border-bottom: none; padding-bottom: 0; }
        .eyebrow { color: var(--muted); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 0.35rem; }
        .summary-list { margin-top: 1rem; display: flex; flex-wrap: wrap; gap: 0.4rem; }
        .empty-state { color: var(--muted); font-size: 0.9rem; }
        .checklist-item { padding: 0.9rem 1rem; border: 1px solid var(--border); border-radius: 10px; background: rgba(255,255,255,0.02); }
        .score-note { color: var(--muted); font-size: 0.8rem; line-height: 1.5; margin-top: 0.45rem; }
        .pill-strong { color: var(--green); }
        .pill-mixed { color: var(--yellow); }
        .pill-weak { color: var(--red); }
        .pill-unknown { color: var(--yellow); }
        footer { text-align: center; color: var(--muted); font-size: 0.8rem; margin-top: 3rem; padding-top: 1.5rem; border-top: 1px solid var(--border); }
    </style>
</head>
<body>
    <h1>LLM Visibility Audit</h1>
    <p class="subtitle">
        {{ audit_run.entity.business_name }} &mdash; {{ audit_run.entity.industry }} in {{ audit_run.entity.city }}
        {% if audit_run.mode == "demo" %}<span class="badge badge-demo">DEMO MODE</span>{% endif %}
        <br><small>Generated {{ timestamp }}</small>
    </p>

    <div class="card score-hero">
        <div class="score-number {{ score_class }}">{{ presentation.score_explanation.final_score }}/100</div>
        <div class="score-label">Overall GEO Score</div>
    </div>

    <h2>Executive Summary</h2>
    <div class="card">
        <p><strong>{{ presentation.summary.headline }}</strong></p>
        <p class="subtitle">{{ presentation.summary.overview }}</p>
        <div class="split">
            <div class="list-card">
                <div class="eyebrow">Observed Wins</div>
                {% if presentation.summary.wins %}
                <div class="summary-list">
                    {% for win in presentation.summary.wins %}
                    <span class="tag">{{ win }}</span>
                    {% endfor %}
                </div>
                {% else %}
                <p class="empty-state">No clear wins surfaced in this run.</p>
                {% endif %}
            </div>
            <div class="list-card">
                <div class="eyebrow">Observed Losses</div>
                {% if presentation.summary.losses %}
                <div class="summary-list">
                    {% for loss in presentation.summary.losses %}
                    <span class="tag">{{ loss }}</span>
                    {% endfor %}
                </div>
                {% else %}
                <p class="empty-state">No major losses surfaced in this run.</p>
                {% endif %}
            </div>
        </div>
        {% if presentation.summary.data_notes %}
        <div class="rec" style="margin-top: 1rem;">
            <div class="rec-label">Partial Data Notes</div>
            <small>{{ presentation.summary.data_notes | join('; ') }}</small>
        </div>
        {% endif %}
    </div>

    <div class="grid">
        {% for card in presentation.score_cards %}
        <div class="card metric">
            <div class="metric-value">{{ format_score(card.score) }}</div>
            <div class="metric-label">{{ card.label }}</div>
            <div class="score-note">{{ card.detail }}</div>
        </div>
        {% endfor %}
    </div>

    <h2>Score Explanation</h2>
    <div class="card">
        <div class="eyebrow">Final Score Calculation</div>
        <p class="score-note">{{ presentation.score_explanation.formula }}</p>
        <div class="grid" style="margin-top: 1rem;">
            <div class="card metric">
                <div class="metric-value">{{ format_score(presentation.score_explanation.readiness_score) }}</div>
                <div class="metric-label">Readiness Score</div>
            </div>
            <div class="card metric">
                <div class="metric-value">{{ format_score(presentation.score_explanation.visibility_score) }}</div>
                <div class="metric-label">Visibility Score</div>
            </div>
            <div class="card metric">
                <div class="metric-value">{{ format_score(presentation.score_explanation.weighted_base_score) }}</div>
                <div class="metric-label">Weighted Base Score</div>
            </div>
            <div class="card metric">
                <div class="metric-value">{{ format_score(presentation.score_explanation.penalties_total) }}</div>
                <div class="metric-label">Penalty Points</div>
            </div>
            <div class="card metric">
                <div class="metric-value">{{ format_score(presentation.score_explanation.final_score) }}</div>
                <div class="metric-label">Final Score</div>
            </div>
        </div>
        <p class="score-note">{{ presentation.score_explanation.rounding_note }}</p>
        {% if presentation.score_explanation.penalties_applied %}
        <table style="margin-top: 1rem;">
            <tr><th>Penalty</th><th>Points</th><th>Reason</th></tr>
            {% for penalty in presentation.score_explanation.penalties_applied %}
            <tr>
                <td>{{ penalty.label }}</td>
                <td>{{ format_score(penalty.points) }}</td>
                <td>{{ penalty.reason }}</td>
            </tr>
            {% endfor %}
        </table>
        {% else %}
        <p class="score-note">No penalties were applied in this run.</p>
        {% endif %}
    </div>

    {% if readiness_dimensions or visibility_dimensions %}
    <h2>Component Detail</h2>
    <div class="grid">
        {% if readiness_dimensions %}
        <div class="card">
            <table>
                <tr><th>Readiness Component</th><th>Score</th><th>Status</th><th>Weight</th><th>Weighted</th><th>Notes</th></tr>
                {% for dimension in readiness_dimensions %}
                <tr>
                    <td>{{ dimension.label }}</td>
                    <td>{{ format_score(dimension.score) }}</td>
                    <td class="{{ readiness_state_class(dimension.state) }}">{{ dimension.state_label or 'UNVERIFIED' }}</td>
                    <td>{{ format_score(dimension.weight) }}</td>
                    <td>{{ format_score(dimension.weighted_score) }}</td>
                    <td>{{ dimension.state_note }}</td>
                </tr>
                {% endfor %}
            </table>
        </div>
        {% endif %}
        {% if visibility_dimensions %}
        <div class="card">
            <table>
                <tr><th>Visibility Component</th><th>Score</th><th>Weight</th><th>Weighted</th></tr>
                {% for dimension in visibility_dimensions %}
                <tr>
                    <td>{{ dimension.label }}</td>
                    <td>{{ format_score(dimension.score) }}</td>
                    <td>{{ format_score(dimension.weight) }}</td>
                    <td>{{ format_score(dimension.weighted_score) }}</td>
                </tr>
                {% endfor %}
            </table>
        </div>
        {% endif %}
    </div>
    {% endif %}

    {% if readiness_dimensions %}
    <h2>Readiness Verification Detail</h2>
    <div class="split">
        {% for dimension in readiness_dimensions %}
        <div class="list-card">
            <h3>{{ dimension.label }} <span class="{{ readiness_state_class(dimension.state) }}">{{ dimension.state_label or 'UNVERIFIED' }}</span></h3>
            <div class="score-note">{{ dimension.description }}</div>
            {% if dimension.state_note %}
            <div class="score-note">{{ dimension.state_note }}</div>
            {% endif %}
            {% if dimension.check_states %}
            <table style="margin-top: 0.8rem;">
                <tr><th>Check</th><th>Status</th><th>Notes</th></tr>
                {% for name, check in dimension.check_states.items() %}
                <tr>
                    <td>{{ name }}</td>
                    <td class="{{ readiness_state_class(check.state) }}">{{ check.short_label }}</td>
                    <td>{{ check.detail }}</td>
                </tr>
                {% endfor %}
            </table>
            {% else %}
            <p class="empty-state">No readiness checks were captured for this area.</p>
            {% endif %}
        </div>
        {% endfor %}
    </div>
    {% endif %}

    <h2>Wins and Losses by Prompt Cluster</h2>
    <div class="split">
        <div class="list-card">
            <h3>Wins</h3>
            {% if cluster_wins %}
            <div class="stack">
                {% for cluster in cluster_wins %}
                <div class="stack-item">
                    <strong>{{ cluster.label }}</strong> <span class="pill-strong">{{ cluster.score }}</span>
                    <div class="score-note">{{ cluster.summary }}</div>
                </div>
                {% endfor %}
            </div>
            {% else %}
            <p class="empty-state">No prompt clusters are performing strongly yet.</p>
            {% endif %}
        </div>
        <div class="list-card">
            <h3>Losses</h3>
            {% if cluster_losses %}
            <div class="stack">
                {% for cluster in cluster_losses %}
                <div class="stack-item">
                    <strong>{{ cluster.label }}</strong> <span class="pill-weak">{{ cluster.score }}</span>
                    <div class="score-note">{{ cluster.summary }}</div>
                </div>
                {% endfor %}
            </div>
            {% else %}
            <p class="empty-state">No material cluster losses were observed in this run.</p>
            {% endif %}
        </div>
    </div>

    <h2>Official Site Citation Share</h2>
    <div class="split">
        <div class="card metric">
            <div class="metric-value">{{ presentation.citation_source_breakdown.official_site_share }}%</div>
            <div class="metric-label">Official Site Share</div>
            <div class="score-note">{{ presentation.citation_source_breakdown.official_citation_count }} official cited prompts, {{ presentation.citation_source_breakdown.third_party_citation_count }} third-party cited prompts.</div>
            {% if presentation.citation_source_breakdown.note %}
            <div class="score-note">{{ presentation.citation_source_breakdown.note }}</div>
            {% endif %}
        </div>
        <div class="list-card">
            <h3>Readiness Gaps</h3>
            {% if presentation.readiness_gaps %}
            <div class="stack">
                {% for gap in presentation.readiness_gaps[:5] %}
                <div class="stack-item">
                    <strong>{{ gap.label }}</strong> <span class="{{ readiness_state_class(gap.state) }}">{{ gap.state_label }}</span>
                    <div class="score-note">Score {{ gap.score }}</div>
                    <div class="score-note">{{ gap.summary }}</div>
                    {% if gap.state_note %}
                    <div class="score-note">{{ gap.state_note }}</div>
                    {% endif %}
                    {% if gap.verified_missing_checks %}
                    <small>Verified missing: {{ gap.verified_missing_checks | join(', ') }}</small><br>
                    {% endif %}
                    {% if gap.partial_checks %}
                    <small>Partial: {{ gap.partial_checks | join(', ') }}</small><br>
                    {% endif %}
                    {% if gap.unknown_checks %}
                    <small>Unverified: {{ gap.unknown_checks | join(', ') }}</small><br>
                    {% endif %}
                    {% if gap.unavailable_checks %}
                    <small>Unavailable: {{ gap.unavailable_checks | join(', ') }}</small>
                    {% endif %}
                </div>
                {% endfor %}
            </div>
            {% else %}
            <p class="empty-state">No major readiness gaps surfaced in this run.</p>
            {% endif %}
            {% if directory_statuses %}
            <div class="rec-label">Directory Check Status</div>
            <small>
                {% for item in directory_statuses %}
                {{ item.label }}: {{ item.status }}{% if not loop.last %}<br>{% endif %}
                {% endfor %}
            </small>
            {% endif %}
        </div>
    </div>

    <h2>Third-Party Authority Picture</h2>
    <div class="card">
        {% if presentation.citation_source_breakdown.top_third_party_domains %}
        <table>
            <tr><th>Domain</th><th>Citations</th></tr>
            {% for domain in presentation.citation_source_breakdown.top_third_party_domains %}
            <tr><td>{{ domain.domain }}</td><td>{{ domain.citations }}</td></tr>
            {% endfor %}
        </table>
        {% else %}
        <p class="empty-state">{{ presentation.citation_source_breakdown.note or 'No third-party citation sources were captured in this run.' }}</p>
        {% endif %}
    </div>

    <h2>Competitor Gap</h2>
    <div class="split">
        <div class="card metric">
            <div class="metric-value">{{ competitor_gap_score }}</div>
            <div class="metric-label">Competitor Gap Score</div>
            <div class="score-note">{{ competitor_gap_evidence }}</div>
        </div>
        <div class="list-card">
            <h3>Top Competitors Mentioned</h3>
            {% if competitors_list %}
            <table>
                <tr><th>Competitor</th><th>Times Mentioned</th></tr>
                {% for comp, count in competitors_list %}
                <tr><td>{{ comp }}</td><td>{{ count }}</td></tr>
                {% endfor %}
            </table>
            {% else %}
            <p class="empty-state">No competitor mentions were captured in this run.</p>
            {% endif %}
        </div>
    </div>

    <h2>Top 10 Fixes</h2>
    <div class="card">
        {% if presentation.top_recommendations %}
        {% for rec in presentation.top_recommendations %}
        <div class="rec {{ 'rec-high' if rec.priority == 'P0' else 'rec-med' }}">
            <strong>{{ rec.priority }}</strong> &mdash; {{ rec.title }}
            <div class="rec-label">Why it matters</div>
            <small>{{ rec.why_it_matters or rec.detail }}</small>
            {% if rec.evidence %}
            <div class="rec-label">Evidence</div>
            <small>{{ rec.evidence | join('; ') }}</small>
            {% endif %}
            {% if rec.impacted_components %}
            <div class="rec-label">Impacted components</div>
            <small>{{ rec.impacted_components | join(', ') }}</small>
            {% endif %}
            {% if rec.implementation_hint %}
            <div class="rec-label">Implementation hint</div>
            <small>{{ rec.implementation_hint }}</small>
            {% endif %}
        </div>
        {% endfor %}
        {% else %}
        <p class="empty-state">No prioritized fixes were generated for this run.</p>
        {% endif %}
    </div>

    <h2>Implementation Checklist</h2>
    <div class="card">
        {% if presentation.implementation_checklist %}
        <div class="stack">
            {% for item in presentation.implementation_checklist %}
            <div class="checklist-item">
                <strong>{{ item.priority }}</strong> &mdash; {{ item.title }}
                <div class="rec-label">{{ item.category }}</div>
                <small>{{ item.implementation_hint }}</small>
                {% if item.evidence %}
                <div class="rec-label">Evidence</div>
                <small>{{ item.evidence | join('; ') }}</small>
                {% endif %}
            </div>
            {% endfor %}
        </div>
        {% else %}
        <p class="empty-state">No implementation checklist was generated for this run.</p>
        {% endif %}
    </div>

    <footer>
        LLM SEO Visibility Audit &mdash; Generated {{ timestamp }}
        {% if audit_run.mode == "demo" %}<br>Demo mode &mdash; simulated data{% endif %}
    </footer>
</body>
</html>"""


class ReportGenerator:
    def __init__(self, audit_run: AuditRun, output_dir: Path):
        if not isinstance(audit_run, AuditRun):
            raise TypeError("ReportGenerator requires an AuditRun instance.")
        self.audit_run = audit_run
        self.output_dir = output_dir

    def save_json(self) -> Path:
        path = self.output_dir / "audit_report.json"
        with open(path, "w") as file_obj:
            json.dump(self.audit_run.model_dump(mode="json"), file_obj, indent=2)
        return path

    def save_html(self) -> Path:
        path = self.output_dir / "audit_report.html"
        presentation = build_audit_ui_response(self.audit_run)
        score = presentation.score_explanation.final_score

        if score >= 70:
            score_class = "score-green"
        elif score >= 40:
            score_class = "score-yellow"
        else:
            score_class = "score-red"

        competitors_list = [
            (entry.name, entry.mentions)
            for entry in presentation.top_competitors
        ]
        readiness_dimensions = list(self.audit_run.readiness.dimensions.values())
        visibility_dimensions = list(self.audit_run.visibility.dimensions.values())
        competitor_gap_dimension = self.audit_run.visibility.dimensions.get("competitor_gap")
        competitor_gap_score = competitor_gap_dimension.score if competitor_gap_dimension else 0
        competitor_gap_evidence = (
            "; ".join(competitor_gap_dimension.evidence)
            if competitor_gap_dimension and competitor_gap_dimension.evidence
            else "No competitor-gap evidence captured."
        )
        directory_statuses = [
            {
                "label": "Google Business Profile",
                "status": _source_status_label(self.audit_run.web_presence, "google_business_found"),
            },
            {
                "label": "Yelp",
                "status": _source_status_label(self.audit_run.web_presence, "yelp_found"),
            },
        ]
        cluster_wins = [
            cluster for cluster in presentation.prompt_cluster_performance
            if cluster.status == "strong"
        ][:4]
        cluster_losses = [
            cluster for cluster in presentation.prompt_cluster_performance
            if cluster.status != "strong"
        ][:4]
        template = Template(HTML_TEMPLATE)
        html = template.render(
            audit_run=self.audit_run,
            presentation=presentation,
            timestamp=self.audit_run.timestamp.isoformat(),
            score_class=score_class,
            competitors_list=competitors_list,
            readiness_dimensions=readiness_dimensions,
            visibility_dimensions=visibility_dimensions,
            cluster_wins=cluster_wins,
            cluster_losses=cluster_losses,
            competitor_gap_score=competitor_gap_score,
            competitor_gap_evidence=competitor_gap_evidence,
            directory_statuses=directory_statuses,
            format_score=format_score_value,
            readiness_state_class=_readiness_state_class,
        )

        with open(path, "w") as file_obj:
            file_obj.write(html)
        return path


def _source_status_label(payload: dict[str, object], key: str) -> str:
    if key not in payload:
        return "NOT CHECKED"
    status = payload.get(key)
    if status is None:
        return "SOURCE UNAVAILABLE"
    return "VERIFIED" if status else "VERIFIED MISSING"


def _readiness_state_class(state: str) -> str:
    if state == "pass":
        return "pill-strong"
    if state == "fail":
        return "pill-weak"
    return "pill-unknown"
