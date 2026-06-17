"""Shared HTTP helpers for the *arr / Overseerr / Tautulli REST clients."""

from __future__ import annotations

from typing import Any

import httpx
from httpx import USE_CLIENT_DEFAULT

DEFAULT_TIMEOUT = 30.0
# Short timeout for liveness probes so a dead service fails fast (vs the 30s default).
PROBE_TIMEOUT = 4.0


class HttpClient:
    """Thin httpx wrapper with retry on transient errors and JSON helpers."""

    def __init__(
        self,
        base_url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        retries: int = 2,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._retries = retries
        transport = httpx.HTTPTransport(retries=retries)
        self._client = httpx.Client(
            base_url=self.base_url,
            headers=headers or {},
            timeout=timeout,
            transport=transport,
        )

    def get_json(
        self, path: str, params: dict[str, Any] | None = None, timeout: Any = USE_CLIENT_DEFAULT
    ) -> Any:
        resp = self._client.get(path, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
