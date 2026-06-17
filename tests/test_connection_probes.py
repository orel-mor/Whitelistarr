import httpx
import respx

from app.clients.radarr import RadarrClient
from app.clients.seerr import SeerrClient
from app.clients.tautulli import TautulliClient

ARR = "http://radarr:7878"
SEERR = "http://seerr:5055"
TAUT = "http://tautulli:8181"


@respx.mock
def test_arr_check_ok():
    respx.get(f"{ARR}/api/v3/system/status").mock(
        return_value=httpx.Response(200, json={"version": "5.0", "appName": "Radarr"})
    )
    out = RadarrClient(ARR, "k").check()
    assert out["ok"] is True
    assert "Radarr" in out["detail"] or "5.0" in out["detail"]


@respx.mock
def test_arr_check_failure_reports_status_not_exception():
    respx.get(f"{ARR}/api/v3/system/status").mock(
        return_value=httpx.Response(401, json={"error": "Unauthorized"})
    )
    out = RadarrClient(ARR, "k").check()
    assert out["ok"] is False
    assert out["detail"] == "HTTP 401"  # status code, not raw exception text


@respx.mock
def test_seerr_check_ok():
    respx.get(f"{SEERR}/api/v1/status").mock(
        return_value=httpx.Response(200, json={"version": "1.33.2"})
    )
    out = SeerrClient(SEERR, "k").check()
    assert out["ok"] is True
    assert "1.33.2" in out["detail"]


@respx.mock
def test_tautulli_check_ok():
    respx.get(f"{TAUT}/api/v2").mock(
        return_value=httpx.Response(
            200,
            json={"response": {"result": "success", "data": {"pms_name": "Home"}}},
        )
    )
    out = TautulliClient(TAUT, "k").check()
    assert out["ok"] is True


@respx.mock
def test_tautulli_check_failure_on_error_result():
    respx.get(f"{TAUT}/api/v2").mock(
        return_value=httpx.Response(200, json={"response": {"result": "error", "message": "bad key"}})
    )
    out = TautulliClient(TAUT, "k").check()
    assert out["ok"] is False


def test_plex_check_ok_with_fake_server():
    from app.clients.plex import PlexClient

    client = PlexClient.__new__(PlexClient)  # skip __init__/connect
    client._server = type("S", (), {"friendlyName": "MyPlex"})()
    out = client.check()
    assert out["ok"] is True
    assert "MyPlex" in out["detail"]


def test_plex_check_failure_when_server_raises():
    from app.clients.plex import PlexClient

    class Boom:
        @property
        def friendlyName(self):
            raise RuntimeError("connection refused")

    client = PlexClient.__new__(PlexClient)
    client._server = Boom()
    out = client.check()
    assert out["ok"] is False
    assert out["detail"] == "unreachable"  # generic, no exception text leaked
