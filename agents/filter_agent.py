import re
from .state import AgentState
from .scoring import PRICE_LEVEL_BY_BUDGET, rejection_reasons

_NON_VEG_OVERRIDE = re.compile(r"non[\s\-]?veg", re.IGNORECASE)
_VEG_ONLY_PATTERN = re.compile(r"\b(vegan|vegetarian|veggie|veg)\b", re.IGNORECASE)


def _diet_ok(restaurant, diet):
    if diet != "non-veg":
        return True
    name = restaurant.get("name") or ""
    if _NON_VEG_OVERRIDE.search(name):
        return True  # explicitly a combo place, e.g. "Veg & Non-Veg Corner"
    return not _VEG_ONLY_PATTERN.search(name)


def _apply_filters(results, min_rating, budget, diet=None):
    allowed_prices = PRICE_LEVEL_BY_BUDGET.get(budget, [0, 1, 2, 3, 4])
    return [
        r for r in results
        if r.get("rating", 0) >= (min_rating or 0)
        and r.get("price_level", 2) in allowed_prices
        and _diet_ok(r, diet)
    ]


def _finish(state, filtered, applied_rating, applied_budget, relaxed, status, trace_msg, relaxed_by_human=False):
    """Shared wrap-up once we have a final filtered list -- rejection reasons + trade-off table."""
    diet = state.get("diet")
    all_results = state.get("search_results", [])
    rejected = [
        {"name": r.get("name"), "reasons": rejection_reasons(r, applied_rating, applied_budget)}
        for r in all_results if r not in filtered
    ]

    state["filtered_results"] = filtered
    state["rejected_results"] = rejected
    state["applied_min_rating"] = applied_rating
    state["applied_budget"] = applied_budget
    state["relaxed_constraint"] = relaxed
    state["relaxed_by_human"] = relaxed_by_human
    state["constraint_status"] = status

    state["needs_human_input"] = False

    original_rating = state.get("min_rating") or 3.5
    original_budget = state.get("budget") or "medium"
    explicitly_asked_rating = state.get("original_min_rating") is not None

    tradeoff_table = [
        {"factor": "Cuisine", "requested": (state.get("cuisine") or "any").title(), "kept": True},
        {"factor": "Budget", "requested": original_budget.title(), "kept": applied_budget == original_budget},
        {
            "factor": "Rating",
            "requested": f"{original_rating}+",
            "kept": applied_rating == original_rating,
            "explicitly_asked": explicitly_asked_rating,
        },
    ]
    if diet:
        tradeoff_table.append({"factor": "Diet", "requested": diet.title(), "kept": True})
    state["tradeoff_table"] = tradeoff_table

    state["agent_trace"].append(
        f"⚖️ Filter Agent → {trace_msg} | Rejected {len(rejected)}, kept {len(filtered)}"
    )
    return state


def _build_relaxation_options(results, original_rating, original_budget, diet=None):
    """Previews each possible relaxation with a live result count, for the person to choose from."""
    relaxed_rating = round(original_rating - 1.0, 1)
    options = []

    rating_count = len(_apply_filters(results, relaxed_rating, original_budget, diet))
    if rating_count > 0:
        options.append({
            "key": "relax_rating",
            "label": f"Show lower-rated options ({original_rating}+ → {relaxed_rating}+ stars)",
            "preview_count": rating_count,
        })

    budget_count = len(_apply_filters(results, original_rating, "any", diet))
    if budget_count > 0:
        options.append({
            "key": "relax_budget",
            "label": f"Show any price ('{original_budget}' → any price)",
            "preview_count": budget_count,
        })

    # FIX (round 5): only offer "show everything" if that would actually
    # return something. With the empty-results short-circuit above, this
    # mainly guards the case where results exist but ALL of them fail the
    # diet filter (e.g. only vegan places nearby, but a non-veg diet was
    # requested) -- offering a button that provably shows "0 results" is a
    # dead end, not a real choice.
    show_all_count = len(_apply_filters(results, 0, "any", diet))
    if show_all_count > 0:
        options.append({
            "key": "show_all",
            "label": "Just show me everything nearby, ignore rating & budget",
            "preview_count": show_all_count,
        })

    return options


def _apply_human_choice(state, results, original_rating, original_budget, choice):
    """The person already picked -- apply EXACTLY that choice, no more guessing."""
    diet = state.get("diet")
    status = {
        "cuisine": f"✅ Matched: {state['cuisine'].title()}" if state.get("cuisine") else "➖ Not specified",
        "budget": f"✅ Kept: {original_budget.title()}",
        "rating": f"✅ Kept: {original_rating}+ stars",
    }

    if choice == "relax_rating":
        relaxed_rating = round(original_rating - 1.0, 1)
        filtered = _apply_filters(results, relaxed_rating, original_budget, diet)
        status["rating"] = f"🙋 You chose to relax: {original_rating} → {relaxed_rating}+ stars"
        return _finish(state, filtered, relaxed_rating, original_budget, "rating", status,
                        "Person chose to relax rating", relaxed_by_human=True)

    if choice == "relax_budget":
        filtered = _apply_filters(results, original_rating, "any", diet)
        status["budget"] = f"🙋 You chose to relax: {original_budget.title()} → Any price"
        return _finish(state, filtered, original_rating, "any", "budget", status,
                        "Person chose to relax budget", relaxed_by_human=True)

    
    status["rating"] = "🙋 You chose to ignore rating"
    status["budget"] = "🙋 You chose to ignore budget"
    filtered = _apply_filters(results, 0, "any", diet)
    return _finish(state, filtered, 0, "any", "rating and budget", status,
                    "Person chose to see everything nearby", relaxed_by_human=True)


def filter_tradeoff_node(state: AgentState) -> AgentState:
    results = state.get("search_results", [])
    original_rating = state.get("min_rating") or 3.5
    original_budget = state.get("budget") or "medium"
    cuisine = state.get("cuisine")
    diet = state.get("diet")

    status = {
        "cuisine": f"✅ Matched: {cuisine.title()}" if cuisine else "➖ Not specified",
        "budget": f"✅ Kept: {original_budget.title()}",
        "rating": f"✅ Kept: {original_rating}+ stars",
    }
    if diet:
        status["diet"] = f"✅ Matched: {diet.title()}"


    if not results:
        state["agent_trace"].append(
            "⚖️Filter Agent → No restaurants were found at all for this search "
            "(not a filtering issue -- nothing exists to relax against)"
        )
        return _finish(state, [], original_rating, original_budget, None, status,
                        "No restaurants found near this location for this search")

   
    filtered = _apply_filters(results, original_rating, original_budget, diet)
    if filtered:
        return _finish(state, filtered, original_rating, original_budget, None, status,
                        "Everything matched, no tradeoffs needed")

    if state.get("relaxation_choice"):
        return _apply_human_choice(state, results, original_rating, original_budget, state["relaxation_choice"])

    # --- human-in-the-loop mode: PAUSE and ask instead of deciding ourselves ---
    if state.get("ask_if_unsure"):
        options = _build_relaxation_options(results, original_rating, original_budget, diet)
        state["needs_human_input"] = True
        state["relaxation_options"] = options
        state["agent_trace"].append(
            f"🙋 Filter Agent → Nothing matched all constraints. Pausing to ask the user "
            f"({len(options)} options offered) instead of deciding automatically."
        )
        return state

    # --- default AI-autonomy mode: same auto-cascade as before (diet is NEVER auto-relaxed) ---
    relaxed_rating = round(original_rating - 1.0, 1)
    filtered = _apply_filters(results, relaxed_rating, original_budget, diet)
    if filtered:
        status["rating"] = f"❌ Relaxed: {original_rating} → {relaxed_rating}+ stars"
        return _finish(state, filtered, relaxed_rating, original_budget, "rating", status,
                        f"Nothing matched at {original_rating}+ stars, relaxed to {relaxed_rating}+")

    filtered = _apply_filters(results, original_rating, "any", diet)
    if filtered:
        status["budget"] = f"❌ Relaxed: {original_budget.title()} → Any price"
        return _finish(state, filtered, original_rating, "any", "budget", status,
                        f"Nothing matched within '{original_budget}' budget, opened up to any price")

    status["rating"] = f"❌ Relaxed: {original_rating} → any rating"
    status["budget"] = f"❌ Relaxed: {original_budget.title()} → any price"
    filtered = _apply_filters(results, 0, "any", diet)
    return _finish(state, filtered, 0, "any", "rating and budget", status,
                    "Nothing matched even after relaxing rating, opened budget too")