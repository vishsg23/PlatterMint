# PlatterMint 🍽️

A multi-agent restaurant recommendation system built with **LangGraph**, **FastAPI**, and **Streamlit**.

## Why it's "agentic" (not just a pipeline)

The **Orchestrator** agent looks at the user's query and *decides* whether it
already has enough info (cuisine + budget) to search directly, or whether it
needs to pull the user's past preferences first. That branching decision is
what LangGraph's conditional edges are for — it's not a fixed 4-step chain.

The **Filter & Tradeoff** agent is the other reasoning step: if nothing
matches every filter, it decides which constraint to relax (rating, then
budget) and tells the user honestly what it changed and why.

## Architecture

```
        START
          |
    orchestrator            <- extracts cuisine/budget, decides route
       /      \
preference_rag  \           <- (only if query is vague) reads Postgres history
       \        /
        search                <- calls Google Places API
          |
   filter_tradeoff            <- filters, relaxes constraints if needed
          |
      recommend                <- writes final answer, saves preference to DB
          |
         END
```

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env      # then fill in your real keys (optional, see below)
```

**The app runs even with an empty `.env`** — it falls back to mock restaurant
data (no Google Maps key needed) and a template-based answer (no OpenAI key
needed), and uses a local SQLite file instead of Postgres. This makes it easy
to demo and test the agent logic before wiring up real credentials.

## Run it

Terminal 1 — backend:
```bash
uvicorn main:app --reload
```

Terminal 2 — frontend:
```bash
streamlit run streamlit_app.py
```

Or test the agent graph directly, no servers needed:
```bash
python graph.py
```

## File guide

| File | What it does |
|---|---|
| `agents/state.py` | The shared data structure passed between every agent |
| `agents/orchestrator.py` | Parses query, decides the route |
| `agents/preference_rag.py` | Retrieves user's past preferences from Postgres |
| `agents/search_agent.py` | Calls Google Places API (or mock data) |
| `agents/filter_agent.py` | Filters results, relaxes constraints if needed |
| `agents/recommendation_agent.py` | Writes final answer, saves preference |
| `graph.py` | Wires all agents into the LangGraph state graph |
| `database.py` | Postgres models + helper functions |
| `main.py` | FastAPI backend (`POST /recommend`) |
| `streamlit_app.py` | Simple frontend |

## Going further (good interview talking points)

- Swap the keyword-based cuisine/budget extraction in `orchestrator.py` for
  an LLM call for more natural parsing.
- Replace the structured-history RAG with a real vector store (e.g. pgvector)
  if you want to retrieve on free-text past reviews, not just structured fields.
- Add a `clarify` node: if the Filter agent has to relax more than one
  constraint, ask the user directly instead of guessing (human-in-the-loop).
