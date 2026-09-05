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
