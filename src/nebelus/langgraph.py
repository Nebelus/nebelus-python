"""LangGraph → Nebelus translation (v0, honest subset).

What translates mechanically: the TOPOLOGY — nodes, edges, and conditional-edge
targets (LangGraph and Nebelus share the ``__start__``/``__end__`` sentinels).

What cannot translate automatically — and is surfaced as diagnostics, never
guessed: what each node DOES (a LangGraph node wraps arbitrary Python; Nebelus
workflow nodes are declarative configs), and each router's decision logic (a
LangGraph branch is a Python callable; a Nebelus condition node is a declared
expression). You supply both via ``node_map`` / ``router_map``. For node logic
that has no declarative equivalent, keep the Python where it runs well and
attach it to the agent as an MCP server or custom API endpoint instead.

Requires the ``langgraph`` extra only for building the source graph — this
module itself has no langgraph import.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import AgentManifest

START = "__start__"
END = "__end__"


@dataclass
class Translation:
    """The result: a manifest when complete, diagnostics when not (or both —
    diagnostics may be advisory once every node and branch is covered)."""

    manifest: AgentManifest | None
    pattern_config: dict[str, Any]
    diagnostics: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return self.manifest is not None


def from_langgraph(
    graph: Any,
    node_map: dict[str, dict],
    *,
    manifest_id: str,
    name: str,
    model_id: str,
    router_map: dict[str, dict] | None = None,
    **manifest_fields: Any,
) -> Translation:
    """Translate an (uncompiled) ``langgraph.graph.StateGraph``.

    ``node_map``: LangGraph node name → Nebelus node dict, e.g.
        {"triage": {"type": "agent", "config": {"system_prompt": ..., "model_id": ...}}}
    ``router_map``: branch source name → condition-node config, e.g.
        {"triage": {"conditions": [{"expression": ..., "target": "billing"}],
                    "default_target": "general"}}
    A router node named ``<source>__router`` is inserted after each mapped
    branch source. Unmapped nodes/branches produce diagnostics and no manifest.
    """
    router_map = router_map or {}
    diagnostics: list[str] = []
    lg_nodes = list(graph.nodes)
    lg_edges = sorted(graph.edges)
    lg_branches = dict(getattr(graph, "branches", {}) or {})

    nodes: list[dict] = []
    for lg_name in lg_nodes:
        mapped = node_map.get(lg_name)
        if mapped is None:
            diagnostics.append(
                f"node '{lg_name}' wraps arbitrary Python and has no node_map entry — "
                f"declare it (e.g. {{'type': 'agent', 'config': {{...}}}}), or keep the "
                f"Python where it runs and attach it via an MCP server or custom API endpoint."
            )
            continue
        nodes.append({"name": lg_name, **mapped})

    edges = [{"from": a, "to": b} for a, b in lg_edges]

    for source, branches in lg_branches.items():
        targets: set[str] = set()
        for branch in branches.values():
            ends = getattr(branch, "ends", None)
            if ends:
                targets.update(ends.values())
            else:
                diagnostics.append(
                    f"branch on '{source}' declares no path_map, so its possible targets "
                    f"are invisible outside the Python callable — add a path_map to the "
                    f"add_conditional_edges call, then re-translate."
                )
        router_cfg = router_map.get(source)
        if router_cfg is None:
            diagnostics.append(
                f"branch on '{source}' routes via a Python callable (targets: "
                f"{sorted(targets) or 'unknown'}) — declare it in router_map as a "
                f"condition config with 'conditions' expressions and a 'default_target'."
            )
            continue
        router_name = f"{source}__router"
        nodes.append({"name": router_name, "type": "condition", "config": router_cfg})
        edges.append({"from": source, "to": router_name})
        declared = {c.get("target") for c in router_cfg.get("conditions", [])}
        declared.add(router_cfg.get("default_target"))
        for missing in sorted(t for t in targets if t not in declared and t != END):
            diagnostics.append(
                f"router_map for '{source}' never routes to '{missing}', which the "
                f"LangGraph branch could reach — add a condition or make it the default."
            )

    pattern_config = {"nodes": nodes, "edges": edges}
    blocking = [d for d in diagnostics if "add a condition" not in d]
    manifest = None
    if not blocking:
        manifest = AgentManifest(
            manifest_id=manifest_id,
            name=name,
            model_id=model_id,
            pattern_type="workflow",
            pattern_config=pattern_config,
            **manifest_fields,
        )
    return Translation(manifest=manifest, pattern_config=pattern_config, diagnostics=diagnostics)
