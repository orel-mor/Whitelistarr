"""Application entrypoint: wires clients, the labeler, scheduler and webhook."""

from __future__ import annotations

import contextlib
import logging
import os
import threading
from dataclasses import dataclass
from typing import Any

from app import __version__
from app.config import Settings, load_settings
from app.scheduler import Scheduler, build_scheduler

log = logging.getLogger(__name__)


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@dataclass
class Components:
    settings: Settings
    label_sync: Any
    watch_monitor: Any | None
    scheduler: Scheduler


def build_components(settings: Settings) -> Components:
    """Construct clients and services from settings (performs network connect)."""
    from app.clients.notify import Notifier
    from app.clients.plex import PlexClient
    from app.clients.radarr import RadarrClient
    from app.clients.seerr import SeerrClient
    from app.clients.sonarr import SonarrClient
    from app.clients.tautulli import TautulliClient
    from app.core.sync import LabelSync
    from app.core.watch_monitor import WatchMonitor
    from app.state import StateStore

    plex = PlexClient(
        settings.plex_url,
        settings.plex_token,
        settings.sections,
        device_name=settings.plex_device_name,
        client_id=settings.plex_client_id,
    )
    radarr = RadarrClient(settings.radarr_url, settings.radarr_api_key)
    sonarr = SonarrClient(settings.sonarr_url, settings.sonarr_api_key)

    # Shared notifier + state (used by both label and watched/stale notifications).
    notifier = None
    state = None
    if settings.apprise_url_list:
        notifier = Notifier(settings.apprise_url_list, dry_run=settings.dry_run)
        loaded, configured = notifier.server_count(), len(settings.apprise_url_list)
        log.info(
            "Notifications: %d/%d Apprise channel(s) loaded, events=%s",
            loaded,
            configured,
            settings.notify_events,
        )
        if loaded < configured:
            log.warning(
                "%d Apprise URL(s) were rejected — check the URL format.",
                configured - loaded,
            )
    notify_labeled = "labeled" in settings.notify_events and notifier is not None
    if notify_labeled or settings.feature_notify:
        _ensure_parent_dir(settings.state_db_path)
        state = StateStore(settings.state_db_path)

    label_sync = LabelSync(
        plex=plex,
        radarr=radarr,
        sonarr=sonarr,
        label_map=settings.label_map,
        managed=settings.managed_labels,
        mode=settings.label_removal,
        dry_run=settings.dry_run,
        notifier=notifier,
        state=state,
        notify_labeled=notify_labeled,
    )

    watch_monitor = None
    if settings.feature_notify:
        watch_monitor = WatchMonitor(
            overseerr=SeerrClient(settings.seerr_url, settings.seerr_api_key),
            tautulli=TautulliClient(settings.tautulli_url, settings.tautulli_api_key),
            plex=plex,
            notifier=notifier,
            state=state,
            events=settings.notify_events,
            watched_percent=settings.watched_percent,
            stale_after_days=settings.stale_after_days,
            unwatched_after_days=settings.unwatched_after_days,
        )

    scheduler = build_scheduler(
        settings,
        sweep_fn=label_sync.sweep,
        watch_fn=(watch_monitor.scan if watch_monitor else (lambda: None)),
    )
    return Components(settings, label_sync, watch_monitor, scheduler)


def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _ui_enabled(settings: Settings) -> bool:
    if not settings.feature_ui:
        return False
    if not settings.pal_secret_key:
        log.error("FEATURE_UI is on but PAL_SECRET_KEY is unset — UI disabled.")
        return False
    return True


def create_application(settings: Settings) -> Any:
    """Build the FastAPI app: webhooks + scheduler (if configured) + UI (if enabled)."""
    from app.webhook import create_app

    configured = not settings.runtime_errors()
    components = build_components(settings) if configured else None
    if not configured:
        log.warning(
            "Not fully configured: %s — starting UI only.",
            "; ".join(settings.runtime_errors()),
        )

    webui_router = None
    if _ui_enabled(settings):
        from app.configstore import ConfigStore
        from app.webui import create_webui_router

        ls = components.label_sync if components else None
        webui_router = create_webui_router(
            settings=settings,
            store=ConfigStore(settings.config_path, settings.pal_secret_key),
            on_sweep=(ls.sweep if ls else None),
            on_reverse=(ls.reverse_sweep if ls else None),
            on_test=((lambda: _send_test_notification(settings)) if settings.apprise_url_list else None),
        )

    @contextlib.asynccontextmanager
    async def lifespan(app: Any):
        if components:
            components.scheduler.start()
            log.info("Scheduler started (%d jobs)", len(components.scheduler.jobs()))
        try:
            yield
        finally:
            if components:
                components.scheduler.shutdown()

    return create_app(
        components.label_sync if components else None,
        webhook_path=settings.webhook_path,
        plex_webhook_path=settings.plex_webhook_path,
        secret=settings.webhook_secret,
        lifespan=lifespan,
        webui_router=webui_router,
    )


def _send_test_notification(settings: Settings) -> bool:
    """Send one real Apprise notification to verify channels (ignores DRY_RUN)."""
    from app.clients.notify import Notifier

    notifier = Notifier(settings.apprise_url_list, dry_run=False)
    log.info("Sending test notification to %d channel(s)...", notifier.server_count())
    ok = notifier.notify(
        "Test Notification", f"Whitelistarr v{__version__}", notify_type="info"
    )
    log.info("Test notification %s", "sent OK" if ok else "FAILED (check Apprise URLs)")
    return bool(ok)


def run_reverse(settings: Settings) -> dict[str, int]:
    """One-shot: remove all managed labels from every Plex item, then return."""
    from app.clients.plex import PlexClient
    from app.core.sync import LabelSync

    if not settings.label_map:
        raise ValueError(
            "TAG_LABEL_MAP is required for REVERSE (it defines which labels to remove)."
        )
    log.warning(
        "REVERSE mode: removing managed labels %s from all items%s",
        sorted(settings.managed_labels),
        " (DRY_RUN — nothing will change)" if settings.dry_run else "",
    )
    plex = PlexClient(
        settings.plex_url,
        settings.plex_token,
        settings.sections,
        device_name=settings.plex_device_name,
        client_id=settings.plex_client_id,
    )
    sync = LabelSync(
        plex=plex,
        radarr=None,
        sonarr=None,
        label_map=settings.label_map,
        managed=settings.managed_labels,
        mode=settings.label_removal,
        dry_run=settings.dry_run,
    )
    summary = sync.reverse_sweep()
    log.info("REVERSE done: processed=%d removed-from=%d", summary["processed"], summary["changed"])
    return summary


def run() -> None:
    settings = load_settings()
    setup_logging(settings.log_level)
    log.info("Whitelistarr v%s starting", __version__)

    if settings.reverse:
        run_reverse(settings)
        return

    ui_enabled = _ui_enabled(settings)

    # Declarative (no-UI) mode fails fast on bad config; UI mode starts anyway so
    # the user can fix config in the browser.
    if not ui_enabled:
        settings.validate_runtime()

    configured = not settings.runtime_errors()
    log.info(
        "Config: ui=%s webhook=%s sweep=%s(%dm) notify=%s mode=%s labels=%s configured=%s",
        ui_enabled,
        settings.feature_webhook,
        settings.feature_sweep,
        settings.sweep_interval_minutes,
        settings.feature_notify,
        settings.label_removal,
        sorted(settings.managed_labels),
        configured,
    )

    if settings.dry_run:
        log.warning("DRY_RUN enabled: no Plex labels or notifications will be applied.")

    # Serve HTTP if the UI or the webhook receiver is on; otherwise run headless.
    if ui_enabled or settings.feature_webhook:
        import uvicorn

        uvicorn.run(
            create_application(settings),
            host=settings.webhook_host,
            port=settings.webhook_port,
            log_level=settings.log_level,
        )
    else:
        components = build_components(settings)
        components.scheduler.start()
        log.info("Scheduler started (%d jobs); webhook disabled.", len(components.scheduler.jobs()))
        try:
            threading.Event().wait()
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            components.scheduler.shutdown()


if __name__ == "__main__":
    run()
