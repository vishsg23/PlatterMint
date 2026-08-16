PRICE_LEVEL_BY_BUDGET = {
    "low": [0, 1],
    "medium": [1, 2],
    "high": [2, 3, 4],
    "any": [0, 1, 2, 3, 4],
}


def score_restaurant(restaurant, cuisine, budget, matched_history=False, history_available=True):
    breakdown = {}
    notes = {}


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

    
    if rating >= 4.5:
        pop_points = 5
    elif rating >= 4.0:
        pop_points = 3
    else:
        pop_points = 1
    breakdown["Popularity"] = (pop_points, 5)


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