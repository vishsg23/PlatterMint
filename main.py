r"""
main.py
-------
FastAPI backend. Exposes one endpoint: POST /recommend

Run it with:
    uvicorn main:app --reload

Then test with:
    curl -X POST http://127.0.0.1:8000/recommend \
         -H "Content-Type: application/json" \
         -d '{"user_id": "khushi", "user_query": "cheap pizza near me", "location": "Nashik"}'

FIX (#8): added an optional `pin` field. If the name has a PIN set, the
wrong (or missing) PIN now blocks the request instead of silently reading
or overwriting someone else's saved preferences.
"""

from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional

from database import init_db, check_user_pin
from graph import restaurant_graph

app = FastAPI(title="PlatterMint API")


class RecommendRequest(BaseModel):
    user_id: str
    user_query: str
    location: str
    ask_if_unsure: bool = True                 # HITL toggle: pause and ask instead of the AI auto-deciding
    relaxation_choice: Optional[str] = None     # set on the SECOND call, once the person has picked an option
    pin: Optional[str] = None                   # NEW: optional PIN protecting this name, see database.py


@app.on_event("startup")
def on_startup():
    # Creates the user_preferences and user_accounts tables if they don't exist yet
    init_db()


@app.post("/recommend")
def recommend(payload: RecommendRequest):
    """
    Runs the multi-agent graph. Possible outcomes:
    1. Auth failed -> the name is PIN-protected and the wrong/missing PIN
       was given. We stop here and don't touch that user's data at all.
    2. Normal case -> full recommendation, same as before.
    3. Human-in-the-loop case -> the Filter agent couldn't find a perfect
       match and ask_if_unsure=True, so the graph paused. We return the
       available options instead of a recommendation; the frontend shows
       them, and calls this endpoint AGAIN with relaxation_choice set to
       whichever the person picked.
    """
    ok, auth_message = check_user_pin(payload.user_id, payload.pin)
    if not ok:
        return {"auth_error": auth_message}

    result = restaurant_graph.invoke({
        "user_id": payload.user_id,
        "user_query": payload.user_query,
        "location": payload.location,
        "ask_if_unsure": payload.ask_if_unsure,
        "relaxation_choice": payload.relaxation_choice,
    })

    if result.get("needs_human_input"):
        return {
            "needs_human_input": True,
            "relaxation_options": result.get("relaxation_options"),
            "agent_trace": result.get("agent_trace"),
            "welcome_message": result.get("welcome_message"),
        }

    return {
        "needs_human_input": False,
        "welcome_message": result.get("welcome_message"),
        "intro_line": result.get("intro_line"),
        "top_pick": result.get("top_pick"),
        "alternatives": result.get("alternatives"),
        "more_options": result.get("more_options"),   # NEW: ranks 4-8, shown in a "see more" list
        "constraint_status": result.get("constraint_status"),
        "tradeoff_table": result.get("tradeoff_table"),
        "decision_dashboard": result.get("decision_dashboard"),
        "history_comparison": result.get("history_comparison"),
        "relaxed_by_human": result.get("relaxed_by_human", False),
        "agent_trace": result.get("agent_trace"),
        "final_answer": result.get("final_answer"),  # plain-text fallback for simple consumers
    }


@app.get("/")
def health_check():
    return {"status": "ok", "message": "Restaurant recommendation agent is running"}