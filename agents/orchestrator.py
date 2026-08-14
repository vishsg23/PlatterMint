"""
orchestrator.py
----------------
This is the agent that makes this project genuinely "agentic" instead of
a fixed pipeline. Its job:

1. Pull cuisine / budget / min_rating out of the user's plain-English query
   (simple keyword rules here -- swap with an LLM call if you want it fancier).
2. DECIDE what to do next:
   - If the user already told us everything we need (cuisine + budget),
     we skip the preference-history lookup and go straight to search.
   - If the query is vague ("find me something good to eat"), we look up
     their past preferences first so we can fill the gaps.

This decision is what LangGraph's conditional edges use to branch.

FIX (2026-08): previously, anything the user typed that wasn't one of the
~12 hardcoded cuisines (e.g. "something sweet", "spicy", "street food")
was silently thrown away -- it never reached search. We now also detect
a "food craving" phrase and store it separately, so the search agent has
something useful even when there's no strict cuisine match.
"""

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

# NEW: cravings that aren't a "cuisine" but are still a perfectly good thing
# to search for. Multi-word keys are matched as exact substrings against the
# raw query; single-word keys are matched token-by-token (with typo tolerance).
FOOD_TYPE_KEYWORDS = {
    "sweet": "desserts",
    "sweets": "desserts",
    "dessert": "desserts",
    "desserts": "desserts",
    "spicy": "spicy food",
    "street food": "street food",
    "comfort food": "comfort food",
    "healthy": "healthy food",
    "vegan": "vegan food",
    "vegetarian": "vegetarian food",
    "breakfast": "breakfast",
    "seafood": "seafood",
    "bakery": "bakery",
    "cafe": "cafe",
    "coffee": "cafe",
    "ice cream": "ice cream",
    "fast food": "fast food",
    "barbecue": "barbecue",
    "bbq": "barbecue",
}


def _fuzzy_find(word_list, query_words, cutoff=0.75):
    """
    Looks for a close match to any word/phrase in word_list among the
    words the user actually typed -- so small typos like "pizaa" -> "pizza"
    or "chiken" -> "chicken" still get detected instead of silently failing.
    `cutoff` is how close the spelling needs to be (0-1, higher = stricter).
    """
    for candidate in word_list:
        # multi-word keywords (e.g. "south indian") are matched against the
        # whole query string; single words are matched token by token
        if " " in candidate:
            continue
        matches = difflib.get_close_matches(candidate, query_words, n=1, cutoff=cutoff)
        if matches:
            return candidate
    return None


def _find_food_craving(query, query_words):
    """
    Best-effort detection of a food-type/craving phrase (e.g. "something
    sweet" -> "desserts") that falls outside the strict cuisine list, so a
    real craving is never silently dropped.
    """
    # 1. multi-word phrases first, exact substring match against raw query
    for phrase, mapped in FOOD_TYPE_KEYWORDS.items():
        if " " in phrase and phrase in query:
            return mapped

    # 2. single-word exact match against tokens
    single_word_map = {k: v for k, v in FOOD_TYPE_KEYWORDS.items() if " " not in k}
    for word, mapped in single_word_map.items():
        if word in query_words:
            return mapped

    # 3. typo-tolerant fallback
    fuzzy_key = _fuzzy_find(list(single_word_map.keys()), query_words)
    if fuzzy_key:
        return single_word_map[fuzzy_key]

    return None


def orchestrator_node(state: AgentState) -> AgentState:
    """LangGraph node: parses the query and decides the route."""
    state["agent_trace"] = []  # start a fresh trace for this run

    query = state.get("user_query", "").lower()
    query_words = query.replace(",", " ").split()

    # --- extract cuisine ---
    found_cuisine = next((c for c in CUISINE_KEYWORDS if c in query), None)
    if not found_cuisine:
        found_cuisine = _fuzzy_find(CUISINE_KEYWORDS, query_words)
    state["cuisine"] = found_cuisine

    # --- NEW: if no strict cuisine was found, try a food-craving phrase
    #     instead, so "something sweet" etc. still reaches search ---
    found_craving = None
    if not found_cuisine:
        found_craving = _find_food_craving(query, query_words)
    state["food_craving"] = found_craving

    # --- extract budget ---
    found_budget = next((v for k, v in BUDGET_KEYWORDS.items() if k in query), None)
    if not found_budget:
        fuzzy_key = _fuzzy_find(list(BUDGET_KEYWORDS.keys()), query_words)
        found_budget = BUDGET_KEYWORDS.get(fuzzy_key)
    state["budget"] = found_budget

    # --- extract a rough minimum rating if user mentions it ---
    explicit_rating = 4.0 if ("best" in query or "top rated" in query) else None
    state["min_rating"] = explicit_rating
    state["original_min_rating"] = explicit_rating  # what was actually asked, before any relaxing

    # --- the actual "agent decision" ---
    state["needs_preference_lookup"] = not (found_cuisine and found_budget)

    detected_bits = []
    if found_cuisine:
        detected_bits.append(f"cuisine = {found_cuisine}")
    elif found_craving:
        detected_bits.append(f"craving = {found_craving} (not a strict cuisine, used as search term)")
    else:
        detected_bits.append("cuisine = not specified")
    detected_bits.append(f"budget = {found_budget or 'not specified'}")

    # simple confidence proxy: more fields detected = more confident this was understood correctly
    intent_confidence = 60 + (20 if found_cuisine else (10 if found_craving else 0)) + (20 if found_budget else 0)

    state["agent_trace"].append(
        f"🧭 Intent Agent → Detected: {', '.join(detected_bits)} (confidence {intent_confidence}%)"
    )

    if not state["needs_preference_lookup"]:
        state["agent_trace"].append(
            "🧠 Preference Agent → Skipped (you gave enough detail already)"
        )
        state["welcome_message"] = None

    return state


def route_after_orchestrator(state: AgentState) -> str:
    """
    Tells LangGraph which node to go to next.
    This function name is passed into add_conditional_edges().
    """
    return "preference_rag" if state.get("needs_preference_lookup") else "search"