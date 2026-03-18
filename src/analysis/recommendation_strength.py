from __future__ import annotations


def score_sentiment(response: str, name_variants: list[str], mentioned: bool) -> float:
    if not mentioned:
        return 0.0

    pos_words = {
        "best", "excellent", "outstanding", "top", "highly", "recommend",
        "trusted", "favorite", "love", "great", "amazing", "fantastic",
        "reliable", "premium", "award", "renowned", "exceptional", "superb",
        "popular", "acclaimed", "stellar", "wonderful", "impressive",
    }
    neg_words = {
        "avoid", "bad", "worst", "terrible", "poor", "disappointing",
        "overpriced", "rude", "slow", "dirty", "mediocre", "complaint",
        "closed", "shutdown", "scam", "fraud", "lawsuit", "negative",
        "declined", "problem", "issue", "warning",
    }

    relevant_sentences = [
        sentence.lower()
        for sentence in __import__("re").split(r"[.\n!?]", response)
        if any(variant in sentence.lower() for variant in name_variants)
    ]
    if not relevant_sentences:
        return 0.0

    pos_count = 0
    neg_count = 0
    for sentence in relevant_sentences:
        words = set(sentence.split())
        pos_count += len(words & pos_words)
        neg_count += len(words & neg_words)

    total = pos_count + neg_count
    if total == 0:
        return 0.1
    return min(1.0, max(-1.0, (pos_count - neg_count) / total))


def compute_legacy_visibility_score(
    *,
    mentioned: bool,
    cited: bool,
    position_normalized: float,
    sentiment: float,
    accuracy: float,
) -> float:
    """Compatibility per-prompt score until canonical scoring is replaced."""
    return round(
        40 * (1.0 if mentioned else 0.0)
        + 25 * (1.0 if cited else 0.0)
        + 15 * position_normalized
        + 10 * max(sentiment, 0)
        + 10 * accuracy,
        2,
    )
