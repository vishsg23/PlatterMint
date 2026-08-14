"""
search_agent.py
----------------
Job: given a location (and optionally a cuisine or food craving), fetch
real restaurants nearby using the Google Places API.

If no API key is configured, we return realistic MOCK data instead, so
you can run and demo the whole pipeline without needing a Google Cloud
billing account set up yet.

FIX (2026-08): previously this only ever used `cuisine` to build the
search query. If the orchestrator didn't detect a strict cuisine (e.g. the
user typed "something sweet"), the query fell back to a generic
"restaurants in {location}" search with the craving completely dropped.
Now it also falls back to `food_craving` (set by the orchestrator) before
going fully generic.
"""

import os
import requests
from .state import AgentState

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
PLACES_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"

# FIX (#10, "only top-3 shown"): this used to be hardcoded to 10, which
# limited how many restaurants the Filter/Recommendation agents ever saw --
# even though Google Places can return up to 20 per page. Raising this lets
# the recommendation agent's new "more options" list (see
# recommendation_agent.py) actually have something to show.
MAX_RESULTS = 20


def _mock_results(search_label: str, location: str):
    """Fake data used when there's no API key -- keeps the demo working offline."""
    label = search_label or "food"
    return [
        {"name": f"The {label.title()} Spot", "rating": 4.5, "price_level": 2, "distance_km": 1.2},
        {"name": f"{label.title()} House", "rating": 4.2, "price_level": 1, "distance_km": 0.8},
        {"name": f"Royal {label.title()}", "rating": 3.9, "price_level": 3, "distance_km": 2.5},
        {"name": f"{location} {label.title()} Corner", "rating": 4.7, "price_level": 2, "distance_km": 1.9},
        {"name": f"Budget {label.title()} Point", "rating": 3.6, "price_level": 1, "distance_km": 0.5},
    ]


def search_restaurants_node(state: AgentState) -> AgentState:
    """LangGraph node: reads location + cuisine/craving from state, writes search_results."""
    cuisine = state.get("cuisine") or ""
    food_craving = state.get("food_craving") or ""
    location = state.get("location", "")

    # Prefer an explicit cuisine; otherwise use a detected food-type craving
    # (e.g. "desserts") so free-text cravings actually reach the search
    # instead of being silently dropped. Only fall back to nothing if
    # neither was detected.
    search_term = cuisine or food_craving

    if not GOOGLE_MAPS_API_KEY:
        state["search_results"] = _mock_results(search_term, location)
        state["agent_trace"].append(
            f"🔎 Search Agent → Found {len(state['search_results'])} restaurants near {location} "
            f"(mock data{f', searched for {search_term!r}' if search_term else ''})"
        )
        return state

    query = f"{search_term} restaurants in {location}".strip()
    params = {"query": query, "key": GOOGLE_MAPS_API_KEY}
    try:
        response = requests.get(PLACES_URL, params=params, timeout=10)
        data = response.json()
        results = []
        for place in data.get("results", [])[:MAX_RESULTS]:
            results.append({
                "name": place.get("name"),
                "rating": place.get("rating", 0),
                # Google's price_level is 0(cheap)-4(expensive); we keep it as-is
                "price_level": place.get("price_level", 2),
                "address": place.get("formatted_address"),
                # Google Text Search doesn't return distance directly;
                # a production version would use Nearby Search with lat/lng instead.
                "distance_km": None,
            })
        state["search_results"] = results if results else _mock_results(search_term, location)
    except Exception as e:
        print(f"[search_agent] API call failed, falling back to mock data: {e}")
        state["search_results"] = _mock_results(search_term, location)

    state["agent_trace"].append(
        f"🔎 Search Agent → Found {len(state['search_results'])} restaurants near {location}"
        + (f", searched for {search_term!r}" if search_term else "")
    )
    return state