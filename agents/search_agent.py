import os
import re
import unicodedata
import requests
from .state import AgentState

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
PLACES_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"


MAX_RESULTS = 20


def _normalize_name(name):
    if not name:
        return ""
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", ascii_only.lower()).strip()


def _dedupe_by_name(results):
    seen = set()
    deduped = []
    for r in results:
        key = _normalize_name(r.get("name"))
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        deduped.append(r)
    return deduped


def _mock_results(search_label: str, location: str):
    """Fake data used ONLY when there's no API key at all -- keeps the demo working offline."""
    label = search_label or "food"
    return [
        {"name": f"The {label.title()} Spot", "rating": 4.5, "price_level": 2, "distance_km": 1.2},
        {"name": f"{label.title()} House", "rating": 4.2, "price_level": 1, "distance_km": 0.8},
        {"name": f"Royal {label.title()}", "rating": 3.9, "price_level": 3, "distance_km": 2.5},
        {"name": f"{location} {label.title()} Corner", "rating": 4.7, "price_level": 2, "distance_km": 1.9},
        {"name": f"Budget {label.title()} Point", "rating": 3.6, "price_level": 1, "distance_km": 0.5},
    ]


def _text_search(query):
    """One real call to Google Places Text Search. Returns a cleaned, deduped list (possibly empty)."""
    params = {"query": query, "key": GOOGLE_MAPS_API_KEY}
    response = requests.get(PLACES_URL, params=params, timeout=10)
    data = response.json()
    results = []
    for place in data.get("results", [])[:MAX_RESULTS]:
        results.append({
            "name": place.get("name"),
            "rating": place.get("rating", 0),
            "price_level": place.get("price_level", 2),
            "address": place.get("formatted_address"),
            # Google Text Search doesn't return distance directly; a
            # production version would use Nearby Search with lat/lng instead.
            "distance_km": None,
        })
    return _dedupe_by_name(results)


def _build_query_attempts(search_term, location):
    attempts = []
    if search_term:
        attempts.append(f"{search_term} restaurants in {location}")
        attempts.append(f"{search_term} in {location}")  
        attempts.append(f"restaurants in {location}")  
    unique_attempts = []
    for a in attempts:
        if a not in seen:
            seen.add(a)
            unique_attempts.append(a)
    return unique_attempts


def search_restaurants_node(state: AgentState) -> AgentState:
    """LangGraph node: reads location + cuisine/craving/diet from state, writes search_results."""
    cuisine = state.get("cuisine") or ""
    food_craving = state.get("food_craving") or ""
    diet = state.get("diet")
    location = state.get("location", "")

    search_term = cuisine or food_craving

    if diet == "non-veg" and "veg" not in search_term:
        search_term = f"non veg {search_term}".strip()
    elif diet == "veg" and "veg" not in search_term:
        search_term = f"veg {search_term}".strip()

    if not GOOGLE_MAPS_API_KEY:
        state["search_results"] = _dedupe_by_name(_mock_results(search_term, location))
        state["agent_trace"].append(
            f"🔎 Search Agent → Found {len(state['search_results'])} restaurants near {location} "
            f"(mock data{f', searched for {search_term!r}' if search_term else ''})"
        )
        return state

    attempts = _build_query_attempts(search_term, location)
    results = []
    used_query = None
    broadened = False

    try:
        for i, query in enumerate(attempts):
            results = _text_search(query)
            if results:
                used_query = query
                broadened = i > 0  # we needed more than the first, most-specific attempt
                break
        state["search_results"] = results
        state["search_broadened"] = broadened  # NEW: lets the recommendation agent be transparent about this
    except Exception as e:
        print(f"[search_agent] API call failed, falling back to mock data: {e}")
        state["search_results"] = _mock_results(search_term, location)
        state["search_broadened"] = False

    trace_note = ""
    if broadened and used_query:
        trace_note = f" (had to broaden the search to {used_query!r} -- the specific term found nothing)"
    state["agent_trace"].append(
        f"🔎 Search Agent → Found {len(state['search_results'])} restaurants near {location}"
        + (f", searched for {search_term!r}" if search_term else "")
        + trace_note
    )
    return state