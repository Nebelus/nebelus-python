"""Unit tests over a mocked transport (respx) — the contract, not the wire."""

import httpx
import pytest
import respx

from nebelus import AgentManifest, Nebelus, NebelusAPIError

BASE = "https://api.test/api/v1/construction"


@pytest.fixture()
def nb():
    return Nebelus(api_key="sk-test", base_url="https://api.test")


@respx.mock
def test_error_carries_machine_payload(nb):
    respx.post(f"{BASE}/agents/x/deploy/").mock(
        return_value=httpx.Response(400, json={"detail": "disabled", "blocked": "programmatic_deploy"})
    )
    with pytest.raises(NebelusAPIError) as e:
        nb.agents.deploy("x")
    assert e.value.blocked == "programmatic_deploy"
    assert e.value.status_code == 400


@respx.mock
def test_apply_creates_then_updates_only_declared_fields(nb):
    listing = respx.get(f"{BASE}/agents/").mock(return_value=httpx.Response(200, json={"results": []}))
    created = respx.post(f"{BASE}/agents/").mock(
        return_value=httpx.Response(201, json={"id": "a1", "status": "draft", "name": "Bot",
                                               "metadata": {"manifest_id": "m1"}})
    )
    m = AgentManifest(manifest_id="m1", name="Bot", model_id="claude-haiku-4-5")
    agent = nb.apply(m)
    assert agent.id == "a1" and created.called
    sent = created.calls.last.request.content
    assert b"manifest_id" in sent and b"claude-haiku-4-5" in sent

    # Second apply: agent exists; the portal set a system_message we did NOT declare —
    # apply must not send (and therefore not clobber) it.
    listing.mock(return_value=httpx.Response(200, json={"results": [{"id": "a1"}]}))
    respx.get(f"{BASE}/agents/a1/").mock(
        return_value=httpx.Response(200, json={
            "id": "a1", "status": "draft", "name": "Bot", "model_id": "claude-haiku-4-5",
            "system_message": "PORTAL EDIT — keep me", "metadata": {"manifest_id": "m1"}})
    )
    m2 = AgentManifest(manifest_id="m1", name="Bot renamed", model_id="claude-haiku-4-5")
    patched = respx.patch(f"{BASE}/agents/a1/").mock(
        return_value=httpx.Response(200, json={"id": "a1", "status": "draft", "name": "Bot renamed",
                                               "metadata": {"manifest_id": "m1"}})
    )
    nb.apply(m2)
    body = patched.calls.last.request.content
    assert b"Bot renamed" in body and b"system_message" not in body


@respx.mock
def test_diff_reports_in_sync(nb):
    respx.get(f"{BASE}/agents/").mock(return_value=httpx.Response(200, json={"results": [{"id": "a1"}]}))
    respx.get(f"{BASE}/agents/a1/").mock(
        return_value=httpx.Response(200, json={"id": "a1", "status": "draft", "name": "Bot",
                                               "metadata": {"manifest_id": "m1", "portal_extra": True}})
    )
    m = AgentManifest(manifest_id="m1", name="Bot")
    assert nb.diff(m) == {}


@respx.mock
def test_graph_ops_and_probe(nb):
    op = respx.post(f"{BASE}/agents/a1/graph/").mock(return_value=httpx.Response(200, json={"ok": True}))
    nb.graph("a1").add_edge("a", "b")
    import json as _json

    assert _json.loads(op.calls.last.request.content) == {"op": "add_edge", "from_node": "a", "to_node": "b"}
    respx.post(f"{BASE}/agents/a1/probe/").mock(
        return_value=httpx.Response(200, json={"status": "completed", "reply": "OK"}))
    assert nb.agents.probe("a1", "hi").reply == "OK"
