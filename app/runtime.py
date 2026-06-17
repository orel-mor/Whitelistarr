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


def _default_builder(settings: Any) -> Any:
    from app.main import build_components

    return build_components(settings)


class Runtime:
    def __init__(
        self,
        settings: Any,
        components: Any | None,
        builder: Callable[[Any], Any] | None = None,
        scheduler_started: bool = False,
    ) -> None:
        self._settings = settings
        self._components = components
        self._builder = builder or _default_builder
        self._scheduler_started = scheduler_started

    @property
    def settings(self) -> Any:
        return self._settings

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

    def reload(self, new_settings: Any) -> ReloadResult:
        restart_fields = self._restart_fields(new_settings)
        try:
            new_components = self._builder(new_settings)
        except Exception as exc:  # noqa: BLE001 - any build failure -> keep old
            log.exception("Reload failed to build components; keeping current ones")
            return ReloadResult(
                ok=False,
                error=str(exc),
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
