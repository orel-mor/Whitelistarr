"""End-to-end wiring: app boots UI-only when unconfigured, no network calls."""

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.config import load_settings
from app.main import create_application

KEY = Fernet.generate_key().decode()


def _app(monkeypatch, tmp_path, **over):
    env = {
        "FEATURE_UI": "true",
        "PAL_SECRET_KEY": KEY,
        "CONFIG_PATH": str(tmp_path / "config.json"),
        "STATE_DB_PATH": str(tmp_path / "state.db"),
        "FEATURE_WEBHOOK": "true",
        "FEATURE_SWEEP": "false",
        "FEATURE_NOTIFY": "false",
    }
    env.update(over)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return create_application(load_settings())


def test_ui_boots_when_unconfigured(monkeypatch, tmp_path):
    with TestClient(_app(monkeypatch, tmp_path)) as client:
        assert client.get("/health").status_code == 200
        assert "text/html" in client.get("/").headers["content-type"]
        assert any(g["name"] == "Plex" for g in client.get("/api/schema").json()["groups"])
        cfg = client.get("/api/config").json()
        assert cfg["errors"]  # unconfigured -> errors listed
        # webhook is registered but inert until configured
        assert client.post("/webhook/seerr", json={"notification_type": "MEDIA_AVAILABLE"}).status_code == 503


def test_save_config_via_api_persists(monkeypatch, tmp_path):
    with TestClient(_app(monkeypatch, tmp_path)) as client:
        resp = client.post("/api/config", json={
            "plex_url": "http://plex:32400",
            "plex_token": "tok",
            "tag_label_map": "niece-ok:kids",
        })
        assert resp.status_code == 200
        assert resp.json()["restart_required"] is True
        # reflected back, secret masked
        values = client.get("/api/config").json()["values"]
        assert values["plex_url"] == "http://plex:32400"
        assert values["plex_token"] == {"set": True}
