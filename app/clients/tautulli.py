"""Tautulli client: read watch history for watched/stale detection."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from httpx import USE_CLIENT_DEFAULT

from app.clients.base import PROBE_TIMEOUT, HttpClient

log = logging.getLogger(__name__)


class TautulliError(RuntimeError):
    pass


class TautulliClient:
    def __init__(self, base_url: str, api_key: str) -> None:
        self._api_key = api_key
        self._http = HttpClient(base_url)

    def _command(self, cmd: str, *, timeout: Any = USE_CLIENT_DEFAULT, **params: Any) -> Any:
        query = {"apikey": self._api_key, "cmd": cmd}
        query.update({k: v for k, v in params.items() if v is not None})
        payload = self._http.get_json("/api/v2", params=query, timeout=timeout)
        response = payload.get("response", {})
        if response.get("result") != "success":
            raise TautulliError(response.get("message") or f"Tautulli {cmd} failed")
        return response.get("data")

    def get_history(
        self,
        rating_key: str | int | None = None,
        user: str | None = None,
        length: int = 100,
    ) -> list[dict[str, Any]]:
        data = self._command(
            "get_history",
            rating_key=rating_key,
            user=user,
            length=length,
        )
        if isinstance(data, dict):
            return data.get("data", [])
        return data or []

    def check(self) -> dict:
        try:
            data = self._command("get_server_info", timeout=PROBE_TIMEOUT)
        except TautulliError:
            return {"ok": False, "detail": "request rejected"}
        except httpx.HTTPStatusError as exc:
            return {"ok": False, "detail": f"HTTP {exc.response.status_code}"}
        except Exception:  # noqa: BLE001
            log.warning("Connection probe failed", exc_info=True)
            return {"ok": False, "detail": "unreachable"}
        name = (data or {}).get("pms_name") or "OK"
        return {"ok": True, "detail": str(name)}

    def close(self) -> None:
        self._http.close()
