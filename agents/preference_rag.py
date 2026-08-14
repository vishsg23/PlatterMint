"""
preference_rag.py
------------------
Job: this is the "retrieval" step. When the Orchestrator decides the user's
query is too vague, this agent looks up that user's past preferences from
PostgreSQL and uses them to fill in the missing cuisine/budget/rating --
so a returning user never has to repeat themselves.

This is a simple, structured form of RAG (retrieval-augmented generation):
instead of embeddings + a vector DB, we retrieve structured rows for this
exact user. That's a perfectly legitimate and easy-to-explain RAG design
for structured personal history like this.
"""

from database import get_recent_preferences
from .state import AgentState


def preference_rag_node(state: AgentState) -> AgentState:
    user_id = state.get("user_id", "guest")
    history = get_recent_preferences(user_id)
    state["past_preferences"] = history

    if not history:
        # New user, nothing to retrieve -- just move on with defaults
        state.setdefault("cuisine", None)
        state.setdefault("budget", "medium")
        state.setdefault("min_rating", 3.5)
        state["welcome_message"] = None
        state["agent_trace"].append("🧠 Preference Agent → No stored preferences yet (new user)")
        return state

    # Use the most recent preference to fill in whatever the user didn't specify
    most_recent = history[0]
    filled_cuisine = state.get("cuisine") or most_recent.get("cuisine")
    filled_budget = state.get("budget") or most_recent.get("budget") or "medium"
    filled_rating = state.get("min_rating") or most_recent.get("min_rating") or 3.5

    state["cuisine"] = filled_cuisine
    state["budget"] = filled_budget
    state["min_rating"] = filled_rating

    # Build a friendly, visible "welcome back" message so this step isn't invisible to the user
    prefs_used = []
    if filled_cuisine:
        prefs_used.append(f"🍽️ {filled_cuisine.title()}")
    prefs_used.append(f"⭐ {filled_rating}+")
    prefs_used.append(f"💰 {filled_budget.title()} budget")

    state["welcome_message"] = (
        f"Welcome back! I remembered you usually prefer: {', '.join(prefs_used)}. "
        f"Searching using your saved preferences..."
    )
    state["agent_trace"].append(
        f"🧠 Preference Agent → Found past history, reused: {', '.join(prefs_used)}"
    )

    return state
