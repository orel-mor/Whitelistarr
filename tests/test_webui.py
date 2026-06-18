from types import SimpleNamespace

import httpx
import respx
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.configstore import ConfigStore
from app.runtime import ReloadResult
from app.webui import create_webui_router

KEY = Fernet.generate_key().decode()


class FakeRuntime:
    def __init__(self, settings, label_sync=None, reload_result=None, components=None):
        self.settings = settings
        self.label_sync = label_sync
        self._reload_result = reload_result or ReloadResult(ok=True)
        self.reloaded_with = None
        self.components = components

    def reload(self, new_settings):
        self.reloaded_with = new_settings
        return self._reload_result


def _client(tmp_path, label_sync=None, settings=None, reload_result=None):
    store = ConfigStore(str(tmp_path / "config.json"), KEY)
    settings = settings or Settings(
        plex_url="http://plex:32400", plex_token="t", tag_label_map="a:b"
    )
    runtime = FakeRuntime(settings, label_sync=label_sync, reload_result=reload_result)
    app = FastAPI()
    app.include_router(create_webui_router(runtime=runtime, store=store))
    return TestClient(app), store, runtime


def test_schema_endpoint(tmp_path):
    client, _, _ = _client(tmp_path)
    resp = client.get("/api/schema")
    assert resp.status_code == 200
    groups = resp.json()["groups"]
    assert any(g["name"] == "Plex" for g in groups)


def test_config_masks_secrets(tmp_path):
    client, store, _ = _client(tmp_path)
    store.save({"plex_url": "http://plex:32400", "plex_token": "s3cret"})
    resp = client.get("/api/config")
    values = resp.json()["values"]
    assert values["plex_url"] == "http://plex:32400"
    assert values["plex_token"] == {"set": True}  # never plaintext
    assert "errors" in resp.json()


def test_apprise_revealed_in_config_but_encrypted_on_disk(tmp_path):
    client, store, _ = _client(tmp_path)
    store.save({"apprise_urls": "discord://tok@id,tgram://bot/chat"})
    # On disk it is encrypted (not the plaintext URLs)...
    import json

    with open(store._path, encoding="utf-8") as fh:
        raw = json.load(fh)
    assert raw["apprise_urls"] != "discord://tok@id,tgram://bot/chat"
    # ...but the UI gets the real value back (it's not a masked secret).
    values = client.get("/api/config").json()["values"]
    assert values["apprise_urls"] == "discord://tok@id,tgram://bot/chat"


def test_save_persists_and_calls_reload(tmp_path):
    client, store, runtime = _client(tmp_path)
    resp = client.post("/api/config", json={"plex_url": "http://new:32400"})
    assert resp.status_code == 200
    assert resp.json()["restart_required"] is False  # managed-tier field
    assert store.load()["plex_url"] == "http://new:32400"
    assert runtime.reloaded_with is not None  # live reload attempted


def test_save_bootstrap_change_flags_restart(tmp_path):
    rr = ReloadResult(ok=True, restart_required=True, restart_fields=["webhook_port"])
    client, store, runtime = _client(tmp_path, reload_result=rr)
    resp = client.post("/api/config", json={"webhook_port": 9000})
    assert resp.status_code == 200
    assert resp.json()["restart_required"] is True
    assert "webhook_port" in resp.json()["restart_fields"]


def test_save_reports_reload_error_but_keeps_store(tmp_path):
    rr = ReloadResult(ok=False, error="cannot connect to Plex")
    client, store, runtime = _client(tmp_path, reload_result=rr)
    resp = client.post("/api/config", json={"plex_url": "http://bad:32400"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is False
    assert "Plex" in resp.json()["error"]
    assert store.load()["plex_url"] == "http://bad:32400"  # saved anyway


def test_save_secret_updates_only_when_provided(tmp_path):
    client, store, _ = _client(tmp_path)
    store.save({"plex_token": "old"})
    client.post("/api/config", json={"plex_url": "x"})  # no token -> keep
    assert store.load()["plex_token"] == "old"
    client.post("/api/config", json={"plex_token": "new"})
    assert store.load()["plex_token"] == "new"


def test_save_rejects_bad_type(tmp_path):
    client, store, _ = _client(tmp_path)
    resp = client.post("/api/config", json={"webhook_port": "not-a-number"})
    assert resp.status_code == 422


def test_save_ignores_unknown_keys(tmp_path):
    client, store, _ = _client(tmp_path)
    client.post("/api/config", json={"plex_url": "x", "evil": "y"})
    assert "evil" not in store.load()


def test_action_sweep_uses_runtime_label_sync(tmp_path):
    calls = []
    ls = SimpleNamespace(sweep=lambda: calls.append(1) or {"processed": 5, "changed": 2})
    client, _, _ = _client(tmp_path, label_sync=ls)
    resp = client.post("/api/actions/sweep")
    assert resp.status_code == 200
    assert resp.json()["changed"] == 2
    assert calls == [1]


def test_action_sweep_409_when_unconfigured(tmp_path):
    client, _, _ = _client(tmp_path, label_sync=None)
    assert client.post("/api/actions/sweep").status_code == 409


@respx.mock
def test_connection_test_uses_posted_credentials_without_saving(tmp_path):
    # The Test connection button must probe the values typed into the form, even
    # before they're saved (and even when the live component isn't built yet).
    respx.get("http://seerr:5055/api/v1/status").mock(
        return_value=httpx.Response(200, json={"version": "1.33.2"})
    )
    client, store, _ = _client(tmp_path)
    resp = client.post(
        "/api/connections/test/seerr",
        json={"url": "http://seerr:5055", "api_key": "k"},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert "1.33.2" in resp.json()["detail"]
    # Probing must not persist anything.
    assert not store.exists() or "seerr_url" not in store.load()


def test_connection_test_unknown_service_409(tmp_path):
    client, _, _ = _client(tmp_path)
    assert client.post("/api/connections/test/bogus", json={}).status_code == 409


def test_action_reverse_requires_confirm(tmp_path):
    ls = SimpleNamespace(reverse_sweep=lambda: {"processed": 1, "changed": 1})
    client, _, _ = _client(tmp_path, label_sync=ls)
    assert client.post("/api/actions/reverse", json={}).status_code == 400
    assert client.post("/api/actions/reverse", json={"confirm": True}).status_code == 200


class FakePlexAuth:
    def __init__(self):
        self.applied = None

    def create_pin(self, forward_url=None):
        auth_url = "https://app.plex.tv/auth#?code=cc"
        if forward_url:
            auth_url = f"{auth_url}&forwardUrl={forward_url}"
        return {"id": 99, "code": "cc", "authUrl": auth_url}

    def poll_pin(self, pin_id):
        return "tok-secret" if str(pin_id) == "99" else None

    def list_servers(self, token):
        assert token == "tok-secret"
        return [{"name": "Home", "clientIdentifier": "s1",
                 "connections": [{"uri": "http://192.168.1.2:32400", "local": True}]}]

    def account(self, token):
        return "orel" if token else None


def _plex_client(tmp_path):
    store = ConfigStore(str(tmp_path / "config.json"), KEY)
    settings = Settings(plex_client_id="cid")
    runtime = FakeRuntime(settings)
    auth = FakePlexAuth()
    app = FastAPI()
    app.include_router(create_webui_router(runtime=runtime, store=store, plex_auth=auth))
    return TestClient(app), store, runtime


def test_plex_pin_create(tmp_path):
    client, _, _ = _plex_client(tmp_path)
    resp = client.post("/api/plex/pin")
    assert resp.status_code == 200
    assert resp.json()["id"] == 99
    assert "authUrl" in resp.json()


def test_plex_pin_success_self_closes(tmp_path):
    client, _, _ = _plex_client(tmp_path)
    resp = client.get("/plex/auth/success")
    assert resp.status_code == 200
    assert b"window.close()" in resp.content
    # No auth token is ever reflected into the self-closing page.
    assert b"tok-secret" not in resp.content


def test_plex_poll_authorizes_without_leaking_token(tmp_path):
    client, _, _ = _plex_client(tmp_path)
    client.post("/api/plex/pin")
    resp = client.get("/api/plex/pin/99")
    assert resp.status_code == 200
    body = resp.json()
    assert body["authorized"] is True
    assert "tok-secret" not in resp.text  # token never returned to browser


def test_plex_pin_token_expires(tmp_path, monkeypatch):
    import app.webui as webui

    monkeypatch.setattr(webui, "PIN_TTL", -1.0)  # any cached token is already expired
    client, _, _ = _plex_client(tmp_path)
    client.post("/api/plex/pin")
    client.get("/api/plex/pin/99")  # caches token server-side
    assert client.get("/api/plex/servers?pin_id=99").status_code == 409


def test_plex_servers_then_apply_writes_url_and_token(tmp_path):
    client, store, runtime = _plex_client(tmp_path)
    client.post("/api/plex/pin")
    client.get("/api/plex/pin/99")  # caches token server-side
    servers = client.get("/api/plex/servers?pin_id=99").json()
    assert servers["servers"][0]["name"] == "Home"
    resp = client.post("/api/plex/apply",
                       json={"pin_id": 99, "uri": "http://192.168.1.2:32400"})
    assert resp.status_code == 200
    saved = store.load()
    assert saved["plex_url"] == "http://192.168.1.2:32400"
    assert saved["plex_token"] == "tok-secret"  # decrypts back via store.load()
    assert runtime.reloaded_with is not None


class FakePlexLibClient:
    def __init__(self, libs):
        self._libs = libs

    def list_libraries(self):
        return self._libs


def test_plex_libraries_lists_from_live_component(tmp_path):
    store = ConfigStore(str(tmp_path / "config.json"), KEY)
    libs = [{"title": "Movies", "type": "movie"}, {"title": "TV", "type": "show"}]
    comps = SimpleNamespace(plex=FakePlexLibClient(libs))
    runtime = FakeRuntime(Settings(), components=comps)
    app = FastAPI()
    app.include_router(create_webui_router(runtime=runtime, store=store))
    client = TestClient(app)
    resp = client.get("/api/plex/libraries")
    assert resp.status_code == 200
    assert resp.json()["libraries"] == libs


def test_plex_libraries_empty_when_no_component(tmp_path):
    client, _, _ = _client(tmp_path)  # FakeRuntime with components=None
    resp = client.get("/api/plex/libraries")
    assert resp.status_code == 200
    assert resp.json()["libraries"] == []


def test_plex_libraries_from_saved_creds_during_onboarding(tmp_path, monkeypatch):
    # Mid-onboarding the live components aren't built yet (config still incomplete),
    # but Plex is already signed in. The picker must still list libraries by building
    # a throwaway client from the saved creds.
    import app.webui as webui

    libs = [{"title": "Movies", "type": "movie"}]
    built = {}

    def fake_make_plex_client(url, token):
        built["url"], built["token"] = url, token
        return FakePlexLibClient(libs)

    monkeypatch.setattr(webui, "_make_plex_client", fake_make_plex_client)

    store = ConfigStore(str(tmp_path / "config.json"), KEY)
    store.save({"plex_url": "http://plex:32400", "plex_token": "tok"})
    runtime = FakeRuntime(Settings(), components=None)  # not configured yet
    app = FastAPI()
    app.include_router(create_webui_router(runtime=runtime, store=store))
    client = TestClient(app)

    resp = client.get("/api/plex/libraries")
    assert resp.status_code == 200
    assert resp.json()["libraries"] == libs
    assert built == {"url": "http://plex:32400", "token": "tok"}


def test_plex_account_reports_connected_and_username(tmp_path):
    store = ConfigStore(str(tmp_path / "config.json"), KEY)
    settings = Settings(plex_url="http://plex:32400", plex_token="t", plex_client_id="cid")
    runtime = FakeRuntime(settings)
    app = FastAPI()
    app.include_router(
        create_webui_router(runtime=runtime, store=store, plex_auth=FakePlexAuth())
    )
    client = TestClient(app)
    body = client.get("/api/plex/account").json()
    assert body["connected"] is True
    assert body["username"] == "orel"


def test_plex_account_not_connected_when_no_token(tmp_path):
    store = ConfigStore(str(tmp_path / "config.json"), KEY)
    runtime = FakeRuntime(Settings(plex_url="", plex_token=""))
    app = FastAPI()
    app.include_router(
        create_webui_router(runtime=runtime, store=store, plex_auth=FakePlexAuth())
    )
    client = TestClient(app)
    body = client.get("/api/plex/account").json()
    assert body["connected"] is False
    assert body["username"] == ""


def test_plex_disconnect_clears_creds_and_reloads(tmp_path):
    store = ConfigStore(str(tmp_path / "config.json"), KEY)
    store.save({"plex_url": "http://plex:32400", "plex_token": "secret",
                "plex_sections": "Movies"})
    runtime = FakeRuntime(Settings())
    app = FastAPI()
    app.include_router(create_webui_router(runtime=runtime, store=store))
    client = TestClient(app)
    resp = client.post("/api/plex/disconnect")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    saved = store.load()
    assert not saved.get("plex_url")
    assert not saved.get("plex_token")
    assert saved.get("plex_sections") == "Movies"  # library picks survive
    assert runtime.reloaded_with is not None


def test_static_serves_packaged_files(tmp_path):
    client, _, _ = _client(tmp_path)
    for name in (
        "index.html", "vendor/alpine.min.js", "css/style.css",
        "js/api.js", "js/router.js", "js/store.js", "js/helpers.js", "js/app.js",
        "logo.svg",
    ):
        assert client.get(f"/static/{name}").status_code == 200, name


def test_static_assets_revalidate(tmp_path):
    # Static assets must carry a no-cache header so a browser revalidates (ETag)
    # on each load — otherwise a UI update ships but stale JS keeps being served.
    client, _, _ = _client(tmp_path)
    for name in ("index.html", "js/app.js"):
        resp = client.get(f"/static/{name}")
        assert "no-cache" in resp.headers.get("cache-control", ""), name


def test_logo_served_with_svg_content_type(tmp_path):
    client, _, _ = _client(tmp_path)
    resp = client.get("/static/logo.svg")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/svg+xml")


def test_static_rejects_traversal(tmp_path):
    # Names that resolve outside the static dir, or to a non-file, must 404 —
    # never serve arbitrary files from the package/filesystem. Only the fixed
    # allowlist is served; anything else (incl. encoded separators) 404s.
    client, _, _ = _client(tmp_path)
    for name in (
        "does-not-exist.js",
        "%2e%2e%2fconfig.py",
        "%2e%2e%2f%2e%2e%2fpyproject.toml",
        "js/../../config.py",
    ):
        assert client.get(f"/static/{name}").status_code == 404


def test_static_confines_to_allowlist(tmp_path):
    # Directly exercise the confinement: only allowlisted relative paths resolve.
    from app.webui import _static_response

    assert _static_response("..").status_code == 404
    assert _static_response("../config.py").status_code == 404
    assert _static_response("js/../store.js").status_code == 404
    assert _static_response("index.html").status_code == 200
