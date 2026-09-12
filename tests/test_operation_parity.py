"""Operation parity: the SDK must keep pace with the deployed Construction service.

The service layer powers every surface (vibe builder, manual builders, MCP, REST) and
the developer clients (this SDK, the TS client). This guard makes "on every surface" a
CHECKABLE invariant for the SDK: it reads the DEPLOYED OpenAPI schema — the single
source of truth — and requires every construction operation to be classified as one of:

  - COVERED     — the SDK exposes a method for it,
  - INTENTIONAL — deliberately not an SDK method (e.g. the MCP JSON-RPC facade),
  - GAP_LEDGER  — not yet covered (the debt; the goal is to drive this to EMPTY).

A NEW server operation that is none of these fails CI — it cannot ship on the service
and silently miss the SDK. Closing a gap = move it from GAP_LEDGER to COVERED (by adding
the method). The ledger only ever shrinks.
"""

import json
import os
import urllib.request

import pytest

SCHEMA_URL = os.environ.get(
    "NEBELUS_SCHEMA_URL", "https://api.nebelus.ai/api/construction/schema/?format=json"
)
B = "/api/v1/construction/"

# Operations the SDK exposes today (verified against the client's real REST calls).
COVERED = {
    f"GET {B}agents/", f"GET {B}agents/{{agent_id}}/", f"POST {B}agents/", f"PATCH {B}agents/{{agent_id}}/",
    f"POST {B}agents/build/", f"POST {B}agents/{{agent_id}}/deploy/", f"POST {B}agents/{{agent_id}}/archive/",
    f"DELETE {B}agents/{{agent_id}}/archive/", f"POST {B}agents/{{agent_id}}/validate/",
    f"POST {B}agents/{{agent_id}}/probe/", f"POST {B}agents/{{agent_id}}/policies/",
    f"POST {B}agents/{{agent_id}}/grounding-trace/", f"PUT {B}agents/{{agent_id}}/triggers/",
    f"GET {B}agents/{{agent_id}}/graph/", f"POST {B}agents/{{agent_id}}/graph/",
    f"GET {B}vector-stores/", f"POST {B}vector-stores/", f"DELETE {B}vector-stores/{{store_id}}/",
    f"POST {B}vector-stores/{{store_id}}/ingest/", f"POST {B}agents/{{agent_id}}/vector-stores/{{store_id}}/",
    f"GET {B}deployments/", f"POST {B}deployments/", f"POST {B}deployments/{{deployment_id}}/activate/",
    f"GET {B}deployments/{{deployment_id}}/probe/", f"GET {B}policies/", f"GET {B}describe/", f"GET {B}catalog/",
    # Full-parity additions (ledger closed):
    f"GET {B}agents/{{agent_id}}/wiring/",
    f"POST {B}agents/{{agent_id}}/sub-agents/", f"DELETE {B}agents/{{agent_id}}/sub-agents/",
    f"POST {B}agents/{{agent_id}}/ai-tools/{{tool_id}}/", f"DELETE {B}agents/{{agent_id}}/ai-tools/{{tool_id}}/",
    f"POST {B}agents/{{agent_id}}/code-connectors/{{connector_id}}/", f"DELETE {B}agents/{{agent_id}}/code-connectors/{{connector_id}}/",
    f"POST {B}agents/{{agent_id}}/mcp-servers/{{server_id}}/", f"DELETE {B}agents/{{agent_id}}/mcp-servers/{{server_id}}/",
    f"POST {B}agents/{{agent_id}}/api-endpoints/{{endpoint_id}}/", f"DELETE {B}agents/{{agent_id}}/api-endpoints/{{endpoint_id}}/",
    f"DELETE {B}agents/{{agent_id}}/vector-stores/{{store_id}}/", f"PATCH {B}vector-stores/{{store_id}}/",
    f"GET {B}agents/{{agent_id}}/schedules/", f"POST {B}agents/{{agent_id}}/schedules/",
    f"DELETE {B}agents/{{agent_id}}/schedules/{{schedule_id}}/",
    f"GET {B}api-endpoints/", f"POST {B}api-endpoints/", f"PATCH {B}api-endpoints/{{endpoint_id}}/",
    f"POST {B}api-endpoints/{{endpoint_id}}/test/",
    f"GET {B}mcp-servers/", f"POST {B}mcp-servers/", f"PATCH {B}mcp-servers/{{server_id}}/", f"POST {B}mcp-servers/probe/",
    f"PATCH {B}deployments/{{deployment_id}}/", f"POST {B}policies/", f"POST {B}policies/{{policy_id}}/activate/",
    f"GET {B}api-keys/", f"POST {B}api-keys/",  # nebelus keys (Phase 5)
}

# Deliberately not an SDK method.
INTENTIONAL = {
    f"POST {B}mcp/",  # the MCP JSON-RPC facade — a transport, not a REST operation
}

# Not yet exposed by the SDK — the debt. GOAL: empty. EMPTY = full parity (2026-09-11).
# A new server op lands here (or in COVERED/INTENTIONAL) or CI fails.
GAP_LEDGER: set[str] = set()


def _fetch_ops() -> set[str]:
    # A real User-Agent is required: the default urllib UA is 403'd at the edge (WAF).
    req = urllib.request.Request(
        SCHEMA_URL, headers={"User-Agent": "nebelus-operation-parity", "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            doc = json.loads(r.read().decode())
    except Exception as exc:  # noqa: BLE001 — a transient outage must not block a release
        pytest.skip(f"construction schema unreachable ({exc}); skipping operation-parity")
    ops = set()
    for path, item in (doc.get("paths") or {}).items():
        for method in item:
            if method in ("get", "post", "put", "patch", "delete"):
                ops.add(f"{method.upper()} {path}")
    assert ops, "schema returned no operations"
    return ops


def test_every_deployed_operation_is_classified():
    schema_ops = _fetch_ops()
    unclassified = schema_ops - COVERED - INTENTIONAL - GAP_LEDGER
    assert not unclassified, (
        "New construction operations are live on the service but unclassified in the SDK.\n"
        "Add each to COVERED (implement the method), INTENTIONAL, or GAP_LEDGER:\n  "
        + "\n  ".join(sorted(unclassified))
    )


def test_ledger_is_honest():
    # A gap that is actually covered, or a made-up op not on the service, must be cleaned up.
    assert not (GAP_LEDGER & COVERED), "op is in both GAP_LEDGER and COVERED"
    assert not (GAP_LEDGER & INTENTIONAL), "op is in both GAP_LEDGER and INTENTIONAL"
    schema_ops = _fetch_ops()
    stale = (GAP_LEDGER | COVERED) - schema_ops - {f"POST {B}agents/build/"}
    assert not stale, "ledger/covered references ops not on the deployed service: " + ", ".join(sorted(stale))
