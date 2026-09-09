"""LangGraph → Nebelus, end to end.

Take a LangGraph ``StateGraph`` you built elsewhere and bring it into Nebelus via
the code path. Run it:

    pip install "nebelus[langgraph]"
    export NEBELUS_API_KEY=...            # minted in the portal (api.construction.*)
    export NEBELUS_BASE_URL=https://api.nebelus.ai      # or api.ksa.nebelus.ai
    python examples/langgraph_to_nebelus.py

What actually happens: ``from_langgraph`` reads the graph's TOPOLOGY (nodes, edges,
conditional-edge targets) from the *uncompiled* graph — it never imports or runs your
node functions. Nebelus agents are declarative, so YOU declare what each node does
(``node_map``) and how each router decides (``router_map``). Anything unmapped comes
back as a named diagnostic and NO manifest — nothing is guessed.
"""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from nebelus import Nebelus, from_langgraph


# ---------------------------------------------------------------------------
# 1. A LangGraph graph — the kind you might already have.
#    The node functions are arbitrary Python; the translation reads only the
#    graph's shape, so these stay stubs here (their real behaviour is declared
#    on the Nebelus side, in node_map below).
# ---------------------------------------------------------------------------
class State(TypedDict):
    request: str
    triage_out: str


def triage(state: State) -> dict:
    # In your real graph this calls a model / your own code and sets triage_out.
    return {"triage_out": "billing" if "invoice" in state["request"].lower() else "general"}


def billing(state: State) -> dict:
    return {}


def general(state: State) -> dict:
    return {}


def route(state: State) -> str:
    # A LangGraph branch is a Python callable — invisible to translation. Its
    # possible targets become visible ONLY through the path_map below.
    return "billing" if state["triage_out"] == "billing" else "general"


graph = StateGraph(State)
graph.add_node("triage", triage)
graph.add_node("billing", billing)
graph.add_node("general", general)
graph.add_edge(START, "triage")
# The path_map is REQUIRED — without it the branch's targets can't be seen outside
# the callable, and from_langgraph returns a blocking diagnostic instead of guessing.
graph.add_conditional_edges("triage", route, path_map={"billing": "billing", "general": "general"})
graph.add_edge("billing", END)
graph.add_edge("general", END)


# ---------------------------------------------------------------------------
# 2. Declare what topology cannot carry: node behaviour + router logic.
#    Every node and every branch must be mapped, or you get diagnostics.
# ---------------------------------------------------------------------------
translation = from_langgraph(
    graph,
    node_map={
        "triage": {"type": "agent", "config": {
            "system_prompt": "Classify the request as 'billing' or 'general'. Reply with one word.",
            "model_id": "claude-haiku-4-5"}},
        "billing": {"type": "agent", "config": {
            "system_prompt": "You are the billing specialist. Be precise.",
            "model_id": "claude-haiku-4-5"}},
        "general": {"type": "agent", "config": {
            "system_prompt": "You are the general assistant. Be brief.",
            "model_id": "claude-haiku-4-5"}},
    },
    # Each conditional branch source -> a declared condition. A LangGraph path_map
    # ({value: target}) maps directly onto `routes`; add a `default`.
    router_map={
        "triage": {"field": "triage_out",
                   "routes": {"billing": "billing", "general": "general"},
                   "default": "general"},
    },
    manifest_id="langgraph-triage-v1",   # stable identity — re-running updates, never duplicates
    name="Support triage (from LangGraph)",
    model_id="claude-haiku-4-5",
    description="Routes billing questions to a specialist, everything else to a generalist.",
)


# ---------------------------------------------------------------------------
# 3. Handle the honest result: a manifest when complete, diagnostics when not.
# ---------------------------------------------------------------------------
if not translation.complete:
    # Unmapped nodes/branches or a missing path_map land here. Each line names
    # exactly what to fix; a node with no declarative equivalent stays in YOUR
    # code and attaches to the agent as a tool (MCP server / custom API endpoint).
    print("Not translatable yet — fix these and re-run:")
    print("\n".join(f"  - {d}" for d in translation.diagnostics))
    raise SystemExit(1)

# Advisory (non-blocking) coverage hints may still be present even when complete.
for note in translation.diagnostics:
    print(f"note: {note}")

if __name__ == "__main__":
    nb = Nebelus()                                  # reads NEBELUS_API_KEY / NEBELUS_BASE_URL
    agent = nb.apply(translation.manifest)          # create-or-update by manifest_id; born a draft
    print(f"applied: {agent.id}")

    # Run the draft through the real runtime before anyone deploys it.
    print(nb.agents.probe(agent.id, "My invoice looks wrong — can you check it?").reply)

    # Deploy stays a human act unless your org opted in to programmatic deploys:
    # nb.agents.deploy(agent.id)   # needs api.construction.deploy + the org opt-in
