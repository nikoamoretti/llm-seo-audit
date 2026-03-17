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
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich import box

from llm_querier import LLMQuerier
from web_presence import WebPresenceChecker
from analyzer import ResponseAnalyzer
from report_generator import ReportGenerator
from demo_mode import DemoAuditor

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
        results["mode"] = "demo"
    else:
        available = ", ".join(api_keys.keys())
        console.print(f"[green]API keys found:[/] {available}\n")
        results = run_live_audit(business_name, industry, city, website_url, api_keys)
        results["mode"] = "live"

    # --- Generate Reports ---
    report_gen = ReportGenerator(results, output_dir)

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  console=console, transient=True) as progress:
        progress.add_task("Generating reports...", total=None)
        json_path = report_gen.save_json()
        html_path = report_gen.save_html()

    console.print()
    print_terminal_report(results)

    console.print()
    console.print(Panel(
        f"[green]JSON:[/] {json_path}\n[green]HTML:[/] {html_path}",
        title="[bold]Reports Saved[/]",
        border_style="green",
    ))

    return results


def run_live_audit(business_name: str, industry: str, city: str,
                   website_url: Optional[str], api_keys: dict) -> dict:
    """Run a live audit using real API calls."""

    queries = [q.format(industry=industry, city=city) for q in QUERIES]
    querier = LLMQuerier(api_keys)
    analyzer = ResponseAnalyzer(business_name)

    # --- Query LLMs ---
    llm_results = {}
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  console=console) as progress:
        for provider in api_keys:
            task = progress.add_task(f"Querying {provider.title()}...", total=len(queries))
            provider_responses = []
            for query in queries:
                try:
                    response = querier.query(provider, query)
                    analysis = analyzer.analyze_response(response, query)
                    provider_responses.append({
                        "query": query,
                        "response": response,
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
    if website_url:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                      console=console, transient=True) as progress:
            progress.add_task("Checking web presence...", total=None)
            checker = WebPresenceChecker()
            web_results = checker.check_all(business_name, website_url, city)

    # --- Compute Scores ---
    scores = compute_scores(llm_results, web_results, list(api_keys.keys()))

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
        "scores": scores,
    }


def compute_scores(llm_results: dict, web_results: dict, providers: list) -> dict:
    """Compute the overall visibility score."""

    per_llm = {}
    total_mentioned = 0
    total_queries = 0
    all_competitors = {}
    all_attributes = []
    best_position_sum = 0
    position_count = 0

    for provider, responses in llm_results.items():
        mentioned = 0
        positions = []
        competitors = {}
        attributes = []

        for r in responses:
            a = r["analysis"]
            total_queries += 1
            if a.get("mentioned"):
                mentioned += 1
                total_mentioned += 1
            if a.get("position") is not None:
                positions.append(a["position"])
                best_position_sum += a["position"]
                position_count += 1
            for comp in a.get("competitors", []):
                competitors[comp] = competitors.get(comp, 0) + 1
                all_competitors[comp] = all_competitors.get(comp, 0) + 1
            attributes.extend(a.get("attributes", []))
            all_attributes.extend(a.get("attributes", []))

        mention_rate = mentioned / len(responses) if responses else 0
        avg_position = sum(positions) / len(positions) if positions else None

        # Score: 60% mention rate + 40% position quality
        position_score = 0
        if avg_position is not None:
            # Position 1 = 100, Position 2 = 75, Position 3 = 50, etc.
            position_score = max(0, 100 - (avg_position - 1) * 25)

        llm_score = int(mention_rate * 60 + (position_score / 100) * 40) if mention_rate > 0 else 0

        per_llm[provider] = {
            "score": llm_score,
            "mention_rate": round(mention_rate * 100, 1),
            "avg_position": round(avg_position, 1) if avg_position else None,
            "total_queries": len(responses),
            "times_mentioned": mentioned,
            "top_competitors": dict(sorted(competitors.items(), key=lambda x: -x[1])[:10]),
            "attributes_cited": list(set(attributes)),
        }

    # Overall LLM score
    overall_mention_rate = total_mentioned / total_queries if total_queries > 0 else 0
    avg_pos = best_position_sum / position_count if position_count > 0 else None
    pos_component = max(0, 100 - ((avg_pos - 1) * 25)) if avg_pos else 0

    llm_score = int(overall_mention_rate * 60 + (pos_component / 100) * 40) if overall_mention_rate > 0 else 0

    # Web presence score
    web_score = 0
    if web_results:
        checks = [
            web_results.get("has_schema_markup", False),
            web_results.get("has_og_tags", False),
            web_results.get("has_meta_description", False),
            web_results.get("has_title_tag", False),
            web_results.get("google_business_found", False),
            web_results.get("yelp_found", False),
            web_results.get("bbb_found", False),
            web_results.get("ssl_valid", False),
            web_results.get("mobile_friendly_meta", False),
            web_results.get("fast_load", False),
        ]
        web_score = int(sum(checks) / len(checks) * 100)

    # Combined: 70% LLM visibility + 30% web presence
    if web_results:
        overall = int(llm_score * 0.7 + web_score * 0.3)
    else:
        overall = llm_score

    return {
        "overall_score": overall,
        "llm_visibility_score": llm_score,
        "web_presence_score": web_score,
        "per_llm": per_llm,
        "overall_mention_rate": round(overall_mention_rate * 100, 1),
        "overall_avg_position": round(avg_pos, 1) if avg_pos else None,
        "top_competitors": dict(sorted(all_competitors.items(), key=lambda x: -x[1])[:15]),
        "attributes_cited": list(set(all_attributes)),
    }


def print_terminal_report(results: dict):
    """Print a formatted terminal report."""

    scores = results["scores"]

    # --- Overall Score ---
    score = scores["overall_score"]
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
        title="[bold]Overall LLM Visibility Score[/]",
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

    for provider, data in scores.get("per_llm", {}).items():
        s = data["score"]
        sc = "green" if s >= 70 else ("yellow" if s >= 40 else "red")
        table.add_row(
            provider.title(),
            f"[{sc}]{s}[/]",
            f"{data['mention_rate']}%",
            str(data['avg_position'] or 'N/A'),
            f"{data['times_mentioned']}/{data['total_queries']}",
        )
    console.print(table)

    # --- Web Presence ---
    if results.get("web_presence"):
        wp = results["web_presence"]
        web_table = Table(title="Web Presence Checks", box=box.ROUNDED, show_lines=True)
        web_table.add_column("Check", width=30)
        web_table.add_column("Status", justify="center", width=10)

        checks = [
            ("Schema/Structured Data", wp.get("has_schema_markup")),
            ("Open Graph Tags", wp.get("has_og_tags")),
            ("Meta Description", wp.get("has_meta_description")),
            ("Title Tag", wp.get("has_title_tag")),
            ("SSL Certificate", wp.get("ssl_valid")),
            ("Mobile-Friendly Meta", wp.get("mobile_friendly_meta")),
            ("Google Business Profile", wp.get("google_business_found")),
            ("Yelp Listing", wp.get("yelp_found")),
            ("BBB Listing", wp.get("bbb_found")),
            ("Fast Load Time", wp.get("fast_load")),
        ]
        for name, status in checks:
            icon = "[green]PASS[/]" if status else "[red]FAIL[/]"
            web_table.add_row(name, icon)

        ws = scores["web_presence_score"]
        web_table.add_row("[bold]Web Presence Score[/]", f"[bold]{ws}/100[/]")
        console.print(web_table)

    # --- Competitors ---
    if scores.get("top_competitors"):
        comp_table = Table(title="Top Competitors Mentioned by LLMs", box=box.ROUNDED)
        comp_table.add_column("Competitor", style="bold")
        comp_table.add_column("Times Mentioned", justify="center")

        for comp, count in list(scores["top_competitors"].items())[:10]:
            comp_table.add_row(comp, str(count))
        console.print(comp_table)

    # --- Attributes ---
    if scores.get("attributes_cited"):
        attrs = scores["attributes_cited"][:15]
        console.print(Panel(
            ", ".join(attrs),
            title="[bold]Attributes/Reasons LLMs Cite[/]",
            border_style="blue",
        ))

    # --- Recommendations ---
    recs = generate_recommendations(results)
    if recs:
        rec_table = Table(title="Recommendations to Improve LLM Visibility",
                          box=box.ROUNDED, show_lines=True)
        rec_table.add_column("Priority", justify="center", width=10)
        rec_table.add_column("Recommendation", width=70)

        for i, rec in enumerate(recs, 1):
            priority = "[red]HIGH[/]" if i <= 3 else "[yellow]MED[/]"
            rec_table.add_row(priority, rec)
        console.print(rec_table)

    # --- Demo mode notice ---
    if results.get("mode") == "demo":
        console.print()
        console.print(Panel(
            "[yellow]This audit was run in DEMO mode with simulated data.\n"
            "Set API keys to run a live audit with real LLM responses.[/]",
            border_style="yellow",
        ))


def generate_recommendations(results: dict) -> list:
    """Generate actionable recommendations based on audit results."""
    recs = []
    scores = results["scores"]
    wp = results.get("web_presence", {})

    if scores["overall_mention_rate"] < 50:
        recs.append(
            "Your business appears in fewer than half of LLM responses. "
            "Research shows there's a strong correlation between third-party mention density "
            "and AI citation rates. Focus on getting listed across directories and mentioned "
            "in comparison articles, roundups, and local press."
        )

    if scores.get("overall_avg_position") and scores["overall_avg_position"] > 3:
        recs.append(
            "When mentioned, you appear late in recommendations (position "
            f"{scores['overall_avg_position']:.0f}+). LLMs rank by perceived authority: "
            "review volume, awards, media coverage, and consistent brand signals across "
            "platforms. Strengthening these pushes you higher in AI-generated lists."
        )

    if wp.get("has_schema_markup") is False:
        recs.append(
            "Add Schema.org structured data (LocalBusiness, FAQ, Review schemas) to your "
            "website. Pages with schema markup are 78% more likely to be cited by AI systems. "
            "This helps LLMs understand your business entity, services, hours, and location."
        )

    if wp.get("has_og_tags") is False:
        recs.append(
            "Add Open Graph meta tags. AI crawlers and social previews use these to parse "
            "your business identity. Include og:title, og:description, og:type, and og:image."
        )

    if wp.get("google_business_found") is False:
        recs.append(
            "Claim and optimize your Google Business Profile. While ChatGPT uses Bing "
            "(not Google Maps), GBP data feeds into training datasets and Google AI Overviews."
        )

    if wp.get("yelp_found") is False:
        recs.append(
            "Create or claim your Yelp business listing. ChatGPT pulls directly from Yelp, "
            "TripAdvisor, and Angi when recommending local businesses. Being absent from "
            "these directories means you're invisible to the most-used AI assistant."
        )

    if wp.get("bbb_found") is False:
        recs.append(
            "Get listed on the Better Business Bureau. BBB is a trust signal that LLMs "
            "reference for credibility, especially for service businesses."
        )

    if wp.get("ssl_valid") is False:
        recs.append(
            "Install an SSL certificate (HTTPS). Insecure sites are deprioritized by both "
            "traditional search and AI systems."
        )

    # Bing-specific recommendation (ChatGPT uses Bing, not Google)
    recs.append(
        "Optimize for Bing — ChatGPT uses Bing for real-time search, NOT Google. "
        "Claim your Bing Places listing and submit your sitemap to Bing Webmaster Tools. "
        "Most businesses overlook this, giving you an easy competitive advantage."
    )

    competitors = scores.get("top_competitors", {})
    if competitors:
        top = list(competitors.keys())[:3]
        recs.append(
            f"Study these frequently-mentioned competitors: {', '.join(top)}. "
            "Analyze their directory presence, review volume, and content strategy — "
            "then replicate what makes them visible to AI."
        )

    recs.append(
        "Create self-contained answer blocks (134-167 words) on your site that directly "
        "answer common questions about your industry in your city. Research shows this "
        "format is 4.2x more likely to be extracted by AI Overviews. Add FAQ sections "
        "that mirror how people ask AI assistants for recommendations."
    )

    recs.append(
        "Build presence on Reddit, Quora, and community forums. These are among the most "
        "heavily cited sources in AI-generated answers. Genuine participation in relevant "
        "threads where your business gets recommended carries significant weight."
    )

    recs.append(
        "Content has a 3-month citation cliff — AI systems strongly favor recently updated "
        "pages. Refresh your key service pages, blog posts, and directory listings quarterly "
        "to maintain visibility."
    )

    recs.append(
        "Encourage customers to leave reviews on Google, Yelp, and industry platforms. "
        "LLMs evaluate review volume, recency, and sentiment when deciding which businesses "
        "to recommend. Respond to reviews — engagement signals authority."
    )

    return recs


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
