from database import get_recent_preferences
from .state import AgentState


def preference_rag_node(state: AgentState) -> AgentState:
    user_id = state.get("user_id", "guest")
    history = get_recent_preferences(user_id)
    state["past_preferences"] = history
    state["has_preference_history"] = bool(history)

   
    already_has_craving_signal = bool(state.get("cuisine") or state.get("food_craving"))

    if not history:
        state.setdefault("budget", "medium")
        state.setdefault("min_rating", 3.5)
        state["welcome_message"] = None
        state["agent_trace"].append("🧠 Preference Agent → No stored preferences yet (new user)")
        return state

    most_recent = history[0]


    if not already_has_craving_signal:
        state["cuisine"] = most_recent.get("cuisine")

    filled_budget = state.get("budget") or most_recent.get("budget") or "medium"
    filled_rating = state.get("min_rating") or most_recent.get("min_rating") or 3.5
    state["budget"] = filled_budget
    state["min_rating"] = filled_rating

    prefs_used = []
    if not already_has_craving_signal and state.get("cuisine"):
        prefs_used.append(f"🍽️ {state['cuisine'].title()}")
    prefs_used.append(f"⭐ {filled_rating}+")
    prefs_used.append(f"💰 {filled_budget.title()} budget")

    state["welcome_message"] = (
        f"Welcome back! I remembered you usually prefer: {', '.join(prefs_used)}. "
        f"Searching using your saved preferences..."
    )

    state["agent_trace"].append(
        f"🧠 Preference Agent → Found past history, reused: {', '.join(prefs_used)}"
        + (" (cuisine kept from THIS query, not overridden)" if already_has_craving_signal else "")
    )
    return state