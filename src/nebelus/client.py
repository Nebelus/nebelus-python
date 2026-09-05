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

    def list(self) -> list[dict]:
        rows = self._t.request("GET", "/agents/")
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

    def update_node(self, name: str, config_patch: dict | None = None,
                    position: dict | None = None, new_name: str | None = None) -> dict:
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

    def attach_store(self, agent_id: str, store_id: str) -> dict:
        return self._t.request("POST", f"/agents/{agent_id}/vector-stores/{store_id}/")

    # deployments
    def deployments(self) -> dict:
        return self._t.request("GET", "/deployments/")

    def create_deployment(self, agent_id: str, deployment_type: str, name: str, **kwargs: Any) -> dict:
        return self._t.request("POST", "/deployments/", json={
            "agent_id": agent_id, "deployment_type": deployment_type, "name": name, **kwargs})

    def activate_deployment(self, deployment_id: str, active: bool = True) -> dict:
        return self._t.request("POST", f"/deployments/{deployment_id}/activate/", json={"active": active})

    def probe_deployment(self, deployment_id: str) -> dict:
        return self._t.request("GET", f"/deployments/{deployment_id}/probe/")

    # governance
    def policies(self) -> list:
        return self._t.request("GET", "/policies/")["results"]


class Nebelus:
    """Entry point. Reads NEBELUS_API_KEY / NEBELUS_BASE_URL when not passed."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None, timeout: float = 60.0):
        self._t = Transport(api_key=api_key, base_url=base_url, timeout=timeout)
        self.agents = _Agents(self._t)
        self.resources = _Resources(self._t)

    def close(self) -> None:
        self._t.close()

    def __enter__(self) -> Nebelus:
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

    def graph(self, agent_id: str) -> _Graph:
        return _Graph(self._t, agent_id)

    # ------------------------------------------------------------------ apply
    def find_by_manifest_id(self, manifest_id: str) -> Agent | None:
        for row in self.agents.list():
            try:
                agent = self.agents.get(row["id"])
            except NotFound:
                continue
            if (agent.metadata or {}).get("manifest_id") == manifest_id:
                return agent
        return None

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
            have = body.get(key)
            if key == "metadata" and isinstance(have, dict):
                have = {k: v for k, v in have.items() if k in (want or {})}
            if have != want:
                changes[key] = (have, want)
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
