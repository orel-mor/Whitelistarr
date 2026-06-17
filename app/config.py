"""Declarative configuration loaded entirely from environment variables.

All settings come from the environment (12-factor). Complex values (CSV lists and
the tag->label map) are stored as raw strings and exposed through parsed
properties so we avoid pydantic-settings' JSON pre-parsing of list/dict fields.
"""

from __future__ import annotations

import uuid
from functools import cached_property
from typing import Literal

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def parse_csv(raw: str) -> list[str]:
    """Split a comma-separated string into a trimmed list, dropping empties."""
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def parse_tag_label_map(raw: str) -> dict[str, str]:
    """Parse ``"tag:label,tag:label"`` into ``{tag: label}``.

    Splits each entry on the first colon only (labels may contain colons).
    Raises ``ValueError`` on an entry without a colon or with an empty side.
    """
    result: dict[str, str] = {}
    if not raw or not raw.strip():
        return result
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if ":" not in entry:
            raise ValueError(f"Invalid TAG_LABEL_MAP entry (missing ':'): {entry!r}")
        tag, label = entry.split(":", 1)
        tag, label = tag.strip(), label.strip()
        if not tag or not label:
            raise ValueError(f"Invalid TAG_LABEL_MAP entry (empty tag or label): {entry!r}")
        result[tag] = label
    return result


def minutes_to_cron(minutes: int) -> str:
    """Translate a legacy interval-in-minutes into an equivalent cron expression."""
    if minutes >= 60 and minutes % 60 == 0:
        hours = minutes // 60
        return "0 * * * *" if hours == 1 else f"0 */{hours} * * *"
    return f"*/{minutes} * * * *"


def is_valid_cron(expr: str) -> bool:
    """True if ``expr`` parses as a 5-field crontab string."""
    from apscheduler.triggers.cron import CronTrigger

    try:
        CronTrigger.from_crontab(expr)
        return True
    except (ValueError, TypeError):
        return False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Connections ---
    # All optional with "" defaults so the app can boot UI-only before anything is
    # configured. Presence is enforced by runtime_errors() per enabled feature.
    plex_url: str = ""
    plex_token: str = ""
    plex_sections: str = ""  # CSV; empty = all sections
    # How this app identifies itself to Plex (Settings > Devices). A stable
    # client id keeps Plex from registering a new device on each restart.
    plex_device_name: str = "Whitelistarr"
    plex_client_id: str = ""  # generated + persisted on first run (UI mode)

    radarr_url: str = ""
    radarr_api_key: str = ""
    sonarr_url: str = ""
    sonarr_api_key: str = ""

    # Seerr (formerly Overseerr). Old OVERSEERR_* env vars still accepted.
    seerr_url: str = Field(default="", validation_alias=AliasChoices("seerr_url", "overseerr_url"))
    seerr_api_key: str = Field(
        default="", validation_alias=AliasChoices("seerr_api_key", "overseerr_api_key")
    )

    tautulli_url: str = ""
    tautulli_api_key: str = ""

    # --- Tag -> label mapping ---
    tag_label_map: str = ""  # "tag:label,tag:label"
    label_removal: Literal["reconcile", "add-only"] = "reconcile"

    # --- Feature toggles ---
    feature_webhook: bool = True
    feature_sweep: bool = True
    feature_notify: bool = False
    # Cron expressions (5-field). Legacy *_interval_minutes below are migrated in.
    sweep_cron: str = "0 * * * *"  # hourly
    watch_scan_cron: str = "0 3 * * *"  # daily at 03:00
    # Legacy interval inputs (undocumented; translated to cron on load if cron unset).
    sweep_interval_minutes: int | None = None
    watch_scan_interval_minutes: int | None = None

    # --- Notifications ---
    apprise_urls: str = ""  # CSV of apprise URLs
    notify_on: str = "watched,stale"  # CSV of event types
    watched_percent: int = 85
    stale_after_days: int = 180
    unwatched_after_days: int = 90

    # --- Server / ops ---
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8000
    webhook_path: str = "/webhook/seerr"
    plex_webhook_path: str = "/webhook/plex"
    webhook_secret: str = ""
    dry_run: bool = False
    reverse: bool = False  # one-shot: remove all managed labels, then exit
    log_level: str = "info"
    state_db_path: str = "/data/state.db"

    # --- Web UI ---
    feature_ui: bool = True
    pal_secret_key: str = ""  # Fernet key; required to enable the UI
    config_path: str = "/data/config.json"

    @model_validator(mode="after")
    def _migrate_legacy_intervals(self) -> Settings:
        if "sweep_cron" not in self.model_fields_set and self.sweep_interval_minutes is not None:
            self.sweep_cron = minutes_to_cron(self.sweep_interval_minutes)
        if (
            "watch_scan_cron" not in self.model_fields_set
            and self.watch_scan_interval_minutes is not None
        ):
            self.watch_scan_cron = minutes_to_cron(self.watch_scan_interval_minutes)
        return self

    # --- Parsed views ---
    @cached_property
    def sections(self) -> list[str]:
        return parse_csv(self.plex_sections)

    @cached_property
    def label_map(self) -> dict[str, str]:
        return parse_tag_label_map(self.tag_label_map)

    @cached_property
    def managed_labels(self) -> set[str]:
        """Plex labels this app is allowed to add/remove. Never touch others."""
        return set(self.label_map.values())

    @cached_property
    def apprise_url_list(self) -> list[str]:
        return parse_csv(self.apprise_urls)

    @cached_property
    def notify_events(self) -> list[str]:
        return parse_csv(self.notify_on)

    def runtime_errors(self) -> list[str]:
        """Return a list of configuration problems for the enabled features.

        Empty list = good to run. Used both for soft checks (UI mode, where we still
        start so the user can fix config) and for ``validate_runtime`` (env-only mode).
        """
        errors: list[str] = []
        if not self.plex_url or not self.plex_token:
            errors.append("PLEX_URL and PLEX_TOKEN are required.")
        if self.feature_webhook or self.feature_sweep:
            if not self.radarr_url or not self.radarr_api_key:
                errors.append("RADARR_URL and RADARR_API_KEY are required for labeling.")
            if not self.sonarr_url or not self.sonarr_api_key:
                errors.append("SONARR_URL and SONARR_API_KEY are required for labeling.")
            if not self.label_map:
                errors.append("TAG_LABEL_MAP is required when labeling is enabled.")
        if self.feature_notify:
            if not self.tautulli_url or not self.tautulli_api_key:
                errors.append("TAUTULLI_URL and TAUTULLI_API_KEY are required for notifications.")
            if not self.apprise_url_list:
                errors.append("APPRISE_URLS is required for notifications.")
            if not self.seerr_url or not self.seerr_api_key:
                errors.append("SEERR_URL and SEERR_API_KEY are required for notifications.")
        if self.feature_sweep and not is_valid_cron(self.sweep_cron):
            errors.append(f"SWEEP_CRON is not a valid cron expression: {self.sweep_cron!r}")
        if self.feature_notify and not is_valid_cron(self.watch_scan_cron):
            errors.append(
                f"WATCH_SCAN_CRON is not a valid cron expression: {self.watch_scan_cron!r}"
            )
        return errors

    def validate_runtime(self) -> None:
        """Raise ``ValueError`` if the current config can't run (env-only mode)."""
        errors = self.runtime_errors()
        if errors:
            raise ValueError(" ".join(errors))


def _dump_for_store(settings: Settings) -> dict:
    """Snapshot the editable (schema) fields of ``settings`` for the config store."""
    from app.config_schema import field_keys

    return {key: getattr(settings, key) for key in field_keys()}


def load_settings(store: object | None = None) -> Settings:
    """Build Settings honoring the UI config store.

    - UI off or no key: plain env-based Settings (declarative mode).
    - UI on, store exists: store wins, env fills gaps.
    - UI on, no store yet: seed the store from env-derived values, then return them.
    """
    base = Settings()
    if not base.feature_ui or not base.pal_secret_key:
        return base

    from app.configstore import ConfigStore

    if store is None:
        try:
            store = ConfigStore(base.config_path, base.pal_secret_key)
        except ValueError:
            return base

    if store.exists():
        settings = Settings(**store.load())
    else:
        store.save(_dump_for_store(base))
        settings = base

    if not settings.plex_client_id:
        generated = uuid.uuid4().hex
        store.save({"plex_client_id": generated})
        settings = Settings(**store.load())
    return settings


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return a cached Settings instance loaded from the environment."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
