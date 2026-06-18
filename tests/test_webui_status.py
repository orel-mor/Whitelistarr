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


def test_status_includes_readonly_label_map(tmp_path):
    body = _client(tmp_path).get("/api/status").json()
    assert body["label_map"] == {"a": "b"}


def test_status_includes_activity_history(tmp_path):
    body = _client(tmp_path).get("/api/status").json()
    assert isinstance(body["history"], list)


def _actions_client(tmp_path, label_sync):
    from app.status import StatusTracker

    tracker = StatusTracker()

    class RT:
        settings = Settings(plex_url="http://p", plex_token="t", tag_label_map="a:b")
        components = None

        def __init__(self):
            self.tracker = tracker
            self.label_sync = label_sync

    store = ConfigStore(str(tmp_path / "c.json"), KEY)
    app = FastAPI()
    app.include_router(create_webui_router(runtime=RT(), store=store))
    return TestClient(app), tracker


def test_manual_sweep_appends_to_activity_history(tmp_path):
    ls = SimpleNamespace(sweep=lambda: {"processed": 3, "changed": 1})
    client, tracker = _actions_client(tmp_path, ls)
    client.post("/api/actions/sweep")
    hist = client.get("/api/status").json()["history"]
    assert hist[0]["action"] == "sweep"
    assert hist[0]["changed"] == 1


def test_manual_noop_sweep_still_logged(tmp_path):
    # A user-clicked sweep that changes nothing must still show feedback.
    ls = SimpleNamespace(sweep=lambda: {"processed": 3, "changed": 0})
    client, _ = _actions_client(tmp_path, ls)
    client.post("/api/actions/sweep")
    assert client.get("/api/status").json()["history"][0]["action"] == "sweep"


def test_status_unconfigured_no_components(tmp_path):
    body = _client(tmp_path, configured=False, components=False).get("/api/status").json()
    assert body["configured"] is False
    assert body["errors"]
    assert body["jobs"] == []
    assert body["connections"] == {}


def test_logs_endpoint_returns_buffered_lines(tmp_path):
    import logging

    from app.logbuffer import LOG_BUFFER

    LOG_BUFFER.handle(
        logging.LogRecord("t", logging.INFO, __file__, 1, "ui-log-marker", None, None)
    )
    body = _client(tmp_path).get("/api/logs").json()
    assert any(line["message"] == "ui-log-marker" for line in body["lines"])
    assert "last_id" in body


def test_logs_endpoint_after_returns_only_newer(tmp_path):
    import logging

    from app.logbuffer import LOG_BUFFER

    client = _client(tmp_path)
    last = client.get("/api/logs").json()["last_id"]
    LOG_BUFFER.handle(
        logging.LogRecord("t", logging.INFO, __file__, 1, "after-marker", None, None)
    )
    body = client.get(f"/api/logs?after={last}").json()
    # The `after` cursor must exclude everything at/before `last` (other tests share
    # the process-global buffer), and include the record we just added.
    assert all(line["id"] > last for line in body["lines"])
    assert any(line["message"] == "after-marker" for line in body["lines"])


def test_logs_endpoint_tail_limits_to_last_n(tmp_path):
    import logging

    from app.logbuffer import LOG_BUFFER

    for i in range(6):
        LOG_BUFFER.handle(
            logging.LogRecord("t", logging.INFO, __file__, 1, f"tail-marker-{i}", None, None)
        )
    body = _client(tmp_path).get("/api/logs?tail=2").json()
    assert len(body["lines"]) == 2
    assert body["lines"][-1]["message"] == "tail-marker-5"


def test_connection_test_ok(tmp_path):
    resp = _client(tmp_path).post("/api/connections/test/plex")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "detail": "MyPlex"}


def test_connection_test_unconfigured_service_409(tmp_path):
    resp = _client(tmp_path).post("/api/connections/test/sonarr")
    assert resp.status_code == 409
