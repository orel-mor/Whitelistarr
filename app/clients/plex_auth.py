"""Plex 'sign in' via the plex.tv PIN OAuth flow + server discovery.

Plain HTTP against plex.tv (no plexapi server connection). The obtained auth
token is a credential — callers hold it server-side and never expose it to the
browser.
"""

from __future__ import annotations

import platform
from typing import Any
from urllib.parse import urlencode

import httpx

PLEX_TV = "https://plex.tv"
AUTH_APP = "https://app.plex.tv/auth"


class PlexAuth:
    def __init__(self, client_id: str, product: str = "Whitelistarr") -> None:
        self._client_id = client_id
        self._product = product

    def _headers(self) -> dict[str, str]:
        # plex.tv ties the PIN's auth token to the full device context, so the
        # same headers must be sent on create *and* poll or the token is never
        # released. Keep this set in sync across both calls.
        return {
            "Accept": "application/json",
            "X-Plex-Product": self._product,
            "X-Plex-Client-Identifier": self._client_id,
            "X-Plex-Version": "1.0",
            "X-Plex-Platform": platform.system(),
            "X-Plex-Device": platform.machine(),
            "X-Plex-Device-Name": self._product,
        }

    def create_pin(self, forward_url: str | None = None) -> dict[str, Any]:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{PLEX_TV}/api/v2/pins",
                headers=self._headers(),
                data={"strong": "true"},
            )
            resp.raise_for_status()
            pin = resp.json()
        query = {
            "clientID": self._client_id,
            "code": pin["code"],
            "context[device][product]": self._product,
        }
        # forwardUrl sends the popup back to our self-closing page once authorized,
        # so it doesn't linger on Plex's "you're signed in" screen.
        if forward_url:
            query["forwardUrl"] = forward_url
        return {"id": pin["id"], "code": pin["code"], "authUrl": f"{AUTH_APP}#?{urlencode(query)}"}

    def poll_pin(self, pin_id: int | str) -> str | None:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(
                f"{PLEX_TV}/api/v2/pins/{pin_id}", headers=self._headers()
            )
            resp.raise_for_status()
            return resp.json().get("authToken") or None

    def list_servers(self, token: str) -> list[dict[str, Any]]:
        headers = {**self._headers(), "X-Plex-Token": token}
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(
                f"{PLEX_TV}/api/v2/resources",
                headers=headers,
                params={"includeHttps": 1},
            )
            resp.raise_for_status()
            resources = resp.json()
        servers = []
        for r in resources:
            if "server" not in (r.get("provides") or ""):
                continue
            servers.append(
                {
                    "name": r.get("name"),
                    "clientIdentifier": r.get("clientIdentifier"),
                    "connections": [
                        {"uri": c.get("uri"), "local": bool(c.get("local"))}
                        for c in (r.get("connections") or [])
                    ],
                }
            )
        return servers
