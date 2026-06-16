"""Apprise-backed notifier for watch-milestone and stale notifications."""

from __future__ import annotations

import logging

import apprise

log = logging.getLogger(__name__)


def ensure_discord_markdown(url: str) -> str:
    """Tune Discord URLs for clean embeds.

    - ``format=markdown`` makes Apprise render an embed (it only does so in
      markdown output mode; ``body_format`` at notify time doesn't control this).
    - ``fields=no`` keeps our markdown in the embed description instead of letting
      Apprise force every section into a code-block field.

    Other services are left untouched.
    """
    if not url.startswith("discord://"):
        return url
    extra = []
    if "format=" not in url:
        extra.append("format=markdown")
    if "fields=" not in url:
        extra.append("fields=no")
    if not extra:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}{'&'.join(extra)}"


class Notifier:
    def __init__(
        self,
        urls: list[str],
        *,
        dry_run: bool = False,
        apprise_obj: object | None = None,
    ) -> None:
        self._dry_run = dry_run
        if apprise_obj is not None:
            self._apprise = apprise_obj
        else:
            # Empty app_id => no "author" line in Discord embeds (the title now
            # carries the event name instead).
            asset = apprise.AppriseAsset(app_id="", app_desc="Whitelistarr")
            self._apprise = apprise.Apprise(asset=asset)
            for url in urls:
                if not self._apprise.add(ensure_discord_markdown(url)):
                    log.warning("Apprise rejected URL: %s", url)

    def server_count(self) -> int:
        return len(self._apprise)

    def notify(
        self,
        title: str,
        body: str,
        body_format: str | None = None,
        notify_type: str | None = None,
    ) -> bool:
        if self._dry_run:
            log.info("[DRY_RUN] notify title=%r body=%r", title, body)
            return True
        kwargs: dict[str, str] = {}
        if body_format:
            kwargs["body_format"] = body_format
        if notify_type:
            kwargs["notify_type"] = notify_type
        return bool(self._apprise.notify(title=title, body=body, **kwargs))
