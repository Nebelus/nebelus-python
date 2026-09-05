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
        return_value=httpx.Response(
            201, json={"id": "a1", "status": "draft", "name": "Bot", "metadata": {"manifest_id": "m1"}}
        )
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
        return_value=httpx.Response(
            200,
            json={
                "id": "a1",
                "status": "draft",
                "name": "Bot",
                "model_id": "claude-haiku-4-5",
                "system_message": "PORTAL EDIT — keep me",
                "metadata": {"manifest_id": "m1"},
            },
        )
    )
    m2 = AgentManifest(manifest_id="m1", name="Bot renamed", model_id="claude-haiku-4-5")
    patched = respx.patch(f"{BASE}/agents/a1/").mock(
        return_value=httpx.Response(
            200, json={"id": "a1", "status": "draft", "name": "Bot renamed", "metadata": {"manifest_id": "m1"}}
        )
    )
    nb.apply(m2)
    body = patched.calls.last.request.content
    assert b"Bot renamed" in body and b"system_message" not in body


@respx.mock
def test_diff_reports_in_sync(nb):
    respx.get(f"{BASE}/agents/").mock(return_value=httpx.Response(200, json={"results": [{"id": "a1"}]}))
    respx.get(f"{BASE}/agents/a1/").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "a1",
                "status": "draft",
                "name": "Bot",
                "metadata": {"manifest_id": "m1", "portal_extra": True},
            },
        )
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
        return_value=httpx.Response(200, json={"status": "completed", "reply": "OK"})
    )
    assert nb.agents.probe("a1", "hi").reply == "OK"


def test_in_sync_ignores_server_normalization_and_other_writers():
    from nebelus.client import Nebelus as N

    want = {"nodes": [{"name": "a", "config": {"x": 1}}], "edges": []}
    have = {"nodes": [{"name": "a", "config": {"x": 1}}], "edges": [], "conditional_edges": []}
    assert N._in_sync(have, want) is True
    assert N._in_sync({"nodes": [], "edges": []}, want) is False


# --------------------------------------------------------------- export / CLI


def test_export_to_code_round_trips_through_manifest():
    from nebelus.export import export_to_code
    from nebelus.models import Agent

    agent = Agent.model_validate(
        {
            "id": "a-1",
            "name": "Support Agent",
            "status": "active",
            "model_id": "claude-haiku-4-5",
            "pattern_type": "react",
            "system_message": "Be helpful.",
            "needed_tools": ["web_search"],
            "metadata": {"manifest_id": "support-v1", "other_writer_key": True},
            "description": "",
            "pattern_config": {},
        }
    )
    src = export_to_code(agent)
    ns = {}
    exec(compile(src, "<exported>", "exec"), ns)  # noqa: S102 — exported source IS the artifact under test
    m = ns["manifest"]
    assert m.manifest_id == "support-v1"
    fields = m.to_fields()
    assert fields["name"] == "Support Agent"
    assert fields["needed_tools"] == ["web_search"]
    # empty/None fields are UNDECLARED — merge contract keeps them out.
    assert "description" not in fields
    assert "pattern_config" not in fields
    # export never claims fields it can't manage (status is server-owned).
    assert "status" not in fields


def test_export_falls_back_to_agent_id_when_no_manifest_id():
    from nebelus.export import export_to_code
    from nebelus.models import Agent

    agent = Agent.model_validate({"id": "a-2", "name": "X", "status": "draft", "metadata": {}})
    assert "exported-a-2" in export_to_code(agent)


def test_cli_apply_and_diff(tmp_path, respx_mock, monkeypatch):
    import json

    from nebelus.cli import main

    monkeypatch.setenv("NEBELUS_API_KEY", "test-key")
    monkeypatch.setenv("NEBELUS_BASE_URL", "https://api.test")

    manifest_py = tmp_path / "m.py"
    manifest_py.write_text(
        "from nebelus import AgentManifest\n"
        "manifest = AgentManifest(manifest_id='cli-v1', name='CLI Agent', model_id='claude-haiku-4-5')\n"
    )
    respx_mock.get(f"{BASE}/agents/").respond(200, json={"results": []})
    respx_mock.post(f"{BASE}/agents/").respond(
        201, json={"id": "a-9", "name": "CLI Agent", "status": "draft", "metadata": {"manifest_id": "cli-v1"}}
    )
    assert main(["apply", str(manifest_py)]) == 0

    manifest_json = tmp_path / "m.json"
    manifest_json.write_text(json.dumps({"manifest_id": "cli-v1", "name": "CLI Agent"}))
    respx_mock.get(f"{BASE}/agents/").respond(200, json={"results": [{"id": "a-9"}]})
    respx_mock.get(f"{BASE}/agents/a-9/").respond(
        200, json={"id": "a-9", "name": "CLI Agent", "status": "draft", "metadata": {"manifest_id": "cli-v1"}}
    )
    assert main(["diff", str(manifest_json)]) == 0


def test_cli_error_paths_exit_nonzero(capsys, respx_mock, monkeypatch):
    from nebelus.cli import main

    monkeypatch.setenv("NEBELUS_API_KEY", "test-key")
    monkeypatch.setenv("NEBELUS_BASE_URL", "https://api.test")

    respx_mock.get(f"{BASE}/describe/").respond(403, json={"detail": "Missing scope", "blocked": "programmatic_access"})
    assert main(["describe"]) == 1
    err = capsys.readouterr().err
    assert "Missing scope" in err and "programmatic_access" in err


# ------------------------------------------------------------- from_langgraph


def _lg_graph():
    from typing import TypedDict

    from langgraph.graph import END, START, StateGraph

    class S(TypedDict):
        x: str

    g = StateGraph(S)
    g.add_node("triage", lambda s: s)
    g.add_node("billing", lambda s: s)
    g.add_node("general", lambda s: s)
    g.add_edge(START, "triage")
    g.add_conditional_edges("triage", lambda s: "billing", {"billing": "billing", "general": "general"})
    g.add_edge("billing", END)
    g.add_edge("general", END)
    return g


AGENT_NODE = {"type": "agent", "config": {"system_prompt": "x", "model_id": "claude-haiku-4-5"}}


def test_from_langgraph_complete_translation():
    from nebelus.langgraph import from_langgraph

    t = from_langgraph(
        _lg_graph(),
        {"triage": AGENT_NODE, "billing": AGENT_NODE, "general": AGENT_NODE},
        router_map={
            "triage": {
                "conditions": [{"expression": "'billing' in str(state.get('triage_out',''))", "target": "billing"}],
                "default_target": "general",
            }
        },
        manifest_id="lg-v1",
        name="LG Triage",
        model_id="claude-haiku-4-5",
    )
    assert t.complete and t.manifest is not None
    names = [n["name"] for n in t.pattern_config["nodes"]]
    assert names == ["triage", "billing", "general", "triage__router"]
    assert {"from": "triage", "to": "triage__router"} in t.pattern_config["edges"]
    assert {"from": "__start__", "to": "triage"} in t.pattern_config["edges"]
    assert t.manifest.to_fields()["pattern_type"] == "workflow"


def test_from_langgraph_diagnostics_block_incomplete_translation():
    from nebelus.langgraph import from_langgraph

    t = from_langgraph(_lg_graph(), {"triage": AGENT_NODE}, manifest_id="lg-v2", name="LG", model_id="claude-haiku-4-5")
    assert not t.complete and t.manifest is None
    joined = " ".join(t.diagnostics)
    assert "'billing'" in joined and "'general'" in joined  # unmapped nodes named
    assert "router_map" in joined  # branch named
    assert "MCP server or custom API endpoint" in joined  # the honest escape hatch


def test_from_langgraph_flags_unrouted_branch_target():
    from nebelus.langgraph import from_langgraph

    t = from_langgraph(
        _lg_graph(),
        {"triage": AGENT_NODE, "billing": AGENT_NODE, "general": AGENT_NODE},
        router_map={"triage": {"conditions": [], "default_target": "general"}},
        manifest_id="lg-v3",
        name="LG",
        model_id="claude-haiku-4-5",
    )
    # advisory, not blocking: manifest still produced, gap still named.
    assert t.complete
    assert any("'billing'" in d and "never routes" in d for d in t.diagnostics)
