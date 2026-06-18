"""create_application must wire ONE StatusTracker into both the components (so
scheduled jobs record into it) and the Runtime (so /api/status reads the same
one). Regression: previously build_components got no tracker, so every job ran
unrecorded and the Status page showed "never run" forever."""

from types import SimpleNamespace

import app.main as main
from app.config import Settings


def _configured_settings():
    return Settings(
        plex_url="http://plex:32400", plex_token="t",
        radarr_url="http://radarr:7878", radarr_api_key="rk",
        sonarr_url="http://sonarr:8989", sonarr_api_key="sk",
        tag_label_map="a:b",
        feature_ui=False,  # skip the ConfigStore/webui branch in this test
    )


def test_create_application_passes_runtime_tracker_to_build_components(monkeypatch):
    captured = {}

    def fake_build(settings, tracker=None):
        captured["tracker"] = tracker
        return SimpleNamespace(
            scheduler=SimpleNamespace(jobs=lambda: [], start=lambda: None, shutdown=lambda: None),
            label_sync=None,
        )

    captured_runtimes = []
    real_runtime_cls = main.Runtime

    def spy_runtime(*args, **kwargs):
        rt = real_runtime_cls(*args, **kwargs)
        captured_runtimes.append(rt)
        return rt

    monkeypatch.setattr(main, "build_components", fake_build)
    monkeypatch.setattr(main, "Runtime", spy_runtime)

    main.create_application(_configured_settings())

    assert captured["tracker"] is not None  # regression: used to be None
    # The very tracker the jobs record into is the one the UI reads.
    assert captured_runtimes[0].tracker is captured["tracker"]


def _ui_settings(tmp_path, **over):
    from cryptography.fernet import Fernet

    base = dict(
        plex_url="http://plex:32400", plex_token="t",
        radarr_url="http://radarr:7878", radarr_api_key="rk",
        sonarr_url="http://sonarr:8989", sonarr_api_key="sk",
        tag_label_map="a:b",
        feature_ui=True, pal_secret_key=Fernet.generate_key().decode(),
        config_path=str(tmp_path / "config.json"),
    )
    base.update(over)
    return Settings(**base)


def _spy_build(monkeypatch):
    built = {"n": 0}

    def fake_build(settings, tracker=None):
        built["n"] += 1
        return SimpleNamespace(
            scheduler=SimpleNamespace(jobs=lambda: [], start=lambda: None, shutdown=lambda: None),
            label_sync=None,
        )

    monkeypatch.setattr(main, "build_components", fake_build)
    return built


def test_ui_mode_builds_nothing_until_onboarding_complete(monkeypatch, tmp_path):
    # Fully configured but onboarding not finished: no clients, no scheduler.
    built = _spy_build(monkeypatch)
    main.create_application(_ui_settings(tmp_path, onboarding_complete=False))
    assert built["n"] == 0


def test_ui_mode_builds_when_onboarding_complete(monkeypatch, tmp_path):
    built = _spy_build(monkeypatch)
    main.create_application(_ui_settings(tmp_path, onboarding_complete=True))
    assert built["n"] == 1


def test_headless_mode_ignores_onboarding_flag(monkeypatch, tmp_path):
    # FEATURE_UI off => no wizard exists; the onboarding gate must not apply.
    built = _spy_build(monkeypatch)
    main.create_application(_configured_settings())  # feature_ui=False, flag default False
    assert built["n"] == 1
