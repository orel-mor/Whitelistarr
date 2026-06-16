"""APScheduler wrapper: periodic reconcile sweep and watch-history scan."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler

log = logging.getLogger(__name__)


class Scheduler:
    def __init__(self) -> None:
        self._sched = BackgroundScheduler()

    def add_interval_job(self, func: Callable[[], Any], minutes: int, name: str) -> None:
        # next_run_time=now -> run once immediately on start, then every `minutes`.
        self._sched.add_job(
            func,
            trigger="interval",
            minutes=minutes,
            name=name,
            id=name,
            max_instances=1,
            coalesce=True,
            replace_existing=True,
            next_run_time=datetime.now(),
        )

    def jobs(self) -> list[Any]:
        return self._sched.get_jobs()

    def start(self) -> None:
        self._sched.start()

    def shutdown(self) -> None:
        if self._sched.running:
            self._sched.shutdown(wait=False)


def build_scheduler(
    settings: Any,
    sweep_fn: Callable[[], Any],
    watch_fn: Callable[[], Any],
) -> Scheduler:
    sched = Scheduler()
    if settings.feature_sweep:
        sched.add_interval_job(sweep_fn, settings.sweep_interval_minutes, "sweep")
    if settings.feature_notify:
        sched.add_interval_job(watch_fn, settings.watch_scan_interval_minutes, "watch_scan")
    return sched
