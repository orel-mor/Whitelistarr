"""In-memory tracker for job/action activity shown on the Status screen.

Held on the Runtime (not on the swappable Components) so a hot-reload doesn't
wipe recent activity. Two views:

- ``snapshot()`` — the *last* result per scheduled job (liveness: "reactive ran
  30s ago"), updated on every run.
- ``history()`` — a rolling, newest-first log of runs that actually *did
  something* (plus all manual UI actions), rendered as the activity table.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

_JOBS = ("sweep", "watch_scan", "reactive")


def _did_something(job: str, summary: dict[str, Any]) -> bool:
    """Whether an automatic run is worth a history row (avoids logging the many
    idle reactive polls / no-op sweeps that change nothing)."""
    if job in ("sweep", "reverse"):
        return int(summary.get("changed", 0)) > 0
    if job == "reactive":
        return int(summary.get("tag_changes", 0)) > 0 or int(summary.get("added", 0)) > 0
    if job == "watch_scan":
        return int(summary.get("notified", 0)) > 0
    return True  # manual / unknown actions always count


class StatusTracker:
    def __init__(self, history_size: int = 25) -> None:
        self._last: dict[str, dict[str, Any]] = {}
        self._history: deque[dict[str, Any]] = deque(maxlen=history_size)
        self._seq = 0

    def record(self, job: str, summary: dict[str, Any], *, history: bool | None = None) -> None:
        """Record one run. Updates the per-job ``snapshot`` and, when the run did
        something (or ``history=True`` for manual actions), appends to ``history``."""
        at = datetime.now(UTC).isoformat()
        if job in _JOBS:
            entry = dict(summary)
            entry["at"] = at
            self._last[job] = entry
        log_it = history if history is not None else _did_something(job, summary)
        if log_it:
            self._seq += 1
            self._history.appendleft({"id": self._seq, "action": job, "at": at, **summary})

    def snapshot(self) -> dict[str, Any]:
        return {job: self._last.get(job) for job in _JOBS}

    def history(self) -> list[dict[str, Any]]:
        return list(self._history)

    def wrap(self, job: str, fn: Callable[[], dict[str, Any]]) -> Callable[[], dict[str, Any]]:
        def runner() -> dict[str, Any]:
            result = fn()
            if isinstance(result, dict):
                self.record(job, result)
            return result

        return runner
