"""Declarative schema describing every UI-editable setting.

Drives the schema-driven form: each field's ``key`` matches an ``app.config.Settings``
field, so saved values pass straight into ``Settings(**values)``. Bootstrap settings
(`pal_secret_key`, `config_path`, `state_db_path`, `feature_ui`) are intentionally NOT
here — they are not editable from the UI.

Field types: text, secret, int, bool, enum, multi (checkbox set), csv (list),
libraries (checkbox set of Plex libraries, options fetched live from the server),
lines (newline-separated list, revealed in the UI), keyvalue (map).
``depends_on`` = ``{"key": <other>, "value": <required value>}``.

``tier`` buckets a group into the Settings page sections: ``core`` (always shown),
``notify`` (the Notifications section, gated by ``feature_notify``), ``advanced``
(behind the "Show advanced" toggle).

Encryption vs. masking are separate concerns: ``secret`` fields are both encrypted
at rest *and* masked from the browser (never returned). A field may instead set
``"encrypt": True`` to be encrypted at rest but still revealed in the UI — used for
Apprise URLs, which the user needs to see and edit but which contain tokens.
"""

from __future__ import annotations

from typing import Any

CONFIG_SCHEMA: list[dict[str, Any]] = [
    {
        "name": "Plex",
        "tier": "core",
        "fields": [
            {"key": "plex_url", "label": "Plex URL", "type": "text",
             "placeholder": "http://plex:32400"},
            {"key": "plex_token", "label": "Plex Token", "type": "secret"},
            {"key": "plex_sections", "label": "Libraries", "type": "libraries",
             "help": "Which Plex libraries to sync and scan. None checked = all."},
            {"key": "plex_device_name", "label": "Device Name", "type": "text",
             "help": "Shown in Plex → Settings → Devices."},
            {"key": "plex_client_id", "label": "Client ID", "type": "text",
             "help": "Stable id so Plex doesn't add a new device each restart."},
        ],
    },
    {
        "name": "Radarr",
        "tier": "core",
        "fields": [
            {"key": "radarr_url", "label": "Radarr URL", "type": "text",
             "placeholder": "http://radarr:7878"},
            {"key": "radarr_api_key", "label": "Radarr API Key", "type": "secret"},
        ],
    },
    {
        "name": "Sonarr",
        "tier": "core",
        "fields": [
            {"key": "sonarr_url", "label": "Sonarr URL", "type": "text",
             "placeholder": "http://sonarr:8989"},
            {"key": "sonarr_api_key", "label": "Sonarr API Key", "type": "secret"},
        ],
    },
    {
        "name": "Labels",
        "tier": "core",
        "fields": [
            {"key": "tag_label_map", "label": "Tag → Label map", "type": "keyvalue",
             "help": "Each Sonarr/Radarr tag maps to a Plex label."},
            {"key": "label_removal", "label": "Removal policy", "type": "enum",
             "options": ["reconcile", "add-only"]},
        ],
    },
    {
        "name": "Scheduling",
        "tier": "core",
        "fields": [
            {"key": "feature_webhook", "label": "Webhook receiver", "type": "bool"},
            {"key": "feature_reactive", "label": "Reactive poll", "type": "bool",
             "help": "Fast poll: reacts to arr tag changes + Plex recently-added "
                     "(no Plex webhook needed)."},
            {"key": "reactive_interval_seconds", "label": "Reactive interval (sec)",
             "type": "int", "depends_on": {"key": "feature_reactive", "value": True}},
            {"key": "feature_sweep", "label": "Periodic sweep", "type": "bool"},
            {"key": "sweep_cron", "label": "Sweep schedule", "type": "cron",
             "placeholder": "0 * * * *", "help": "When the reconcile sweep runs."},
        ],
    },
    # --- Notifications section (gated by feature_notify) ---------------------
    # feature_notify is the section's enable toggle: the Settings UI renders it as
    # the Notifications header checkbox, not as a field inside a group.
    {
        "name": "Notifications",
        "tier": "notify",
        "fields": [
            {"key": "apprise_urls", "label": "Apprise URLs", "type": "lines",
             "encrypt": True,
             "help": "One Apprise URL per line — e.g. a Discord webhook or a Telegram "
                     "bot. These are how watched/stale alerts reach you. Stored "
                     "encrypted on disk."},
            {"key": "notify_on", "label": "Notify on", "type": "multi",
             "options": ["labeled", "watched", "stale"]},
            {"key": "watch_scan_cron", "label": "Watch scan schedule", "type": "cron",
             "placeholder": "0 3 * * *", "help": "When the watch-history scan runs."},
            {"key": "watched_percent", "label": "Watched %", "type": "int"},
            {"key": "stale_after_days", "label": "Stale after (days)", "type": "int"},
            {"key": "unwatched_after_days", "label": "Unwatched window (days)", "type": "int"},
        ],
    },
    {
        "name": "Tautulli",
        "tier": "notify",
        "fields": [
            {"key": "tautulli_url", "label": "Tautulli URL", "type": "text",
             "placeholder": "http://tautulli:8181",
             "help": "Tautulli tracks Plex watch history — Whitelistarr reads it to "
                     "decide when something is watched or has gone stale."},
            {"key": "tautulli_api_key", "label": "Tautulli API Key", "type": "secret"},
        ],
    },
    {
        "name": "Seerr",
        "tier": "notify",
        "fields": [
            {"key": "seerr_url", "label": "Seerr URL", "type": "text",
             "placeholder": "http://seerr:5055",
             "help": "Seerr (Overseerr/Jellyseerr) maps each title to the user who "
                     "requested it, so stale/watched alerts can name the requester."},
            {"key": "seerr_api_key", "label": "Seerr API Key", "type": "secret"},
        ],
    },
    {
        # feature_notify lives here so it's a known, saveable field; the UI surfaces
        # it as the Notifications section toggle rather than a standalone group.
        "name": "_notify_toggle",
        "tier": "hidden",
        "fields": [
            {"key": "feature_notify", "label": "Enable notifications", "type": "bool"},
        ],
    },
    {
        "name": "Server",
        "tier": "advanced",
        "fields": [
            {"key": "webhook_host", "label": "Bind host", "type": "text"},
            {"key": "webhook_port", "label": "Bind port", "type": "int"},
            {"key": "webhook_path", "label": "Seerr webhook path", "type": "text"},
            {"key": "plex_webhook_path", "label": "Plex webhook path", "type": "text"},
            {"key": "webhook_secret", "label": "Webhook secret (?token=)", "type": "secret"},
        ],
    },
    {
        "name": "Ops",
        "tier": "advanced",
        "fields": [
            {"key": "dry_run", "label": "Dry run", "type": "bool",
             "help": "Log intended changes without applying."},
            {"key": "log_level", "label": "Log level", "type": "enum",
             "options": ["debug", "info", "warning", "error"]},
        ],
    },
]


def fields_by_key() -> dict[str, dict[str, Any]]:
    return {f["key"]: f for group in CONFIG_SCHEMA for f in group["fields"]}


def field_keys() -> list[str]:
    return [f["key"] for group in CONFIG_SCHEMA for f in group["fields"]]


def secret_keys() -> list[str]:
    """Fields masked from the browser (never returned). Always encrypted too."""
    return [f["key"] for f in fields_by_key().values() if f["type"] == "secret"]


def encrypted_keys() -> list[str]:
    """Fields encrypted at rest: every secret, plus any with ``encrypt: True``."""
    return [
        f["key"]
        for f in fields_by_key().values()
        if f["type"] == "secret" or f.get("encrypt")
    ]
