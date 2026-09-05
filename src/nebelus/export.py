"""Export a live agent as code — the other half of the two-way story: an agent
born in the portal (or the chat builder) becomes a maintainable Python manifest,
and `apply` takes it back. Mechanical, no model calls."""

from __future__ import annotations

from typing import Any

from .models import Agent

_EXPORT_FIELDS = (
    "name",
    "description",
    "model_id",
    "system_message",
    "pattern_type",
    "pattern_config",
    "needed_tools",
    "tags",
)

_TEMPLATE = '''"""{name} — exported from Nebelus ({agent_id}).

Edit and re-apply:  nebelus apply {module_name}.py   (or nb.apply(manifest) in code)
Only fields declared here are managed by this manifest; portal edits to other
fields survive every apply (key-wise merge).
"""

from nebelus import AgentManifest

manifest = AgentManifest(
    manifest_id={manifest_id!r},
{fields}
)

if __name__ == "__main__":
    from nebelus import Nebelus

    agent = Nebelus().apply(manifest)
    print(agent.id, agent.status)
'''


def export_to_code(agent: Agent, module_name: str = "agent") -> str:
    body: dict[str, Any] = agent.model_dump()
    manifest_id = (body.get("metadata") or {}).get("manifest_id") or f"exported-{body['id']}"
    lines = []
    for field in _EXPORT_FIELDS:
        value = body.get(field)
        if value in (None, "", {}, []):
            continue
        lines.append(f"    {field}={value!r},")
    return _TEMPLATE.format(
        name=body.get("name") or "Agent",
        agent_id=body["id"],
        module_name=module_name,
        manifest_id=manifest_id,
        fields="\n".join(lines),
    )
