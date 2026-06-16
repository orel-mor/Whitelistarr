from app.config import Settings
from app.config_schema import (
    CONFIG_SCHEMA,
    field_keys,
    fields_by_key,
    secret_keys,
)

SETTINGS_FIELDS = set(Settings.model_fields)


def test_every_schema_key_is_a_real_settings_field():
    for key in field_keys():
        assert key in SETTINGS_FIELDS, f"{key} not a Settings field"


def test_secret_keys_subset_and_expected():
    expected = {
        "plex_token",
        "radarr_api_key",
        "sonarr_api_key",
        "seerr_api_key",
        "tautulli_api_key",
        "webhook_secret",
        "apprise_urls",
    }
    assert set(secret_keys()) == expected
    assert set(secret_keys()).issubset(set(field_keys()))


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
