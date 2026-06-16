"""Core label reconciliation logic.

Pure functions decide *which* labels to add/remove; ``apply_labels`` performs the
side effects against a Plex item. The reconciler only ever touches *managed*
labels (the values in ``TAG_LABEL_MAP``) so manual labels are never clobbered.
"""

from __future__ import annotations

import logging
from typing import Protocol

log = logging.getLogger(__name__)


class LabelableItem(Protocol):
    title: str

    def labels(self) -> set[str]: ...

    def add_labels(self, labels: list[str]) -> None: ...

    def remove_labels(self, labels: list[str]) -> None: ...


_GUID_PRIORITY = ("tmdb", "tvdb", "imdb")


def describe_item(item: object) -> str:
    """Human + machine friendly label for logs, e.g. ``"Aladdin [tmdb:812]"``.

    Falls back to just the title if the item exposes no GUID keys.
    """
    title = getattr(item, "title", "?")
    keys_fn = getattr(item, "guid_keys", None)
    if not callable(keys_fn):
        return title
    keys = keys_fn()
    if not keys:
        return title
    by_source = {key.split(":", 1)[0]: key for key in keys}
    for source in _GUID_PRIORITY:
        if source in by_source:
            return f"{title} [{by_source[source]}]"
    return f"{title} [{sorted(keys)[0]}]"


def desired_labels(tag_names: list[str], label_map: dict[str, str]) -> set[str]:
    """Translate *arr tag names into Plex labels via the configured map."""
    return {label_map[tag] for tag in tag_names if tag in label_map}


def reconcile(
    current: set[str],
    desired: set[str],
    managed: set[str],
    mode: str = "reconcile",
) -> tuple[set[str], set[str]]:
    """Compute ``(to_add, to_remove)`` with **case-insensitive** matching.

    Plex capitalizes the first letter of labels (``mika-whitelist`` is stored as
    ``Mika-whitelist``), so comparisons must ignore case. Returns desired labels
    to add in their configured casing, and the *actual* stored strings to remove
    (so ``removeLabel`` targets what Plex really has).

    - Add any desired label not already present (case-insensitive).
    - In ``reconcile`` mode, remove managed labels present but no longer desired.
      Labels outside ``managed`` are never removed.
    - In ``add-only`` mode, never remove anything.
    """
    current_by_cf = {c.casefold(): c for c in current}
    desired_by_cf = {d.casefold(): d for d in desired}
    managed_cf = {m.casefold() for m in managed}

    to_add = {orig for cf, orig in desired_by_cf.items() if cf not in current_by_cf}
    if mode == "reconcile":
        to_remove = {
            current_by_cf[cf]
            for cf in current_by_cf
            if cf in managed_cf and cf not in desired_by_cf
        }
    else:
        to_remove = set()
    return to_add, to_remove


def apply_labels(
    item: LabelableItem,
    to_add: set[str],
    to_remove: set[str],
    dry_run: bool = False,
) -> bool:
    """Apply label changes to ``item``. Returns whether anything changed.

    In ``dry_run`` the intended change is logged and ``True`` is returned if it
    *would* have changed, but the item is not mutated.
    """
    if not to_add and not to_remove:
        return False
    desc = describe_item(item)
    if dry_run:
        log.info("[DRY_RUN] %s: +%s -%s", desc, sorted(to_add) or "-", sorted(to_remove) or "-")
        return True
    if to_add:
        item.add_labels(sorted(to_add))
    if to_remove:
        item.remove_labels(sorted(to_remove))
    log.info("%s: +%s -%s", desc, sorted(to_add) or "-", sorted(to_remove) or "-")
    return True
