"""`nebelus login` — the OAuth 2.0 device-authorization flow (RFC 8628) + a local
token store. No browser redirect, no secrets: the CLI shows a short code, you
approve it in the browser, and the tokens land in ~/.nebelus/credentials.json (0600).

The transport uses these tokens when NEBELUS_API_KEY isn't set, and refreshes on 401.
"""

from __future__ import annotations

import json
import os
import time
import webbrowser
from pathlib import Path

import httpx

DEFAULT_BASE_URL = "https://api.nebelus.ai"
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
_UA = {"User-Agent": "nebelus-cli"}


def config_dir() -> Path:
    return Path(os.environ.get("NEBELUS_CONFIG_DIR") or (Path.home() / ".nebelus"))


def creds_path() -> Path:
    return config_dir() / "credentials.json"


def load_credentials() -> dict | None:
    try:
        return json.loads(creds_path().read_text())
    except Exception:  # noqa: BLE001 — missing/corrupt store = not logged in
        return None


def save_credentials(data: dict) -> None:
    config_dir().mkdir(parents=True, exist_ok=True)
    p = creds_path()
    p.write_text(json.dumps(data, indent=2))
    try:
        os.chmod(p, 0o600)  # tokens are secrets — owner-only
    except OSError:
        pass


def clear_credentials() -> bool:
    try:
        creds_path().unlink()
        return True
    except FileNotFoundError:
        return False


def _base(base_url: str | None) -> str:
    return (base_url or os.environ.get("NEBELUS_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


def _register_client(base: str) -> str:
    # Dynamic client registration (RFC 7591) — a public client; device flow ignores
    # redirect_uris but registration requires the field.
    r = httpx.post(
        f"{base}/oauth/register/",
        json={"client_name": "Nebelus CLI", "redirect_uris": ["http://localhost"]},
        headers=_UA, timeout=30,
    )
    r.raise_for_status()
    return r.json()["client_id"]


def refresh_access_token(base: str, refresh_token: str, client_id: str | None) -> dict | None:
    """Rotate the token pair. Returns the new token body, or None if refresh failed
    (revoked/expired) — the caller then prompts for a fresh `nebelus login`."""
    try:
        r = httpx.post(
            f"{base}/oauth/token/",
            json={"grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": client_id or ""},
            headers=_UA, timeout=30,
        )
    except httpx.HTTPError:
        return None
    return r.json() if r.status_code == 200 else None


def device_login(base_url: str | None = None, *, open_browser: bool = True, printer=print) -> dict:
    """Run the device flow to completion; persist and return the credentials."""
    base = _base(base_url)
    client_id = _register_client(base)

    dev = httpx.post(f"{base}/oauth/device/", json={"client_id": client_id}, headers=_UA, timeout=30)
    dev.raise_for_status()
    d = dev.json()
    verify = d.get("verification_uri_complete") or d["verification_uri"]

    printer(f"\n  Visit: {verify}")
    printer(f"  Code:  {d['user_code']}\n")
    if open_browser:
        try:
            webbrowser.open(verify)
        except Exception:  # noqa: BLE001,S110 — headless is fine; the URL is printed
            pass
    printer("Waiting for you to authorize in the browser…")

    interval = max(1, int(d.get("interval", 5)))
    deadline = time.time() + int(d.get("expires_in", 900))
    while time.time() < deadline:
        time.sleep(interval)
        tok = httpx.post(
            f"{base}/oauth/token/",
            json={"grant_type": DEVICE_GRANT, "device_code": d["device_code"], "client_id": client_id},
            headers=_UA, timeout=30,
        )
        if tok.status_code == 200:
            body = tok.json()
            creds = {
                "base_url": base, "client_id": client_id,
                "access_token": body["access_token"], "refresh_token": body.get("refresh_token"),
            }
            save_credentials(creds)
            return creds
        err = None
        try:
            err = tok.json().get("error")
        except Exception:  # noqa: BLE001,S110 — non-JSON error body → treat as generic failure
            pass
        if err == "authorization_pending":
            continue
        if err == "slow_down":
            interval += 5
            continue
        raise RuntimeError(f"Login failed: {err or tok.status_code}")
    raise RuntimeError("Login timed out — run `nebelus login` again.")
