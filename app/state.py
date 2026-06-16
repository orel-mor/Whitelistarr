"""SQLite-backed dedup store so a notification fires at most once per event.

The store is shared across scheduler threads (sweep + watch scan) and the webhook
handler, so every operation is guarded by a lock — a single sqlite3 connection
used concurrently from multiple threads can otherwise crash the process.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime


class StateStore:
    def __init__(self, db_path: str) -> None:
        self._lock = threading.Lock()
        # check_same_thread=False: accessed from scheduler/worker threads (guarded
        # by self._lock, so concurrent use is serialized and safe).
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS notifications "
            "(key TEXT PRIMARY KEY, sent_at TEXT NOT NULL)"
        )
        self._conn.commit()

    def already_notified(self, key: str) -> bool:
        with self._lock:
            cur = self._conn.execute("SELECT 1 FROM notifications WHERE key = ?", (key,))
            return cur.fetchone() is not None

    def mark_notified(self, key: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO notifications (key, sent_at) VALUES (?, ?)",
                (key, datetime.now(UTC).isoformat()),
            )
            self._conn.commit()

    def clear(self, key: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM notifications WHERE key = ?", (key,))
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
