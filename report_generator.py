#!/usr/bin/env python3
"""Generate JSON and HTML audit reports."""

import json
from pathlib import Path
from datetime import datetime

from jinja2 import Template


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LLM Visibility Audit — {{ business_name }}</title>
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
        .tag { display: inline-block; background: var(--border); border-radius: 6px; padding: 0.25rem 0.6rem; margin: 0.2rem; font-size: 0.8rem; }
        .rec { padding: 0.75rem 1rem; border-left: 3px solid var(--accent); margin-bottom: 0.75rem; background: rgba(99,102,241,0.05); border-radius: 0 8px 8px 0; }
        .rec-high { border-left-color: var(--red); }
        .rec-med { border-left-color: var(--yellow); }
        .badge { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }
        .badge-demo { background: rgba(234,179,8,0.2); color: var(--yellow); }
        footer { text-align: center; color: var(--muted); font-size: 0.8rem; margin-top: 3rem; padding-top: 1.5rem; border-top: 1px solid var(--border); }
    </style>
</head>
<body>
    <h1>LLM Visibility Audit</h1>
    <p class="subtitle">
        {{ business_name }} &mdash; {{ industry }} in {{ city }}
        {% if mode == "demo" %}<span class="badge badge-demo">DEMO MODE</span>{% endif %}
        <br><small>Generated {{ timestamp }}</small>
    </p>

    <!-- Overall Score -->
    <div class="card score-hero">
        <div class="score-number {{ score_class }}">{{ scores.overall_score }}/100</div>
        <div class="score-label">Overall LLM Visibility Score</div>
    </div>

    <!-- Score Breakdown -->
    <div class="grid">
        <div class="card metric">
            <div class="metric-value">{{ scores.llm_visibility_score }}</div>
            <div class="metric-label">LLM Visibility</div>
        </div>
        <div class="card metric">
            <div class="metric-value">{{ scores.web_presence_score }}</div>
            <div class="metric-label">Web Presence</div>
        </div>
        <div class="card metric">
            <div class="metric-value">{{ scores.overall_mention_rate }}%</div>
            <div class="metric-label">Mention Rate</div>
        </div>
    </div>

    <!-- Per-LLM Breakdown -->
    <h2>Per-LLM Breakdown</h2>
    <div class="card">
        <table>
            <tr><th>LLM</th><th>Score</th><th>Mention Rate</th><th>Avg Position</th><th>Mentioned</th></tr>
            {% for provider, data in scores.per_llm.items() %}
            <tr>
                <td>{{ provider|title }}</td>
                <td><strong>{{ data.score }}</strong></td>
                <td>{{ data.mention_rate }}%</td>
                <td>{{ data.avg_position or 'N/A' }}</td>
                <td>{{ data.times_mentioned }}/{{ data.total_queries }}</td>
            </tr>
            {% endfor %}
        </table>
    </div>

    <!-- Web Presence -->
    {% if web_presence %}
    <h2>Web Presence</h2>
    <div class="card">
        <table>
            <tr><th>Check</th><th>Status</th></tr>
            {% for check_name, check_val in web_checks %}
            <tr>
                <td>{{ check_name }}</td>
                <td class="{{ 'pass' if check_val else 'fail' }}">{{ 'PASS' if check_val else 'FAIL' }}</td>
            </tr>
            {% endfor %}
        </table>
    </div>
    {% endif %}

    <!-- Top Competitors -->
    {% if scores.top_competitors %}
    <h2>Top Competitors Mentioned by LLMs</h2>
    <div class="card">
        <table>
            <tr><th>Competitor</th><th>Times Mentioned</th></tr>
            {% for comp, count in competitors_list %}
            <tr><td>{{ comp }}</td><td>{{ count }}</td></tr>
            {% endfor %}
        </table>
    </div>
    {% endif %}

    <!-- Attributes -->
    {% if scores.attributes_cited %}
    <h2>Attributes Cited</h2>
    <div class="card">
        {% for attr in scores.attributes_cited[:15] %}
        <span class="tag">{{ attr }}</span>
        {% endfor %}
    </div>
    {% endif %}

    <!-- Recommendations -->
    {% if recommendations %}
    <h2>Recommendations</h2>
    <div class="card">
        {% for rec in recommendations %}
        <div class="rec {{ 'rec-high' if loop.index <= 3 else 'rec-med' }}">
            <strong>{{ 'HIGH' if loop.index <= 3 else 'MED' }}</strong> &mdash; {{ rec }}
        </div>
        {% endfor %}
    </div>
    {% endif %}

    <footer>
        LLM SEO Visibility Audit &mdash; Generated {{ timestamp }}
        {% if mode == "demo" %}<br>Demo mode &mdash; simulated data{% endif %}
    </footer>
</body>
</html>"""


class ReportGenerator:
    def __init__(self, results: dict, output_dir: Path):
        self.results = results
        self.output_dir = output_dir

    def save_json(self) -> Path:
        path = self.output_dir / "audit_report.json"
        with open(path, "w") as f:
            json.dump(self.results, f, indent=2, default=str)
        return path

    def save_html(self) -> Path:
        path = self.output_dir / "audit_report.html"
        scores = self.results["scores"]
        score = scores["overall_score"]

        if score >= 70:
            score_class = "score-green"
        elif score >= 40:
            score_class = "score-yellow"
        else:
            score_class = "score-red"

        web_presence = self.results.get("web_presence", {})
        web_checks = []
        if web_presence:
            web_checks = [
                ("Schema/Structured Data", web_presence.get("has_schema_markup", False)),
                ("Open Graph Tags", web_presence.get("has_og_tags", False)),
                ("Meta Description", web_presence.get("has_meta_description", False)),
                ("Title Tag", web_presence.get("has_title_tag", False)),
                ("SSL Certificate", web_presence.get("ssl_valid", False)),
                ("Mobile-Friendly Meta", web_presence.get("mobile_friendly_meta", False)),
                ("Google Business Profile", web_presence.get("google_business_found", False)),
                ("Yelp Listing", web_presence.get("yelp_found", False)),
                ("BBB Listing", web_presence.get("bbb_found", False)),
                ("Fast Load Time", web_presence.get("fast_load", False)),
            ]

        competitors_list = list(scores.get("top_competitors", {}).items())[:10]

        # Generate recommendations
        from audit import generate_recommendations
        recommendations = generate_recommendations(self.results)

        template = Template(HTML_TEMPLATE)
        html = template.render(
            business_name=self.results["business_name"],
            industry=self.results["industry"],
            city=self.results["city"],
            mode=self.results.get("mode", "live"),
            timestamp=self.results.get("timestamp", datetime.now().isoformat()),
            scores=scores,
            score_class=score_class,
            web_presence=web_presence,
            web_checks=web_checks,
            competitors_list=competitors_list,
            recommendations=recommendations,
        )

        with open(path, "w") as f:
            f.write(html)
        return path
