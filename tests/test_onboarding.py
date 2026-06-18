from app.config import Settings
from app.onboarding import ARR, DONE, NOTIFY, PLEX, TAGS, next_incomplete_step


def _settings(**over):
    base = dict(
        plex_url="http://plex:32400", plex_token="t",
        radarr_url="http://radarr:7878", radarr_api_key="rk",
        sonarr_url="http://sonarr:8989", sonarr_api_key="sk",
        tag_label_map="a:b",
    )
    base.update(over)
    return Settings(**base)


def test_plex_first_incomplete_step_when_no_plex():
    assert next_incomplete_step(Settings()) == PLEX


def test_arr_step_when_plex_set_but_arr_missing():
    s = _settings(radarr_url="", radarr_api_key="", sonarr_url="", sonarr_api_key="")
    assert next_incomplete_step(s) == ARR


def test_arr_step_when_only_one_arr_present():
    # runtime_errors requires BOTH radarr and sonarr for labeling.
    assert next_incomplete_step(_settings(sonarr_url="", sonarr_api_key="")) == ARR


def test_tags_step_when_arr_set_but_no_label_map():
    assert next_incomplete_step(_settings(tag_label_map="")) == TAGS


def test_notify_step_when_notifications_enabled_but_incomplete():
    s = _settings(feature_notify=True)  # tautulli/apprise/seerr all missing
    assert next_incomplete_step(s) == NOTIFY


def test_done_when_everything_required_present():
    assert next_incomplete_step(_settings()) == DONE


def test_done_ignores_notify_details_when_notify_disabled():
    # Notifications are optional: a fully-labeling config with notify off is done.
    assert next_incomplete_step(_settings(feature_notify=False)) == DONE


def test_labeling_steps_skipped_when_labeling_disabled():
    # No webhook + no sweep => arr/tags aren't required to finish onboarding.
    s = Settings(
        plex_url="http://plex:32400", plex_token="t",
        feature_webhook=False, feature_sweep=False, feature_notify=False,
    )
    assert next_incomplete_step(s) == DONE
