import difflib
from .state import AgentState

BUDGET_KEYWORDS = {
    "cheap": "low", "budget": "low", "affordable": "low",
    "moderate": "medium", "mid-range": "medium",
    "expensive": "high", "fancy": "high", "premium": "high", "fine dining": "high",
}

CUISINE_KEYWORDS = [
    "pizza", "chinese", "italian", "indian", "mexican", "thai",
    "japanese", "sushi", "biryani", "burger", "south indian", "north indian",
]

FOOD_TYPE_KEYWORDS = {
    "sweet": "desserts", "sweets": "desserts", "dessert": "desserts", "desserts": "desserts",
    "spicy": "spicy food",
    "street food": "street food",
    "comfort food": "comfort food",
    "healthy": "healthy food",
    "vegan": "vegan food",
    "vegetarian": "vegetarian food",
    "breakfast": "breakfast",
    "seafood": "seafood",
    "bakery": "bakery",
    "cafe": "cafe", "coffee": "cafe",
    "ice cream": "ice cream",
    "fast food": "fast food",
    "barbecue": "barbecue", "bbq": "barbecue",
}


FILLER_WORDS = {
    "something", "some", "food", "restaurant", "restaurants", "please",
    "near", "me", "want", "craving", "a", "an", "the", "good", "nice",
    "for", "to", "eat", "in", "at", "any", "just", "looking",
}

NON_VEG_PHRASES = ["non veg", "non-veg", "nonveg", "non vegetarian", "non-vegetarian"]
VEG_PHRASES = ["veg", "vegetarian", "pure veg"]


def _fuzzy_find(word_list, query_words, cutoff=0.75):
    for candidate in word_list:
        if " " in candidate:
            continue
        matches = difflib.get_close_matches(candidate, query_words, n=1, cutoff=cutoff)
        if matches:
            return candidate
    return None


def _find_food_craving(query, query_words):
    """Matches a known food-type/craving phrase, e.g. 'something sweet' -> 'desserts'."""
    for phrase, mapped in FOOD_TYPE_KEYWORDS.items():
        if " " in phrase and phrase in query:
            return mapped
    single_word_map = {k: v for k, v in FOOD_TYPE_KEYWORDS.items() if " " not in k}
    for word, mapped in single_word_map.items():
        if word in query_words:
            return mapped
    fuzzy_key = _fuzzy_find(list(single_word_map.keys()), query_words)
    if fuzzy_key:
        return single_word_map[fuzzy_key]
    return None


def _raw_craving_fallback(query_words):
    """
    NEW: last-resort fallback when nothing matched any known list. Strips
    filler words and uses whatever's left as the search term directly, so
    a word we simply never thought to add to a list (like "non veg") still
    reaches the search agent instead of being silently dropped.
    """
    cleaned = [w for w in query_words if w not in FILLER_WORDS]
    if not cleaned:
        return None
    return " ".join(cleaned)


def _find_diet(query):
    """Returns 'non-veg', 'veg', or None. Checks non-veg phrases first so
    'non veg' isn't mistaken for a plain 'veg' match."""
    for phrase in NON_VEG_PHRASES:
        if phrase in query:
            return "non-veg"
    for phrase in VEG_PHRASES:
        if phrase in query:
            return "veg"
    return None


def orchestrator_node(state: AgentState) -> AgentState:
    state["agent_trace"] = []

    query = state.get("user_query", "").lower()
    query_words = query.replace(",", " ").split()

    found_cuisine = next((c for c in CUISINE_KEYWORDS if c in query), None)
    if not found_cuisine:
        found_cuisine = _fuzzy_find(CUISINE_KEYWORDS, query_words)
    state["cuisine"] = found_cuisine

    found_craving = None
    if not found_cuisine:
        found_craving = _find_food_craving(query, query_words)
        if not found_craving:
          
            found_craving = _raw_craving_fallback(query_words)
    state["food_craving"] = found_craving

    state["diet"] = _find_diet(query)

    found_budget = next((v for k, v in BUDGET_KEYWORDS.items() if k in query), None)
    if not found_budget:
        fuzzy_key = _fuzzy_find(list(BUDGET_KEYWORDS.keys()), query_words)
        found_budget = BUDGET_KEYWORDS.get(fuzzy_key)
    state["budget"] = found_budget

    explicit_rating = 4.0 if ("best" in query or "top rated" in query) else None
    state["min_rating"] = explicit_rating
    state["original_min_rating"] = explicit_rating

   
    has_craving_signal = bool(found_cuisine or found_craving)
    state["needs_preference_lookup"] = not (has_craving_signal and found_budget)

    detected_bits = []
    if found_cuisine:
        detected_bits.append(f"cuisine = {found_cuisine}")
    elif found_craving:
        detected_bits.append(f"craving = {found_craving!r} (used as search term)")
    else:
        detected_bits.append("cuisine = not specified")
    if state["diet"]:
        detected_bits.append(f"diet = {state['diet']}")
    detected_bits.append(f"budget = {found_budget or 'not specified'}")

    intent_confidence = 60 + (20 if found_cuisine else (10 if found_craving else 0)) + (20 if found_budget else 0)

    state["agent_trace"].append(
        f"Intent Agent → Detected: {', '.join(detected_bits)} (confidence {intent_confidence}%)"
    )

    if not state["needs_preference_lookup"]:
        state["agent_trace"].append("Preference Agent → Skipped (you gave enough detail already)")
        state["welcome_message"] = None

    return state


def route_after_orchestrator(state: AgentState) -> str:
    return "preference_rag" if state.get("needs_preference_lookup") else "search"