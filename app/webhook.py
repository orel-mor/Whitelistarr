"""FastAPI webhook receiver.

Accepts two trigger sources, both optional:
- Seerr/Overseerr 'Media Available' (JSON body) at ``WEBHOOK_PATH``.
- Plex 'library.new' (multipart form with a ``payload`` field) at ``PLEX_WEBHOOK_PATH``.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request, Response
from starlette.concurrency import run_in_threadpool

from app import __version__

log = logging.getLogger(__name__)

# Seerr media_type -> our Plex-domain media_type.
_MEDIA_TYPE = {"movie": "movie", "tv": "show"}


@dataclass(frozen=True)
class SeerrEvent:
    notification_type: str
    media_type: str | None
    tmdb_id: int | None
    tvdb_id: int | None


def _as_int(value: Any) -> int | None:
    if value in (None, "", "null"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class PlexEvent:
    event: str
    rating_key: str | None


def parse_plex_payload(payload: dict[str, Any]) -> PlexEvent:
    """Parse a Plex webhook body into a PlexEvent."""
    metadata = payload.get("Metadata") or {}
    rating_key = metadata.get("ratingKey")
    return PlexEvent(
        event=payload.get("event", ""),
        rating_key=str(rating_key) if rating_key is not None else None,
    )


def parse_seerr_payload(payload: dict[str, Any]) -> SeerrEvent:
    """Parse a Seerr/Overseerr webhook body defensively into a SeerrEvent."""
    media = payload.get("media") or {}
    raw_type = media.get("media_type") or media.get("mediaType")
    return SeerrEvent(
        notification_type=payload.get("notification_type", ""),
        media_type=_MEDIA_TYPE.get(raw_type) if raw_type else None,
        tmdb_id=_as_int(media.get("tmdbId")),
        tvdb_id=_as_int(media.get("tvdbId")),
    )


def create_app(
    get_sync: Callable[[], Any],
    webhook_path: str = "/webhook/seerr",
    plex_webhook_path: str = "/webhook/plex",
    secret: str = "",
    lifespan: Any | None = None,
    webui_router: Any | None = None,
) -> FastAPI:
    app = FastAPI(title="Whitelistarr", lifespan=lifespan)
    if webui_router is not None:
        app.include_router(webui_router)

    def _secret_ok(request: Request) -> bool:
        if not secret:
            return True
        provided = request.query_params.get("token") or request.headers.get(
            "X-Webhook-Secret"
        )
        return provided == secret

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.post(webhook_path)
    async def seerr_webhook(request: Request) -> Response:
        sync = get_sync()
        if sync is None:
            return Response(status_code=503)
        if not _secret_ok(request):
            log.warning("Rejected Seerr webhook with invalid secret")
            return Response(status_code=401)

        try:
            payload = await request.json()
        except Exception:  # noqa: BLE001 - bad body shouldn't 500
            return Response(status_code=400)

        event = parse_seerr_payload(payload)

        if event.notification_type != "MEDIA_AVAILABLE":
            log.debug("Ignoring notification_type=%s", event.notification_type)
            return Response(status_code=200)
        if not event.media_type or (event.tmdb_id is None and event.tvdb_id is None):
            log.warning("MEDIA_AVAILABLE without usable media ids: %s", payload)
            return Response(status_code=200)

        log.info(
            "Webhook: %s tmdb=%s tvdb=%s", event.media_type, event.tmdb_id, event.tvdb_id
        )
        await run_in_threadpool(
            sync.sync_by_ids,
            event.media_type,
            tmdb_id=event.tmdb_id,
            tvdb_id=event.tvdb_id,
        )
        return Response(status_code=200)

    @app.post(plex_webhook_path)
    async def plex_webhook(request: Request) -> Response:
        sync = get_sync()
        if sync is None:
            return Response(status_code=503)
        if not _secret_ok(request):
            log.warning("Rejected Plex webhook with invalid secret")
            return Response(status_code=401)

        # Plex posts multipart/form-data with a JSON string in the `payload` field.
        try:
            form = await request.form()
        except Exception:  # noqa: BLE001 - bad body shouldn't 500
            return Response(status_code=400)
        raw = form.get("payload")
        if not raw:
            return Response(status_code=200)
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            return Response(status_code=400)

        event = parse_plex_payload(payload)
        if event.event != "library.new" or not event.rating_key:
            log.debug("Ignoring Plex event=%s", event.event)
            return Response(status_code=200)

        log.info("Plex webhook: library.new ratingKey=%s", event.rating_key)
        await run_in_threadpool(sync.sync_by_rating_key, event.rating_key)
        return Response(status_code=200)

    return app
