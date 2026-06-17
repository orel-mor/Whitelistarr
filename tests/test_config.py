import pytest

from app.config import (
    Settings,
    is_valid_cron,
    minutes_to_cron,
    parse_csv,
    parse_tag_label_map,
)


class TestParseTagLabelMap:
    def test_parses_single_pair(self):
        assert parse_tag_label_map("kids:kids-allowed") == {"kids": "kids-allowed"}

    def test_parses_multiple_pairs(self):
        result = parse_tag_label_map("kids:kids-allowed,family:shared")
        assert result == {"kids": "kids-allowed", "family": "shared"}

    def test_trims_whitespace_around_entries_and_pairs(self):
        result = parse_tag_label_map(" kids : kids-allowed ,  family:shared ")
        assert result == {"kids": "kids-allowed", "family": "shared"}

    def test_empty_string_returns_empty_dict(self):
        assert parse_tag_label_map("") == {}
        assert parse_tag_label_map("   ") == {}

    def test_splits_on_first_colon_only(self):
        # label values are allowed to contain a colon
        assert parse_tag_label_map("tag:label:extra") == {"tag": "label:extra"}

    def test_raises_on_entry_without_colon(self):
        with pytest.raises(ValueError):
            parse_tag_label_map("kids,family:shared")

    def test_raises_on_empty_tag_or_label(self):
        with pytest.raises(ValueError):
            parse_tag_label_map(":label")
        with pytest.raises(ValueError):
            parse_tag_label_map("tag:")


class TestMinutesToCron:
    def test_60_is_hourly(self):
        assert minutes_to_cron(60) == "0 * * * *"

    def test_360_is_every_6_hours(self):
        assert minutes_to_cron(360) == "0 */6 * * *"

    def test_sub_hour_divisor_is_minute_interval(self):
        assert minutes_to_cron(30) == "*/30 * * * *"

    def test_non_divisor_is_minute_interval(self):
        assert minutes_to_cron(45) == "*/45 * * * *"


class TestCronValidation:
    def test_accepts_valid(self):
        assert is_valid_cron("0 * * * *") is True

    def test_rejects_garbage(self):
        assert is_valid_cron("not a cron") is False


class TestParseCsv:
    def test_splits_and_trims(self):
        assert parse_csv("Movies, TV Shows") == ["Movies", "TV Shows"]

    def test_drops_empty_segments(self):
        assert parse_csv("a,,b, ,c") == ["a", "b", "c"]

    def test_empty_returns_empty_list(self):
        assert parse_csv("") == []
        assert parse_csv("   ") == []


def _base_env(**overrides):
    env = {
        "PLEX_URL": "http://plex:32400",
        "PLEX_TOKEN": "token",
        "RADARR_URL": "http://radarr:7878",
        "RADARR_API_KEY": "rk",
        "SONARR_URL": "http://sonarr:8989",
        "SONARR_API_KEY": "sk",
        "SEERR_URL": "http://seerr:5055",
        "SEERR_API_KEY": "ok",
        "TAG_LABEL_MAP": "kids:kids-allowed,family:shared",
    }
    env.update(overrides)
    return env


class TestSettings:
    def test_loads_core_fields_from_env(self, monkeypatch):
        for k, v in _base_env().items():
            monkeypatch.setenv(k, v)
        s = Settings()
        assert s.plex_url == "http://plex:32400"
        assert s.seerr_url == "http://seerr:5055"
        assert s.label_map == {"kids": "kids-allowed", "family": "shared"}
        assert s.managed_labels == {"kids-allowed", "shared"}

    def test_legacy_overseerr_env_still_accepted(self, monkeypatch):
        env = _base_env()
        del env["SEERR_URL"]
        del env["SEERR_API_KEY"]
        env["OVERSEERR_URL"] = "http://overseerr:5055"
        env["OVERSEERR_API_KEY"] = "legacy"
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        s = Settings()
        assert s.seerr_url == "http://overseerr:5055"
        assert s.seerr_api_key == "legacy"

    def test_sections_parsed_as_list(self, monkeypatch):
        for k, v in _base_env(PLEX_SECTIONS="Movies,TV Shows").items():
            monkeypatch.setenv(k, v)
        assert Settings().sections == ["Movies", "TV Shows"]

    def test_defaults(self, monkeypatch):
        for k, v in _base_env().items():
            monkeypatch.setenv(k, v)
        s = Settings()
        assert s.label_removal == "reconcile"
        assert s.dry_run is False
        assert s.sweep_cron == "0 * * * *"
        assert s.watched_percent == 85
        assert s.feature_reactive is True
        assert s.reactive_interval_seconds == 60

    def test_notify_test_on_start_removed(self, monkeypatch):
        for k, v in _base_env().items():
            monkeypatch.setenv(k, v)
        assert not hasattr(Settings(), "notify_test_on_start")

    def test_notify_requires_tautulli(self, monkeypatch):
        env = _base_env(FEATURE_NOTIFY="true", APPRISE_URLS="json://x")
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        s = Settings()
        with pytest.raises(ValueError, match="TAUTULLI"):
            s.validate_runtime()

    def test_notify_requires_apprise_urls(self, monkeypatch):
        env = _base_env(
            FEATURE_NOTIFY="true",
            TAUTULLI_URL="http://tautulli:8181",
            TAUTULLI_API_KEY="tk",
        )
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        s = Settings()
        with pytest.raises(ValueError, match="APPRISE"):
            s.validate_runtime()

    def test_labeling_requires_tag_label_map(self, monkeypatch):
        env = _base_env(TAG_LABEL_MAP="")
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        s = Settings()
        with pytest.raises(ValueError, match="TAG_LABEL_MAP"):
            s.validate_runtime()

    def test_valid_full_config_passes_validation(self, monkeypatch):
        env = _base_env(
            FEATURE_NOTIFY="true",
            TAUTULLI_URL="http://tautulli:8181",
            TAUTULLI_API_KEY="tk",
            APPRISE_URLS="json://localhost",
        )
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        s = Settings()
        s.validate_runtime()  # should not raise
        assert s.apprise_url_list == ["json://localhost"]
        assert s.notify_events == ["watched", "stale"]


class TestCronMigration:
    def test_legacy_minutes_translate_to_cron(self, monkeypatch):
        for k, v in _base_env(SWEEP_INTERVAL_MINUTES="30").items():
            monkeypatch.setenv(k, v)
        assert Settings().sweep_cron == "*/30 * * * *"

    def test_cron_wins_when_both_set(self, monkeypatch):
        env = _base_env(SWEEP_INTERVAL_MINUTES="30", SWEEP_CRON="0 2 * * *")
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        assert Settings().sweep_cron == "0 2 * * *"

    def test_cron_defaults(self, monkeypatch):
        for k, v in _base_env().items():
            monkeypatch.setenv(k, v)
        s = Settings()
        assert s.sweep_cron == "0 * * * *"
        assert s.watch_scan_cron == "0 3 * * *"

    def test_invalid_cron_flagged_by_runtime_errors(self, monkeypatch):
        for k, v in _base_env(SWEEP_CRON="bogus").items():
            monkeypatch.setenv(k, v)
        assert any("cron" in e.lower() for e in Settings().runtime_errors())
