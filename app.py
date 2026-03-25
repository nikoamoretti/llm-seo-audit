#!/usr/bin/env python3
"""
GEO Audit Tool — SOTA Blueprint Implementation
Two-layer scoring: Readiness (static) + Visibility (dynamic) → Composite GEO Score
GEO_Score = 0.55 * V + 0.45 * R
"""

import asyncio
import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import requests

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from analyzer import ResponseAnalyzer
from demo_mode import DemoAuditor
from llm_querier import LLMQuerier
from src.core.audit_builder import build_audit_run, prompt_results_from_llm_results
from src.core.models import CheckDimension, ReadinessResult, VisibilityResult
from src.presentation import AuditUIResponse, build_audit_ui_response
from src.prompts.loader import load_prompt_profile, select_prompt_profile
from src.prompts.renderer import render_prompt_bank
from src.scoring.final import score_final
from src.scoring.readiness import score_readiness
from src.scoring.visibility import score_visibility
from web_presence import WebPresenceChecker

app = FastAPI(title="GEO Audit Tool")
executor = ThreadPoolExecutor(max_workers=4)


class AuditRequest(BaseModel):
    business_name: str
    industry: str = ""
    city: str = ""
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


def build_prompt_list(
    business_name: str,
    industry: str,
    city: str,
    service_area: Optional[str] = None,
    competitors: Optional[list[str]] = None,
) -> list[dict[str, str]]:
    """Build prompts from a vertical-specific prompt profile."""
    profile_slug = select_prompt_profile(industry)
    profile = load_prompt_profile(profile_slug)
    return render_prompt_bank(
        profile,
        business_name=business_name,
        industry=industry,
        city=city,
        service_area=service_area or city,
        competitors=competitors,
    )


def _query_single(querier, provider, prompt_info, analyzer):
    """Query a single provider+prompt combo. Used for parallel execution."""
    try:
        engine_response = querier.query_structured(provider, prompt_info["text"])
        response = engine_response.raw_text
        analysis = analyzer.analyze_response(response, prompt_info["text"])
        return {
            "query": prompt_info["text"],
            "cluster": prompt_info["cluster"],
            "response": response,
            "engine_response": asdict(engine_response),
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
    prompts = build_prompt_list(
        business_name=business_name,
        industry=industry,
        city=city,
        service_area=city,
    )
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
        checker = WebPresenceChecker()
        web_future = pool.submit(checker.check_all, business_name, website_url or "", city)

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


def compute_readiness_score(web_results: dict) -> dict:
    """Legacy wrapper over score_v2 readiness results."""
    readiness = score_readiness(web_results)
    payload = {"R": readiness.score}
    payload.update(
        {
            key: dimension.model_dump(mode="json")
            for key, dimension in readiness.dimensions.items()
        }
    )
    return payload

def compute_visibility_score(llm_results: dict) -> dict:
    """Legacy wrapper over score_v2 visibility results."""
    visibility = score_visibility(prompt_results_from_llm_results(llm_results))
    return {
        "V": round(visibility.score, 1),
        "overall_mention_rate": visibility.overall_mention_rate,
        "dimensions": {
            key: dimension.model_dump(mode="json")
            for key, dimension in visibility.dimensions.items()
        },
        "per_llm": {
            provider: data.model_dump(mode="json")
            for provider, data in visibility.per_llm.items()
        },
        "per_cluster": {
            cluster: data.model_dump(mode="json")
            for cluster, data in visibility.per_cluster.items()
        },
        "top_competitors": visibility.top_competitors,
        "attributes_cited": visibility.attributes_cited,
    }

def compute_geo_score(readiness: dict, visibility: dict, has_web: bool) -> dict:
    """Legacy wrapper over score_v2 final score."""
    readiness_model = ReadinessResult(
        score=int(readiness.get("R", 0)),
        dimensions={
            key: CheckDimension.model_validate(value)
            for key, value in readiness.items()
            if key != "R" and isinstance(value, dict)
        },
    )
    visibility_model = VisibilityResult(
        score=float(visibility.get("V", 0)),
        overall_mention_rate=float(visibility.get("overall_mention_rate", 0)),
        dimensions={
            key: CheckDimension.model_validate(value)
            for key, value in visibility.get("dimensions", {}).items()
            if isinstance(value, dict)
        },
        per_llm={},
        per_cluster={},
        top_competitors=visibility.get("top_competitors", {}),
        attributes_cited=visibility.get("attributes_cited", []),
        prompt_results=[],
    )
    score = score_final(
        readiness=readiness_model,
        visibility=visibility_model,
        web_presence={"website_accessible": bool(has_web)},
    )
    return {
        "geo_score": score.final,
        "readiness_score": score.readiness,
        "visibility_score": round(score.visibility, 1),
        "formula": score.formula,
        "readiness": readiness,
        "visibility": visibility,
    }


def _discover_website(business_name: str, api_keys: dict) -> Optional[str]:
    """Find the business website. Uses OpenAI JSON mode for reliable structured output."""
    import re
    if "openai" in api_keys:
        try:
            import openai as _openai
            client = _openai.OpenAI(api_key=api_keys["openai"])
            resp = client.chat.completions.create(
                model="gpt-4.1",
                max_completion_tokens=100,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "Return JSON only."},
                    {"role": "user", "content": f'Return the official website URL for "{business_name}" as JSON: {{"url": "https://..."}}. If unknown return {{"url": null}}'}
                ])
            import json
            data = json.loads(resp.choices[0].message.content)
            url = data.get("url")
            if url and url.startswith("http"):
                return url.rstrip("/")
        except Exception:
            pass
    if "anthropic" in api_keys:
        try:
            import anthropic as _anthropic
            client = _anthropic.Anthropic(api_key=api_keys["anthropic"])
            resp = client.messages.create(
                model="claude-sonnet-4-6", max_tokens=100,
                messages=[{"role": "user", "content": f'Return ONLY a JSON object with the official website URL for "{business_name}": {{"url": "https://..."}}. If unknown: {{"url": null}}'}])
            import json
            text = resp.content[0].text.strip()
            # Extract JSON from response
            match = re.search(r'\{[^}]+\}', text)
            if match:
                data = json.loads(match.group())
                url = data.get("url")
                if url and url.startswith("http"):
                    return url.rstrip("/")
        except Exception:
            pass
    return None


# ─── API Endpoints ────────────────────────────────────────────────────

@app.post("/api/audit", response_model=AuditUIResponse)
async def run_audit(req: AuditRequest):
    api_keys = detect_api_keys()

    if req.demo or not api_keys:
        demo = DemoAuditor(req.business_name, req.industry, req.city, req.website_url)
        results = demo.run()
        audit_run = build_audit_run(
            mode="demo",
            business_name=req.business_name,
            industry=req.industry,
            city=req.city,
            website_url=req.website_url,
            phone=req.phone,
            web_presence=results["web_presence"],
            llm_results=results["llm_results"],
            api_keys_used=results.get("api_keys_available", []),
            timestamp=results.get("timestamp"),
        )
        return build_audit_ui_response(audit_run)

    # Auto-discover website if not provided
    website_url = req.website_url
    print(f"[AUDIT] req.website_url={repr(req.website_url)}", flush=True)
    if not website_url:
        print(f"[AUDIT] Running discovery...", flush=True)
        website_url = _discover_website(req.business_name, api_keys)
        print(f"[AUDIT] Discovery returned: {repr(website_url)}", flush=True)

    # Live audit
    loop = asyncio.get_event_loop()
    llm_results, web_results = await loop.run_in_executor(
        executor, run_live_audit,
        req.business_name, req.industry, req.city,
        website_url, req.phone, api_keys
    )

    audit_run = build_audit_run(
        mode="live",
        business_name=req.business_name,
        industry=req.industry,
        city=req.city,
        website_url=website_url,
        phone=req.phone,
        web_presence=web_results,
        llm_results=llm_results,
        api_keys_used=list(api_keys.keys()),
        timestamp=datetime.now().isoformat(),
    )
    return build_audit_ui_response(audit_run)


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


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    parts = stripped.split("```")
    fenced = parts[1] if len(parts) > 1 else stripped
    if fenced.startswith("json"):
        fenced = fenced[4:]
    return fenced.strip()


def _normalized_lookup_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_lookup_result(payload: dict[str, Any], *, allow_contact_fields: bool) -> dict[str, Any]:
    normalized = {
        "business_name": _normalized_lookup_value(payload.get("business_name")),
        "industry": _normalized_lookup_value(payload.get("industry")),
        "city": _normalized_lookup_value(payload.get("city")),
        "website_url": _normalized_lookup_value(payload.get("website_url")) if allow_contact_fields else "",
        "phone": _normalized_lookup_value(payload.get("phone")) if allow_contact_fields else "",
        "address": _normalized_lookup_value(payload.get("address")) if allow_contact_fields else "",
    }
    normalized["found"] = bool(normalized["business_name"] and (normalized["city"] or normalized["industry"]))
    return normalized


@app.post("/api/lookup")
async def lookup_business(req: LookupRequest):
    """Look up a business using Google Places API, returns multiple results."""
    api_keys = detect_api_keys()

    # ── Try Google Places API first — return up to 5 results ──
    places_key = os.environ.get("GOOGLE_PLACES_API_KEY")
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
                    results = [
                        _normalize_lookup_result(_parse_place(p, req.query), allow_contact_fields=True)
                        for p in places
                    ]
                    return {"results": results, "found": True}
        except Exception:
            pass

    # ── Fallback: LLM lookup (single result) ──
    prompt = (
        f"Identify the business \"{req.query}\".\n\n"
        "Reply with ONLY a JSON object, no markdown:\n"
        '{"business_name": "full name", "industry": "type like coffee shop", '
        '"city": "Neighborhood, City, State or null", "website_url": null, "phone": null, "address": null}\n\n'
        "Use null for any field you cannot verify directly from the query. "
        "Do not guess or invent website URLs, phone numbers, or street addresses."
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
            data = json.loads(_strip_json_fence(text))
            normalized = _normalize_lookup_result(data, allow_contact_fields=False)
            if normalized["found"]:
                return {"results": [normalized], "found": True}
        except Exception:
            continue

    return {"results": [], "found": False}


@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    return Path(__file__).parent.joinpath("ui.html").read_text()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
