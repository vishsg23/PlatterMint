from typing import TypedDict, List, Dict, Optional


class AgentState(TypedDict, total=False):
    # ---- input from the user ----
    user_id: str
    user_query: str
    location: str                       # e.g. "Nashik" or "19.99,73.78"
    ask_if_unsure: bool                 # HITL toggle: pause and ask instead of auto-relaxing?
    relaxation_choice: Optional[str]    # set on the SECOND call, once the user has picked an option

    # ---- filled in by the Orchestrator ----
    cuisine: Optional[str]
    food_craving: Optional[str]         # fallback search term when no strict cuisine was detected
    diet: Optional[str]                 # NEW: "veg" / "non-veg" / None, detected from the query
    original_min_rating: Optional[float]  # what the user actually asked for (now used in the trade-off table)
    budget: Optional[str]               # "low" / "medium" / "high"
    min_rating: Optional[float]
    needs_preference_lookup: bool

    # ---- filled in by the Preference RAG agent ----
    past_preferences: List[Dict]
    has_preference_history: bool        # NEW: True only if this user has ANY saved history at all
    welcome_message: Optional[str]      # "Welcome back! I remembered you usually prefer..."

    # ---- filled in by the Search agent ----
    search_results: List[Dict]
    search_broadened: bool              # NEW: True if the specific search term found nothing and we broadened it

    # ---- filled in by the Filter & Tradeoff agent ----
    filtered_results: List[Dict]
    rejected_results: List[Dict]        # restaurants that didn't make the cut, each with "reasons"
    applied_min_rating: float           # the rating threshold actually used (after any relaxing)
    applied_budget: str                 # the budget actually used (after any relaxing)
    relaxed_constraint: Optional[str]   # which filter got relaxed, if any
    relaxed_by_human: bool              # True if a PERSON picked the relaxation, not the AI
    constraint_status: Dict[str, str]   # e.g. {"cuisine": "kept", "rating": "relaxed from 4.8 to 3.8"}
    tradeoff_table: List[Dict]          # [{"factor": "Rating", "requested": "...", "reality": "✔/✘"}]
    needs_human_input: bool             # True = graph should PAUSE here and ask the person
    relaxation_options: List[Dict]      # the choices offered to the person when paused

    # ---- filled in by the Recommendation agent ----
    final_answer: str
    top_pick: Optional[Dict]            # the #1 restaurant: score breakdown, reasons, confidence, links
    alternatives: List[Dict]            # 2nd/3rd choices, each with their own score + short reason
    more_options: List[Dict]            # NEW: ranks 4-8, simple entries for a "see more" list
    intro_line: str                     # one sentence summarizing what the system understood/did
    decision_dashboard: Dict            # summary block: found/rejected/compared counts, winner, confidence
    history_comparison: Optional[Dict]  # "without your history" vs "using your history" top pick

    # ---- visible trail of what each agent did, shown in the UI ----
    agent_trace: List[str]