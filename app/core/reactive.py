"""Reactive poller: fast, cheap reactions between full sweeps.

Two jobs run every ``REACTIVE_INTERVAL_SECONDS`` (default 60), so the app reacts
to changes in seconds without a manual Plex webhook (Plex Pass-only) and without
waiting for the hourly reconcile sweep:

- **Arr tag-change diff** — pull the Radarr/Sonarr guid->tags index (arr APIs
  only, never iterates Plex), diff it against the previous snapshot, and
  targeted-reconcile only the Plex items whose tags actually changed. Radarr and
  Sonarr emit no "tag changed" webhook, so diffing is the only way to react.
- **Plex recently-added** — ask Plex for items added since a high-watermark and
  label them, replacing the optional Plex ``library.new`` webhook.

State is in-memory: on the first poll each path *baselines* (records the current
state, reacts to nothing) because the sweep owns the cold start. A restart simply
re-baselines; the sweep remains the safety net. Reconcile is idempotent, so the
poller never fights the sweep.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from app.core.matching import parse_guid

log = logging.getLogger(__name__)

# Bounds a cold catch-up of recently-added items in a single poll.
RECENT_CAP = 100


class ReactivePoller:
    def __init__(
        self,
        plex: Any,
        label_sync: Any,
        radarr: Any,
        sonarr: Any,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._plex = plex
        self._sync = label_sync
        self._radarr = radarr
        self._sonarr = sonarr
        self._now = now_fn or datetime.now
        # guid_key -> frozenset(tag names) at the previous poll. None = not yet baselined.
        self._prev: dict[str, frozenset[str]] | None = None
        # Newest Plex addedAt we've reacted to. None = not yet baselined.
        self._watermark: datetime | None = None

    def poll(self) -> dict[str, Any]:
        merged, types, snapshot = self._build_arr_index()
        tag_changes = self._react_to_tag_changes(merged, types, snapshot)
        added_titles = self._react_to_recently_added(merged)
        summary = {
            "tag_changes": tag_changes,
            "added": len(added_titles),
            "added_titles": added_titles,
        }
        if tag_changes or added_titles:
            log.info(
                "Reactive poll: tag_changes=%d added=%d", tag_changes, len(added_titles)
            )
        return summary

    # --- arr tag-change diff ------------------------------------------------

    def _build_arr_index(
        self,
    ) -> tuple[dict[str, set[str]], dict[str, str], dict[str, frozenset[str]]]:
        """Return (merged guid->tags, guid->media_type, snapshot guid->frozenset tags).

        Unlike ``LabelSync.build_index`` this keeps untagged items, so a tag being
        *added* to a previously-untagged item shows up as a snapshot change.
        """
        merged: dict[str, set[str]] = {}
        types: dict[str, str] = {}
        snapshot: dict[str, frozenset[str]] = {}
        for client, media_type in ((self._radarr, "movie"), (self._sonarr, "show")):
            for keys, tags in client.iter_all_with_tags():
                tagset = frozenset(tags)
                for key in keys:
                    if tags:
                        merged.setdefault(key, set()).update(tags)
                    types.setdefault(key, media_type)
                    snapshot[key] = snapshot.get(key, frozenset()) | tagset
        return merged, types, snapshot

    def _react_to_tag_changes(
        self,
        merged: dict[str, set[str]],
        types: dict[str, str],
        snapshot: dict[str, frozenset[str]],
    ) -> int:
        if self._prev is None:  # baseline: react to nothing
            self._prev = snapshot
            return 0
        changed_keys = [
            key for key, tags in snapshot.items() if tags != self._prev.get(key, frozenset())
        ]
        self._prev = snapshot

        reconciled: set[str] = set()  # rating_keys, to avoid double work per item
        count = 0
        for key in changed_keys:
            item = self._resolve(key, types.get(key))
            if item is None:
                continue
            rk = getattr(item, "rating_key", None) or item.title
            if rk in reconciled:
                continue
            reconciled.add(rk)
            try:
                self._sync.reconcile_found(item, merged)
                count += 1
            except Exception:  # noqa: BLE001 - one bad item shouldn't abort the poll
                log.exception("Reactive reconcile failed for %s", key)
        return count

    def _resolve(self, guid_key: str, media_type: str | None) -> Any:
        """Find the Plex item for a changed guid_key (e.g. ``tmdb:603``)."""
        if media_type is None:
            return None
        parsed = parse_guid(guid_key.replace(":", "://", 1))
        if parsed is None:
            return None
        source, value = parsed
        try:
            identifier = int(value)
        except (TypeError, ValueError):
            return None
        if source == "tmdb":
            return self._plex.find_item(media_type, tmdb_id=identifier)
        if source == "tvdb":
            return self._plex.find_item(media_type, tvdb_id=identifier)
        return None  # imdb-only: same item carries a tmdb/tvdb key handled above

    # --- Plex recently-added ------------------------------------------------

    def _react_to_recently_added(self, merged: dict[str, set[str]]) -> list[str]:
        if self._watermark is None:  # baseline: only react to items added from now on
            self._watermark = self._now()
            return []
        recent = self._plex.recently_added(self._watermark, cap=RECENT_CAP)
        titles: list[str] = []
        newest = self._watermark
        for item in recent:
            try:
                self._sync.reconcile_found(item, merged)
                titles.append(item.title)
            except Exception:  # noqa: BLE001 - one bad item shouldn't abort the poll
                log.exception("Reactive reconcile failed for recently-added %s", item.title)
            added_at = getattr(item, "added_at", None)
            if added_at is not None and added_at > newest:
                newest = added_at
        self._watermark = newest
        return titles
