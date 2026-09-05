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
    ``router_map``: branch source name → condition-node config in the canonical
    schema (route on a value map and/or an expression), e.g.
        {"triage": {"field": "triage_out",
                    "routes": {"billing": "billing", "general": "general"},
                    "default": "general"}}
    A LangGraph ``path_map`` ({value: target}) maps directly onto ``routes``.
    A router node named ``<source>__router`` is inserted after each mapped
    branch source. Unmapped nodes/branches produce diagnostics and no manifest.
    """
    router_map = router_map or {}
    diagnostics: list[str] = []
    advisories: list[str] = []  # non-blocking: a manifest is still produced
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
                f"condition config with a 'routes' map (value -> target) and a "
                f"'default', or an 'expression' (+ 'default')."
            )
            continue
        # Canonical condition schema (matches the API's describe/ and the visual
        # builder): route on config.routes (value -> target, drawn on the canvas)
        # and/or config.expression (+ config.default). A LangGraph path_map maps
        # directly onto routes. A config with no routing basis can't branch.
        if not (router_cfg.get("routes") or router_cfg.get("expression") or router_cfg.get("field")):
            diagnostics.append(
                f"router_map['{source}'] has no routing basis — give it a 'routes' map "
                f"(value -> target) and/or an 'expression'; keys like 'conditions'/"
                f"'default_target' are not part of the condition schema and are ignored."
            )
            continue
        router_name = f"{source}__router"
        nodes.append({"name": router_name, "type": "condition", "config": router_cfg})
        edges.append({"from": source, "to": router_name})
        declared = set((router_cfg.get("routes") or {}).values())
        declared.add(router_cfg.get("default"))
        # Only value-routing exposes its targets statically; skip the coverage
        # hint for expression-only routers (targets aren't knowable here).
        if router_cfg.get("routes"):
            for missing in sorted(t for t in targets if t not in declared and t != END):
                advisories.append(
                    f"router_map for '{source}' never routes to '{missing}', which the "
                    f"LangGraph branch could reach — add it to 'routes' or make it the 'default'."
                )

    pattern_config = {"nodes": nodes, "edges": edges}
    # `diagnostics` are blocking (no manifest); `advisories` are non-blocking
    # coverage hints. Both are surfaced together on the result.
    manifest = None
    if not diagnostics:
        manifest = AgentManifest(
            manifest_id=manifest_id,
            name=name,
            model_id=model_id,
            pattern_type="workflow",
            pattern_config=pattern_config,
            **manifest_fields,
        )
    return Translation(manifest=manifest, pattern_config=pattern_config,
                       diagnostics=diagnostics + advisories)
