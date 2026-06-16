"""Common logic for Radarr and Sonarr (both expose an identical /api/v3 tag API).

We pull *all* items once and emit, per item, the set of external GUID keys it
carries (tmdb/tvdb/imdb) alongside its resolved tag names. Matching on *any*
shared GUID makes us robust to which id a given Plex agent stored.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from app.clients.base import HttpClient
from app.core.matching import guid_key


class ArrClient:
    """Base for Radarr/Sonarr. Subclasses set the list endpoint and GUID fields."""

    lookup_path: str = ""  # e.g. "/api/v3/movie"

    def __init__(self, base_url: str, api_key: str) -> None:
        self._http = HttpClient(base_url, headers={"X-Api-Key": api_key})

    def get_tags(self) -> dict[int, str]:
        """Return ``{tag_id: label}`` for all tags defined in the *arr instance."""
        return {tag["id"]: tag["label"] for tag in self._http.get_json("/api/v3/tag")}

    def get_all(self) -> list[dict[str, Any]]:
        return self._http.get_json(self.lookup_path)

    def _guid_keys(self, item: dict[str, Any]) -> set[str]:
        raise NotImplementedError

    def iter_all_with_tags(self) -> Iterator[tuple[set[str], list[str]]]:
        tags = self.get_tags()
        for item in self.get_all():
            names = [tags[tid] for tid in item.get("tags", []) if tid in tags]
            yield self._guid_keys(item), names

    def close(self) -> None:
        self._http.close()


def _add_guid(keys: set[str], source: str, value: Any) -> None:
    if value:
        keys.add(guid_key(source, value))
