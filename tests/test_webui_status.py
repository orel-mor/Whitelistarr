import time
from types import SimpleNamespace

from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.configstore import ConfigStore
from app.status import StatusTracker
from app.webui import create_webui_router

KEY = Fernet.generate_key().decode()


def _rt_with_plex(plex_check, tmp_path):
    settings = Settings(
        plex_url="http://p", plex_token="t",
        radarr_url="http://r", radarr_api_key="k",
        sonarr_url="http://s", sonarr_api_key="k", tag_label_map="a:b",
    )
    comps = SimpleNamespace(
        scheduler=FakeScheduler(),
        plex=SimpleNamespace(check=plex_check),
        radarr=None, sonarr=None, seerr=None, tautulli=None, label_sync="ls",
    )

    class RT:
        def __init__(self):
            self.settings = settings
            self.components = comps
            self.tracker = StatusTracker()
            self.label_sync = "ls"

    store = ConfigStore(str(tmp_path / "c.json"), KEY)
    app = FastAPI()
    app.include_router(create_webui_router(runtime=RT(), store=store))
    return TestClient(app)


def test_status_caches_connections(tmp_path):
    calls = {"n": 0}

    def chk():
        calls["n"] += 1
        return {"ok": True, "detail": "x"}

    client = _rt_with_plex(chk, tmp_path)
    client.get("/api/status")
    client.get("/api/status")
    assert calls["n"] == 1  # second poll served from cache


def test_status_handles_probe_exception(tmp_path):
    def chk():
        raise RuntimeError("boom")

    client = _rt_with_plex(chk, tmp_path)
    r = client.get("/api/status")
    assert r.status_code == 200
    assert r.json()["connections"]["plex"]["ok"] is False


def test_status_bounds_slow_probe(tmp_path, monkeypatch):
    import app.webui as webui

    monkeypatch.setattr(webui, "PROBE_TIMEOUT", 0.05)

    def chk():
        time.sleep(0.4)
        return {"ok": True, "detail": "slow"}

    client = _rt_with_plex(chk, tmp_path)
    body = client.get("/api/status").json()
    assert body["connections"]["plex"]["ok"] is False
    assert "out" in body["connections"]["plex"]["detail"]  # "timed out"


class FakeJob:
    def __init__(self, name, next_run):
        self.name = name
        self.next_run_time = next_run


class FakeScheduler:
    def jobs(self):
        return [FakeJob("sweep", _Iso("2026-06-17T10:00:00+00:00"))]


class _Iso:
    def __init__(self, s):
        self._s = s

    def isoformat(self):
        return self._s


def _runtime(tmp_path, configured=True, components=True):
    settings = (
        Settings(
            plex_url="http://plex:32400", plex_token="t",
            radarr_url="http://radarr:7878", radarr_api_key="rk",
            sonarr_url="http://sonarr:8989", sonarr_api_key="sk",
            tag_label_map="a:b",
        )
        if configured
        else Settings()
    )
    tracker = StatusTracker()
    tracker.record("sweep", {"processed": 9, "changed": 2})
    comps = None
    if components:
        comps = SimpleNamespace(
            scheduler=FakeScheduler(),
            plex=SimpleNamespace(check=lambda: {"ok": True, "detail": "MyPlex"}),
            radarr=SimpleNamespace(check=lambda: {"ok": False, "detail": "401"}),
            sonarr=None,
            seerr=None,
            tautulli=None,
            label_sync="ls",
        )

    class RT:
        def __init__(self):
            self.settings = settings
            self.components = comps
            self.tracker = tracker
            self.label_sync = comps.label_sync if comps else None

    return RT()


def _client(tmp_path, **kw):
    store = ConfigStore(str(tmp_path / "config.json"), KEY)
    app = FastAPI()
    app.include_router(create_webui_router(runtime=_runtime(tmp_path, **kw), store=store))
    return TestClient(app)


def test_status_shape(tmp_path):
    body = _client(tmp_path).get("/api/status").json()
    assert body["configured"] is True
    assert body["jobs"][0]["name"] == "sweep"
    assert body["jobs"][0]["next_run"] == "2026-06-17T10:00:00+00:00"
    assert body["last"]["sweep"]["changed"] == 2
    assert body["connections"]["plex"] == {"ok": True, "detail": "MyPlex"}
    assert body["connections"]["radarr"]["ok"] is False
    assert "sonarr" not in body["connections"]  # None clients omitted


def test_status_unconfigured_no_components(tmp_path):
    body = _client(tmp_path, configured=False, components=False).get("/api/status").json()
    assert body["configured"] is False
    assert body["errors"]
    assert body["jobs"] == []
    assert body["connections"] == {}


def test_connection_test_ok(tmp_path):
    resp = _client(tmp_path).post("/api/connections/test/plex")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "detail": "MyPlex"}


def test_connection_test_unconfigured_service_409(tmp_path):
    resp = _client(tmp_path).post("/api/connections/test/sonarr")
    assert resp.status_code == 409
