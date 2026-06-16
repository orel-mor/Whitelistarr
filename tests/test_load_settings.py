from cryptography.fernet import Fernet

from app.config import load_settings

KEY = Fernet.generate_key().decode()


def _env(monkeypatch, tmp_path, **over):
    env = {
        "FEATURE_UI": "true",
        "PAL_SECRET_KEY": KEY,
        "CONFIG_PATH": str(tmp_path / "config.json"),
        "PLEX_URL": "http://plex:32400",
        "PLEX_TOKEN": "env-token",
        "TAG_LABEL_MAP": "kids:kids-allowed",
    }
    env.update(over)
    for k, v in env.items():
        monkeypatch.setenv(k, v)


def test_first_run_seeds_store_from_env(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    from app.configstore import ConfigStore

    settings = load_settings()
    assert settings.plex_url == "http://plex:32400"
    store = ConfigStore(str(tmp_path / "config.json"), KEY)
    assert store.exists()
    seeded = store.load()
    assert seeded["plex_url"] == "http://plex:32400"
    assert seeded["plex_token"] == "env-token"  # decrypts back to plaintext


def test_store_wins_over_env_on_second_run(monkeypatch, tmp_path):
    from app.configstore import ConfigStore

    ConfigStore(str(tmp_path / "config.json"), KEY).save({"plex_url": "http://stored:32400"})
    _env(monkeypatch, tmp_path)  # env says http://plex:32400
    settings = load_settings()
    assert settings.plex_url == "http://stored:32400"  # store wins


def test_ui_off_uses_env_only_no_store(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path, FEATURE_UI="false")
    settings = load_settings()
    assert settings.plex_url == "http://plex:32400"
    assert not (tmp_path / "config.json").exists()  # no store written


def test_runtime_errors_flags_missing_core(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path, PLEX_URL="", PLEX_TOKEN="")
    settings = load_settings()
    errs = settings.runtime_errors()
    assert any("PLEX" in e for e in errs)
