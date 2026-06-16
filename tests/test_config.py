import pytest

from app.config import Settings, parse_csv, parse_tag_label_map


class TestParseTagLabelMap:
    def test_parses_single_pair(self):
        assert parse_tag_label_map("niece-ok:kids-allowed") == {"niece-ok": "kids-allowed"}

    def test_parses_multiple_pairs(self):
        result = parse_tag_label_map("niece-ok:kids-allowed,sister:shared")
        assert result == {"niece-ok": "kids-allowed", "sister": "shared"}

    def test_trims_whitespace_around_entries_and_pairs(self):
        result = parse_tag_label_map(" niece-ok : kids-allowed ,  sister:shared ")
        assert result == {"niece-ok": "kids-allowed", "sister": "shared"}

    def test_empty_string_returns_empty_dict(self):
        assert parse_tag_label_map("") == {}
        assert parse_tag_label_map("   ") == {}

    def test_splits_on_first_colon_only(self):
        # label values are allowed to contain a colon
        assert parse_tag_label_map("tag:label:extra") == {"tag": "label:extra"}

    def test_raises_on_entry_without_colon(self):
        with pytest.raises(ValueError):
            parse_tag_label_map("niece-ok,sister:shared")

    def test_raises_on_empty_tag_or_label(self):
        with pytest.raises(ValueError):
            parse_tag_label_map(":label")
        with pytest.raises(ValueError):
            parse_tag_label_map("tag:")


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
        "TAG_LABEL_MAP": "niece-ok:kids-allowed,sister:shared",
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
        assert s.label_map == {"niece-ok": "kids-allowed", "sister": "shared"}
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
        assert s.sweep_interval_minutes == 60
        assert s.watched_percent == 85

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
