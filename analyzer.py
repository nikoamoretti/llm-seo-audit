"""
Response Analyzer - SOTA GEO Blueprint Implementation.
Analyzes LLM responses for: mention, citation, position, sentiment, accuracy.
Per-prompt visibility: v = 40*m + 25*c + 15*pos + 10*max(s,0) + 10*a
"""

import re
from thefuzz import fuzz


class ResponseAnalyzer:
    """Analyzes LLM responses for business visibility using the SAGEO framework."""

    # Positive/negative sentiment lexicons for lightweight scoring
    POS_WORDS = {
        "best", "excellent", "outstanding", "top", "highly", "recommend",
        "trusted", "favorite", "love", "great", "amazing", "fantastic",
        "reliable", "premium", "award", "renowned", "exceptional", "superb",
        "popular", "acclaimed", "stellar", "wonderful", "impressive",
    }
    NEG_WORDS = {
        "avoid", "bad", "worst", "terrible", "poor", "disappointing",
        "overpriced", "rude", "slow", "dirty", "mediocre", "complaint",
        "closed", "shutdown", "scam", "fraud", "lawsuit", "negative",
        "declined", "problem", "issue", "warning",
    }

    def __init__(self, business_name: str, known_facts: dict = None):
        self.business_name = business_name
        self.name_lower = business_name.lower()
        self.name_variants = self._generate_variants(business_name)
        # Known facts for accuracy checking: {phone, address, city, website, hours}
        self.known_facts = known_facts or {}

    def _generate_variants(self, name: str) -> list:
        variants = [name.lower()]
        variants.append(re.sub(r"'s\b", "", name.lower()))
        for suffix in [" llc", " inc", " corp", " co", " company", " group", " services"]:
            if name.lower().endswith(suffix):
                variants.append(name.lower().replace(suffix, "").strip())
        variants.append(re.sub(r'[^\w\s]', '', name.lower()))
        return list(set(variants))

    def analyze_response(self, response: str, query: str) -> dict:
        """Full SAGEO analysis of a single LLM response.

        Returns dict with: mentioned, cited, position, position_normalized,
        sentiment, accuracy, visibility_score, competitors, attributes.
        """
        if response.startswith("ERROR:"):
            return self.empty_analysis()

        response_lower = response.lower()

        # --- Mention detection (m) ---
        exact_match = any(v in response_lower for v in self.name_variants)
        fuzzy_match = False
        fuzzy_score = 0
        if not exact_match:
            sentences = re.split(r'[.\n]', response)
            for sentence in sentences:
                for variant in self.name_variants:
                    words = sentence.lower().split()
                    name_word_count = len(variant.split())
                    for i in range(len(words) - name_word_count + 1):
                        chunk = " ".join(words[i:i + name_word_count])
                        score = fuzz.ratio(variant, chunk)
                        if score > fuzzy_score:
                            fuzzy_score = score
                        if score >= 80:
                            fuzzy_match = True

        mentioned = exact_match or fuzzy_match
        m = 1.0 if mentioned else 0.0

        # --- Citation detection (c) ---
        cited = self._detect_citation(response)
        c = 1.0 if cited else 0.0

        # --- Position detection (pos) ---
        raw_position = None
        total_items = 0
        if mentioned:
            raw_position, total_items = self._find_position_detailed(response)

        # Normalize position: 1st of 5 -> 1.0, 5th of 5 -> 0.0
        if raw_position is not None and total_items > 1:
            pos_normalized = max(0, 1.0 - (raw_position - 1) / (total_items - 1))
        elif raw_position == 1:
            pos_normalized = 1.0
        elif mentioned:
            pos_normalized = 0.5  # mentioned but position unclear
        else:
            pos_normalized = 0.0

        # --- Sentiment scoring (s) ---
        sentiment = self._score_sentiment(response, mentioned)

        # --- Accuracy scoring (a) ---
        accuracy = self._score_accuracy(response)

        # --- Per-prompt visibility score ---
        # v = 40*m + 25*c + 15*pos + 10*max(s,0) + 10*a
        visibility_score = (
            40 * m
            + 25 * c
            + 15 * pos_normalized
            + 10 * max(sentiment, 0)
            + 10 * accuracy
        )

        # --- Competitors & attributes ---
        competitors = self._extract_business_names(response)
        attributes = self._extract_attributes(response)

        return {
            "mentioned": mentioned,
            "exact_match": exact_match,
            "fuzzy_match": fuzzy_match and not exact_match,
            "fuzzy_score": fuzzy_score,
            "cited": cited,
            "position": raw_position,
            "total_items": total_items,
            "position_normalized": round(pos_normalized, 3),
            "sentiment": round(sentiment, 3),
            "accuracy": round(accuracy, 3),
            "visibility_score": round(visibility_score, 2),
            "competitors": competitors,
            "attributes": attributes,
        }

    def _detect_citation(self, response: str) -> bool:
        """Check if the response cites/links the business website or profile."""
        response_lower = response.lower()

        # Check for URL mentions
        website = self.known_facts.get("website", "")
        if website:
            # Normalize URL for matching
            clean_url = website.lower().replace("https://", "").replace("http://", "").rstrip("/")
            if clean_url in response_lower:
                return True

        # Check for explicit source citations (Perplexity-style [1], [source])
        if re.search(r'\[(?:source|ref|\d+)\]', response, re.IGNORECASE):
            # Check if the citation context mentions the business
            for variant in self.name_variants:
                pattern = rf'{re.escape(variant)}[^.]*\[\d+\]'
                if re.search(pattern, response_lower):
                    return True

        # Check for "visit" or "website" links near business name
        for variant in self.name_variants:
            if variant in response_lower:
                # Check within surrounding context
                idx = response_lower.index(variant)
                context = response_lower[max(0, idx - 100):idx + 200]
                if any(w in context for w in ["http", "www.", ".com", ".org", "website", "visit"]):
                    return True

        return False

    def _find_position_detailed(self, response: str) -> tuple:
        """Find position and total list items. Returns (position, total)."""
        lines = response.split('\n')
        position = None
        current_pos = 0
        max_pos = 0

        for line in lines:
            num_match = re.match(r'\s*(?:#?\s*)?(\d+)[.):\s]', line)
            if num_match:
                current_pos = int(num_match.group(1))
            elif re.match(r'\s*[-*]\s', line):
                current_pos += 1
            elif re.match(r'\s*\*\*', line):
                current_pos += 1

            if current_pos > max_pos:
                max_pos = current_pos

            line_lower = line.lower()
            if position is None and any(v in line_lower for v in self.name_variants):
                position = current_pos if current_pos > 0 else 1

        return position, max(max_pos, 1)

    def _score_sentiment(self, response: str, mentioned: bool) -> float:
        """Score sentiment toward the business in the response. Range: -1 to 1."""
        if not mentioned:
            return 0.0

        response_lower = response.lower()

        # Find sentences mentioning the business
        sentences = re.split(r'[.\n!?]', response)
        relevant_sentences = []
        for sent in sentences:
            if any(v in sent.lower() for v in self.name_variants):
                relevant_sentences.append(sent.lower())

        if not relevant_sentences:
            return 0.0

        pos_count = 0
        neg_count = 0
        for sent in relevant_sentences:
            words = set(sent.split())
            pos_count += len(words & self.POS_WORDS)
            neg_count += len(words & self.NEG_WORDS)

        total = pos_count + neg_count
        if total == 0:
            return 0.1  # Neutral mention is slightly positive

        return min(1.0, max(-1.0, (pos_count - neg_count) / total))

    def _score_accuracy(self, response: str) -> float:
        """Score factual accuracy of claims about the business. Range: 0 to 1."""
        if not self.known_facts:
            return 0.5  # No ground truth to compare against

        checks = 0
        correct = 0
        response_lower = response.lower()

        # Check city/location
        city = self.known_facts.get("city", "")
        if city:
            checks += 1
            if city.lower().split(",")[0].strip() in response_lower:
                correct += 1

        # Check phone
        phone = self.known_facts.get("phone", "")
        if phone:
            checks += 1
            phone_digits = re.sub(r'\D', '', phone)
            if phone_digits and phone_digits in re.sub(r'\D', '', response):
                correct += 1

        # Check website
        website = self.known_facts.get("website", "")
        if website:
            checks += 1
            clean = website.lower().replace("https://", "").replace("http://", "").rstrip("/")
            if clean in response_lower:
                correct += 1

        # Check industry/type
        industry = self.known_facts.get("industry", "")
        if industry:
            checks += 1
            if industry.lower() in response_lower:
                correct += 1

        if checks == 0:
            return 0.5

        return correct / checks

    def _extract_business_names(self, response: str) -> list:
        competitors = []
        lines = response.split('\n')

        for line in lines:
            bold_matches = re.findall(r'\*\*([^*]+)\*\*', line)
            for match in bold_matches:
                name = match.strip().rstrip(':').strip()
                if (len(name) > 2 and len(name) < 60
                        and not any(v in name.lower() for v in self.name_variants)
                        and not self._is_generic_phrase(name)):
                    competitors.append(name)

            num_match = re.match(r'\s*\d+[.)]\s*\*?\*?([^*\n:]+)', line)
            if num_match:
                name = num_match.group(1).strip().rstrip(':').strip(' -')
                if (len(name) > 2 and len(name) < 60
                        and not any(v in name.lower() for v in self.name_variants)
                        and not self._is_generic_phrase(name)):
                    if name not in competitors:
                        competitors.append(name)

        return competitors[:15]

    def _is_generic_phrase(self, text: str) -> bool:
        generic = [
            "here are", "top rated", "best", "recommend", "option",
            "note", "disclaimer", "important", "however", "also",
            "consider", "additionally", "keep in mind", "please",
            "i would", "you can", "they offer", "known for",
            "why", "pros", "cons", "features", "services",
        ]
        text_lower = text.lower()
        return any(g in text_lower for g in generic) or len(text.split()) > 8

    def _extract_attributes(self, response: str) -> list:
        attributes = []
        patterns = [
            r'known for\s+(?:their\s+)?([^.,\n]+)',
            r'specializ(?:es?|ing) in\s+([^.,\n]+)',
            r'offers?\s+([^.,\n]+)',
            r'(?:excellent|great|outstanding|exceptional)\s+([^.,\n]+)',
            r'(?:highly rated|well-known|popular|trusted)\s+(?:for\s+)?([^.,\n]+)',
            r'reputation for\s+([^.,\n]+)',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, response, re.IGNORECASE)
            for match in matches:
                attr = match.strip()
                if 3 < len(attr) < 60:
                    attributes.append(attr)

        return list(set(attributes))[:10]

    def empty_analysis(self) -> dict:
        return {
            "mentioned": False,
            "exact_match": False,
            "fuzzy_match": False,
            "fuzzy_score": 0,
            "cited": False,
            "position": None,
            "total_items": 0,
            "position_normalized": 0.0,
            "sentiment": 0.0,
            "accuracy": 0.0,
            "visibility_score": 0.0,
            "competitors": [],
            "attributes": [],
        }
