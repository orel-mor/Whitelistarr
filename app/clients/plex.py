"""Plex client + item adapter.

``PlexItem`` wraps a plexapi video and exposes the shape ``LabelSync`` expects
(``media_type``, ``tmdb_id``, ``tvdb_id``, ``labels``/``add_labels``/``remove_labels``).
``PlexClient`` connects to the server and yields/looks up items.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from datetime import datetime

from app.core.matching import extract_guids, guid_key, parse_legacy_guid

log = logging.getLogger(__name__)

# Plex section type -> our media_type domain.
_SECTION_TYPE = {"movie": "movie", "show": "show"}


def configure_plex_identity(product: str, device_name: str, identifier: str) -> dict:
    """Set the X-Plex-* identity headers plexapi sends, so this app shows up as a
    clearly-named, stable device in Plex (instead of the container hostname).

    A stable ``identifier`` keeps Plex from registering a new device each restart.
    Returns the rebuilt base headers (handy for tests).
    """
    import plexapi

    plexapi.X_PLEX_PRODUCT = product
    plexapi.X_PLEX_DEVICE_NAME = device_name
    plexapi.X_PLEX_IDENTIFIER = identifier
    plexapi.BASE_HEADERS = plexapi.reset_base_headers()
    return plexapi.BASE_HEADERS


class PlexItem:
    """Adapter over a plexapi video object."""

    def __init__(self, video: object, media_type: str) -> None:
        self._v = video
        self.media_type = media_type
        self.title = getattr(video, "title", "?")
        self._guid_map: dict[str, str] | None = None

    def _read_current_guids(self) -> dict[str, str]:
        """Extract ``{source: id}`` from the video's current in-memory metadata.

        Prefers the modern ``guids`` list; falls back to the single legacy ``guid``
        (e.g. ``com.plexapp.agents.thetvdb://383203?lang=en``) that legacy Plex
        agents populate when no ``Guid[]`` is present.
        """
        ids = [g.id for g in (getattr(self._v, "guids", None) or [])]
        guid_map = extract_guids(ids)
        if guid_map:
            return guid_map
        legacy = parse_legacy_guid(getattr(self._v, "guid", None) or "")
        return {legacy[0]: legacy[1]} if legacy else {}

    def _guids(self) -> dict[str, str]:
        if self._guid_map is None:
            guid_map = self._read_current_guids()
            # A modern item may need a reload before Guid[] is populated; legacy
            # items resolve from ``guid`` above, so only reload if we found nothing.
            if not guid_map and hasattr(self._v, "reload"):
                self._v.reload()
                guid_map = self._read_current_guids()
            self._guid_map = guid_map
        return self._guid_map

    def _int_guid(self, source: str) -> int | None:
        value = self._guids().get(source)
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @property
    def tmdb_id(self) -> int | None:
        return self._int_guid("tmdb")

    @property
    def tvdb_id(self) -> int | None:
        return self._int_guid("tvdb")

    @property
    def rating_key(self) -> str:
        return str(self._v.ratingKey)

    @property
    def added_at(self) -> datetime | None:
        return getattr(self._v, "addedAt", None)

    def guid_keys(self) -> set[str]:
        return {guid_key(src, val) for src, val in self._guids().items()}

    def labels(self) -> set[str]:
        return {label.tag for label in getattr(self._v, "labels", [])}

    def add_labels(self, labels: list[str]) -> None:
        self._v.addLabel(list(labels))

    def remove_labels(self, labels: list[str]) -> None:
        self._v.removeLabel(list(labels))


class PlexClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        sections: list[str] | None = None,
        device_name: str = "Whitelistarr",
        client_id: str = "whitelistarr",
    ) -> None:
        configure_plex_identity(
            product="Whitelistarr", device_name=device_name, identifier=client_id
        )
        from plexapi.server import PlexServer

        self._server = PlexServer(base_url, token)
        self._section_filter = set(sections or [])
        # Lazily-built {media_type: {guid_key: video}} index, used only as the
        # legacy/cross-id fallback in find_item_by_keys (getGuid can't resolve
        # legacy-agent items). Cached so a batch of lookups — e.g. one watch
        # scan over every Overseerr request — costs a single library scan, not
        # one per lookup. The sweep is the backstop, so a coarse TTL is fine.
        self._resolve_index: dict[str, dict[str, object]] | None = None
        self._resolve_index_at = 0.0
        self._resolve_ttl = 300.0

    def check(self) -> dict:
        try:
            name = self._server.friendlyName
        except Exception:  # noqa: BLE001 - generic detail; full error logged, never sent to UI
            log.warning("Plex connection probe failed", exc_info=True)
            return {"ok": False, "detail": "unreachable"}
        return {"ok": True, "detail": str(name)}

    def list_libraries(self) -> list[dict[str, str]]:
        """List every labelable Plex library (movie/show) for the picker.

        Ignores the configured section filter — the UI needs the full set of
        pickable libraries so the user can choose which ones to include.
        """
        libs = []
        for section in self._server.library.sections():
            if section.type in _SECTION_TYPE:
                libs.append({"title": section.title, "type": section.type})
        return libs

    def _sections(self) -> list[object]:
        result = []
        for section in self._server.library.sections():
            if section.type not in _SECTION_TYPE:
                continue
            if self._section_filter and section.title not in self._section_filter:
                continue
            result.append(section)
        return result

    def iter_items(self) -> Iterator[PlexItem]:
        for section in self._sections():
            media_type = _SECTION_TYPE[section.type]
            for video in section.all():
                yield PlexItem(video, media_type)

    def recently_added(self, since: datetime | None, cap: int = 100) -> list[PlexItem]:
        """Return items added after ``since`` (newest first), across matching sections.

        Each section is searched ``addedAt`` descending; because the list is sorted
        we can stop at the first item at/older than the watermark. ``since=None``
        returns the most-recent ``cap`` items per section (used to baseline).
        """
        items: list[PlexItem] = []
        for section in self._sections():
            media_type = _SECTION_TYPE[section.type]
            for video in section.search(sort="addedAt:desc", maxresults=cap):
                item = PlexItem(video, media_type)
                if since is not None:
                    added_at = item.added_at
                    if added_at is None or added_at <= since:
                        break  # sorted desc -> everything after is older too
                items.append(item)
        return items

    def fetch_labelable(self, rating_key: str | int) -> PlexItem | None:
        """Fetch the labelable item for a Plex ratingKey.

        Movies/shows map directly; seasons/episodes are walked up to their show
        (labels must sit on the show for share-label filtering to apply).
        """
        from plexapi.exceptions import NotFound

        try:
            item = self._server.fetchItem(int(rating_key))
        except (NotFound, ValueError, TypeError):
            return None

        item_type = getattr(item, "type", None)
        if item_type == "movie":
            return PlexItem(item, "movie")
        if item_type == "show":
            return PlexItem(item, "show")
        if item_type in ("season", "episode"):
            show = item.show() if hasattr(item, "show") else None
            return PlexItem(show, "show") if show is not None else None
        return None

    def find_item(
        self, media_type: str, tmdb_id: int | None = None, tvdb_id: int | None = None
    ) -> PlexItem | None:
        """Find a Plex item by tmdb/tvdb id. Thin wrapper over find_item_by_keys."""
        keys: set[str] = set()
        if tmdb_id is not None:
            keys.add(guid_key("tmdb", tmdb_id))
        if tvdb_id is not None:
            keys.add(guid_key("tvdb", tvdb_id))
        return self.find_item_by_keys(media_type, keys)

    def find_item_by_keys(self, media_type: str, keys: set[str]) -> PlexItem | None:
        """Find a Plex item matching *any* of these ``"<source>:<id>"`` keys.

        Fast path: plexapi's ``getGuid`` for the tmdb/tvdb keys — resolved
        server-side for the modern Plex Movie/TV agents. Fallback: a cached
        ``guid_key -> video`` index, which is the only way to resolve
        legacy-agent items (no modern ``Guid[]`` for getGuid to match) and
        cross-id requests (e.g. a tmdb request whose legacy Plex item carries
        only an imdb guid — callers pass the sibling ids so this still matches).
        """
        from plexapi.exceptions import NotFound

        if not keys:
            return None

        sections = [s for s in self._sections() if _SECTION_TYPE[s.type] == media_type]
        candidates = [
            f"{src}://{val}"
            for src, _, val in (key.partition(":") for key in keys)
            if src in ("tmdb", "tvdb") and val
        ]
        for section in sections:
            for guid in candidates:
                try:
                    video = section.getGuid(guid)
                except NotFound:
                    video = None
                if video is not None:
                    return PlexItem(video, media_type)

        # Fallback: consult the cached index (built once per TTL window).
        index = self._resolution_index(media_type)
        for key in keys:
            video = index.get(key)
            if video is not None:
                return PlexItem(video, media_type)
        return None

    def _resolution_index(self, media_type: str) -> dict[str, object]:
        """Cached ``{guid_key: video}`` for one media type, for legacy fallback.

        Rebuilt when older than the TTL. Scans each matching section once and
        keys every video by all of its guid_keys (which include legacy-agent
        ids), so a getGuid miss can still be resolved by any known id.
        """
        now = time.monotonic()
        if self._resolve_index is None or (now - self._resolve_index_at) > self._resolve_ttl:
            self._resolve_index = {}
            self._resolve_index_at = now
        if media_type not in self._resolve_index:
            index: dict[str, object] = {}
            for section in self._sections():
                if _SECTION_TYPE[section.type] != media_type:
                    continue
                for video in section.all():
                    for key in PlexItem(video, media_type).guid_keys():
                        index.setdefault(key, video)
            self._resolve_index[media_type] = index
        return self._resolve_index[media_type]
