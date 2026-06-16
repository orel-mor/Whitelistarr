import httpx
import respx

from app.clients.seerr import SeerrClient
from app.clients.tautulli import TautulliClient

SEERR = "http://seerr:5055"
TAUTULLI = "http://tautulli:8181"


def _request_page(results, pages=1):
    return {"pageInfo": {"pages": pages, "results": len(results)}, "results": results}


@respx.mock
def test_seerr_iter_requests_normalizes_fields():
    results = [
        {
            "type": "movie",
            "media": {"tmdbId": 603, "tvdbId": None, "mediaType": "movie", "ratingKey": "111"},
            "requestedBy": {"plexUsername": "family", "displayName": "Family"},
        }
    ]
    respx.get(f"{SEERR}/api/v1/request").mock(
        return_value=httpx.Response(200, json=_request_page(results))
    )
    reqs = list(SeerrClient(SEERR, "key").iter_requests())
    assert len(reqs) == 1
    r = reqs[0]
    assert r.media_type == "movie"
    assert r.tmdb_id == 603
    assert r.requester == "family"
    assert r.rating_key == "111"


@respx.mock
def test_seerr_sends_api_key_header():
    route = respx.get(f"{SEERR}/api/v1/request").mock(
        return_value=httpx.Response(200, json=_request_page([]))
    )
    list(SeerrClient(SEERR, "secret").iter_requests())
    assert route.calls.last.request.headers["X-Api-Key"] == "secret"


@respx.mock
def test_seerr_paginates():
    page0 = _request_page(
        [{"type": "movie", "media": {"tmdbId": 1, "mediaType": "movie"}, "requestedBy": {"plexUsername": "a"}}],
        pages=2,
    )
    page1 = _request_page(
        [{"type": "tv", "media": {"tvdbId": 2, "mediaType": "tv"}, "requestedBy": {"plexUsername": "b"}}],
        pages=2,
    )
    respx.get(f"{SEERR}/api/v1/request").mock(
        side_effect=[httpx.Response(200, json=page0), httpx.Response(200, json=page1)]
    )
    reqs = list(SeerrClient(SEERR, "key").iter_requests())
    assert [r.requester for r in reqs] == ["a", "b"]
    assert reqs[1].tvdb_id == 2


@respx.mock
def test_tautulli_get_history_returns_rows():
    respx.get(f"{TAUTULLI}/api/v2").mock(
        return_value=httpx.Response(
            200,
            json={
                "response": {
                    "result": "success",
                    "data": {"data": [{"rating_key": "111", "user": "family", "percent_complete": 100}]},
                }
            },
        )
    )
    rows = TautulliClient(TAUTULLI, "key").get_history(rating_key="111", user="family")
    assert rows == [{"rating_key": "111", "user": "family", "percent_complete": 100}]


@respx.mock
def test_tautulli_sends_apikey_and_cmd_params():
    route = respx.get(f"{TAUTULLI}/api/v2").mock(
        return_value=httpx.Response(
            200, json={"response": {"result": "success", "data": {"data": []}}}
        )
    )
    TautulliClient(TAUTULLI, "secret").get_history(rating_key="5")
    req = route.calls.last.request
    assert req.url.params["apikey"] == "secret"
    assert req.url.params["cmd"] == "get_history"
    assert req.url.params["rating_key"] == "5"
