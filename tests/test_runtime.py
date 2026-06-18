from types import SimpleNamespace

from app.runtime import BOOTSTRAP_FIELDS, Runtime


class FakeScheduler:
    def __init__(self):
        self.started = False
        self.shutdown_called = False

    def start(self):
        self.started = True

    def shutdown(self):
        self.shutdown_called = True


def _components(label="ls"):
    return SimpleNamespace(label_sync=label, scheduler=FakeScheduler())


def _settings(**over):
    base = dict(
        plex_url="http://plex:32400", webhook_host="0.0.0.0", webhook_port=8000,
        pal_secret_key="k", config_path="/data/config.json",
        state_db_path="/data/state.db", feature_ui=True,
        runtime_errors=lambda: [],
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_label_sync_resolves_through_holder():
    rt = Runtime(_settings(), _components("first"))
    assert rt.label_sync == "first"


def test_label_sync_none_when_unconfigured():
    rt = Runtime(_settings(), None)
    assert rt.label_sync is None


def test_reload_swaps_components_on_success():
    old = _components("old")
    new = _components("new")
    rt = Runtime(_settings(), old, builder=lambda s: new)
    rt.start()
    result = rt.reload(_settings(plex_url="http://other:32400"))
    assert result.ok is True
    assert rt.label_sync == "new"
    assert old.scheduler.shutdown_called is True   # old torn down
    assert new.scheduler.started is True            # new started


def test_reload_does_not_start_scheduler_when_unconfigured():
    # Mid-onboarding (e.g. Plex saved but Radarr/Sonarr not yet): don't build or
    # start jobs until config is complete. Mirror boot's "UI only" behaviour.
    old = _components("old")
    new = _components("new")
    rt = Runtime(_settings(), old, builder=lambda s: new)
    rt.start()
    result = rt.reload(_settings(runtime_errors=lambda: ["RADARR_URL is required."]))
    assert result.ok is True
    assert new.scheduler.started is False           # jobs not started yet
    assert old.scheduler.shutdown_called is True    # old torn down
    assert rt.components is None                     # UI-only until configured


def test_reload_stays_ui_only_until_onboarding_complete():
    # Config is valid but the user hasn't pressed Finish yet: don't build clients
    # or start jobs. Routines only start once onboarding_complete flips true.
    old = _components("old")
    new = _components("new")
    rt = Runtime(_settings(onboarding_complete=False), old, builder=lambda s: new)
    rt.start()
    result = rt.reload(_settings(onboarding_complete=False))
    assert result.ok is True
    assert rt.components is None
    assert new.scheduler.started is False
    assert old.scheduler.shutdown_called is True


def test_reload_builds_when_onboarding_complete():
    old = _components("old")
    new = _components("new")
    rt = Runtime(_settings(onboarding_complete=False), old, builder=lambda s: new)
    rt.start()
    result = rt.reload(_settings(onboarding_complete=True))
    assert result.ok is True
    assert rt.label_sync == "new"
    assert new.scheduler.started is True


def test_reload_rolls_back_on_build_failure():
    old = _components("old")

    def boom(_settings):
        raise RuntimeError("cannot connect to Plex")

    rt = Runtime(_settings(), old, builder=boom)
    rt.start()
    result = rt.reload(_settings(plex_url="http://bad:32400"))
    assert result.ok is False
    assert result.error == "RuntimeError"           # class name, not raw message
    assert rt.label_sync == "old"                   # unchanged
    assert old.scheduler.shutdown_called is False   # still running


def test_reload_flags_restart_required_for_bootstrap_change():
    rt = Runtime(_settings(), _components(), builder=lambda s: _components())
    result = rt.reload(_settings(webhook_port=9000))
    assert result.ok is True
    assert result.restart_required is True
    assert "webhook_port" in result.restart_fields


def test_bootstrap_fields_cover_bind_and_secret():
    assert {"webhook_host", "webhook_port", "pal_secret_key"} <= BOOTSTRAP_FIELDS


def test_runtime_has_status_tracker():
    from app.status import StatusTracker

    rt = Runtime(_settings(), _components(), builder=lambda s: _components())
    assert isinstance(rt.tracker, StatusTracker)
