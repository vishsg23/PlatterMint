# PlatterMint 🍽️

A multi-agent restaurant recommendation system built with **LangGraph**, **FastAPI**, and **Streamlit**.

![Query form](assets/screenshots/query-form.png)
![Top pick result](assets/screenshots/top-pick.png)

## Why it's "agentic" (not just a pipeline)

The **Orchestrator** agent reads the user's free-text query and decides how
to proceed — cuisine, a looser food craving ("something sweet"), or, if
neither matches anything on a fixed list, the user's own words directly, so
nothing typed is ever silently dropped. It also detects a dietary need
(veg / non-veg) as its own signal, and decides whether it already has
enough to search with, or whether it needs to check the user's saved
history first. That branching decision is what LangGraph's conditional
edges are for — it's not a fixed chain.

The **Filter & Tradeoff** agent is the other real reasoning step. Diet is
treated as a hard constraint (a "pure veg" place is excluded outright from
a non-veg search). If nothing matches every filter, behavior depends on a
setting the user controls: the AI can relax constraints itself (rating,
then budget — genuinely opening to *any* price tier, not a narrow one) and
explain what it changed, or it can pause entirely and hand the decision
back to the user with real, live-counted options. If the user picks one,
that choice comes back as a fresh request that reruns the whole graph, with
the Filter agent applying the exact choice on that second pass.

The **Recommendation agent** turns a filtered list into an explained
decision — a 0–100 score per restaurant (excluding categories that
genuinely don't apply, like cuisine when none was detected, rather than
handing out free credit), a deterministic tie-breaker (rating, then price,
then name — never just API response order), and a confidence percentage
driven by how close the race was against the runner-up, not a copy of the
score itself.

## Architecture

```
        START
          |
    orchestrator            <- extracts cuisine / craving / diet / budget, decides route
       /      \
preference_rag  \           <- (only if query is vague) reads Postgres history;
       \        \              never overrides a craving already given this query
        \______ search        <- calls Google Places API, retries broader phrasing
                    |             if the specific search finds nothing, de-dupes results
             filter_tradeoff   <- hard diet filter + rating/budget; relaxes or pauses
                /        \
    (needs human input?)  \
          |                 \
         END              recommend    <- scores, breaks ties, sets confidence,
    (pause + ask)             |            saves preference only on a real match
                             END
```

See `assets/architecture/` for a fuller diagram, including the filter
agent's internal decision logic (strict match vs. auto-relax vs. pause).

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env      # then fill in your real keys (optional, see below)
```

**The app runs even with an empty `.env`** — it falls back to mock
restaurant data (no Google Maps key needed) and a template-based answer (no
OpenAI key needed), and uses a local SQLite file instead of Postgres. This
makes it easy to demo and test the agent logic before wiring up real
credentials. Set `ENVIRONMENT=production` if deploying for real — this
makes a missing `DATABASE_URL` a hard startup error instead of a silent
fallback to a file that resets on every deploy.

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
| `agents/orchestrator.py` | Parses query — cuisine, craving fallback, diet, budget — and decides the route |
| `agents/preference_rag.py` | Retrieves past preferences from Postgres; fills gaps only, never overrides a craving given this query |
| `agents/search_agent.py` | Calls Google Places API, retries with broader real phrasing if needed, de-duplicates results |
| `agents/filter_agent.py` | Hard diet filter + rating/budget; auto-relaxes or pauses for human input; applies the user's choice on resume |
| `agents/scoring.py` | The 0–100 scoring logic — weighted categories, excludes ones that don't apply rather than faking credit |
| `agents/recommendation_agent.py` | Ranks restaurants, breaks ties deterministically, computes confidence, saves preference only on success |
| `graph.py` | Wires all agents into the LangGraph state graph |
| `database.py` | Postgres models + helper functions; refuses a silent SQLite fallback in production |
| `main.py` | FastAPI backend (`POST /recommend`) |
| `streamlit_app.py` | Frontend — form, results, and the human-in-the-loop prompt |

## Known limitations

- **Diet detection is a name-text heuristic.** Google Places has no
  structured veg/non-veg field, so this relies on restaurants mentioning
  "veg"/"vegan"/"vegetarian" in their own name. It can't catch a
  vegetarian-only place that doesn't advertise it in the name.
- **No authentication.** `user_id` is a plain name with no login — fine for
  a personal/demo project, not for anything with real user accounts.
- **Distance is often an estimate**, not a measurement — Google's basic
  Text Search doesn't return coordinates, so this is clearly labeled as an
  estimate in the score breakdown rather than presented as precise.

## Going further (good interview talking points)

- Swap the keyword-based cuisine/craving/diet extraction in
  `orchestrator.py` for an LLM call for more natural parsing.
- Use the Places Details API's menu text for real diet detection instead
  of a name-text heuristic.
- Switch to Nearby Search with lat/lng so distance is a real measurement,
  not an estimate.
- Replace the structured-history RAG with a real vector store (e.g.
  pgvector) if you want to retrieve on free-text past reviews, not just
  structured fields.
- Add real authentication if this ever needs to support actual user
  accounts rather than plain names.
