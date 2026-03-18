from __future__ import annotations

from src.core.models import AuditRun, Recommendation
from src.recommendations.explainer import explain_recommendation
from src.scoring.final import load_score_config


PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2}


def build_recommendations(audit_run: AuditRun) -> list[Recommendation]:
    config = load_score_config()
    low_component_score = int(config["thresholds"]["visibility"]["low_component_score"])
    web_presence = audit_run.web_presence
    visibility_dimensions = audit_run.visibility.dimensions
    recommendations: list[Recommendation] = []

    if web_presence.get("has_noindex") is True:
        recommendations.append(
            explain_recommendation(
                priority="P0",
                category="Website Access",
                title="Remove the noindex directive from the public site",
                why_it_matters="A noindex directive blocks the site from being treated as a retrievable source for AI answers.",
                evidence=["web_presence.has_noindex=True"],
                impacted_components=["crawlability"],
                implementation_hint="Remove the noindex directive from page templates or response headers for the pages you want crawled.",
            )
        )

    if web_presence.get("robots_allows_crawl") is False:
        recommendations.append(
            explain_recommendation(
                priority="P0",
                category="Website Access",
                title="Allow crawl access in robots rules",
                why_it_matters="Blocked crawl access prevents answer engines from reading and refreshing the site content.",
                evidence=["web_presence.robots_allows_crawl=False"],
                impacted_components=["crawlability"],
                implementation_hint="Update robots rules so public service and location pages can be fetched by common crawlers.",
            )
        )

    if web_presence and web_presence.get("website_accessible") is False:
        recommendations.append(
            explain_recommendation(
                priority="P0",
                category="Website Access",
                title="Restore public access to the website",
                why_it_matters="If the site does not load, the business cannot build trustworthy on-site evidence.",
                evidence=["web_presence.website_accessible=False"],
                impacted_components=["crawlability", "trust_signals"],
                implementation_hint="Resolve the availability issue and verify the homepage loads without authentication or server errors.",
            )
        )

    if web_presence.get("google_business_found") is False:
        recommendations.append(
            explain_recommendation(
                priority="P0",
                category="Listing Presence",
                title="Claim and verify the Google Business Profile",
                why_it_matters="Local answer engines need an observed entity source before they can confidently recommend the business in discovery prompts.",
                evidence=["web_presence.google_business_found=False"],
                impacted_components=["listing_presence", "official_citation_share"],
                implementation_hint="Claim the profile, confirm the business details, and keep hours, category, phone, and website aligned with the site.",
            )
        )

    if web_presence.get("yelp_found") is False:
        recommendations.append(
            explain_recommendation(
                priority="P1",
                category="Listing Presence",
                title="Complete the Yelp listing",
                why_it_matters="A missing Yelp listing removes one of the observed third-party sources that local answer engines can cite.",
                evidence=["web_presence.yelp_found=False"],
                impacted_components=["listing_presence", "citation_rate"],
                implementation_hint="Claim the listing and align the business name, address, phone, and website with the site.",
            )
        )

    if web_presence.get("has_schema_markup") is False:
        recommendations.append(
            explain_recommendation(
                priority="P1",
                category="Machine-Readable Info",
                title="Add business schema to the site",
                why_it_matters="Without machine-readable entity markup, the site exposes fewer explicit facts for engines to quote back.",
                evidence=["web_presence.has_schema_markup=False"],
                impacted_components=["entity_completeness", "official_citation_share"],
                implementation_hint="Add LocalBusiness or the closest subtype with business name, address, phone, hours, and site URL.",
            )
        )

    official_citation_share = visibility_dimensions.get("official_citation_share")
    if official_citation_share and official_citation_share.score < low_component_score:
        recommendations.append(
            explain_recommendation(
                priority="P1",
                category="On-Site Evidence",
                title="Publish more quotable first-party facts on the site",
                why_it_matters="The business is being cited without enough official-domain support, which weakens authority in answer generation.",
                evidence=official_citation_share.evidence or ["visibility.official_citation_share=0"],
                impacted_components=["citation_rate", "official_citation_share"],
                implementation_hint="Add precise service, location, hours, and FAQ content to crawlable pages that link back to the homepage and contact page.",
            )
        )

    discovery_strength = visibility_dimensions.get("discovery_strength")
    if discovery_strength and discovery_strength.score < low_component_score:
        recommendations.append(
            explain_recommendation(
                priority="P1",
                category="Discovery Coverage",
                title="Expand pages that answer non-branded discovery questions",
                why_it_matters="The business appears less often in discovery prompts than it should, which limits new-customer visibility.",
                evidence=discovery_strength.evidence,
                impacted_components=["mention_rate", "recommendation_rate", "discovery_strength"],
                implementation_hint="Build or strengthen service, location, and FAQ pages around the problems and comparisons customers ask before they know the brand.",
            )
        )

    competitor_gap = visibility_dimensions.get("competitor_gap")
    if competitor_gap and competitor_gap.score < low_component_score and audit_run.visibility.top_competitors:
        competitors = list(audit_run.visibility.top_competitors)[:3]
        recommendations.append(
            explain_recommendation(
                priority="P2",
                category="Competitive Gap",
                title=f"Close the answer-space gap with {', '.join(competitors)}",
                why_it_matters="Competitors occupy more of the answer space across prompts, which pushes the business out of recommendation sets.",
                evidence=competitor_gap.evidence + [f"visibility.top_competitors={', '.join(competitors)}"],
                impacted_components=["competitor_gap", "recommendation_rate"],
                implementation_hint="Compare the competitors' service, FAQ, and location coverage against the site and fill the missing intent pages and citations.",
            )
        )

    recommendations.sort(key=lambda recommendation: PRIORITY_ORDER[recommendation.priority])
    return recommendations
