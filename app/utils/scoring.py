import re


COMMERCIAL_INTENT_KEYWORDS = [
    "best", "top", "vs", "versus", "compare", "comparison", "review", "alternative",
    "tool", "software", "service", "pricing", "cost", "cheap", "free", "trial",
    "how to choose", "which is better", "recommended", "buy", "hire",
]


def normalize_volume(volume: int, max_volume: int = 10000) -> float:
    return min(volume / max_volume, 1.0)


def normalize_difficulty(difficulty: int) -> float:
    return max((100 - difficulty) / 100, 0.0)


def visibility_gap_score(domain_visible: bool) -> float:
    return 0.0 if domain_visible else 1.0


def commercial_intent_score(query_text: str) -> float:
    query_lower = query_text.lower()
    matched = sum(1 for kw in COMMERCIAL_INTENT_KEYWORDS if kw in query_lower)
    if matched == 0:
        return 0.0
    return min(matched / 3, 1.0)


def calculate_opportunity_score(
    estimated_search_volume: int,
    competitive_difficulty: int,
    domain_visible: bool,
    query_text: str,
) -> float:
    volume_component = normalize_volume(estimated_search_volume)
    difficulty_component = normalize_difficulty(competitive_difficulty)
    visibility_component = visibility_gap_score(domain_visible)
    intent_component = commercial_intent_score(query_text)

    score = (
        0.35 * volume_component
        + 0.25 * difficulty_component
        + 0.25 * visibility_component
        + 0.15 * intent_component
    )

    return round(min(max(score, 0.0), 1.0), 4)
