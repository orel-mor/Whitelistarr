"""Match media across Plex / Radarr / Sonarr using their external GUIDs.

Plex exposes per-item GUIDs like ``tmdb://603``, ``imdb://tt0133093`` and
``tvdb://121361``. Radarr keys movies on ``tmdbId``; Sonarr keys series on
``tvdbId``. Normalizing both to ``"<source>:<id>"`` keys lets us index Plex
items and look them up cheaply.
"""

from __future__ import annotations

from collections.abc import Iterable


def parse_guid(guid: str) -> tuple[str, str] | None:
    """Parse ``"tmdb://603"`` into ``("tmdb", "603")``; ``None`` if malformed."""
    if not guid or "://" not in guid:
        return None
    source, _, value = guid.partition("://")
    if not source or not value:
        return None
    return source, value


def extract_guids(guids: Iterable[str]) -> dict[str, str]:
    """Build a ``{source: id}`` map from a list of GUID strings."""
    result: dict[str, str] = {}
    for guid in guids:
        parsed = parse_guid(guid)
        if parsed:
            source, value = parsed
            result[source] = value
    return result


def guid_key(source: str, value: str | int) -> str:
    """Normalized index/lookup key, e.g. ``guid_key("tmdb", 603) -> "tmdb:603"``."""
    return f"{source}:{value}"


def guid_keys(guids: Iterable[str]) -> set[str]:
    """Return the set of normalized keys for a list of GUID strings."""
    return {guid_key(src, val) for src, val in extract_guids(guids).items()}
