"""In-memory tracker for the last result of each scheduled job.

Held on the Runtime (not on the swappable Components) so a hot-reload doesn't
wipe recent-activity history shown on the Status screen.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

_JOBS = ("sweep", "watch_scan")


class StatusTracker:
    def __init__(self) -> None:
        self._last: dict[str, dict[str, Any]] = {}

    def record(self, job: str, summary: dict[str, Any]) -> None:
        entry = dict(summary)
        entry["at"] = datetime.now(UTC).isoformat()
        self._last[job] = entry

    def snapshot(self) -> dict[str, Any]:
        return {job: self._last.get(job) for job in _JOBS}

    def wrap(self, job: str, fn: Callable[[], dict[str, Any]]) -> Callable[[], dict[str, Any]]:
        def runner() -> dict[str, Any]:
            result = fn()
            if isinstance(result, dict):
                self.record(job, result)
            return result

        return runner
