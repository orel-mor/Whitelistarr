import httpx
import respx

from app.clients.radarr import RadarrClient
from app.clients.sonarr import SonarrClient

RADARR = "http://radarr:7878"
SONARR = "http://sonarr:8989"


@respx.mock
def test_radarr_iter_all_with_tags():
    respx.get(f"{RADARR}/api/v3/tag").mock(
        return_value=httpx.Response(
            200, json=[{"id": 1, "label": "kids"}, {"id": 2, "label": "family"}]
        )
    )
    respx.get(f"{RADARR}/api/v3/movie").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"id": 1, "tmdbId": 603, "imdbId": "tt0133093", "tags": [1]},
                {"id": 2, "tmdbId": 604, "tags": []},
            ],
        )
    )
    items = list(RadarrClient(RADARR, "k").iter_all_with_tags())
    assert items[0] == ({"tmdb:603", "imdb:tt0133093"}, ["kids"])
    assert items[1] == ({"tmdb:604"}, [])


@respx.mock
def test_radarr_sends_api_key_header():
    respx.get(f"{RADARR}/api/v3/tag").mock(return_value=httpx.Response(200, json=[]))
    route = respx.get(f"{RADARR}/api/v3/movie").mock(return_value=httpx.Response(200, json=[]))
    list(RadarrClient(RADARR, "secret-key").iter_all_with_tags())
    assert route.calls.last.request.headers["X-Api-Key"] == "secret-key"


@respx.mock
def test_sonarr_iter_all_with_tags_includes_tmdb_and_tvdb():
    respx.get(f"{SONARR}/api/v3/tag").mock(
        return_value=httpx.Response(
            200, json=[{"id": 1, "label": "kids"}, {"id": 2, "label": "family"}]
        )
    )
    respx.get(f"{SONARR}/api/v3/series").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"id": 5, "tvdbId": 121361, "tmdbId": 2316, "imdbId": "tt0098904", "tags": [2]}
            ],
        )
    )
    items = list(SonarrClient(SONARR, "k").iter_all_with_tags())
    assert items[0] == ({"tvdb:121361", "tmdb:2316", "imdb:tt0098904"}, ["family"])


@respx.mock
def test_iter_all_with_tags_skips_unconfigured_client():
    # No base_url (Radarr/Sonarr not set up yet during onboarding) -> yield nothing,
    # make no HTTP call, rather than blowing up with httpx.UnsupportedProtocol.
    assert list(RadarrClient("", "k").iter_all_with_tags()) == []
    assert respx.calls.call_count == 0


@respx.mock
def test_unknown_tag_id_is_skipped():
    respx.get(f"{RADARR}/api/v3/tag").mock(
        return_value=httpx.Response(200, json=[{"id": 1, "label": "kids"}])
    )
    respx.get(f"{RADARR}/api/v3/movie").mock(
        return_value=httpx.Response(200, json=[{"id": 1, "tmdbId": 1, "tags": [99]}])
    )
    items = list(RadarrClient(RADARR, "k").iter_all_with_tags())
    assert items[0] == ({"tmdb:1"}, [])
