"""LabelSync orchestrates: build a GUID->tags index from Radarr+Sonarr, then
reconcile Plex labels for items matched on *any* shared GUID.

Dependencies (Plex / Radarr / Sonarr clients) are injected so the logic is
testable with fakes. Matching on any of tmdb/tvdb/imdb makes labeling robust to
the id a given Plex agent happens to store (new agents often use tmdb, not tvdb).
"""

from __future__ import annotations

import logging
import time
from itertools import chain
from typing import Any

from app.core.labeler import apply_labels, desired_labels, reconcile

log = logging.getLogger(__name__)

# Plex media_type -> human heading for notifications.
_TYPE_HEADING = {"movie": "Movies", "show": "TV Shows"}


def format_label_groups(groups: dict[str, dict[str, list[str]]]) -> str:
    """Render ``{media_type: {label: [titles]}}`` as a clean markdown body:

        **Movies**
        `kids-allowed`
        - Dune

        **TV Shows**
        `kids-allowed`
        - Wednesday
    """
    blocks: list[str] = []
    for media_type in ("movie", "show"):
        by_label = groups.get(media_type)
        if not by_label:
            continue
        label_blocks = []
        for label in sorted(by_label):
            lines = [f"`{label}`"] + [f"- {title}" for title in by_label[label]]
            label_blocks.append("\n".join(lines))
        heading = _TYPE_HEADING.get(media_type, media_type)
        blocks.append(f"**{heading}**\n" + "\n\n".join(label_blocks))
    return "\n\n".join(blocks)


class LabelSync:
    def __init__(
        self,
        plex: Any,
        radarr: Any,
        sonarr: Any,
        label_map: dict[str, str],
        managed: set[str],
        mode: str = "reconcile",
        dry_run: bool = False,
        index_ttl_seconds: float = 30.0,
        notifier: Any = None,
        state: Any = None,
        notify_labeled: bool = False,
    ) -> None:
        self._plex = plex
        self._radarr = radarr
        self._sonarr = sonarr
        self._label_map = label_map
        self._managed = managed
        self._mode = mode
        self._dry_run = dry_run
        self._index_ttl = index_ttl_seconds
        self._index: dict[str, set[str]] | None = None
        self._index_at = 0.0
        self._notifier = notifier
        self._state = state
        self._notify_labeled = notify_labeled and notifier is not None

    def build_index(self) -> dict[str, set[str]]:
        """Map every external GUID key -> the set of *arr tag names on that item."""
        index: dict[str, set[str]] = {}
        for keys, tags in chain(
            self._radarr.iter_all_with_tags(), self._sonarr.iter_all_with_tags()
        ):
            if not tags:
                continue
            for key in keys:
                index.setdefault(key, set()).update(tags)
        return index

    def _get_index(self, force: bool = False) -> dict[str, set[str]]:
        now = time.monotonic()
        if force or self._index is None or (now - self._index_at) > self._index_ttl:
            self._index = self.build_index()
            self._index_at = now
        return self._index

    def _desired_for_item(self, item: Any, index: dict[str, set[str]]) -> set[str]:
        tags: set[str] = set()
        for key in item.guid_keys():
            tags |= index.get(key, set())
        return desired_labels(sorted(tags), self._label_map)

    def _reconcile_item(
        self, item: Any, index: dict[str, set[str]]
    ) -> tuple[bool, set[str], set[str]]:
        desired = self._desired_for_item(item, index)
        to_add, to_remove = reconcile(item.labels(), desired, self._managed, self._mode)
        changed = apply_labels(item, to_add, to_remove, dry_run=self._dry_run)
        return changed, to_add, to_remove

    def sync_item(self, item: Any, index: dict[str, set[str]] | None = None) -> bool:
        idx = index if index is not None else self._get_index()
        changed, _, _ = self._reconcile_item(item, idx)
        return changed

    def _collect_label_changes(
        self,
        item: Any,
        to_add: set[str],
        to_remove: set[str],
        added: dict[str, dict[str, list[str]]],
        removed: dict[str, dict[str, list[str]]],
    ) -> None:
        """Record label additions/removals for this item, deduped via state.

        A single state key per (item, label) means "we've announced this label is
        present": added -> notify once + mark; removed -> notify once + clear, so a
        later re-add announces again. Keys are casefolded (Plex capitalizes labels).
        ``added``/``removed`` are ``{media_type: {label: [titles]}}``.
        """
        if not self._notify_labeled or self._dry_run:
            return
        media_type = getattr(item, "media_type", "movie")
        rk = getattr(item, "rating_key", item.title)

        for label in to_add:
            key = f"label:{rk}:{label.casefold()}"
            if self._state is not None:
                if self._state.already_notified(key):
                    continue
                self._state.mark_notified(key)
            added.setdefault(media_type, {}).setdefault(label, []).append(item.title)

        for label in to_remove:
            key = f"label:{rk}:{label.casefold()}"
            if self._state is not None:
                if not self._state.already_notified(key):
                    continue  # never announced as present -> don't announce removal
                self._state.clear(key)
            removed.setdefault(media_type, {}).setdefault(label, []).append(item.title)

    def sync_by_ids(
        self, media_type: str, tmdb_id: int | None = None, tvdb_id: int | None = None
    ) -> bool:
        item = self._plex.find_item(media_type, tmdb_id=tmdb_id, tvdb_id=tvdb_id)
        if item is None:
            log.warning(
                "No Plex item found for %s tmdb=%s tvdb=%s", media_type, tmdb_id, tvdb_id
            )
            return False
        return self._sync_single(item)

    def sync_by_rating_key(self, rating_key: str) -> bool:
        """Label the item with this Plex ratingKey (used by the Plex webhook).

        Episodes/seasons are resolved up to their show by the Plex client.
        """
        item = self._plex.fetch_labelable(rating_key)
        if item is None:
            log.warning("No labelable Plex item for ratingKey=%s", rating_key)
            return False
        return self._sync_single(item)

    def _sync_single(self, item: Any) -> bool:
        changed, to_add, to_remove = self._reconcile_item(item, self._get_index(force=True))
        added: dict[str, dict[str, list[str]]] = {}
        removed: dict[str, dict[str, list[str]]] = {}
        self._collect_label_changes(item, to_add, to_remove, added, removed)
        self._notify_label_changes(added, removed)
        return changed

    def sweep(self) -> dict[str, int]:
        index = self.build_index()
        processed = 0
        changed = 0
        added: dict[str, dict[str, list[str]]] = {}
        removed: dict[str, dict[str, list[str]]] = {}
        for item in self._plex.iter_items():
            processed += 1
            try:
                item_changed, to_add, to_remove = self._reconcile_item(item, index)
                if item_changed:
                    changed += 1
                self._collect_label_changes(item, to_add, to_remove, added, removed)
            except Exception:  # noqa: BLE001 - one bad item shouldn't abort the sweep
                log.exception("Failed to sync item: %s", getattr(item, "title", "?"))
        self._notify_label_changes(added, removed)
        log.info("Sweep complete: processed=%d changed=%d", processed, changed)
        return {"processed": processed, "changed": changed}

    def _notify_label_changes(
        self,
        added: dict[str, dict[str, list[str]]],
        removed: dict[str, dict[str, list[str]]],
    ) -> None:
        """Send a 'Label Added' and/or 'Label Removed' notification.

        Each message is grouped by media type with the label shown as inline code;
        markdown so Discord renders a clean embed (green for added, orange for
        removed) and Telegram gets organized text."""
        if not self._notifier:
            return
        if added:
            self._notifier.notify(
                "Label Added",
                format_label_groups(added),
                body_format="markdown",
                notify_type="success",
            )
        if removed:
            self._notifier.notify(
                "Label Removed",
                format_label_groups(removed),
                body_format="markdown",
                notify_type="warning",
            )

    def reverse_sweep(self) -> dict[str, int]:
        """Remove all managed labels from every Plex item (one-shot undo).

        Ignores the *arr index entirely and the add/remove mode -- this is an
        explicit teardown. Only managed labels are removed; manual labels stay.
        """
        managed_cf = {m.casefold() for m in self._managed}
        processed = 0
        changed = 0
        for item in self._plex.iter_items():
            processed += 1
            try:
                # Case-insensitive: Plex stores labels capitalized.
                to_remove = {lbl for lbl in item.labels() if lbl.casefold() in managed_cf}
                if apply_labels(item, set(), to_remove, dry_run=self._dry_run):
                    changed += 1
            except Exception:  # noqa: BLE001 - one bad item shouldn't abort the sweep
                log.exception("Failed to unlabel item: %s", getattr(item, "title", "?"))
        log.info("Reverse sweep complete: processed=%d changed=%d", processed, changed)
        return {"processed": processed, "changed": changed}
