"""
scoring.py
----------
This is what turns "here's a list of restaurants" into "here's a decision."
Every restaurant gets scored across factors, then rescaled to a 0-100 total,
so the score breakdown shown in the UI reflects exactly WHY one restaurant
beat another -- not just a rating number.

Weights when every factor applies (add up to 100):
    Cuisine Match          30
    Budget Match           25
    Rating Quality         20
    Distance               15
    Popularity               5
    Preference History        5

FIX (2026-08), two changes from the original:

1. Cuisine Match no longer hands out 15/30 "for free" when no cuisine was
   detected. That criterion simply doesn't apply for that search, so it's
   now excluded from both earned and possible points (0/0) instead of
   quietly inflating every restaurant's score. The final score is rescaled
   to still read out of 100 using only the criteria that actually applied.

2. Distance is now flagged when it's an *estimate* (Google Text Search
   doesn't return coordinates, so distance_km is often None). The points
   still count toward the total so scores stay comparable, but a `notes`
   dict is returned alongside the breakdown so the UI can show
   "estimated -- not measured for this search" instead of implying a real
   calculation happened.

3. Added an "any" budget tier (all price levels) for genuine "show me
   anything" relaxation, instead of silently mapping that to "high" only.
"""

PRICE_LEVEL_BY_BUDGET = {
    "low": [0, 1],
    "medium": [1, 2],
    "high": [2, 3, 4],
    "any": [0, 1, 2, 3, 4],
}


def score_restaurant(restaurant, cuisine, budget, matched_history=False, history_available=True):
    """
    Returns (breakdown_dict, total_score, notes_dict).

    breakdown_dict looks like: {"Cuisine Match": (30, 30), "Budget Match": (10, 25), ...}
    where each value is (points_earned, points_possible). A factor with
    possible == 0 means it didn't apply to this search and was excluded.

    notes_dict maps factor name -> a short caveat string, only present for
    factors where the number shown needs context (e.g. an estimate).

    `history_available` tells us whether this user has ANY saved preference
    history at all. This is different from `matched_history` (whether THIS
    restaurant happens to match it). A brand-new user has no history to
    match against -- that's not a failure, it just doesn't apply yet.
    """
    breakdown = {}
    notes = {}

    # Cuisine Match (30) -- only scored when a cuisine was actually specified.
    # If nothing was detected, this factor is excluded rather than given a
    # free default, so it can't inflate the score for a search where the AI
    # genuinely doesn't know what cuisine the person wants.
    if cuisine:
        breakdown["Cuisine Match"] = (30, 30)
    else:
        breakdown["Cuisine Match"] = (0, 0)
        notes["Cuisine Match"] = "Not applicable — no cuisine was detected for this search"

    # Budget Match (25)
    price_level = restaurant.get("price_level", 2)
    allowed_prices = PRICE_LEVEL_BY_BUDGET.get(budget, [0, 1, 2, 3, 4])
    budget_ok = price_level in allowed_prices
    breakdown["Budget Match"] = (25, 25) if budget_ok else (10, 25)

    # Rating Quality (20) -- scaled straight from the restaurant's star rating
    rating = restaurant.get("rating", 0)
    breakdown["Rating Quality"] = (round((rating / 5) * 20), 20)

    # Distance (15) -- closer is better, full points under 1km, 0 points past 4km
    distance = restaurant.get("distance_km")
    if distance is None:
        dist_points = 10  # neutral estimate, not a penalty
        notes["Distance"] = "Estimated — exact distance wasn't available for this search"
    else:
        dist_points = max(0, min(15, round(15 - distance * 4)))
    breakdown["Distance"] = (dist_points, 15)

    # Popularity (5) -- simple proxy using rating, since we don't have review counts
    if rating >= 4.5:
        pop_points = 5
    elif rating >= 4.0:
        pop_points = 3
    else:
        pop_points = 1
    breakdown["Popularity"] = (pop_points, 5)

    # Preference History (5) -- bonus if this matches what the user usually picks.
    # FIX: if the user has no saved history at all, this factor doesn't apply --
    # excluded (0/0) instead of showing a flat 0/5 that looks like a broken feature.
    if not history_available:
        breakdown["Preference History"] = (0, 0)
        notes["Preference History"] = "Not applicable — you don't have any saved preferences yet"
    else:
        breakdown["Preference History"] = (5, 5) if matched_history else (0, 5)

    earned_total = sum(earned for earned, _ in breakdown.values())
    possible_total = sum(possible for _, possible in breakdown.values())
    total = round((earned_total / possible_total) * 100) if possible_total else 0

    return breakdown, total, notes


def rejection_reasons(restaurant, min_rating, budget):
    """Why a restaurant DIDN'T make the cut -- used for 'AI rejected' transparency."""
    allowed_prices = PRICE_LEVEL_BY_BUDGET.get(budget, [0, 1, 2, 3, 4])
    reasons = []
    if restaurant.get("rating", 0) < min_rating:
        reasons.append(f"Rating below your {min_rating}+ requirement")
    if restaurant.get("price_level", 2) not in allowed_prices:
        reasons.append(f"Doesn't fit your '{budget}' budget")
    return reasons or ["Didn't rank high enough overall"]