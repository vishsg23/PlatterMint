import os
from .state import AgentState
from .scoring import score_restaurant, PRICE_LEVEL_BY_BUDGET
from database import save_preference
from utils import price_display, google_maps_search_url, google_maps_directions_url

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

REASON_LABELS = {
    "Cuisine Match": "Perfect match for your craving",
    "Budget Match": "Fits comfortably within your budget",
    "Rating Quality": "Excellent rating quality",
    "Distance": "Very close to your location",
    "Popularity": "Popular and highly reviewed",
    "Preference History": "Matches what you've liked before",
}


def _build_reasons(breakdown, relaxed_constraint):
    """Turn a score breakdown into plain-English reasons -- only factors that
    both applied (possible > 0) and scored full marks."""
    reasons = [
        REASON_LABELS[factor]
        for factor, (earned, possible) in breakdown.items()
        if possible and earned == possible
    ]
    if not reasons:
        reasons.append("Best overall balance of your criteria")
    if relaxed_constraint:
        reasons.append(f"Best available after relaxing the {relaxed_constraint} requirement")
    return reasons


def _enrich_restaurant(restaurant, breakdown, total_score, location, notes=None):
    """Attaches score, readable price, caveats, and free Maps links to a restaurant dict."""
    notes = notes or {}
    return {
        "name": restaurant.get("name"),
        "rating": restaurant.get("rating"),
        "price_level": restaurant.get("price_level"),
        "price_display": price_display(restaurant.get("price_level")),
        "distance_km": restaurant.get("distance_km"),
        "match_score": total_score,
        "score_breakdown": [
            {
                "factor": factor,
                "earned": earned,
                "possible": possible,
                "note": notes.get(factor),  # e.g. "Estimated — not measured for this search"
            }
            for factor, (earned, possible) in breakdown.items()
            if possible  # don't show factors that didn't apply at all (0/0)
        ],
        "maps_url": google_maps_search_url(restaurant.get("name"), location),
        "directions_url": google_maps_directions_url(restaurant.get("name"), location),
    }


def _tie_break_key(scored_entry):
    restaurant, breakdown, total = scored_entry
    rating = restaurant.get("rating") or 0
    price_level = restaurant.get("price_level")
    price_level = price_level if price_level is not None else 2  # neutral default if unknown
    name = (restaurant.get("name") or "").lower()
    return (total, rating, -price_level, name)


def _baseline_top_pick(search_results):
    allowed = PRICE_LEVEL_BY_BUDGET.get("medium", [0, 1, 2, 3, 4])
    baseline_matches = [
        r for r in search_results
        if r.get("rating", 0) >= 3.5 and r.get("price_level", 2) in allowed
    ]
    if not baseline_matches:
        return None
    return max(baseline_matches, key=lambda r: r.get("rating", 0))


def _build_confidence(scored, top_breakdown, relaxed_constraint):
    top_score = scored[0][2]
    runner_up_score = scored[1][2] if len(scored) > 1 else None

    confidence = 50  # baseline: "we found a legitimate match at all"

    if runner_up_score is not None:
        gap = top_score - runner_up_score
        if gap >= 15:
            confidence += 30
        elif gap >= 8:
            confidence += 20
        elif gap >= 3:
            confidence += 10
        else:
            confidence += 2  # near-tie -- genuinely less sure this is THE best
    else:
        confidence += 10  # only one candidate at all, nothing to compare against

    if len(scored) >= 5:
        confidence += 10
    elif len(scored) >= 3:
        confidence += 5

    if relaxed_constraint:
        confidence -= 15  # had to give up something the person actually asked for

    confidence = min(95, max(35, confidence))


    reasons = []
    if runner_up_score is not None:
        gap = top_score - runner_up_score
        if gap >= 8:
            reasons.append("Clearly ahead of the next-best option")
        elif gap < 3:
            reasons.append("Very close to the next-best option — worth checking both")
    if len(scored) >= 3:
        reasons.append("Plenty of matching restaurants")
    if relaxed_constraint:
        reasons.append(f"Had to relax {relaxed_constraint} to find a match")

    return confidence, reasons


def _rule_based_recommendation(state: AgentState):
    filtered = state.get("filtered_results", [])
    cuisine = state.get("cuisine")
    budget = state.get("applied_budget") or state.get("budget") or "medium"
    relaxed = state.get("relaxed_constraint")
    location = state.get("location", "")
    used_history = bool(state.get("welcome_message"))
    history_available = state.get("has_preference_history", False)

    if not filtered:
        return None, [], "I couldn't find any restaurants matching your search --- try a different area or craving.", None, []

    # score every candidate, keep the breakdown + notes for the winner
    scored = []
    breakdown_notes = {}
    for r in filtered:
        breakdown, total, notes = score_restaurant(
            r, cuisine, budget, matched_history=used_history, history_available=history_available
        )
        scored.append((r, breakdown, total))
        breakdown_notes[id(r)] = notes

    scored.sort(key=_tie_break_key, reverse=True)
    top_r, top_breakdown, top_score = scored[0]
    top_notes = breakdown_notes[id(top_r)]

    confidence, confidence_reasons = _build_confidence(scored, top_breakdown, relaxed)

    top_pick = _enrich_restaurant(top_r, top_breakdown, top_score, location, notes=top_notes)
    top_pick["reasons"] = _build_reasons(top_breakdown, relaxed)
    top_pick["confidence"] = confidence
    top_pick["confidence_reasons"] = confidence_reasons

    alternatives = []
    for alt_r, alt_breakdown, alt_score in scored[1:3]:
        alt_notes = breakdown_notes[id(alt_r)]
        alt = _enrich_restaurant(alt_r, alt_breakdown, alt_score, location, notes=alt_notes)
        gap = top_score - alt_score
        if alt_r.get("distance_km") is not None and top_r.get("distance_km") is not None \
                and alt_r["distance_km"] < top_r["distance_km"]:
            alt["reason"] = "Closer to you, but scored slightly lower overall"
        elif gap <= 5:
            alt["reason"] = "Nearly as good, worth considering"
        else:
            alt["reason"] = "Solid backup option"
        alternatives.append(alt)


    more_options = []
    for r, breakdown, total in scored[3:8]:
        more_options.append({
            "name": r.get("name"),
            "match_score": total,
            "rating": r.get("rating"),
            "price_display": price_display(r.get("price_level")),
            "maps_url": google_maps_search_url(r.get("name"), location),
        })

    # history impact comparison
    history_comparison = None
    if used_history:
        baseline = _baseline_top_pick(state.get("search_results", []))
        if baseline and baseline.get("name") != top_r.get("name"):
            history_comparison = {
                "without_history": {
                    "name": baseline.get("name"),
                    "price_display": price_display(baseline.get("price_level")),
                },
                "with_history": {
                    "name": top_r.get("name"),
                    "price_display": price_display(top_r.get("price_level")),
                },
                "reason": f"Based on your saved preferences, I prioritized a {budget}-budget option that better fits what you usually pick.",
            }

    # one-line plain-English summary
    intro_bits = []
    food_craving = state.get("food_craving")
    if cuisine:
        intro_bits.append(f"looked for {cuisine} restaurants near you")
    elif food_craving:
        intro_bits.append(f"looked for {food_craving} near you")
    else:
        intro_bits.append("couldn't detect a specific cuisine, so I looked for highly-rated options nearby")
    if state.get("search_broadened"):
        # NEW: transparency for when the specific search term found nothing
        # and we had to fall back to a broader real search instead.
        intro_bits.append("had to broaden the search since that specific craving didn't turn up results nearby")
    if relaxed:
        intro_bits.append(f"had to relax the {relaxed} requirement to find good matches")
    intro_line = "I " + ", and ".join(intro_bits) + "."

    return top_pick, alternatives, intro_line, history_comparison, more_options


def _llm_reword(top_pick, user_query):
    """Optional: ask an LLM to reword the reasons more naturally. Purely cosmetic, scores stay rule-based."""
    from langchain_openai import ChatOpenAI
    import json

    llm = ChatOpenAI(model="gpt-4o-mini", api_key=OPENAI_API_KEY, temperature=0.4)
    prompt = f"""
Rewrite these restaurant recommendation reasons to sound warmer and more natural,
as 2-3 short phrases. Keep them factually the same, just less robotic.

Reasons: {json.dumps(top_pick['reasons'])}
User asked: "{user_query}"

Return ONLY a JSON list of short strings, nothing else.
"""
    try:
        response = llm.invoke(prompt)
        reworded = json.loads(response.content)
        if isinstance(reworded, list) and reworded:
            top_pick["reasons"] = reworded
    except Exception as e:
        print(f"[recommendation_agent] LLM rewording failed, keeping rule-based reasons: {e}")


def recommend_node(state: AgentState) -> AgentState:
    top_pick, alternatives, intro_line, history_comparison, more_options = _rule_based_recommendation(state)

    if top_pick and OPENAI_API_KEY:
        _llm_reword(top_pick, state.get("user_query", ""))

    state["top_pick"] = top_pick
    state["alternatives"] = alternatives
    state["more_options"] = more_options
    state["intro_line"] = intro_line
    state["history_comparison"] = history_comparison

    # Build the "AI Decision Dashboard" summary block
    rejected = state.get("rejected_results", [])
    state["decision_dashboard"] = {
        "user_asked": state.get("user_query"),
        "remembered": state.get("welcome_message") is not None,
        "found_count": len(state.get("search_results", [])),
        "rejected_count": len(rejected),
        "rejected_examples": rejected[:3],
        "compared_count": len(state.get("filtered_results", [])),
        "winner": top_pick.get("name") if top_pick else None,
        "score": top_pick.get("match_score") if top_pick else None,
        "confidence": top_pick.get("confidence") if top_pick else None,
    }

    state["final_answer"] = (
        f"{intro_line} My top pick: {top_pick['name']} ({top_pick['match_score']}/100)."
        if top_pick else intro_line
    )

    picked_count = 1 + len(alternatives) if top_pick else 0
    state["agent_trace"].append(
        f"🏆 Recommendation Agent → Compared {len(state.get('filtered_results', []))}, "
        f"selected top {picked_count}, winner confidence {top_pick['confidence'] if top_pick else 0}%"
    )

    
    if top_pick:
        save_preference(
            user_id=state.get("user_id", "guest"),
            cuisine=state.get("cuisine"),
            budget=state.get("budget"),
            min_rating=state.get("min_rating"),
        )

    return state