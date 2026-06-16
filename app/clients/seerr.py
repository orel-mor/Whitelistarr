"""Seerr (formerly Overseerr) client: enumerate requests to map media -> requester."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from app.clients.base import HttpClient

PAGE_SIZE = 50


@dataclass(frozen=True)
class RequestInfo:
    media_type: str  # "movie" | "tv"
    tmdb_id: int | None
    tvdb_id: int | None
    requester: str | None  # Plex username
    requester_name: str | None
    rating_key: str | None  # Plex ratingKey, when Seerr knows it


class SeerrClient:
    def __init__(self, base_url: str, api_key: str) -> None:
        self._http = HttpClient(base_url, headers={"X-Api-Key": api_key})

    def iter_requests(self) -> Iterator[RequestInfo]:
        skip = 0
        pages = 1
        while True:
            data = self._http.get_json(
                "/api/v1/request",
                params={"take": PAGE_SIZE, "skip": skip, "sort": "added"},
            )
            pages = data.get("pageInfo", {}).get("pages", 1)
            for result in data.get("results", []):
                yield _normalize(result)
            skip += PAGE_SIZE
            if skip // PAGE_SIZE >= pages:
                break

    def close(self) -> None:
        self._http.close()


# Backwards-compatible alias.
OverseerrClient = SeerrClient


def _normalize(result: dict) -> RequestInfo:
    media = result.get("media") or {}
    requester = result.get("requestedBy") or {}
    return RequestInfo(
        media_type=media.get("mediaType") or result.get("type") or "",
        tmdb_id=media.get("tmdbId"),
        tvdb_id=media.get("tvdbId"),
        requester=requester.get("plexUsername"),
        requester_name=requester.get("displayName"),
        rating_key=media.get("ratingKey"),
    )
