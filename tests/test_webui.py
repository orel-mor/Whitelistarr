from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.configstore import ConfigStore
from app.webui import create_webui_router

KEY = Fernet.generate_key().decode()


def _client(tmp_path, on_sweep=None, on_reverse=None, on_test=None, settings=None):
    store = ConfigStore(str(tmp_path / "config.json"), KEY)
    settings = settings or Settings(
        plex_url="http://plex:32400", plex_token="t", tag_label_map="a:b"
    )
    app = FastAPI()
    app.include_router(
        create_webui_router(
            settings=settings,
            store=store,
            on_sweep=on_sweep,
            on_reverse=on_reverse,
            on_test=on_test,
        )
    )
    return TestClient(app), store


def test_schema_endpoint(tmp_path):
    client, _ = _client(tmp_path)
    resp = client.get("/api/schema")
    assert resp.status_code == 200
    groups = resp.json()["groups"]
    assert any(g["name"] == "Plex" for g in groups)


def test_config_masks_secrets(tmp_path):
    client, store = _client(tmp_path)
    store.save({"plex_url": "http://plex:32400", "plex_token": "s3cret"})
    resp = client.get("/api/config")
    values = resp.json()["values"]
    assert values["plex_url"] == "http://plex:32400"
    assert values["plex_token"] == {"set": True}  # never plaintext
    assert "errors" in resp.json()


def test_save_persists_and_requests_restart(tmp_path):
    client, store = _client(tmp_path)
    resp = client.post("/api/config", json={"plex_url": "http://new:32400"})
    assert resp.status_code == 200
    assert resp.json()["restart_required"] is True
    assert store.load()["plex_url"] == "http://new:32400"


def test_save_secret_updates_only_when_provided(tmp_path):
    client, store = _client(tmp_path)
    store.save({"plex_token": "old"})
    client.post("/api/config", json={"plex_url": "x"})  # no token -> keep
    assert store.load()["plex_token"] == "old"
    client.post("/api/config", json={"plex_token": "new"})
    assert store.load()["plex_token"] == "new"


def test_save_rejects_bad_type(tmp_path):
    client, store = _client(tmp_path)
    resp = client.post("/api/config", json={"webhook_port": "not-a-number"})
    assert resp.status_code == 422


def test_save_ignores_unknown_keys(tmp_path):
    client, store = _client(tmp_path)
    client.post("/api/config", json={"plex_url": "x", "evil": "y"})
    assert "evil" not in store.load()


def test_action_sweep_invokes_callable(tmp_path):
    calls = []
    client, _ = _client(tmp_path, on_sweep=lambda: calls.append(1) or {"processed": 5, "changed": 2})
    resp = client.post("/api/actions/sweep")
    assert resp.status_code == 200
    assert resp.json()["changed"] == 2
    assert calls == [1]


def test_action_unavailable_returns_409(tmp_path):
    client, _ = _client(tmp_path, on_sweep=None)
    assert client.post("/api/actions/sweep").status_code == 409


def test_action_reverse_requires_confirm(tmp_path):
    client, _ = _client(tmp_path, on_reverse=lambda: {"processed": 1, "changed": 1})
    assert client.post("/api/actions/reverse", json={}).status_code == 400
    ok = client.post("/api/actions/reverse", json={"confirm": True})
    assert ok.status_code == 200


def test_action_test_notification(tmp_path):
    sent = []
    client, _ = _client(tmp_path, on_test=lambda: sent.append(1) or True)
    resp = client.post("/api/actions/test-notification")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert sent == [1]


def test_static_serves_packaged_files(tmp_path):
    client, _ = _client(tmp_path)
    for name in ("index.html", "app.js", "style.css"):
        assert client.get(f"/static/{name}").status_code == 200


def test_static_rejects_traversal(tmp_path):
    # Names that resolve outside the static dir, or to a non-file, must 404 —
    # never serve arbitrary files from the package/filesystem. Encoded separators
    # are the server-reachable form (a plain `..` is normalized away by the client).
    client, _ = _client(tmp_path)
    for name in (
        "does-not-exist.js",
        "%2e%2e%2fconfig.py",
        "%2e%2e%2f%2e%2e%2fpyproject.toml",
    ):
        assert client.get(f"/static/{name}").status_code == 404


def test_static_confines_to_static_dir(tmp_path):
    # Directly exercise the confinement: a sibling package file (config.py lives in
    # app/, one level above app/static/) must not be served.
    from app.webui import _static_response

    assert _static_response("..").status_code == 404
    assert _static_response("../config.py").status_code == 404
    assert _static_response("index.html").status_code == 200
