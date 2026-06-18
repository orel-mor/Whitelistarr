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
