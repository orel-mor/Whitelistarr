"""Derive onboarding progress from persisted config.

The step indices mirror the UI setup wizard (``app/static`` ``wizard``). The
service builds nothing and starts no routines until onboarding is finished (the
user presses Finish, persisting ``Settings.onboarding_complete``). Until then the
UI reroutes to the wizard; ``next_incomplete_step`` tells it which step to resume.

Completion of each step reuses the same required-field logic as
``Settings.runtime_errors``, so "finishable" and "no runtime errors" agree. When
everything required is present we return ``DONE`` so a fully-configured user lands
on the final Finish screen rather than being bounced through completed steps.
"""

from __future__ import annotations

from typing import Any

WELCOME, PLEX, ARR, TAGS, NOTIFY, DONE = 0, 1, 2, 3, 4, 5


def next_incomplete_step(settings: Any) -> int:
    """Return the first wizard step whose required config is missing (else DONE)."""
    if not (settings.plex_url and settings.plex_token):
        return PLEX

    labeling = settings.feature_webhook or settings.feature_sweep
    if labeling:
        arr_ok = (
            settings.radarr_url and settings.radarr_api_key
            and settings.sonarr_url and settings.sonarr_api_key
        )
        if not arr_ok:
            return ARR
        if not settings.label_map:
            return TAGS

    if settings.feature_notify:
        notify_ok = (
            settings.tautulli_url and settings.tautulli_api_key
            and settings.apprise_url_list and settings.seerr_url and settings.seerr_api_key
        )
        if not notify_ok:
            return NOTIFY

    return DONE
