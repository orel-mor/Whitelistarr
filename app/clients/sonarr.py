"""Sonarr client: enumerate series and resolve their tags to GUID-keyed labels."""

from __future__ import annotations

from typing import Any

from app.clients.arr import ArrClient, _add_guid


class SonarrClient(ArrClient):
    lookup_path = "/api/v3/series"

    def _guid_keys(self, item: dict[str, Any]) -> set[str]:
        keys: set[str] = set()
        _add_guid(keys, "tvdb", item.get("tvdbId"))
        _add_guid(keys, "tmdb", item.get("tmdbId"))
        _add_guid(keys, "imdb", item.get("imdbId"))
        return keys
