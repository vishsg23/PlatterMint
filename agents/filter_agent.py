"""
filter_agent.py
----------------
Job: filter results by rating and budget, with FULL transparency about any
tradeoffs -- and now, real human-in-the-loop (HITL) support.

Two modes, controlled by `ask_if_unsure` in the state:

  ask_if_unsure = False (default AI autonomy):
      Same as before -- if nothing matches, the agent decides on its own
      which constraint to relax (rating first, then budget) and explains
      why afterwards.

  ask_if_unsure = True (human-in-the-loop):
      If nothing matches, the agent does NOT decide by itself. Instead it
      sets needs_human_input = True and lists the possible relaxation
      options with a live preview count for each ("12 results if we relax
      rating" vs "5 results if we relax budget"). The LangGraph graph then
      stops there (see graph.py's conditional edge) and returns control to
      the person. Once they pick an option, the SAME query is sent again
      with relaxation_choice set, and this agent applies exactly that
      choice -- no guessing on the AI's part.

FIX (2026-08): the "relax budget" option used to silently map to the
"high" price tier ([2,3,4]) no matter what, while its label said
"-> any price". That meant a person on a "low" budget who relaxed would
never see cheap places again, despite the option's own wording. There's
now a real "any" tier (all price levels) and the label matches the
behavior in both the HITL path and the AI-autonomy auto-cascade path.
"""

from .state import AgentState
from .scoring import PRICE_LEVEL_BY_BUDGET, rejection_reasons


def _apply_filters(results, min_rating, budget):
    allowed_prices = PRICE_LEVEL_BY_BUDGET.get(budget, [0, 1, 2, 3, 4])
    return [
        r for r in results
        if r.get("rating", 0) >= (min_rating or 0)
        and r.get("price_level", 2) in allowed_prices
    ]


def _finish(state, filtered, applied_rating, applied_budget, relaxed, status, trace_msg, relaxed_by_human=False):
    """Shared wrap-up once we have a final filtered list -- rejection reasons + trade-off table."""
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

    # FIX (#6): original_min_rating was being set by the orchestrator but
    # never actually used anywhere. It holds what the person EXPLICITLY
    # typed (e.g. "best" -> 4.0), before any default or preference-history
    # fill-in happened. We now use it to say whether the "requested" rating
    # in the trade-off table was a real ask or just a default/fallback.
    explicitly_asked_rating = state.get("original_min_rating") is not None

    state["tradeoff_table"] = [
        {"factor": "Cuisine", "requested": (state.get("cuisine") or "any").title(), "kept": True},
        {"factor": "Budget", "requested": original_budget.title(), "kept": applied_budget == original_budget},
        {
            "factor": "Rating",
            "requested": f"{original_rating}+",
            "kept": applied_rating == original_rating,
            "explicitly_asked": explicitly_asked_rating,  # False = this was a default, not something you asked for
        },
    ]

    state["agent_trace"].append(
        f"⚖️ Filter Agent → {trace_msg} | Rejected {len(rejected)}, kept {len(filtered)}"
    )
    return state


def _build_relaxation_options(results, original_rating, original_budget):
    """Previews each possible relaxation with a live result count, for the person to choose from."""
    relaxed_rating = round(original_rating - 1.0, 1)
    options = []

    rating_count = len(_apply_filters(results, relaxed_rating, original_budget))
    if rating_count > 0:
        options.append({
            "key": "relax_rating",
            "label": f"Show lower-rated options ({original_rating}+ → {relaxed_rating}+ stars)",
            "preview_count": rating_count,
        })

    # FIX: "any price" now genuinely means all price levels, not just "high"
    budget_count = len(_apply_filters(results, original_rating, "any"))
    if budget_count > 0:
        options.append({
            "key": "relax_budget",
            "label": f"Show any price ('{original_budget}' → any price)",
            "preview_count": budget_count,
        })

    options.append({
        "key": "show_all",
        "label": "Just show me everything nearby, ignore rating & budget",
        "preview_count": len(results),
    })

    return options


def _apply_human_choice(state, results, original_rating, original_budget, choice):
    """The person already picked -- apply EXACTLY that choice, no more guessing."""
    status = {
        "cuisine": f"✅ Matched: {state['cuisine'].title()}" if state.get("cuisine") else "➖ Not specified",
        "budget": f"✅ Kept: {original_budget.title()}",
        "rating": f"✅ Kept: {original_rating}+ stars",
    }

    if choice == "relax_rating":
        relaxed_rating = round(original_rating - 1.0, 1)
        filtered = _apply_filters(results, relaxed_rating, original_budget)
        status["rating"] = f"🙋 You chose to relax: {original_rating} → {relaxed_rating}+ stars"
        return _finish(state, filtered, relaxed_rating, original_budget, "rating", status,
                        "Person chose to relax rating", relaxed_by_human=True)

    if choice == "relax_budget":
        # FIX: was "high" only; now genuinely "any" price level
        filtered = _apply_filters(results, original_rating, "any")
        status["budget"] = f"🙋 You chose to relax: {original_budget.title()} → Any price"
        return _finish(state, filtered, original_rating, "any", "budget", status,
                        "Person chose to relax budget", relaxed_by_human=True)

    # "show_all" or anything unrecognized -> fall back to showing everything found
    status["rating"] = "🙋 You chose to ignore rating"
    status["budget"] = "🙋 You chose to ignore budget"
    return _finish(state, results, 0, "any", "rating and budget", status,
                    "Person chose to see everything nearby", relaxed_by_human=True)


def filter_tradeoff_node(state: AgentState) -> AgentState:
    results = state.get("search_results", [])
    original_rating = state.get("min_rating") or 3.5
    original_budget = state.get("budget") or "medium"
    cuisine = state.get("cuisine")

    status = {
        "cuisine": f"✅ Matched: {cuisine.title()}" if cuisine else "➖ Not specified",
        "budget": f"✅ Kept: {original_budget.title()}",
        "rating": f"✅ Kept: {original_rating}+ stars",
    }

    # --- attempt 1: strict, both constraints applied -- always tried first, HITL or not ---
    filtered = _apply_filters(results, original_rating, original_budget)
    if filtered:
        return _finish(state, filtered, original_rating, original_budget, None, status,
                        "Everything matched, no tradeoffs needed")

    # --- nothing matched strictly. resuming after a human choice? apply it directly ---
    if state.get("relaxation_choice"):
        return _apply_human_choice(state, results, original_rating, original_budget, state["relaxation_choice"])

    # --- human-in-the-loop mode: PAUSE and ask instead of deciding ourselves ---
    if state.get("ask_if_unsure"):
        options = _build_relaxation_options(results, original_rating, original_budget)
        state["needs_human_input"] = True
        state["relaxation_options"] = options
        state["agent_trace"].append(
            f"🙋 Filter Agent → Nothing matched all constraints. Pausing to ask the user "
            f"({len(options)} options offered) instead of deciding automatically."
        )
        return state

    # --- default AI-autonomy mode: same auto-cascade as before ---
    relaxed_rating = round(original_rating - 1.0, 1)
    filtered = _apply_filters(results, relaxed_rating, original_budget)
    if filtered:
        status["rating"] = f"❌ Relaxed: {original_rating} → {relaxed_rating}+ stars"
        return _finish(state, filtered, relaxed_rating, original_budget, "rating", status,
                        f"Nothing matched at {original_rating}+ stars, relaxed to {relaxed_rating}+")

    # FIX: was "high" only; now genuinely "any" price level, and the trace/status say so
    filtered = _apply_filters(results, original_rating, "any")
    if filtered:
        status["budget"] = f"❌ Relaxed: {original_budget.title()} → Any price"
        return _finish(state, filtered, original_rating, "any", "budget", status,
                        f"Nothing matched within '{original_budget}' budget, opened up to any price")

    status["rating"] = f"❌ Relaxed: {original_rating} → any rating"
    status["budget"] = f"❌ Relaxed: {original_budget.title()} → any price"
    return _finish(state, results, 0, "any", "rating and budget", status,
                    "Nothing matched even after relaxing rating, opened budget too")