"""HTTP transport: auth, errors-as-exceptions with the API's machine payload intact."""

from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_BASE_URL = "https://api.nebelus.ai"
API_PREFIX = "/api/v1/construction"


class NebelusAPIError(Exception):
    """Any non-2xx from the API. Carries the FULL machine-readable payload:
    `detail` (human reason), and when present `envelope` ({blocked, requested,
    allowed_hint}), `blocked` (opt-in gates), etc."""

    def __init__(self, status_code: int, payload: Any):
        self.status_code = status_code
        self.payload = payload if isinstance(payload, dict) else {"detail": str(payload)}
        super().__init__(f"[{status_code}] {self.payload.get('detail') or self.payload}")

    @property
    def detail(self) -> str:
        return str(self.payload.get("detail", ""))

    @property
    def envelope(self) -> dict | None:
        """The Build Envelope refusal payload, when the refusal came from one."""
        return self.payload.get("envelope")

    @property
    def blocked(self) -> str | None:
        return self.payload.get("blocked")


class NotFound(NebelusAPIError):
    pass


class Transport:
    def __init__(self, api_key: str | None = None, base_url: str | None = None, timeout: float = 60.0):
        self.api_key = api_key or os.environ.get("NEBELUS_API_KEY") or ""
        if not self.api_key:
            raise ValueError("No API key. Pass api_key= or set NEBELUS_API_KEY.")
        self.base_url = (base_url or os.environ.get("NEBELUS_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self._client = httpx.Client(
            base_url=f"{self.base_url}{API_PREFIX}",
            headers={"Authorization": f"Bearer {self.api_key}", "User-Agent": "nebelus-python/0.1.0"},
            timeout=timeout,
        )

    def request(self, method: str, path: str, *, json: Any = None, params: Any = None) -> Any:
        r = self._client.request(method, path, json=json, params=params)
        body: Any
        try:
            body = r.json()
        except Exception:  # noqa: BLE001
            body = r.text
        if r.status_code == 404:
            raise NotFound(r.status_code, body)
        if r.status_code >= 400:
            raise NebelusAPIError(r.status_code, body)
        return body

    def close(self) -> None:
        self._client.close()
