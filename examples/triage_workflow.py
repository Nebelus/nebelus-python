"""A complete workflow agent as code — apply with `nebelus apply examples/triage_workflow.py`."""

from nebelus import AgentManifest

manifest = AgentManifest(
    manifest_id="triage-example-v1",
    name="Support triage",
    model_id="claude-haiku-4-5",
    pattern_type="workflow",
    description="Routes billing questions to a specialist, everything else to a generalist.",
    pattern_config={
        "nodes": [
            {"name": "triage", "type": "agent",
             "config": {"system_prompt": "Classify the request as 'billing' or 'general'. Reply with exactly one word.",
                        "model_id": "claude-haiku-4-5"}},
            # A condition node routes on config.routes (value -> target; the canvas
            # draws one line per entry) and/or config.expression (+ config.default).
            {"name": "router", "type": "condition",
             "config": {"expression": "'billing' if 'billing' in str(state.get('triage_out','')).lower() else 'general'",
                        "routes": {"billing": "billing", "general": "general"},
                        "default": "general"}},
            {"name": "billing", "type": "agent",
             "config": {"system_prompt": "You are the billing specialist. Be precise.",
                        "model_id": "claude-haiku-4-5"}},
            {"name": "general", "type": "agent",
             "config": {"system_prompt": "You are the general assistant. Be brief.",
                        "model_id": "claude-haiku-4-5"}},
        ],
        "edges": [
            {"from": "__start__", "to": "triage"},
            {"from": "triage", "to": "router"},
            {"from": "billing", "to": "__end__"},
            {"from": "general", "to": "__end__"},
        ],
    },
)
