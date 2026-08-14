r"""
graph.py
--------
This is where all the agents get connected into one graph.

Flow:

              START
                |
          orchestrator  <-- decides the route (this is the "agentic" part)
             /      \
   preference_rag    \
             \        \
              \_______ search
                          |
                  filter_tradeoff
                     /        \
        (needs human input?)   \
              |                  \
             END              recommend
        (pause + ask)              |
                                   END

When filter_tradeoff can't find a perfect match AND human-in-the-loop mode
is on (ask_if_unsure=True), the graph stops right there and hands control
back to the person instead of guessing. Once they pick an option, the same
query runs again with their choice attached, and this time filter_tradeoff
applies it directly and the graph continues on to recommend as normal.

Run `python graph.py` directly to test the whole pipeline from the terminal
without needing FastAPI or Streamlit running.
"""

from langgraph.graph import StateGraph, END

from agents.state import AgentState
from agents.orchestrator import orchestrator_node, route_after_orchestrator
from agents.preference_rag import preference_rag_node
from agents.search_agent import search_restaurants_node
from agents.filter_agent import filter_tradeoff_node
from agents.recommendation_agent import recommend_node


def route_after_filter(state: AgentState) -> str:
    """If the Filter agent is pausing for human input, stop here instead of recommending."""
    return END if state.get("needs_human_input") else "recommend"


def build_graph():
    graph = StateGraph(AgentState)

    # 1. register every agent as a node
    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("preference_rag", preference_rag_node)
    graph.add_node("search", search_restaurants_node)
    graph.add_node("filter_tradeoff", filter_tradeoff_node)
    graph.add_node("recommend", recommend_node)

    # 2. set the entry point
    graph.set_entry_point("orchestrator")

    # 3. branching decision #1: does this query need preference history first?
    graph.add_conditional_edges(
        "orchestrator",
        route_after_orchestrator,
        {"preference_rag": "preference_rag", "search": "search"},
    )
    graph.add_edge("preference_rag", "search")
    graph.add_edge("search", "filter_tradeoff")

    # 4. branching decision #2: pause for a human, or continue automatically?
    graph.add_conditional_edges(
        "filter_tradeoff",
        route_after_filter,
        {"recommend": "recommend", END: END},
    )
    graph.add_edge("recommend", END)

    return graph.compile()


# Compiled once and reused by both FastAPI and the manual test below
restaurant_graph = build_graph()


if __name__ == "__main__":
    from database import init_db
    init_db()

    test_input = {
        "user_id": "khushi_test",
        "user_query": "find me the best cheap pizza near me",
        "location": "Nashik",
    }

    result = restaurant_graph.invoke(test_input)

    print("\n--- FINAL ANSWER ---")
    print(result["final_answer"])
    print("\n--- DEBUG STATE ---")
    print({k: v for k, v in result.items() if k != "final_answer"})
