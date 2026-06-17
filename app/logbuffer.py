"""In-memory ring buffer of recent log records, exposed to the web UI's Logs tab.

A process-global :class:`LogBuffer` is attached to the root logger in
``setup_logging`` so everything the app logs is retained (capped) and can be
fetched incrementally by ``GET /api/logs``. It holds formatted strings only — no
references to the original records — so it never grows unbounded or pins objects.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from datetime import UTC, datetime
from typing import Any


class LogBuffer:
    def __init__(self, capacity: int = 2000) -> None:
        self._records: deque[dict[str, Any]] = deque(maxlen=capacity)
        self._lock = threading.Lock()
        self._next_id = 1
        self._handler: logging.Handler | None = None

    def handle(self, record: logging.LogRecord) -> None:
        """Append one already-emitted ``LogRecord`` (formatted defensively)."""
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - a bad format string must not break logging
            message = str(record.msg)
        with self._lock:
            entry = {
                "id": self._next_id,
                "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
                "level": record.levelname,
                "levelno": record.levelno,
                "logger": record.name,
                "message": message,
            }
            self._next_id += 1
            self._records.append(entry)

    def records(self, after: int = 0, level: str | None = None) -> list[dict[str, Any]]:
        """Return records with ``id > after`` at or above ``level`` (oldest first)."""
        threshold = logging.getLevelName(level.upper()) if level else 0
        if not isinstance(threshold, int):
            threshold = 0
        with self._lock:
            snapshot = list(self._records)
        return [
            {k: v for k, v in r.items() if k != "levelno"}
            for r in snapshot
            if r["id"] > after and r["levelno"] >= threshold
        ]

    def handler(self) -> logging.Handler:
        """A ``logging.Handler`` that feeds this buffer (memoized)."""
        if self._handler is None:
            self._handler = _BufferHandler(self)
        return self._handler


class _BufferHandler(logging.Handler):
    def __init__(self, buffer: LogBuffer) -> None:
        super().__init__()
        self._buffer = buffer

    def emit(self, record: logging.LogRecord) -> None:
        self._buffer.handle(record)


# Process-global buffer installed by setup_logging; shared with the web UI.
LOG_BUFFER = LogBuffer()
