"""
Demo Mode - SOTA GEO Blueprint Implementation.
Generates realistic simulated audit data matching the two-layer scoring model.
"""

import random
from datetime import datetime


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


class DemoAuditor:
    """Simulates a GEO audit with realistic data for the two-layer model."""

    COMPETITOR_TEMPLATES = [
        "{city} Premier {industry}",
        "Elite {industry} of {city}",
        "{city} {industry} Experts",
        "All-Star {industry} {city}",
        "Trusted {industry} Services",
        "Pro {industry} {city}",
        "First Choice {industry}",
        "{city} Quality {industry}",
        "Gold Standard {industry}",
        "NextGen {industry} Solutions",
        "Precision {industry} Co",
        "Summit {industry} Group",
    ]

    ATTRIBUTES = [
        "excellent customer service", "years of experience", "competitive pricing",
        "strong online reviews", "licensed and insured", "fast response times",
        "highly trained staff", "wide range of services", "community involvement",
        "transparent pricing", "award-winning service", "family-owned business",
        "modern equipment", "eco-friendly practices", "24/7 availability",
        "free consultations", "satisfaction guarantee", "certified professionals",
        "local expertise", "strong reputation",
    ]

    def __init__(self, business_name: str, industry: str, city: str, website_url: str = None):
        self.business_name = business_name
        self.industry = industry
        self.city = city.split(",")[0].strip()
        self.website_url = website_url
        self.full_city = city

        self.competitors = self._generate_competitors()
        # Most small businesses have LOW visibility
        self.visibility = random.choice(["low", "low", "low", "medium", "medium"])

    def _generate_competitors(self) -> list:
        competitors = []
        for tmpl in self.COMPETITOR_TEMPLATES:
            name = tmpl.format(city=self.city, industry=self.industry.title())
            competitors.append(name)
        random.shuffle(competitors)
        return competitors[:8]

    def run(self) -> dict:
        providers = ["anthropic", "openai", "perplexity"]

        llm_results = {}
        for provider in providers:
            llm_results[provider] = self._simulate_provider(provider)

        web_results = self._simulate_web_presence()

        return {
            "business_name": self.business_name,
            "industry": self.industry,
            "city": self.full_city,
            "website_url": self.website_url,
            "timestamp": datetime.now().isoformat(),
            "api_keys_available": providers,
            "llm_results": llm_results,
            "web_presence": web_results,
        }

    def _simulate_provider(self, provider: str) -> list:
        results = []
        mention_prob = {
            "low": {"anthropic": 0.15, "openai": 0.20, "perplexity": 0.25},
            "medium": {"anthropic": 0.50, "openai": 0.55, "perplexity": 0.60},
        }
        cite_prob = {
            "low": {"anthropic": 0.05, "openai": 0.05, "perplexity": 0.15},
            "medium": {"anthropic": 0.20, "openai": 0.15, "perplexity": 0.35},
        }

        m_prob = mention_prob.get(self.visibility, mention_prob["low"])[provider]
        c_prob = cite_prob.get(self.visibility, cite_prob["low"])[provider]

        for cluster, templates in PROMPT_BANK.items():
            for tmpl in templates:
                query = tmpl.format(industry=self.industry, city=self.full_city)

                mentioned = random.random() < m_prob
                cited = mentioned and random.random() < (c_prob / m_prob if m_prob > 0 else 0)
                position = None
                total_items = 5
                if mentioned:
                    position = random.choices([1, 2, 3, 4, 5], weights=[5, 15, 25, 30, 25])[0]

                # Position normalized
                pos_norm = max(0, 1.0 - (position - 1) / (total_items - 1)) if position else 0.0

                # Sentiment: slightly positive when mentioned
                sentiment = round(random.uniform(0.1, 0.6), 3) if mentioned else 0.0

                # Accuracy: partial
                accuracy = round(random.uniform(0.3, 0.8), 3) if mentioned else 0.0

                # Visibility score: v = 40*m + 25*c + 15*pos + 10*max(s,0) + 10*a
                m = 1.0 if mentioned else 0.0
                c_val = 1.0 if cited else 0.0
                v_score = round(
                    40 * m + 25 * c_val + 15 * pos_norm + 10 * max(sentiment, 0) + 10 * accuracy,
                    2
                )

                num_competitors = random.randint(3, 7)
                response_competitors = random.sample(self.competitors, min(num_competitors, len(self.competitors)))

                response = self._build_mock_response(query, mentioned, position, response_competitors)
                attrs = random.sample(self.ATTRIBUTES, random.randint(2, 5))

                analysis = {
                    "mentioned": mentioned,
                    "exact_match": mentioned,
                    "fuzzy_match": False,
                    "fuzzy_score": 95 if mentioned else random.randint(20, 55),
                    "cited": cited,
                    "position": position,
                    "total_items": total_items,
                    "position_normalized": round(pos_norm, 3),
                    "sentiment": sentiment,
                    "accuracy": accuracy,
                    "visibility_score": v_score,
                    "competitors": [c for c in response_competitors if c != self.business_name],
                    "attributes": attrs,
                }

                results.append({
                    "query": query,
                    "cluster": cluster,
                    "response": response,
                    "analysis": analysis,
                })

        return results

    def _build_mock_response(self, query, mentioned, position, competitors):
        lines = [f"Here are some recommended {self.industry} businesses in {self.city}:\n"]
        items = list(competitors)
        if mentioned and position:
            items.insert(position - 1, self.business_name)
        for i, name in enumerate(items[:6], 1):
            attrs = random.sample(self.ATTRIBUTES, 2)
            lines.append(f"{i}. **{name}** - Known for {attrs[0]} and {attrs[1]}.")
        lines.append(f"\nI'd recommend checking recent reviews before making a decision.")
        return "\n".join(lines)

    def _simulate_web_presence(self) -> dict:
        return {
            # Core website checks
            "has_schema_markup": random.random() < 0.3,
            "schema_types": ["LocalBusiness"] if random.random() < 0.3 else [],
            "has_faq_schema": random.random() < 0.15,
            "has_local_business_schema": random.random() < 0.25,
            "has_og_tags": random.random() < 0.4,
            "has_meta_description": random.random() < 0.6,
            "has_title_tag": True,
            "ssl_valid": random.random() < 0.8,
            "mobile_friendly_meta": random.random() < 0.7,
            "fast_load": random.random() < 0.5,
            "load_time_seconds": round(random.uniform(1.0, 5.0), 2),
            "website_accessible": True,
            "has_canonical": random.random() < 0.4,
            "has_hreflang": False,
            # Indexability
            "robots_txt_exists": random.random() < 0.5,
            "robots_allows_crawl": True,
            "sitemap_exists": random.random() < 0.35,
            "has_noindex": False,
            # Content readiness
            "has_answer_blocks": random.random() < 0.2,
            "answer_block_count": random.randint(0, 3),
            "word_count": random.randint(200, 1500),
            "has_faq_section": random.random() < 0.15,
            "faq_count": random.randint(0, 4),
            "has_contact_info": random.random() < 0.7,
            "has_hours": random.random() < 0.5,
            "has_address": random.random() < 0.6,
            # Directories
            "google_business_found": random.random() < 0.6,
            "yelp_found": random.random() < 0.4,
            "bbb_found": random.random() < 0.25,
        }
