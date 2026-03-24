#!/usr/bin/env python3
"""
LLM SEO Visibility Audit Tool
Audits a business's visibility across major LLM platforms.

Usage:
    python audit.py "Business Name" "industry" "city"
    python audit.py "Business Name" "industry" "city" --url https://example.com
    python audit.py "Business Name" "industry" "city" --demo
"""

import argparse
import os
import re
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich import box

from app import compute_geo_score, compute_readiness_score, compute_visibility_score
from analyzer import ResponseAnalyzer
from demo_mode import DemoAuditor
from llm_querier import LLMQuerier
from report_generator import ReportGenerator
from src.analysis.competitors import select_report_competitors
from src.core.audit_builder import build_audit_run
from src.core.models import AuditRun
from web_presence import WebPresenceChecker

console = Console()

QUERIES = [
    "What are the best {industry} businesses in {city}?",
    "Can you recommend a {industry} in {city}?",
    "Top rated {industry} near {city}",
    "Who is the most trusted {industry} in {city}?",
    "I'm looking for {industry} services in {city}. What are my options?",
    "Which {industry} companies in {city} have the best reputation?",
]


def detect_api_keys() -> dict:
    """Detect available API keys from environment."""
    keys = {}
    for name, env_var in [
        ("anthropic", "ANTHROPIC_API_KEY"),
        ("openai", "OPENAI_API_KEY"),
        ("gemini", "GEMINI_API_KEY"),
        ("perplexity", "PERPLEXITY_API_KEY"),
    ]:
        val = os.environ.get(env_var, "")
        if val and not val.startswith("your-"):
            keys[name] = val
    return keys


def run_audit(business_name: str, industry: str, city: str,
              website_url: Optional[str] = None, demo: bool = False):
    """Run the full LLM visibility audit."""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = re.sub(r'[^\w]', '_', business_name.lower())
    output_dir = Path(__file__).parent / "reports" / f"{safe_name}_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    console.print()
    console.print(Panel.fit(
        f"[bold cyan]LLM SEO Visibility Audit[/]\n"
        f"[white]Business:[/] [bold]{business_name}[/]\n"
        f"[white]Industry:[/] {industry}\n"
        f"[white]City:[/] {city}\n"
        f"[white]Website:[/] {website_url or 'Not provided'}",
        border_style="cyan",
        title="[bold]Audit Configuration[/]",
    ))
    console.print()

    # --- Check for API keys ---
    api_keys = detect_api_keys()

    if demo or not api_keys:
        if not api_keys:
            console.print("[yellow]No API keys detected. Running in DEMO mode with simulated data.[/]")
            console.print("[dim]Set ANTHROPIC_API_KEY, OPENAI_API_KEY, or PERPLEXITY_API_KEY to run live.[/]\n")
        else:
            console.print("[yellow]Demo mode requested. Using simulated data.[/]\n")

        demo_auditor = DemoAuditor(business_name, industry, city, website_url)
        results = demo_auditor.run()
        audit_run = build_audit_run(
            mode="demo",
            business_name=business_name,
            industry=industry,
            city=city,
            website_url=website_url,
            phone=None,
            web_presence=results["web_presence"],
            llm_results=results["llm_results"],
            api_keys_used=results.get("api_keys_available", []),
            timestamp=results.get("timestamp"),
        )
    else:
        available = ", ".join(api_keys.keys())
        console.print(f"[green]API keys found:[/] {available}\n")
        results = run_live_audit(business_name, industry, city, website_url, api_keys)
        audit_run = build_audit_run(
            mode="live",
            business_name=business_name,
            industry=industry,
            city=city,
            website_url=website_url,
            phone=None,
            web_presence=results["web_presence"],
            llm_results=results["llm_results"],
            api_keys_used=results.get("api_keys_available", []),
            timestamp=results.get("timestamp"),
        )

    # --- Generate Reports ---
    report_gen = ReportGenerator(audit_run, output_dir)

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  console=console, transient=True) as progress:
        progress.add_task("Generating reports...", total=None)
        json_path = report_gen.save_json()
        html_path = report_gen.save_html()

    console.print()
    print_terminal_report(audit_run)

    console.print()
    console.print(Panel(
        f"[green]JSON:[/] {json_path}\n[green]HTML:[/] {html_path}",
        title="[bold]Reports Saved[/]",
        border_style="green",
    ))

    return audit_run.model_dump(mode="json")


def run_live_audit(business_name: str, industry: str, city: str,
                   website_url: Optional[str], api_keys: dict) -> dict:
    """Run a live audit using real API calls."""

    queries = [q.format(industry=industry, city=city) for q in QUERIES]
    querier = LLMQuerier(api_keys)
    known_facts = {"city": city, "industry": industry}
    if website_url:
        known_facts["website"] = website_url
    analyzer = ResponseAnalyzer(business_name, known_facts=known_facts)

    # --- Query LLMs ---
    llm_results = {}
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  console=console) as progress:
        for provider in api_keys:
            task = progress.add_task(f"Querying {provider.title()}...", total=len(queries))
            provider_responses = []
            for query in queries:
                try:
                    engine_response = querier.query_structured(provider, query)
                    response = engine_response.raw_text
                    analysis = analyzer.analyze_response(response, query)
                    provider_responses.append({
                        "query": query,
                        "response": response,
                        "engine_response": asdict(engine_response),
                        "analysis": analysis,
                    })
                except Exception as e:
                    console.print(f"  [red]Error querying {provider}: {e}[/]")
                    provider_responses.append({
                        "query": query,
                        "response": f"ERROR: {e}",
                        "analysis": analyzer.empty_analysis(),
                    })
                progress.update(task, advance=1)
                time.sleep(0.5)  # Rate limiting
            llm_results[provider] = provider_responses

    # --- Web Presence Check ---
    web_results = {}
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  console=console, transient=True) as progress:
        progress.add_task("Checking web presence...", total=None)
        checker = WebPresenceChecker()
        web_results = checker.check_all(business_name, website_url or "", city)

    return {
        "business_name": business_name,
        "industry": industry,
        "city": city,
        "website_url": website_url,
        "timestamp": datetime.now().isoformat(),
        "api_keys_available": list(api_keys.keys()),
        "queries": [q.format(industry=industry, city=city) for q in QUERIES],
        "llm_results": llm_results,
        "web_presence": web_results,
    }


def compute_scores(llm_results: dict, web_results: dict, providers: list) -> dict:
    """Legacy wrapper over the active score_v2 engine."""
    del providers

    readiness = compute_readiness_score(web_results)
    visibility = compute_visibility_score(llm_results)
    canonical_scores = compute_geo_score(readiness, visibility, bool(web_results))

    per_llm = {
        provider: {
            "score": data.get("visibility_score", 0),
            "mention_rate": data.get("mention_rate", 0),
            "avg_position": data.get("avg_position"),
            "total_queries": data.get("total_queries", 0),
            "times_mentioned": data.get("times_mentioned", 0),
            "top_competitors": data.get("top_competitors", {}),
            "attributes_cited": data.get("attributes_cited", []),
        }
        for provider, data in visibility.get("per_llm", {}).items()
    }
    avg_positions = [
        data["avg_position"]
        for data in per_llm.values()
        if data.get("avg_position") is not None
    ]

    return {
        "overall_score": canonical_scores["geo_score"],
        "llm_visibility_score": canonical_scores["visibility_score"],
        "web_presence_score": canonical_scores["readiness_score"],
        "per_llm": per_llm,
        "overall_mention_rate": visibility.get("overall_mention_rate", 0),
        "overall_avg_position": round(sum(avg_positions) / len(avg_positions), 1) if avg_positions else None,
        "top_competitors": visibility.get("top_competitors", {}),
        "attributes_cited": visibility.get("attributes_cited", []),
    }


def print_terminal_report(audit_run: AuditRun):
    """Print a formatted terminal report."""

    def format_check_status(status):
        if status is None:
            return "[yellow]NOT CHECKED[/]"
        return "[green]PASS[/]" if status else "[red]FAIL[/]"

    def format_source_status(payload, key):
        if key not in payload:
            return "[yellow]NOT CHECKED[/]"
        status = payload.get(key)
        if status is None:
            return "[yellow]SOURCE UNAVAILABLE[/]"
        return "[green]VERIFIED[/]" if status else "[red]VERIFIED MISSING[/]"

    business_variants = [audit_run.entity.business_name, audit_run.input.business_name]

    # --- Overall Score ---
    score = audit_run.score.final
    if score >= 70:
        color = "green"
        grade = "STRONG"
    elif score >= 40:
        color = "yellow"
        grade = "MODERATE"
    else:
        color = "red"
        grade = "WEAK"

    console.print(Panel(
        f"[bold {color}]{score}/100[/] - {grade}",
        title="[bold]Overall GEO Score[/]",
        border_style=color,
        padding=(1, 4),
    ))

    # --- Per-LLM Breakdown ---
    table = Table(title="Per-LLM Breakdown", box=box.ROUNDED, show_lines=True)
    table.add_column("LLM", style="bold cyan", width=14)
    table.add_column("Score", justify="center", width=8)
    table.add_column("Mention Rate", justify="center", width=14)
    table.add_column("Avg Position", justify="center", width=14)
    table.add_column("Times Mentioned", justify="center", width=16)

    for provider, data in audit_run.visibility.per_llm.items():
        s = round(data.visibility_score, 1)
        sc = "green" if s >= 70 else ("yellow" if s >= 40 else "red")
        table.add_row(
            provider.title(),
            f"[{sc}]{s}[/]",
            f"{data.mention_rate}%",
            str(data.avg_position or 'N/A'),
            f"{data.times_mentioned}/{data.total_queries}",
        )
    console.print(table)

    # --- Web Presence ---
    if audit_run.web_presence:
        wp = audit_run.web_presence
        web_table = Table(title="Web Presence Checks", box=box.ROUNDED, show_lines=True)
        web_table.add_column("Check", width=30)
        web_table.add_column("Status", justify="center", width=18)

        checks = [
            ("Schema/Structured Data", wp.get("has_schema_markup")),
            ("Open Graph Tags", wp.get("has_og_tags")),
            ("Meta Description", wp.get("has_meta_description")),
            ("Title Tag", wp.get("has_title_tag")),
            ("SSL Certificate", wp.get("ssl_valid")),
            ("Mobile-Friendly Meta", wp.get("mobile_friendly_meta")),
            ("Google Business Profile", format_source_status(wp, "google_business_found")),
            ("Yelp Listing", format_source_status(wp, "yelp_found")),
            ("Fast Load Time", wp.get("fast_load")),
        ]
        for name, status in checks:
            rendered_status = status if isinstance(status, str) else format_check_status(status)
            web_table.add_row(name, rendered_status)

        ws = audit_run.score.readiness
        web_table.add_row("[bold]Web Presence Score[/]", f"[bold]{ws}/100[/]")
        console.print(web_table)

    # --- Competitors ---
    visible_competitors = select_report_competitors(
        audit_run.visibility.top_competitors,
        business_variants=business_variants,
    )
    if visible_competitors:
        comp_table = Table(title="Top Competitors Mentioned by LLMs", box=box.ROUNDED)
        comp_table.add_column("Competitor", style="bold")
        comp_table.add_column("Times Mentioned", justify="center")

        for comp, count in visible_competitors[:10]:
            comp_table.add_row(comp, str(count))
        console.print(comp_table)

    # --- Attributes ---
    if audit_run.visibility.attributes_cited:
        attrs = audit_run.visibility.attributes_cited[:15]
        console.print(Panel(
            ", ".join(attrs),
            title="[bold]Attributes/Reasons LLMs Cite[/]",
            border_style="blue",
        ))

    # --- Recommendations ---
    recs = audit_run.recommendations
    if recs:
        rec_table = Table(title="Recommendations to Improve LLM Visibility",
                          box=box.ROUNDED, show_lines=True)
        rec_table.add_column("Priority", justify="center", width=10)
        rec_table.add_column("Recommendation", width=70)

        priority_colors = {"P0": "red", "P1": "yellow", "P2": "cyan"}
        for rec in recs:
            color = priority_colors.get(rec.priority, "white")
            rec_table.add_row(
                f"[{color}]{rec.priority}[/]",
                (
                    f"{rec.title}\n"
                    f"[dim]{rec.why_it_matters or rec.detail}[/]\n"
                    f"[blue]Hint:[/] {rec.implementation_hint}"
                ),
            )
        console.print(rec_table)

    # --- Demo mode notice ---
    if audit_run.mode == "demo":
        console.print()
        console.print(Panel(
            "[yellow]This audit was run in DEMO mode with simulated data.\n"
            "Set API keys to run a live audit with real LLM responses.[/]",
            border_style="yellow",
        ))


def main():
    parser = argparse.ArgumentParser(
        description="LLM SEO Visibility Audit Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python audit.py "Joe's Pizza" "pizza restaurant" "Brooklyn, NY"
  python audit.py "Smith Law Firm" "personal injury lawyer" "Dallas, TX" --url https://smithlaw.com
  python audit.py "ABC Plumbing" "plumber" "Austin, TX" --demo
        """,
    )
    parser.add_argument("business_name", help="Name of the business to audit")
    parser.add_argument("industry", help="Industry or category (e.g., 'plumber', 'restaurant')")
    parser.add_argument("city", help="City and state (e.g., 'Austin, TX')")
    parser.add_argument("--url", dest="website_url", help="Business website URL", default=None)
    parser.add_argument("--demo", action="store_true", help="Force demo mode with simulated data")

    args = parser.parse_args()
    run_audit(args.business_name, args.industry, args.city, args.website_url, args.demo)


if __name__ == "__main__":
    main()
