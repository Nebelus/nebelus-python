"""The Nebelus client — a thin, faithful skin over the Agents API.

Every operation maps 1:1 to a route; all governance (Build Envelope, identity
ladder, deploy opt-in, RBAC) is enforced server-side and surfaces here as
`NebelusAPIError` with the machine payload intact.
"""

from __future__ import annotations

from typing import Any

from ._transport import NebelusAPIError, NotFound, Transport
from .models import Agent, AgentManifest, ProbeResult, ValidationResult

__all__ = ["Nebelus", "NebelusAPIError", "NotFound"]


class _Agents:
    def __init__(self, t: Transport):
        self._t = t

    def list(self, manifest_id: str | None = None) -> list[dict]:
        params = {"manifest_id": manifest_id} if manifest_id else None
        rows = self._t.request("GET", "/agents/", params=params)
        return rows.get("results", []) if isinstance(rows, dict) else rows

    def get(self, agent_id: str) -> Agent:
        return Agent.model_validate(self._t.request("GET", f"/agents/{agent_id}/"))

    def create(self, **fields: Any) -> Agent:
        return Agent.model_validate(self._t.request("POST", "/agents/", json=fields))

    def update(self, agent_id: str, **fields: Any) -> Agent:
        return Agent.model_validate(self._t.request("PATCH", f"/agents/{agent_id}/", json=fields))

    def deploy(self, agent_id: str) -> dict:
        return self._t.request("POST", f"/agents/{agent_id}/deploy/")

    def archive(self, agent_id: str) -> dict:
        return self._t.request("POST", f"/agents/{agent_id}/archive/")

    def unarchive(self, agent_id: str) -> dict:
        return self._t.request("DELETE", f"/agents/{agent_id}/archive/")

    def validate(self, agent_id: str) -> ValidationResult:
        return ValidationResult.model_validate(self._t.request("POST", f"/agents/{agent_id}/validate/"))

    def probe(self, agent_id: str, message: str, thread_id: str | None = None) -> ProbeResult:
        body: dict[str, Any] = {"message": message}
        if thread_id:
            body["thread_id"] = thread_id
        return ProbeResult.model_validate(self._t.request("POST", f"/agents/{agent_id}/probe/", json=body))

    def set_policies(self, agent_id: str, policy_ids: list[str], mode: str = "replace") -> dict:
        return self._t.request("POST", f"/agents/{agent_id}/policies/", json={"policy_ids": policy_ids, "mode": mode})

    def set_grounding_trace(self, agent_id: str, **kwargs: Any) -> dict:
        return self._t.request("POST", f"/agents/{agent_id}/grounding-trace/", json=kwargs)

    def set_triggers(self, agent_id: str, used_triggers: list) -> dict:
        return self._t.request("PUT", f"/agents/{agent_id}/triggers/", json={"used_triggers": used_triggers})

    def wiring(self, agent_id: str) -> dict:
        """REST invoke / WebSocket / webhook / widget-embed / MCP wiring, region-correct."""
        return self._t.request("GET", f"/agents/{agent_id}/wiring/")

    # sub-agents (the sub-agent's id travels in the body)
    def attach_sub_agent(self, agent_id: str, sub_agent_id: str, *, instruction: str | None = None,
                         mode: str = "as_tool", stream_to_client: bool | None = None) -> dict:
        body: dict[str, Any] = {"agent_id": sub_agent_id, "mode": mode}
        if instruction is not None:
            body["instruction"] = instruction
        if stream_to_client is not None:
            body["stream_to_client"] = stream_to_client
        return self._t.request("POST", f"/agents/{agent_id}/sub-agents/", json=body)

    def detach_sub_agent(self, agent_id: str, sub_agent_id: str) -> dict:
        return self._t.request("DELETE", f"/agents/{agent_id}/sub-agents/", json={"agent_id": sub_agent_id})

    # tools & connectors (id in the path)
    def attach_ai_tool(self, agent_id: str, tool_id: str) -> dict:
        return self._t.request("POST", f"/agents/{agent_id}/ai-tools/{tool_id}/")

    def detach_ai_tool(self, agent_id: str, tool_id: str) -> dict:
        return self._t.request("DELETE", f"/agents/{agent_id}/ai-tools/{tool_id}/")

    def attach_code_connector(self, agent_id: str, connector_id: str) -> dict:
        return self._t.request("POST", f"/agents/{agent_id}/code-connectors/{connector_id}/")

    def detach_code_connector(self, agent_id: str, connector_id: str) -> dict:
        return self._t.request("DELETE", f"/agents/{agent_id}/code-connectors/{connector_id}/")

    def attach_mcp_server(self, agent_id: str, server_id: str) -> dict:
        return self._t.request("POST", f"/agents/{agent_id}/mcp-servers/{server_id}/")

    def detach_mcp_server(self, agent_id: str, server_id: str) -> dict:
        return self._t.request("DELETE", f"/agents/{agent_id}/mcp-servers/{server_id}/")

    def attach_api_endpoint(self, agent_id: str, endpoint_id: str, **auth: Any) -> dict:
        """Attach a custom API endpoint. Optional auth-by-REFERENCE kwargs only
        (use_endpoint_auth / auth_profile_id / auth_method[+auth_config, auth_profile_name])
        — the service never accepts raw secrets here."""
        return self._t.request("POST", f"/agents/{agent_id}/api-endpoints/{endpoint_id}/", json=auth or None)

    def detach_api_endpoint(self, agent_id: str, endpoint_id: str) -> dict:
        return self._t.request("DELETE", f"/agents/{agent_id}/api-endpoints/{endpoint_id}/")

    # schedules
    def list_schedules(self, agent_id: str) -> Any:
        return self._t.request("GET", f"/agents/{agent_id}/schedules/")

    def create_schedule(self, agent_id: str, name: str, instruction: str, **cadence: Any) -> dict:
        return self._t.request(
            "POST", f"/agents/{agent_id}/schedules/", json={"name": name, "instruction": instruction, **cadence}
        )

    def cancel_schedule(self, agent_id: str, schedule_id: str) -> dict:
        return self._t.request("DELETE", f"/agents/{agent_id}/schedules/{schedule_id}/")


class _Graph:
    """Granular workflow-graph ops with the visual builder's cascade semantics."""

    def __init__(self, t: Transport, agent_id: str):
        self._t = t
        self._id = agent_id

    def get(self) -> dict:
        return self._t.request("GET", f"/agents/{self._id}/graph/")

    def _op(self, op: str, **args: Any) -> dict:
        return self._t.request("POST", f"/agents/{self._id}/graph/", json={"op": op, **args})

    def add_node(self, node: dict) -> dict:
        return self._op("add_node", node=node)

    def update_node(
        self, name: str, config_patch: dict | None = None, position: dict | None = None, new_name: str | None = None
    ) -> dict:
        args: dict[str, Any] = {"name": name}
        if config_patch is not None:
            args["config_patch"] = config_patch
        if position is not None:
            args["position"] = position
        if new_name is not None:
            args["new_name"] = new_name
        return self._op("update_node", **args)

    def remove_node(self, name: str) -> dict:
        return self._op("remove_node", name=name)

    def add_edge(self, from_node: str, to_node: str, **kwargs: Any) -> dict:
        return self._op("add_edge", from_node=from_node, to_node=to_node, **kwargs)

    def remove_edge(self, from_node: str, to_node: str) -> dict:
        return self._op("remove_edge", from_node=from_node, to_node=to_node)

    def set_state_field(self, field: str, field_type: str = "str", **kwargs: Any) -> dict:
        return self._op("set_state_field", field=field, field_type=field_type, **kwargs)


class _Keys:
    """Manage org API keys from code (the `nebelus keys` CLI). Reachable with a
    `nebelus login` token — key-minting lives on the construction surface."""

    def __init__(self, t: Transport):
        self._t = t

    def list(self) -> list:
        return self._t.request("GET", "/api-keys/")["results"]

    def create(self, scopes: list[str], name: str | None = None, is_service_account: bool = False) -> dict:
        """Mint an API key. The full key is in the response ONCE (``sensitive_id``).
        The deploy scope needs the org's programmatic-deploy opt-in."""
        body: dict[str, Any] = {"scopes": scopes, "is_service_account": is_service_account}
        if name:
            body["name"] = name
        return self._t.request("POST", "/api-keys/", json=body)


class _Resources:
    def __init__(self, t: Transport):
        self._t = t

    # vector stores
    def vector_stores(self, query: str | None = None) -> list:
        return self._t.request("GET", "/vector-stores/", params={"query": query} if query else None)["results"]

    def create_vector_store(self, name: str, metadata: dict | None = None) -> dict:
        return self._t.request("POST", "/vector-stores/", json={"name": name, "metadata": metadata})

    def delete_vector_store(self, store_id: str, force: bool = False) -> dict:
        return self._t.request("DELETE", f"/vector-stores/{store_id}/", params={"force": force})

    def ingest_file(self, store_id: str, file_id: str) -> dict:
        return self._t.request("POST", f"/vector-stores/{store_id}/ingest/", json={"file_id": file_id})

    def update_vector_store(self, store_id: str, name: str | None = None, metadata: dict | None = None) -> dict:
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if metadata is not None:
            body["metadata"] = metadata
        return self._t.request("PATCH", f"/vector-stores/{store_id}/", json=body)

    def attach_store(self, agent_id: str, store_id: str) -> dict:
        return self._t.request("POST", f"/agents/{agent_id}/vector-stores/{store_id}/")

    def detach_store(self, agent_id: str, store_id: str) -> dict:
        return self._t.request("DELETE", f"/agents/{agent_id}/vector-stores/{store_id}/")

    # custom API endpoints (outbound tool endpoints)
    def api_endpoints(self, query: str | None = None) -> list:
        return self._t.request("GET", "/api-endpoints/", params={"query": query} if query else None)["results"]

    def create_api_endpoint(self, **fields: Any) -> dict:
        return self._t.request("POST", "/api-endpoints/", json=fields)

    def update_api_endpoint(self, endpoint_id: str, **fields: Any) -> dict:
        return self._t.request("PATCH", f"/api-endpoints/{endpoint_id}/", json=fields)

    def test_api_endpoint(self, endpoint_id: str, test_parameters: dict | None = None) -> dict:
        return self._t.request("POST", f"/api-endpoints/{endpoint_id}/test/", json={"test_parameters": test_parameters})

    # MCP servers
    def mcp_servers(self, query: str | None = None) -> list:
        return self._t.request("GET", "/mcp-servers/", params={"query": query} if query else None)["results"]

    def create_mcp_server(self, **fields: Any) -> dict:
        return self._t.request("POST", "/mcp-servers/", json=fields)

    def update_mcp_server(self, server_id: str, **fields: Any) -> dict:
        return self._t.request("PATCH", f"/mcp-servers/{server_id}/", json=fields)

    def probe_mcp_server(self, **fields: Any) -> dict:
        return self._t.request("POST", "/mcp-servers/probe/", json=fields)

    # deployments
    def deployments(self) -> dict:
        return self._t.request("GET", "/deployments/")

    def update_deployment(self, deployment_id: str, name: str | None = None,
                          description: str | None = None, config_patch: dict | None = None) -> dict:
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if config_patch is not None:
            body["config_patch"] = config_patch
        return self._t.request("PATCH", f"/deployments/{deployment_id}/", json=body)

    def create_deployment(self, agent_id: str, deployment_type: str, name: str, **kwargs: Any) -> dict:
        return self._t.request(
            "POST",
            "/deployments/",
            json={"agent_id": agent_id, "deployment_type": deployment_type, "name": name, **kwargs},
        )

    def activate_deployment(self, deployment_id: str, active: bool = True) -> dict:
        return self._t.request("POST", f"/deployments/{deployment_id}/activate/", json={"active": active})

    def probe_deployment(self, deployment_id: str) -> dict:
        return self._t.request("GET", f"/deployments/{deployment_id}/probe/")

    # governance
    def policies(self) -> list:
        return self._t.request("GET", "/policies/")["results"]

    def create_policy(self, **fields: Any) -> dict:
        return self._t.request("POST", "/policies/", json=fields)

    def activate_policy(self, policy_id: str, active: bool = True) -> dict:
        return self._t.request("POST", f"/policies/{policy_id}/activate/", json={"active": active})


class Nebelus:
    """Entry point. Reads NEBELUS_API_KEY / NEBELUS_BASE_URL when not passed."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None, timeout: float | None = None):
        self._t = Transport(api_key=api_key, base_url=base_url, timeout=timeout)
        self.agents = _Agents(self._t)
        self.resources = _Resources(self._t)
        self.keys = _Keys(self._t)

    def close(self) -> None:
        self._t.close()

    def __enter__(self) -> Nebelus:  # noqa: PYI034 — Self needs py3.11; floor is 3.10
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def describe(self) -> dict:
        """Everything buildable in this organization, machine-readable."""
        return self._t.request("GET", "/describe/")

    def catalog(self, view: str = "models", query: str | None = None, mode: str = "list") -> Any:
        params: dict[str, Any] = {"view": view, "mode": mode}
        if query:
            params["query"] = query
        return self._t.request("GET", "/catalog/", params=params)["results"]

    def build(self, prompt: str, constraints: str | None = None) -> dict:
        """AI-assisted build: describe an agent in plain language and the Nebelus Vibe
        Builder builds it for you — always as a DRAFT. Returns
        ``{built, agent, agents, notes, status, run_id, thread_id}`` where ``agent`` is
        the created draft's editable surface (round-trippable via ``export``) and
        ``notes`` is the builder's summary + assumptions. Billed as AI credits at the
        build rate. Unlike ``apply`` (you specify every field), this SYNTHESISES."""
        body: dict[str, Any] = {"prompt": prompt}
        if constraints:
            body["constraints"] = constraints
        # The Vibe Builder synthesises an agent server-side — allow the 10-minute
        # Agent Builder budget rather than the general read timeout.
        return self._t.request("POST", "/agents/build/", json=body, timeout=self._t.ai_timeout)

    def graph(self, agent_id: str) -> _Graph:
        return _Graph(self._t, agent_id)

    # ------------------------------------------------------------------ apply
    def find_by_manifest_id(self, manifest_id: str) -> Agent | None:
        # Fast path: server-side ?manifest_id= lookup (rows echo manifest_id).
        # Older servers ignore the filter and omit the field from rows — for
        # those, fall through to checking each agent's metadata directly.
        rows = self.agents.list(manifest_id=manifest_id)
        if all("manifest_id" in row for row in rows):
            rows = [row for row in rows if row.get("manifest_id") == manifest_id]
        for row in rows:
            try:
                agent = self.agents.get(row["id"])
            except NotFound:
                continue
            if (agent.metadata or {}).get("manifest_id") == manifest_id:
                return agent
        return None

    @staticmethod
    def _in_sync(have: Any, want: Any) -> bool:
        """Merge-contract equality: for dict values, only the keys the manifest
        DECLARES count — server-side normalization keys (e.g. a pattern_config
        gaining `conditional_edges: []`) and other writers' keys are not drift."""
        if isinstance(want, dict) and isinstance(have, dict):
            return all(Nebelus._in_sync(have.get(k), v) for k, v in want.items())
        if isinstance(want, list) and isinstance(have, list):
            return len(have) == len(want) and all(Nebelus._in_sync(h, w) for h, w in zip(have, want))
        return have == want

    def diff(self, manifest: AgentManifest) -> dict[str, Any]:
        """What `apply` would change: {} when in sync; {'create': fields} when the
        agent doesn't exist; else {field: (current, desired)} for declared fields."""
        desired = manifest.to_fields()
        current: Agent | None = None
        if manifest.manifest_id:
            current = self.find_by_manifest_id(manifest.manifest_id)
        if current is None:
            return {"create": desired}
        body = current.model_dump()
        changes: dict[str, Any] = {}
        for key, want in desired.items():
            if not self._in_sync(body.get(key), want):
                changes[key] = (body.get(key), want)
        return changes

    def apply(self, manifest: AgentManifest) -> Agent:
        """Create-or-update under the server's key-wise merge contract. Only fields
        the manifest DECLARES are sent; portal edits to undeclared fields survive."""
        changes = self.diff(manifest)
        if "create" in changes:
            return self.agents.create(**changes["create"])
        if not changes:
            assert manifest.manifest_id
            found = self.find_by_manifest_id(manifest.manifest_id)
            assert found is not None
            return found
        target = self.find_by_manifest_id(manifest.manifest_id)  # type: ignore[arg-type]
        assert target is not None
        return self.agents.update(target.id, **{k: v[1] for k, v in changes.items()})
