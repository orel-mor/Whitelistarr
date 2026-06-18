"""Web UI: schema-driven config editor + action endpoints (same FastAPI app/port).

Decoupled from the running components via injected callables (``on_sweep`` etc.) so it
is easy to test and the app can serve the UI even when nothing is configured yet.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.config import Settings
from app.config_schema import CONFIG_SCHEMA, field_keys, secret_keys

log = logging.getLogger(__name__)

# Connection probes run off the event loop, each bounded by this many seconds, and
# the combined result is cached briefly so a 10s status poll doesn't hammer the
# upstream services (or stall when one is unreachable).
PROBE_TIMEOUT = 5.0
CONN_CACHE_TTL = 8.0
# How long a Plex auth token from an in-progress sign-in is kept server-side
# before an abandoned flow's token is purged.
PIN_TTL = 600.0

STATIC_DIR = Path(__file__).parent / "static"
_MEDIA = {
    ".html": "text/html",
    ".js": "text/javascript",
    ".css": "text/css",
    ".svg": "image/svg+xml",
}

# The web UI ships exactly these static assets, keyed by their request path. The
# user-provided path is only ever used as a dict key, so it can't traverse out of
# STATIC_DIR or read arbitrary files.
_STATIC_NAMES = (
    "index.html",
    "logo.svg",
    "vendor/alpine.min.js",
    "css/style.css",
    "js/api.js",
    "js/router.js",
    "js/store.js",
    "js/helpers.js",
    "js/app.js",
)
_STATIC_FILES = {name: STATIC_DIR / name for name in _STATIC_NAMES}


def _make_test_client(service: str, url: str, key: str) -> tuple[Any, bool]:
    """Build a throwaway client from posted credentials for a one-off probe.

    Returns ``(client, is_ephemeral)``. Plex isn't built here (it connects via the
    sign-in flow, not a URL/key pair). Both a URL and key are required; otherwise
    ``(None, False)`` so the caller falls back to the live, saved component (which
    still holds the previously saved credentials).
    """
    if not url or not key:
        return None, False
    if service == "radarr":
        from app.clients.radarr import RadarrClient

        return RadarrClient(url, key), True
    if service == "sonarr":
        from app.clients.sonarr import SonarrClient

        return SonarrClient(url, key), True
    if service == "seerr":
        from app.clients.seerr import SeerrClient

        return SeerrClient(url, key), True
    if service == "tautulli":
        from app.clients.tautulli import TautulliClient

        return TautulliClient(url, key), True
    return None, False


def _static_response(name: str) -> Response:
    """Serve a packaged static file by name from the fixed allowlist."""
    path = _STATIC_FILES.get(name)
    if path is None or not path.is_file():
        return Response(status_code=404)
    return FileResponse(path, media_type=_MEDIA.get(path.suffix, "text/plain"))


def create_webui_router(
    runtime: Any,
    store: Any,
    plex_auth: Any | None = None,
) -> APIRouter:
    router = APIRouter()
    keys = set(field_keys())
    secrets = set(secret_keys())

    def _log_action(action: str, summary: dict[str, Any]) -> None:
        # Manual UI actions always appear in the activity log (history=True), even
        # when they change nothing. Guarded so test runtimes without a tracker work.
        tracker = getattr(runtime, "tracker", None)
        if tracker is not None:
            tracker.record(action, summary, history=True)

    @router.get("/")
    async def index() -> Response:
        return _static_response("index.html")

    @router.get("/static/{name:path}")
    async def static_file(name: str) -> Response:
        return _static_response(name)

    @router.get("/api/schema")
    async def schema() -> dict:
        return {"groups": CONFIG_SCHEMA}

    @router.get("/api/config")
    async def get_config() -> dict:
        settings = runtime.settings
        saved = store.load() if store and store.exists() else {}
        values: dict[str, Any] = {}
        for key in keys:
            current = saved.get(key, getattr(settings, key, ""))
            if key in secrets:
                values[key] = {"set": bool(current)}
            else:
                values[key] = current
        return {"values": values, "errors": settings.runtime_errors()}

    @router.post("/api/config")
    async def save_config(request: Request) -> Response:
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            return JSONResponse({"errors": ["Invalid JSON body"]}, status_code=400)

        candidate = store.load() if store and store.exists() else {}
        for key, value in body.items():
            if key in keys:
                candidate[key] = value

        try:
            new_settings = Settings(**candidate)
        except ValidationError as exc:
            messages = [f"{e['loc'][0]}: {e['msg']}" for e in exc.errors()]
            return JSONResponse({"errors": messages}, status_code=422)

        store.save(candidate)
        result = runtime.reload(new_settings)
        return {
            "ok": result.ok,
            "error": result.error,
            "restart_required": result.restart_required,
            "restart_fields": result.restart_fields or [],
            "warnings": new_settings.runtime_errors(),
        }

    @router.post("/api/actions/sweep")
    async def action_sweep() -> Response:
        ls = runtime.label_sync
        if ls is None:
            return JSONResponse({"error": "Not configured"}, status_code=409)
        result = ls.sweep()
        _log_action("sweep", result)
        return JSONResponse(result)

    @router.post("/api/actions/reverse")
    async def action_reverse(request: Request) -> Response:
        ls = runtime.label_sync
        if ls is None:
            return JSONResponse({"error": "Not configured"}, status_code=409)
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = {}
        if not body.get("confirm"):
            return JSONResponse({"error": "confirm required"}, status_code=400)
        result = ls.reverse_sweep()
        _log_action("reverse", result)
        return JSONResponse(result)

    @router.post("/api/actions/test-notification")
    async def action_test() -> Response:
        from app.main import _send_test_notification

        settings = runtime.settings
        if not settings.apprise_url_list:
            return JSONResponse({"error": "Not configured"}, status_code=409)
        ok = bool(_send_test_notification(settings))
        _log_action("test-notification", {"ok": ok})
        return JSONResponse({"ok": ok})

    _PROBE_SERVICES = ("plex", "radarr", "sonarr", "seerr", "tautulli")
    _conn_cache: dict[str, Any] = {"at": 0.0, "data": None}

    async def _probe(name: str, client: Any) -> tuple[str, dict]:
        # Run the blocking client.check() off the event loop and bound it, so a
        # dead service can't stall the loop or the status poll.
        try:
            result = await asyncio.wait_for(run_in_threadpool(client.check), PROBE_TIMEOUT)
            return name, result
        except TimeoutError:
            return name, {"ok": False, "detail": "timed out"}
        except Exception:  # noqa: BLE001 - log server-side; never surface exception text
            log.warning("Connection probe error for %s", name, exc_info=True)
            return name, {"ok": False, "detail": "error"}

    async def _connections(comps: Any) -> dict[str, dict]:
        now = time.monotonic()
        if _conn_cache["data"] is not None and now - _conn_cache["at"] < CONN_CACHE_TTL:
            return _conn_cache["data"]
        clients = [(n, getattr(comps, n, None)) for n in _PROBE_SERVICES]
        pairs = await asyncio.gather(*[_probe(n, c) for n, c in clients if c is not None])
        data = dict(pairs)
        _conn_cache.update(at=now, data=data)
        return data

    @router.get("/api/status")
    async def status() -> dict:
        settings = runtime.settings
        comps = runtime.components
        jobs = []
        connections: dict[str, Any] = {}
        if comps is not None:
            for job in comps.scheduler.jobs():
                nrt = getattr(job, "next_run_time", None)
                jobs.append(
                    {"name": job.name, "next_run": nrt.isoformat() if hasattr(nrt, "isoformat") else nrt}
                )
            connections = await _connections(comps)
        return {
            "configured": not settings.runtime_errors(),
            "errors": settings.runtime_errors(),
            "jobs": jobs,
            "last": runtime.tracker.snapshot(),
            "history": runtime.tracker.history(),
            "connections": connections,
            "label_map": settings.label_map,
        }

    @router.get("/api/logs")
    async def logs(after: int = 0, level: str | None = None, tail: int | None = None) -> dict:
        from app.logbuffer import LOG_BUFFER

        records = LOG_BUFFER.records(after=after, level=level, tail=tail)
        last_id = records[-1]["id"] if records else after
        return {"lines": records, "last_id": last_id}

    @router.post("/api/connections/test/{service}")
    async def connection_test(service: str, request: Request) -> Response:
        if service not in _PROBE_SERVICES:
            return JSONResponse({"error": "Unknown service"}, status_code=409)
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001 - empty/invalid body => probe saved config
            body = {}

        # Prefer the credentials typed into the form so the user can test before
        # saving; fall back to the live (saved) component when none are posted.
        url = (body.get("url") or "").strip()
        key = (body.get("api_key") or body.get("token") or "").strip()
        client, ephemeral = _make_test_client(service, url, key)
        if client is None:
            comps = getattr(runtime, "components", None)
            client = getattr(comps, service, None) if comps is not None else None
        if client is None:
            return JSONResponse({"error": "Service not configured"}, status_code=409)

        try:
            _, result = await _probe(service, client)
        finally:
            if ephemeral:
                with contextlib.suppress(Exception):
                    await run_in_threadpool(client.close)
        return JSONResponse(result)

    # pin_id -> (auth token, stored_at). Held server-side only (never sent to the
    # browser) and purged after PIN_TTL so an abandoned sign-in doesn't linger.
    _pin_tokens: dict[str, tuple[str, float]] = {}

    def _store_pin_token(pin_id: str, token: str) -> None:
        _pin_tokens[str(pin_id)] = (token, time.monotonic())

    def _get_pin_token(pin_id: str) -> str | None:
        entry = _pin_tokens.get(str(pin_id))
        if entry is None:
            return None
        token, ts = entry
        if time.monotonic() - ts > PIN_TTL:
            _pin_tokens.pop(str(pin_id), None)
            return None
        return token

    def _auth() -> Any:
        if plex_auth is not None:
            return plex_auth
        from app.clients.plex_auth import PlexAuth

        return PlexAuth(client_id=runtime.settings.plex_client_id)

    @router.post("/api/plex/pin")
    async def plex_pin() -> Response:
        return JSONResponse(_auth().create_pin())

    @router.get("/api/plex/pin/{pin_id}")
    async def plex_pin_poll(pin_id: str) -> Response:
        token = _auth().poll_pin(pin_id)
        if token:
            _store_pin_token(pin_id, token)
        return JSONResponse({"authorized": bool(token)})

    @router.get("/api/plex/servers")
    async def plex_servers(pin_id: str) -> Response:
        token = _get_pin_token(pin_id)
        if not token:
            return JSONResponse({"error": "Not authorized yet"}, status_code=409)
        return JSONResponse({"servers": _auth().list_servers(token)})

    @router.post("/api/plex/apply")
    async def plex_apply(request: Request) -> Response:
        body = await request.json()
        pin_id = str(body.get("pin_id", ""))
        uri = body.get("uri")
        token = _get_pin_token(pin_id)
        if not token or not uri:
            return JSONResponse({"error": "Missing token or uri"}, status_code=400)

        candidate = store.load() if store and store.exists() else {}
        candidate["plex_url"] = uri
        candidate["plex_token"] = token
        store.save(candidate)
        _pin_tokens.pop(pin_id, None)  # one-time use

        result = runtime.reload(Settings(**candidate))
        return JSONResponse(
            {"ok": result.ok, "error": result.error,
             "restart_required": result.restart_required}
        )

    return router
