import json

import pytest
from cryptography.fernet import Fernet

from app.configstore import ConfigStore

KEY = Fernet.generate_key().decode()


def _store(tmp_path, key=KEY):
    return ConfigStore(str(tmp_path / "config.json"), key)


def test_requires_a_key(tmp_path):
    with pytest.raises(ValueError):
        ConfigStore(str(tmp_path / "c.json"), "")


def test_exists_false_then_true(tmp_path):
    store = _store(tmp_path)
    assert store.exists() is False
    store.save({"plex_url": "x"})
    assert store.exists() is True


def test_roundtrip_plain_and_secret(tmp_path):
    store = _store(tmp_path)
    store.save({"plex_url": "http://plex:32400", "plex_token": "s3cr3t"})
    loaded = store.load()
    assert loaded["plex_url"] == "http://plex:32400"
    assert loaded["plex_token"] == "s3cr3t"


def test_secret_is_encrypted_on_disk(tmp_path):
    path = tmp_path / "config.json"
    ConfigStore(str(path), KEY).save({"plex_token": "s3cr3t"})
    raw = json.loads(path.read_text())
    assert raw["plex_token"] != "s3cr3t"  # ciphertext on disk
    # and a different key cannot read it back
    other = ConfigStore(str(path), Fernet.generate_key().decode())
    assert other.load().get("plex_token", "") == ""  # decrypt fails -> empty


def test_empty_secret_stays_empty(tmp_path):
    store = _store(tmp_path)
    store.save({"plex_token": ""})
    assert store.load()["plex_token"] == ""


def test_atomic_write_leaves_no_tmp(tmp_path):
    store = _store(tmp_path)
    store.save({"plex_url": "x"})
    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == []


def test_save_merges_over_existing(tmp_path):
    store = _store(tmp_path)
    store.save({"plex_url": "a", "plex_token": "t1"})
    store.save({"plex_url": "b"})  # partial update keeps token
    loaded = store.load()
    assert loaded["plex_url"] == "b"
    assert loaded["plex_token"] == "t1"
