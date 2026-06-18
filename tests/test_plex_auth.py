import httpx
import respx

from app.clients.plex_auth import PlexAuth

PLEX = "https://plex.tv"


@respx.mock
def test_create_pin_returns_id_code_and_auth_url():
    respx.post(f"{PLEX}/api/v2/pins").mock(
        return_value=httpx.Response(201, json={"id": 12345, "code": "abcd"})
    )
    out = PlexAuth(client_id="cid").create_pin()
    assert out["id"] == 12345
    assert out["code"] == "abcd"
    assert "clientID=cid" in out["authUrl"]
    assert "code=abcd" in out["authUrl"]


@respx.mock
def test_poll_pin_returns_none_until_authorized():
    respx.get(f"{PLEX}/api/v2/pins/12345").mock(
        return_value=httpx.Response(200, json={"id": 12345, "authToken": None})
    )
    assert PlexAuth(client_id="cid").poll_pin(12345) is None


@respx.mock
def test_poll_pin_returns_token_when_authorized():
    respx.get(f"{PLEX}/api/v2/pins/12345").mock(
        return_value=httpx.Response(200, json={"id": 12345, "authToken": "tok-xyz"})
    )
    assert PlexAuth(client_id="cid").poll_pin(12345) == "tok-xyz"


@respx.mock
def test_list_servers_filters_and_shapes():
    resources = [
        {"name": "Home", "provides": "server", "clientIdentifier": "srv1",
         "connections": [{"uri": "http://192.168.1.2:32400", "local": True},
                         {"uri": "https://x.plex.direct:32400", "local": False}]},
        {"name": "Phone", "provides": "client", "clientIdentifier": "c1", "connections": []},
    ]
    respx.get(f"{PLEX}/api/v2/resources").mock(
        return_value=httpx.Response(200, json=resources)
    )
    servers = PlexAuth(client_id="cid").list_servers("tok-xyz")
    assert len(servers) == 1
    assert servers[0]["name"] == "Home"
    assert {c["uri"] for c in servers[0]["connections"]} == {
        "http://192.168.1.2:32400", "https://x.plex.direct:32400"}


@respx.mock
def test_account_returns_username():
    respx.get(f"{PLEX}/api/v2/user").mock(
        return_value=httpx.Response(200, json={"username": "orel", "title": "Orel"})
    )
    assert PlexAuth(client_id="cid").account("tok-xyz") == "orel"


@respx.mock
def test_account_falls_back_to_title_then_none():
    respx.get(f"{PLEX}/api/v2/user").mock(
        return_value=httpx.Response(200, json={"title": "Orel"})
    )
    assert PlexAuth(client_id="cid").account("tok-xyz") == "Orel"


@respx.mock
def test_account_sends_token_header():
    route = respx.get(f"{PLEX}/api/v2/user").mock(
        return_value=httpx.Response(200, json={"username": "orel"})
    )
    PlexAuth(client_id="cid").account("tok-xyz")
    assert route.calls.last.request.headers["X-Plex-Token"] == "tok-xyz"


@respx.mock
def test_requests_send_client_identifier_header():
    route = respx.post(f"{PLEX}/api/v2/pins").mock(
        return_value=httpx.Response(201, json={"id": 1, "code": "z"})
    )
    PlexAuth(client_id="my-id").create_pin()
    assert route.calls.last.request.headers["X-Plex-Client-Identifier"] == "my-id"
