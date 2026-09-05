"""Typed shapes. Deliberately permissive (`extra="allow"`): the API's GET body is
derived from the server's writable-field surface and may grow — the SDK must
round-trip fields it doesn't know yet, never drop them."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Agent(BaseModel):
    model_config = ConfigDict(extra="allow", protected_namespaces=())

    id: str
    status: str
    name: str | None = None
    description: str | None = None
    pattern_type: str | None = None
    pattern_config: dict | None = None
    model_id: str | None = None
    system_message: str | None = None
    needed_tools: list | dict | None = None
    needed_agents: list | dict | None = None
    tags: list | None = None
    metadata: dict | None = None
    governance_policies: list | None = None


class ProbeResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str
    reply: str | None = None
    thread_id: str | None = None
    tool_trace: list | None = None


class ValidationResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    valid: bool
    findings: list[str] = Field(default_factory=list)


class AgentManifest(BaseModel):
    """Declarative agent definition for `Nebelus.apply()`.

    Only the fields you SET are sent — the server merges key-wise, so applying a
    manifest never clobbers what a colleague changed in the portal on fields you
    didn't declare. Inside `pattern_config`, an explicit None deletes a key.
    `manifest_id` pins identity across applies: set it once (any stable string);
    apply finds the agent by metadata.manifest_id, else creates it.
    """

    model_config = ConfigDict(extra="allow", protected_namespaces=())

    manifest_id: str | None = None
    name: str
    description: str | None = None
    model_id: str | None = None
    system_message: str | None = None
    pattern_type: str | None = None
    pattern_config: dict | None = None
    needed_tools: list | dict | None = None
    tags: list | None = None
    metadata: dict | None = None

    def to_fields(self) -> dict[str, Any]:
        fields = self.model_dump(exclude_none=True, exclude={"manifest_id"})
        if self.manifest_id:
            meta = dict(fields.get("metadata") or {})
            meta["manifest_id"] = self.manifest_id
            fields["metadata"] = meta
        return fields
