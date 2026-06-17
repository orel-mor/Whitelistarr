"""APScheduler wrapper: periodic reconcile sweep and watch-history scan."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

log = logging.getLogger(__name__)


class Scheduler:
    def __init__(self) -> None:
        self._sched = BackgroundScheduler()

    def add_cron_job(self, func: Callable[[], Any], cron: str, name: str) -> None:
        # next_run_time=now -> run once immediately on start, then on the cron cadence.
        self._sched.add_job(
            func,
            trigger=CronTrigger.from_crontab(cron),
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
        sched.add_cron_job(sweep_fn, settings.sweep_cron, "sweep")
    if settings.feature_notify:
        sched.add_cron_job(watch_fn, settings.watch_scan_cron, "watch_scan")
    return sched
