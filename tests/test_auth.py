"""`nebelus login` device flow + the transport's stored-credential fallback."""

import os

import httpx
import pytest
import respx

from nebelus import _auth
from nebelus._transport import Transport

BASE = "https://api.test"


@pytest.fixture()
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("NEBELUS_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("NEBELUS_API_KEY", raising=False)
    monkeypatch.delenv("NEBELUS_BASE_URL", raising=False)
    return tmp_path


def test_credentials_roundtrip_and_perms(cfg):
    assert _auth.load_credentials() is None
    _auth.save_credentials({"access_token": "nbo_x", "base_url": BASE})
    assert _auth.load_credentials()["access_token"] == "nbo_x"
    assert oct(os.stat(_auth.creds_path()).st_mode)[-3:] == "600"  # owner-only
    assert _auth.clear_credentials() is True
    assert _auth.load_credentials() is None


@respx.mock
def test_device_login_persists_tokens(cfg, monkeypatch):
    monkeypatch.setattr(_auth.time, "sleep", lambda s: None)  # no real waiting
    respx.post(f"{BASE}/oauth/register/").mock(return_value=httpx.Response(201, json={"client_id": "cid"}))
    respx.post(f"{BASE}/oauth/device/").mock(return_value=httpx.Response(200, json={
        "device_code": "dc", "user_code": "ABCD-EFGH",
        "verification_uri": f"{BASE}/oauth/device/verify/",
        "verification_uri_complete": f"{BASE}/oauth/device/verify/?user_code=ABCD-EFGH",
        "interval": 1, "expires_in": 60,
    }))
    respx.post(f"{BASE}/oauth/token/").mock(side_effect=[
        httpx.Response(400, json={"error": "authorization_pending"}),
        httpx.Response(200, json={"access_token": "nbo_a", "refresh_token": "nbr_b"}),
    ])
    creds = _auth.device_login(base_url=BASE, open_browser=False, printer=lambda *a: None)
    assert creds["access_token"] == "nbo_a" and creds["client_id"] == "cid"
    assert _auth.load_credentials()["refresh_token"] == "nbr_b"


@respx.mock
def test_transport_uses_stored_token_and_refreshes_on_401(cfg):
    _auth.save_credentials({"base_url": BASE, "client_id": "cid", "access_token": "nbo_old", "refresh_token": "nbr_r"})
    route = respx.get(f"{BASE}/api/v1/construction/describe/").mock(side_effect=[
        httpx.Response(401, json={"detail": "expired"}),
        httpx.Response(200, json={"ok": True}),
    ])
    respx.post(f"{BASE}/oauth/token/").mock(
        return_value=httpx.Response(200, json={"access_token": "nbo_new", "refresh_token": "nbr_r2"})
    )
    t = Transport()  # no api key → stored creds
    try:
        assert t.request("GET", "/describe/") == {"ok": True}
        assert route.call_count == 2  # 401, then retry after refresh
        assert _auth.load_credentials()["access_token"] == "nbo_new"  # rotated + persisted
    finally:
        t.close()


def test_transport_without_credentials_raises(cfg):
    with pytest.raises(ValueError, match="nebelus login"):
        Transport()


def test_api_key_still_wins_over_stored_creds(cfg):
    _auth.save_credentials({"base_url": BASE, "access_token": "nbo_x"})
    t = Transport(api_key="sk-test", base_url=BASE)
    assert t.api_key == "sk-test" and t._oauth is None  # API key path unchanged
    t.close()
