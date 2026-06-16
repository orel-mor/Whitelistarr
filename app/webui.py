"""Web UI: schema-driven config editor + action endpoints (same FastAPI app/port).

Decoupled from the running components via injected callables (``on_sweep`` etc.) so it
is easy to test and the app can serve the UI even when nothing is configured yet.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError

from app.config import Settings
from app.config_schema import CONFIG_SCHEMA, field_keys, secret_keys

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
_MEDIA = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}

# The web UI ships exactly these static assets. Map each name to a pre-built,
# constant path so a request only ever looks one up by key — the user-provided
# name never enters a filesystem path expression, so it can't traverse out of
# STATIC_DIR or read arbitrary files.
_STATIC_FILES = {name: STATIC_DIR / name for name in ("index.html", "app.js", "style.css")}


def _static_response(name: str) -> Response:
    """Serve a packaged static file by name from the fixed allowlist."""
    path = _STATIC_FILES.get(name)
    if path is None or not path.is_file():
        return Response(status_code=404)
    return FileResponse(path, media_type=_MEDIA.get(path.suffix, "text/plain"))


def create_webui_router(
    settings: Settings,
    store: Any,
    on_sweep: Callable[[], dict] | None = None,
    on_reverse: Callable[[], dict] | None = None,
    on_test: Callable[[], bool] | None = None,
) -> APIRouter:
    router = APIRouter()
    keys = set(field_keys())
    secrets = set(secret_keys())

    @router.get("/")
    async def index() -> Response:
        return _static_response("index.html")

    @router.get("/static/{name}")
    async def static_file(name: str) -> Response:
        return _static_response(name)

    @router.get("/api/schema")
    async def schema() -> dict:
        return {"groups": CONFIG_SCHEMA}

    @router.get("/api/config")
    async def get_config() -> dict:
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
            tentative = Settings(**candidate)
        except ValidationError as exc:
            messages = [f"{e['loc'][0]}: {e['msg']}" for e in exc.errors()]
            return JSONResponse({"errors": messages}, status_code=422)

        store.save(candidate)
        return {"ok": True, "restart_required": True, "warnings": tentative.runtime_errors()}

    @router.post("/api/actions/sweep")
    async def action_sweep() -> Response:
        if on_sweep is None:
            return JSONResponse({"error": "Not configured"}, status_code=409)
        return JSONResponse(on_sweep())

    @router.post("/api/actions/reverse")
    async def action_reverse(request: Request) -> Response:
        if on_reverse is None:
            return JSONResponse({"error": "Not configured"}, status_code=409)
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = {}
        if not body.get("confirm"):
            return JSONResponse({"error": "confirm required"}, status_code=400)
        return JSONResponse(on_reverse())

    @router.post("/api/actions/test-notification")
    async def action_test() -> Response:
        if on_test is None:
            return JSONResponse({"error": "Not configured"}, status_code=409)
        return JSONResponse({"ok": bool(on_test())})

    return router
