from app.config import Settings
from app.config_schema import (
    CONFIG_SCHEMA,
    encrypted_keys,
    field_keys,
    fields_by_key,
    secret_keys,
)

SETTINGS_FIELDS = set(Settings.model_fields)


def test_every_schema_key_is_a_real_settings_field():
    for key in field_keys():
        assert key in SETTINGS_FIELDS, f"{key} not a Settings field"


def test_secret_keys_subset_and_expected():
    # Masked-from-browser secrets. Apprise URLs are deliberately NOT here — the
    # user must see/edit them — but they are still encrypted at rest.
    expected = {
        "plex_token",
        "radarr_api_key",
        "sonarr_api_key",
        "seerr_api_key",
        "tautulli_api_key",
        "webhook_secret",
    }
    assert set(secret_keys()) == expected
    assert set(secret_keys()).issubset(set(field_keys()))
    assert "apprise_urls" not in secret_keys()


def test_apprise_encrypted_but_not_masked():
    # Revealed in the UI (not a secret) yet encrypted on disk.
    assert "apprise_urls" not in secret_keys()
    assert "apprise_urls" in encrypted_keys()
    assert set(secret_keys()).issubset(set(encrypted_keys()))


def test_bootstrap_fields_are_not_editable():
    # The encryption key and infra paths must never be in the editable schema.
    for forbidden in ("pal_secret_key", "config_path", "state_db_path", "feature_ui"):
        assert forbidden not in field_keys()


def test_depends_on_references_known_keys():
    keys = set(field_keys())
    for field in fields_by_key().values():
        dep = field.get("depends_on")
        if dep:
            assert dep["key"] in keys, f"{field['key']} depends on unknown {dep['key']}"


def test_groups_have_names_and_fields():
    assert CONFIG_SCHEMA
    for group in CONFIG_SCHEMA:
        assert group["name"]
        assert group["fields"]


def test_enum_fields_declare_options():
    for field in fields_by_key().values():
        if field["type"] == "enum":
            assert field.get("options"), f"{field['key']} enum needs options"


def test_every_group_has_a_tier():
    for group in CONFIG_SCHEMA:
        assert group.get("tier") in ("core", "notify", "advanced", "hidden"), group["name"]


def test_cron_fields_use_cron_type():
    by_key = fields_by_key()
    assert by_key["sweep_cron"]["type"] == "cron"
    assert by_key["watch_scan_cron"]["type"] == "cron"


def test_core_groups_present():
    tiers = {g["name"]: g["tier"] for g in CONFIG_SCHEMA}
    assert tiers["Plex"] == "core"
    assert tiers["Server"] == "advanced"
