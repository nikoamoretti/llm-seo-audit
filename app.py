#!/usr/bin/env python3
"""
GEO Audit Tool — SOTA Blueprint Implementation
Two-layer scoring: Readiness (static) + Visibility (dynamic) → Composite GEO Score
GEO_Score = 0.55 * V + 0.45 * R
"""

import asyncio
import json
import os
import re
import time
import requests
from datetime import datetime
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from llm_querier import LLMQuerier
from analyzer import ResponseAnalyzer
from web_presence import WebPresenceChecker
from demo_mode import DemoAuditor

app = FastAPI(title="GEO Audit Tool")
executor = ThreadPoolExecutor(max_workers=4)

# ─── Prompt Bank with Intent Clusters ────────────────────────────────
# Head queries: broad "best X in Y" discovery
# Mid-tail: specific need or use case
# Comparison: "X vs competitors"
# Policy/Trust: trust, reliability, safety queries

PROMPT_BANK = {
    "head": [
        "What are the best {industry} businesses in {city}?",
        "Can you recommend a good {industry} in {city}?",
        "Top rated {industry} near {city}",
    ],
    "mid_tail": [
        "I'm looking for a {industry} in {city} with great reviews and reasonable prices. What do you suggest?",
        "What {industry} in {city} would you recommend for a first-time visitor?",
        "I need a reliable {industry} in {city} — who should I go with?",
    ],
    "comparison": [
        "Who are the top 5 {industry} businesses in {city} and how do they compare?",
        "Which {industry} companies in {city} have the best reputation?",
        "Compare the best {industry} options in {city}",
    ],
    "trust": [
        "Who is the most trusted {industry} in {city}?",
        "Which {industry} in {city} has the best customer service?",
        "What {industry} in {city} do locals recommend the most?",
    ],
}


class AuditRequest(BaseModel):
    business_name: str
    industry: str
    city: str
    website_url: Optional[str] = None
    phone: Optional[str] = None
    demo: bool = False


def detect_api_keys() -> dict:
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


def build_prompt_list(industry: str, city: str) -> list:
    """Build full prompt list from all intent clusters."""
    prompts = []
    for cluster, templates in PROMPT_BANK.items():
        for tmpl in templates:
            prompts.append({
                "text": tmpl.format(industry=industry, city=city),
                "cluster": cluster,
            })
    return prompts


def _query_single(querier, provider, prompt_info, analyzer):
    """Query a single provider+prompt combo. Used for parallel execution."""
    try:
        response = querier.query(provider, prompt_info["text"])
        analysis = analyzer.analyze_response(response, prompt_info["text"])
        return {
            "query": prompt_info["text"],
            "cluster": prompt_info["cluster"],
            "response": response,
            "analysis": analysis,
        }
    except Exception as e:
        return {
            "query": prompt_info["text"],
            "cluster": prompt_info["cluster"],
            "response": f"ERROR: {e}",
            "analysis": analyzer.empty_analysis(),
        }


def run_live_audit(business_name, industry, city, website_url, phone, api_keys):
    prompts = build_prompt_list(industry, city)
    querier = LLMQuerier(api_keys)

    known_facts = {"city": city, "industry": industry}
    if website_url:
        known_facts["website"] = website_url
    if phone:
        known_facts["phone"] = phone

    analyzer = ResponseAnalyzer(business_name, known_facts=known_facts)

    # Run ALL queries in parallel — providers × prompts + web checks
    from concurrent.futures import ThreadPoolExecutor, as_completed

    futures = {}
    with ThreadPoolExecutor(max_workers=12) as pool:
        # Submit all LLM queries at once
        for provider in api_keys:
            for prompt_info in prompts:
                key = (provider, prompt_info["text"], prompt_info["cluster"])
                futures[pool.submit(_query_single, querier, provider, prompt_info, analyzer)] = key

        # Submit web checks in parallel too
        web_future = None
        if website_url:
            checker = WebPresenceChecker()
            web_future = pool.submit(checker.check_all, business_name, website_url, city)

        # Collect LLM results
        llm_results = {provider: [] for provider in api_keys}
        for future in as_completed(futures):
            provider, query_text, cluster = futures[future]
            result = future.result()
            llm_results[provider].append(result)

        # Collect web results
        web_results = web_future.result() if web_future else {}

    # Sort each provider's results to maintain prompt order
    prompt_order = {p["text"]: i for i, p in enumerate(prompts)}
    for provider in llm_results:
        llm_results[provider].sort(key=lambda r: prompt_order.get(r["query"], 0))

    return llm_results, web_results


# ─── Readiness Layer (Static) ─────────────────────────────────────────
# R = 0.25*R_LocalEntity + 0.20*R_Index + 0.15*R_Schema + 0.20*R_Trust + 0.20*R_Content

def compute_readiness_score(web_results: dict) -> dict:
    """Compute the Readiness layer score from static web checks."""
    if not web_results:
        return {
            "R": 0,
            "R_local_entity": {"score": 0, "checks": {}},
            "R_index": {"score": 0, "checks": {}},
            "R_schema": {"score": 0, "checks": {}},
            "R_trust": {"score": 0, "checks": {}},
            "R_content": {"score": 0, "checks": {}},
        }

    # R_LocalEntity (GBP, NAP, review indicators)
    local_checks = {
        "Found on Google Business": web_results.get("google_business_found", False),
        "Phone number on website": web_results.get("has_contact_info", False),
        "Business hours on website": web_results.get("has_hours", False),
        "Street address on website": web_results.get("has_address", False),
        "Found on Yelp": web_results.get("yelp_found", False),
    }
    r_local = int(sum(local_checks.values()) / len(local_checks) * 100)

    # R_Index (Crawlability: robots.txt, sitemap, canonical, no noindex)
    index_checks = {
        "Website loads correctly": web_results.get("website_accessible", False),
        "Has a robots.txt file": web_results.get("robots_txt_exists", False),
        "AI crawlers are allowed in": web_results.get("robots_allows_crawl", True),
        "Has a sitemap for AI to follow": web_results.get("sitemap_exists", False),
        "Pages point to their correct URL": web_results.get("has_canonical", False),
        "Not blocking AI from reading pages": not web_results.get("has_noindex", False),
    }
    r_index = int(sum(index_checks.values()) / len(index_checks) * 100)

    # R_Schema (JSON-LD, LocalBusiness, FAQ)
    schema_checks = {
        "Structured data on site": web_results.get("has_schema_markup", False),
        "Business type labeled for AI": web_results.get("has_local_business_schema", False),
        "FAQ markup for AI to read": web_results.get("has_faq_schema", False),
        "Social sharing info set up": web_results.get("has_og_tags", False),
    }
    r_schema = int(sum(schema_checks.values()) / len(schema_checks) * 100)

    # R_Trust (SSL, directories, page speed)
    trust_checks = {
        "Site is secure (HTTPS)": web_results.get("ssl_valid", False),
        "Page loads fast (under 3 sec)": web_results.get("fast_load", False),
        "Found on Better Business Bureau": web_results.get("bbb_found", False),
        "Works well on mobile phones": web_results.get("mobile_friendly_meta", False),
    }
    r_trust = int(sum(trust_checks.values()) / len(trust_checks) * 100)

    # R_Content (answer blocks, FAQ, meta desc, word count)
    content_checks = {
        "Has a page description for search": web_results.get("has_meta_description", False),
        "Has a page title": web_results.get("has_title_tag", False),
        "Has Q&A-style content AI can quote": web_results.get("has_answer_blocks", False),
        "Has an FAQ section": web_results.get("has_faq_section", False),
        "Enough text for AI to learn from": (web_results.get("word_count", 0) or 0) > 300,
    }
    r_content = int(sum(content_checks.values()) / len(content_checks) * 100)

    # Composite Readiness
    R = int(
        0.25 * r_local
        + 0.20 * r_index
        + 0.15 * r_schema
        + 0.20 * r_trust
        + 0.20 * r_content
    )

    return {
        "R": R,
        "R_local_entity": {"score": r_local, "label": "Online Listings", "checks": local_checks,
                           "description": "Can AI find your business on Google, Yelp, and other directories?"},
        "R_index": {"score": r_index, "label": "AI Can Find You", "checks": index_checks,
                    "description": "Is your website set up so AI systems can actually read and access it?"},
        "R_schema": {"score": r_schema, "label": "Machine-Readable Info", "checks": schema_checks,
                     "description": "Does your site have structured data that helps AI understand what your business does?"},
        "R_trust": {"score": r_trust, "label": "Trust & Speed", "checks": trust_checks,
                    "description": "Is your site secure, fast, and listed on trusted directories?"},
        "R_content": {"score": r_content, "label": "AI-Ready Content", "checks": content_checks,
                      "description": "Does your site have clear answers to the questions people ask AI?"},
    }


# ─── Visibility Layer (Dynamic) ──────────────────────────────────────
# V = mean of per-prompt visibility scores across all providers and prompts

def compute_visibility_score(llm_results: dict) -> dict:
    """Compute the Visibility layer score from LLM query results."""
    all_scores = []
    per_llm = {}
    all_competitors = {}
    all_attributes = []
    per_cluster = {}

    for provider, responses in llm_results.items():
        provider_scores = []
        mentioned_count = 0
        cited_count = 0
        positions = []
        competitors = {}
        attributes = []

        for r in responses:
            a = r["analysis"]
            v_score = a.get("visibility_score", 0)
            provider_scores.append(v_score)
            all_scores.append(v_score)

            cluster = r.get("cluster", "head")
            if cluster not in per_cluster:
                per_cluster[cluster] = []
            per_cluster[cluster].append(v_score)

            if a.get("mentioned"):
                mentioned_count += 1
            if a.get("cited"):
                cited_count += 1
            if a.get("position") is not None:
                positions.append(a["position"])

            for comp in a.get("competitors", []):
                competitors[comp] = competitors.get(comp, 0) + 1
                all_competitors[comp] = all_competitors.get(comp, 0) + 1
            attributes.extend(a.get("attributes", []))
            all_attributes.extend(a.get("attributes", []))

        total_queries = len(responses)
        avg_visibility = sum(provider_scores) / len(provider_scores) if provider_scores else 0
        mention_rate = mentioned_count / total_queries if total_queries > 0 else 0
        citation_rate = cited_count / total_queries if total_queries > 0 else 0
        avg_position = sum(positions) / len(positions) if positions else None

        per_llm[provider] = {
            "visibility_score": round(avg_visibility, 1),
            "mention_rate": round(mention_rate * 100, 1),
            "citation_rate": round(citation_rate * 100, 1),
            "avg_position": round(avg_position, 1) if avg_position else None,
            "total_queries": total_queries,
            "times_mentioned": mentioned_count,
            "times_cited": cited_count,
            "top_competitors": dict(sorted(competitors.items(), key=lambda x: -x[1])[:10]),
            "attributes_cited": list(set(attributes)),
        }

    V = sum(all_scores) / len(all_scores) if all_scores else 0

    # Per-cluster breakdown
    cluster_scores = {}
    for cluster, scores in per_cluster.items():
        cluster_scores[cluster] = {
            "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
            "query_count": len(scores),
        }

    return {
        "V": round(V, 1),
        "per_llm": per_llm,
        "per_cluster": cluster_scores,
        "overall_mention_rate": round(
            sum(1 for s in all_scores if s >= 40) / len(all_scores) * 100, 1
        ) if all_scores else 0,
        "top_competitors": dict(sorted(all_competitors.items(), key=lambda x: -x[1])[:15]),
        "attributes_cited": list(set(all_attributes)),
    }


# ─── Composite GEO Score ─────────────────────────────────────────────

def compute_geo_score(readiness: dict, visibility: dict, has_web: bool) -> dict:
    """Compute composite: GEO_Score = 0.55 * V + 0.45 * R"""
    R = readiness["R"]
    V = visibility["V"]

    if has_web:
        geo_score = int(0.55 * V + 0.45 * R)
    else:
        # No website: score based purely on visibility
        geo_score = int(V)

    return {
        "geo_score": geo_score,
        "readiness_score": R,
        "visibility_score": round(V, 1),
        "formula": "0.55 × Visibility + 0.45 × Readiness",
        "readiness": readiness,
        "visibility": visibility,
    }


# ─── Recommendations Engine ──────────────────────────────────────────

def generate_recommendations(scores: dict, web_results: dict) -> list:
    """Generate prioritized recommendations based on the P0/P1/P2 framework."""
    recs = []
    R = scores["readiness"]
    V = scores["visibility"]
    geo = scores["geo_score"]

    # === P0: Fix These First — You're Invisible Without Them ===

    if web_results.get("has_noindex"):
        recs.append({
            "priority": "P0", "category": "Website Access",
            "title": "Your website is telling AI to ignore it",
            "detail": "There's a hidden tag on your site that literally tells Google, ChatGPT, and other AI systems: 'don't read this page.' That means no AI can ever recommend you. A web developer can fix this in 5 minutes by removing the 'noindex' tag.",
        })

    if web_results.get("robots_allows_crawl") is False:
        recs.append({
            "priority": "P0", "category": "Website Access",
            "title": "Your website is blocking AI from reading it",
            "detail": "There's a file on your site (robots.txt) that blocks all search engines and AI systems from reading your pages. It's like having a store with the blinds closed — nobody can see what's inside. Ask your web developer to update it.",
        })

    if web_results.get("website_accessible") is False and web_results:
        recs.append({
            "priority": "P0", "category": "Website Access",
            "title": "Your website is down or password-protected",
            "detail": "We couldn't load your website — it's either offline, behind a password, or returning errors. AI can only recommend businesses whose websites it can actually read. Make sure your site is publicly accessible.",
        })

    if web_results.get("google_business_found") is False:
        recs.append({
            "priority": "P0", "category": "Online Listings",
            "title": "You're not on Google Business Profile",
            "detail": "This is the #1 most important thing you can do. Google's AI reads your Google Business listing to recommend local businesses. Without one, you're invisible. Go to business.google.com, claim your listing, and fill in everything: photos, hours, services, and your phone number.",
        })

    if V.get("V", 0) < 15:
        recs.append({
            "priority": "P0", "category": "AI Visibility",
            "title": "AI assistants almost never mention your business",
            "detail": "When people ask ChatGPT, Claude, or other AI tools for a recommendation in your area, your business almost never comes up. This is the core problem this audit measures. The fixes below will help change that.",
        })

    # === P1: High Impact — These Will Move the Needle ===

    if web_results.get("has_schema_markup") is False:
        recs.append({
            "priority": "P1", "category": "Machine-Readable Info",
            "title": "Add structured data so AI understands your business",
            "detail": "Right now, AI has to guess what your business does by reading your website like a human. Structured data is a special code block that tells AI exactly what you are, where you're located, your hours, and your services. Sites with this are 78% more likely to be recommended by AI. Ask your web developer to add 'LocalBusiness JSON-LD' markup.",
        })

    if web_results.get("has_local_business_schema") is False and web_results.get("has_schema_markup"):
        recs.append({
            "priority": "P1", "category": "Machine-Readable Info",
            "title": "Your structured data doesn't identify your business type",
            "detail": "Your site has some structured data, but it doesn't tell AI what kind of business you are (like 'Restaurant' or 'Dentist'). Adding this specific label helps AI recommend you for the right searches.",
        })

    if web_results.get("has_answer_blocks") is False and web_results:
        recs.append({
            "priority": "P1", "category": "AI-Ready Content",
            "title": "Add a Q&A section that AI can quote directly",
            "detail": "When someone asks AI 'What's the best [your industry] in [your city]?', AI looks for ready-made answers on websites. Add a FAQ section with 3-5 questions and clear, detailed answers (about 150 words each). Sites with these are 4x more likely to be quoted by AI.",
        })

    if web_results.get("yelp_found") is False:
        recs.append({
            "priority": "P1", "category": "Online Listings",
            "title": "You're not on Yelp",
            "detail": "ChatGPT gets its local business data from Yelp (through Bing). If you're not on Yelp, ChatGPT literally can't find you. Claim your free Yelp business page and ask happy customers to leave reviews there.",
        })

    if web_results.get("sitemap_exists") is False and web_results:
        recs.append({
            "priority": "P1", "category": "Website Access",
            "title": "No sitemap — AI doesn't know all your pages exist",
            "detail": "A sitemap is like a table of contents for your website that helps AI find all your pages. Without one, AI might miss important pages about your services. Your web developer can generate one automatically.",
        })

    if web_results.get("has_canonical") is False and web_results:
        recs.append({
            "priority": "P1", "category": "Website Access",
            "title": "Pages don't have a canonical URL set",
            "detail": "This is a small technical fix that tells AI which version of each page is the 'official' one. Without it, AI might get confused by duplicate pages and spread your ranking power thin. A quick fix for your web developer.",
        })

    if web_results.get("ssl_valid") is False and web_results:
        recs.append({
            "priority": "P1", "category": "Trust & Speed",
            "title": "Your site isn't secure (no HTTPS)",
            "detail": "Your website doesn't have an SSL certificate, which means browsers show a 'Not Secure' warning. AI systems trust secure sites more and are less likely to recommend insecure ones. Most web hosts offer free SSL — just turn it on.",
        })

    if web_results.get("has_meta_description") is False and web_results:
        recs.append({
            "priority": "P1", "category": "AI-Ready Content",
            "title": "Your site has no description for search engines",
            "detail": "When AI and Google look at your site, there's no summary telling them what you do. They have to guess — and they often get it wrong. Add a clear 1-2 sentence description of your business, location, and what makes you special.",
        })

    # === P2: Growth — Take It to the Next Level ===

    recs.append({
        "priority": "P1", "category": "AI Visibility",
        "title": "Get listed on Bing (it powers ChatGPT)",
        "detail": "Most people don't know this: ChatGPT uses Bing, not Google, when searching for local businesses. Almost nobody optimizes for Bing, so it's a huge opportunity. Go to bingplaces.com and claim your free listing.",
    })

    if web_results.get("has_faq_schema") is False and web_results:
        recs.append({
            "priority": "P2", "category": "AI-Ready Content",
            "title": "Add FAQ markup so AI can directly read your Q&As",
            "detail": "If you have a FAQ section, add special markup (FAQ schema) so AI systems can read each question and answer individually. This makes it much easier for AI to pull your answers into its responses when someone asks a relevant question.",
        })

    recs.append({
        "priority": "P2", "category": "Trust & Speed",
        "title": "Get mentioned on Reddit and local forums",
        "detail": "AI tools like Perplexity and ChatGPT love Reddit. When real people recommend your business in Reddit threads, AI picks that up and is more likely to recommend you too. Encourage happy customers to mention you in local subreddits.",
    })

    recs.append({
        "priority": "P2", "category": "AI-Ready Content",
        "title": "Update your website content every 3 months",
        "detail": "AI strongly prefers fresh content. If your website hasn't been updated in months, AI treats it as stale and is less likely to cite it. Even small updates — a new blog post, updated hours, seasonal specials — signal that you're active and relevant.",
    })

    if web_results.get("bbb_found") is False:
        recs.append({
            "priority": "P2", "category": "Trust & Speed",
            "title": "Get a Better Business Bureau listing",
            "detail": "A BBB listing adds credibility. AI systems see it as a trust signal, especially for service businesses like contractors, lawyers, and financial services. It's not as critical as Google or Yelp, but it helps.",
        })

    # Competitor gap analysis
    competitors = V.get("top_competitors", {})
    if competitors:
        top = list(competitors.keys())[:3]
        recs.append({
            "priority": "P2", "category": "AI Visibility",
            "title": f"Study what these competitors are doing right: {', '.join(top)}",
            "detail": "These businesses come up the most when AI recommends businesses in your space. Look at what they're doing: Are they on Yelp? Do they have lots of reviews? Is their website well set up? Copy what works and do it better.",
        })

    # Per-cluster analysis
    per_cluster = V.get("per_cluster", {})
    weakest_cluster = None
    weakest_score = 100
    for cluster, data in per_cluster.items():
        if data["avg_score"] < weakest_score:
            weakest_score = data["avg_score"]
            weakest_cluster = cluster

    cluster_labels = {
        "head": "general 'best of' questions",
        "mid_tail": "specific need questions",
        "comparison": "comparison questions",
        "trust": "'who's most trusted' questions",
    }
    if weakest_cluster and weakest_score < 30:
        recs.append({
            "priority": "P1", "category": "AI Visibility",
            "title": f"You're weakest when people ask {cluster_labels.get(weakest_cluster, weakest_cluster)}",
            "detail": f"When people ask AI {cluster_labels.get(weakest_cluster, weakest_cluster)} about your industry, you almost never come up. This is a specific type of question real customers ask. Focus on building the right content and reputation to show up for these searches.",
        })

    # Sort by priority
    priority_order = {"P0": 0, "P1": 1, "P2": 2}
    recs.sort(key=lambda r: priority_order.get(r["priority"], 3))

    return recs


# ─── API Endpoints ────────────────────────────────────────────────────

@app.post("/api/audit")
async def run_audit(req: AuditRequest):
    api_keys = detect_api_keys()

    if req.demo or not api_keys:
        demo = DemoAuditor(req.business_name, req.industry, req.city, req.website_url)
        results = demo.run()
        readiness = compute_readiness_score(results["web_presence"])
        visibility = compute_visibility_score(results["llm_results"])
        scores = compute_geo_score(readiness, visibility, bool(req.website_url))
        recs = generate_recommendations(scores, results["web_presence"])

        return {
            "mode": "demo",
            "business_name": req.business_name,
            "industry": req.industry,
            "city": req.city,
            "website_url": req.website_url,
            "timestamp": datetime.now().isoformat(),
            "scores": scores,
            "recommendations": recs,
            "llm_responses": {
                p: [{
                    "query": r["query"],
                    "cluster": r.get("cluster", "head"),
                    "mentioned": r["analysis"]["mentioned"],
                    "cited": r["analysis"].get("cited", False),
                    "position": r["analysis"]["position"],
                    "visibility_score": r["analysis"].get("visibility_score", 0),
                } for r in resps]
                for p, resps in results["llm_results"].items()
            },
        }

    # Live audit
    loop = asyncio.get_event_loop()
    llm_results, web_results = await loop.run_in_executor(
        executor, run_live_audit,
        req.business_name, req.industry, req.city,
        req.website_url, req.phone, api_keys
    )

    readiness = compute_readiness_score(web_results)
    visibility = compute_visibility_score(llm_results)
    scores = compute_geo_score(readiness, visibility, bool(web_results))
    recs = generate_recommendations(scores, web_results)

    return {
        "mode": "live",
        "business_name": req.business_name,
        "industry": req.industry,
        "city": req.city,
        "website_url": req.website_url,
        "timestamp": datetime.now().isoformat(),
        "api_keys_used": list(api_keys.keys()),
        "scores": scores,
        "recommendations": recs,
        "web_presence": web_results,
        "llm_responses": {
            p: [{
                "query": r["query"],
                "cluster": r.get("cluster", "head"),
                "response": r["response"][:500],
                "mentioned": r["analysis"]["mentioned"],
                "cited": r["analysis"].get("cited", False),
                "position": r["analysis"]["position"],
                "visibility_score": r["analysis"].get("visibility_score", 0),
                "sentiment": r["analysis"].get("sentiment", 0),
            } for r in resps]
            for p, resps in llm_results.items()
        },
    }


class LookupRequest(BaseModel):
    query: str


PLACES_TYPE_MAP = {
    "restaurant": "restaurant", "cafe": "coffee shop", "coffee_shop": "coffee shop",
    "bakery": "bakery", "bar": "bar", "meal_delivery": "restaurant",
    "meal_takeaway": "restaurant", "night_club": "nightclub",
    "dentist": "dentist", "doctor": "doctor", "hospital": "hospital",
    "pharmacy": "pharmacy", "veterinary_care": "veterinarian",
    "physiotherapist": "physical therapist", "hair_care": "hair salon",
    "beauty_salon": "beauty salon", "spa": "spa",
    "gym": "gym", "yoga_studio": "yoga studio",
    "lawyer": "lawyer", "accounting": "accountant", "insurance_agency": "insurance",
    "real_estate_agency": "real estate", "bank": "bank",
    "car_repair": "auto repair", "car_wash": "car wash", "car_dealer": "car dealer",
    "gas_station": "gas station", "parking": "parking",
    "plumber": "plumber", "electrician": "electrician", "roofing_contractor": "roofing",
    "painter": "painter", "moving_company": "moving company",
    "locksmith": "locksmith", "laundry": "laundry",
    "lodging": "hotel", "travel_agency": "travel agency",
    "store": "retail store", "clothing_store": "clothing store",
    "grocery_or_supermarket": "grocery store", "supermarket": "grocery store",
    "convenience_store": "convenience store", "hardware_store": "hardware store",
    "pet_store": "pet store", "florist": "florist", "jewelry_store": "jewelry store",
    "book_store": "bookstore", "electronics_store": "electronics store",
    "furniture_store": "furniture store", "shoe_store": "shoe store",
    "shopping_mall": "shopping mall",
    "school": "school", "university": "university",
    "church": "church", "mosque": "mosque", "synagogue": "synagogue",
    "library": "library", "museum": "museum", "art_gallery": "art gallery",
    "amusement_park": "amusement park", "aquarium": "aquarium", "zoo": "zoo",
    "bowling_alley": "bowling alley", "movie_theater": "movie theater",
}


def _places_type_to_industry(types: list) -> str:
    """Convert Google Places types to a simple industry label."""
    for t in types:
        t_clean = t.replace("_", " ") if t not in PLACES_TYPE_MAP else ""
        if t in PLACES_TYPE_MAP:
            return PLACES_TYPE_MAP[t]
    # Fallback: humanize the first non-generic type
    skip = {"point_of_interest", "establishment", "food", "health", "finance",
            "general_contractor", "local_government_office", "political"}
    for t in types:
        if t not in skip:
            return t.replace("_", " ")
    return ""


def _format_city(components: list) -> str:
    """Extract neighborhood, city, state from address components."""
    neighborhood = ""
    city = ""
    state = ""
    for comp in components:
        types = comp.get("types", [])
        if "neighborhood" in types or "sublocality_level_1" in types or "sublocality" in types:
            neighborhood = comp.get("longText", "")
        elif "locality" in types:
            city = comp.get("longText", "")
        elif "administrative_area_level_1" in types:
            state = comp.get("shortText", "")
    parts = [p for p in [neighborhood, city, state] if p]
    return ", ".join(parts)


def _parse_place(place: dict, query: str) -> dict:
    """Parse a single Google Places result into our format."""
    name = place.get("displayName", {}).get("text", query)
    types = place.get("types", [])
    primary = place.get("primaryType", "")
    if primary:
        types = [primary] + [t for t in types if t != primary]
    industry = _places_type_to_industry(types)
    city = _format_city(place.get("addressComponents", []))
    if not city:
        addr = place.get("formattedAddress", "")
        parts = [p.strip() for p in addr.split(",")]
        city = ", ".join(parts[1:]) if len(parts) > 1 else addr
    return {
        "business_name": name,
        "industry": industry,
        "city": city,
        "website_url": place.get("websiteUri", ""),
        "phone": place.get("nationalPhoneNumber", ""),
        "address": place.get("formattedAddress", ""),
        "found": True,
    }


@app.post("/api/lookup")
async def lookup_business(req: LookupRequest):
    """Look up a business using Google Places API, returns multiple results."""
    api_keys = detect_api_keys()

    # ── Try Google Places API first — return up to 5 results ──
    places_key = os.environ.get("GOOGLE_PLACES_API_KEY") or api_keys.get("gemini")
    if places_key:
        try:
            resp = requests.post(
                "https://places.googleapis.com/v1/places:searchText",
                headers={
                    "Content-Type": "application/json",
                    "X-Goog-Api-Key": places_key,
                    "X-Goog-FieldMask": (
                        "places.displayName,places.formattedAddress,"
                        "places.types,places.websiteUri,places.nationalPhoneNumber,"
                        "places.primaryType,places.addressComponents"
                    ),
                },
                json={"textQuery": req.query, "maxResultCount": 5, "strictTypeFiltering": False},
                timeout=8,
            )
            if resp.status_code == 200:
                data = resp.json()
                places = data.get("places", [])
                if places:
                    results = [_parse_place(p, req.query) for p in places]
                    return {"results": results, "found": True}
        except Exception:
            pass

    # ── Fallback: LLM lookup (single result) ──
    prompt = (
        f"What is \"{req.query}\"? Give me the business details.\n\n"
        "Reply with ONLY a JSON object, no markdown:\n"
        '{"business_name": "full name", "industry": "type like coffee shop", '
        '"city": "Neighborhood, City, State", "website_url": "https://...", "phone": "xxx-xxx-xxxx"}\n\n'
        "Do NOT return empty strings — always give your best guess."
    )
    for provider in ["gemini", "openai", "anthropic"]:
        if provider not in api_keys:
            continue
        try:
            text = ""
            if provider == "gemini":
                from google import genai
                client = genai.Client(api_key=api_keys["gemini"])
                resp = client.models.generate_content(
                    model="gemini-3.1-flash-lite-preview", contents=prompt)
                text = resp.text.strip()
            elif provider == "openai":
                import openai
                client = openai.OpenAI(api_key=api_keys["openai"])
                resp = client.chat.completions.create(
                    model="gpt-5.4", max_completion_tokens=256,
                    messages=[{"role": "user", "content": prompt}])
                text = resp.choices[0].message.content.strip()
            elif provider == "anthropic":
                import anthropic
                client = anthropic.Anthropic(api_key=api_keys["anthropic"])
                message = client.messages.create(
                    model="claude-sonnet-4-6", max_tokens=256,
                    messages=[{"role": "user", "content": prompt}])
                text = message.content[0].text.strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            data = json.loads(text)
            data["found"] = bool(data.get("city") or data.get("industry"))
            if data["found"]:
                return {"results": [data], "found": True}
        except Exception:
            continue

    return {"results": [], "found": False}


@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    return Path(__file__).parent.joinpath("ui.html").read_text()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
