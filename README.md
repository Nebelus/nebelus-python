# Nebelus Agents API — Python SDK

Build, edit, and ship governed AI agents from code. Every agent you create here is the
same artifact your team sees in the Nebelus portal — one construction service, every
surface, your organization's governance applied identically.

```python
from nebelus import Nebelus, AgentManifest

nb = Nebelus()  # NEBELUS_API_KEY + NEBELUS_BASE_URL (default https://api.nebelus.ai)

# Discover what this organization can build — machine-readable.
info = nb.describe()

manifest = AgentManifest(
    name="Return-policy concierge",
    model_id="claude-haiku-4-5",
    system_message="Answer from the return policy. Escalate anything ambiguous.",
)
agent = nb.apply(manifest)               # create-or-update, key-wise merge — never clobbers portal edits
print(nb.agents.probe(agent.id, "Can I return a jacket after 20 days?").reply)
# Deploying is a human act unless your org opted in to programmatic deployment:
# nb.agents.deploy(agent.id)             # needs the api.construction.deploy scope + the org opt-in
```

Keys: Nebelus portal → Settings → API keys (administrator-managed). Scopes:
`api.construction.read`, `api.construction.write`, and `api.construction.deploy`.
Your Build Envelope (if your organization uses one) applies to code exactly as it applies
to every other surface.

## CLI

Everything above is also a command (`pip install nebelus` puts `nebelus` on your PATH):

```bash
nebelus describe                       # everything your org can build, machine-readable
nebelus catalog --view tools --query crm
nebelus apply agent.py                 # a file defining `manifest = AgentManifest(...)`
nebelus diff agent.py                  # what apply would change ("in sync" when nothing)
nebelus validate <agent-id>            # pre-flight findings before you probe or deploy
nebelus probe <agent-id> "Hi there"    # run the draft through the real runtime
nebelus export <agent-id> > agent.py   # a live agent as a maintainable Python manifest
nebelus deploy <agent-id>              # needs the deploy scope + the org's opt-in
```

## Two-way with the portal

`nebelus export` (or `nebelus.export_to_code`) turns any live agent — including one a
colleague built visually — into a Python manifest you own in git. `apply` takes it back.
The merge contract makes this safe in both directions: a manifest only manages the fields
it declares, so portal edits to everything else survive every apply, and `diff` never
reports server-side normalization as drift.

## Coming from LangGraph

`from_langgraph` translates a `StateGraph`'s topology into a Nebelus workflow — nodes,
edges, and conditional-edge targets map mechanically (both sides share the
`__start__`/`__end__` sentinels). What a node *does* and how a router *decides* live in
your Python, so you declare those explicitly; anything with no declarative equivalent
stays in your code and attaches to the agent as an MCP server or custom API endpoint.
Incomplete translations return named diagnostics instead of a manifest — nothing is
guessed:

```python
from nebelus import Nebelus, from_langgraph

t = from_langgraph(
    my_state_graph,
    node_map={"triage": {"type": "agent", "config": {"system_prompt": "...", "model_id": "claude-haiku-4-5"}}},
    router_map={"triage": {"conditions": [{"expression": "...", "target": "billing"}],
                           "default_target": "general"}},
    manifest_id="triage-v1", name="Triage", model_id="claude-haiku-4-5",
)
if t.complete:
    Nebelus().apply(t.manifest)
else:
    print("\n".join(t.diagnostics))   # names every unmapped node and undeclared router
```

Install the source-graph dependency with `pip install "nebelus[langgraph]"`.
