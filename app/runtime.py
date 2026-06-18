"""Runtime holder enabling hot-reload of config without a process restart.

Owns the current Components (clients, label_sync, scheduler). Routes and UI
actions resolve the live label_sync through this holder, so reload() can build a
new component set and atomically swap it in — rolling back if the build fails.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

# Settings that cannot be hot-applied: they bind sockets, unlock the store, or
# set on-disk paths. Changing one requires a process restart.
BOOTSTRAP_FIELDS = {
    "pal_secret_key",
    "config_path",
    "state_db_path",
    "feature_ui",
    "webhook_host",
    "webhook_port",
}


@dataclass
class ReloadResult:
    ok: bool
    error: str | None = None
    restart_required: bool = False
    restart_fields: list[str] | None = None


def _default_builder(settings: Any, tracker: Any) -> Any:
    from app.main import build_components

    return build_components(settings, tracker=tracker)


class Runtime:
    def __init__(
        self,
        settings: Any,
        components: Any | None,
        builder: Callable[[Any], Any] | None = None,
        scheduler_started: bool = False,
        tracker: Any | None = None,
    ) -> None:
        from app.status import StatusTracker

        self._settings = settings
        self._components = components
        self._tracker = tracker or StatusTracker()
        self._builder = builder or (lambda s: _default_builder(s, self._tracker))
        self._scheduler_started = scheduler_started

    @property
    def settings(self) -> Any:
        return self._settings

    @property
    def tracker(self) -> Any:
        return self._tracker

    @property
    def components(self) -> Any | None:
        return self._components

    @property
    def label_sync(self) -> Any | None:
        return self._components.label_sync if self._components else None

    def start(self) -> None:
        if self._components and not self._scheduler_started:
            self._components.scheduler.start()
            self._scheduler_started = True

    def shutdown(self) -> None:
        if self._components and self._scheduler_started:
            self._components.scheduler.shutdown()
            self._scheduler_started = False

    def _restart_fields(self, new_settings: Any) -> list[str]:
        return [
            f
            for f in sorted(BOOTSTRAP_FIELDS)
            if getattr(new_settings, f, None) != getattr(self._settings, f, None)
        ]

    def _teardown(self) -> None:
        if self._components is not None and self._scheduler_started:
            try:
                self._components.scheduler.shutdown()
            except Exception:  # noqa: BLE001 - best-effort teardown
                log.exception("Error shutting down old scheduler during reload")
        self._scheduler_started = False

    def reload(self, new_settings: Any) -> ReloadResult:
        restart_fields = self._restart_fields(new_settings)

        # Mid-onboarding the user saves config one step at a time, so a save can
        # land while config is still incomplete (e.g. Plex set but Radarr/Sonarr
        # not). Mirror boot: stay "UI only" — don't build clients or start the
        # sweep/reactive jobs until everything required is present AND the user has
        # finished onboarding (pressed Finish, setting onboarding_complete).
        onboarded = getattr(new_settings, "onboarding_complete", True)
        if new_settings.runtime_errors() or not onboarded:
            self._teardown()
            self._components = None
            self._settings = new_settings
            return ReloadResult(
                ok=True,
                restart_required=bool(restart_fields),
                restart_fields=restart_fields or None,
            )

        try:
            new_components = self._builder(new_settings)
        except Exception as exc:  # noqa: BLE001 - any build failure -> keep old
            # Surface only the exception type (e.g. "Unauthorized",
            # "ConnectionError") to the UI; the full detail is logged server-side
            # so exception text/tracebacks never reach the browser.
            log.exception("Reload failed to build components; keeping current ones")
            return ReloadResult(
                ok=False,
                error=type(exc).__name__,
                restart_required=bool(restart_fields),
                restart_fields=restart_fields or None,
            )

        old, old_started = self._components, self._scheduler_started
        self._components = new_components
        self._settings = new_settings
        self._scheduler_started = False
        if old is not None and old_started:
            try:
                old.scheduler.shutdown()
            except Exception:  # noqa: BLE001 - best-effort teardown
                log.exception("Error shutting down old scheduler during reload")
        self.start()
        return ReloadResult(
            ok=True,
            restart_required=bool(restart_fields),
            restart_fields=restart_fields or None,
        )
