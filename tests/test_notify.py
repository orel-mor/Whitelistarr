from app.clients.notify import Notifier, ensure_discord_markdown


class TestEnsureDiscordMarkdown:
    def test_appends_format_and_fields_to_plain_discord_url(self):
        assert (
            ensure_discord_markdown("discord://id/token")
            == "discord://id/token?format=markdown&fields=no"
        )

    def test_uses_ampersand_when_query_exists(self):
        assert (
            ensure_discord_markdown("discord://id/token?avatar=no")
            == "discord://id/token?avatar=no&format=markdown&fields=no"
        )

    def test_leaves_existing_params_untouched(self):
        assert (
            ensure_discord_markdown("discord://id/token?format=text&fields=yes")
            == "discord://id/token?format=text&fields=yes"
        )

    def test_ignores_non_discord_urls(self):
        assert ensure_discord_markdown("tgram://tok/chat") == "tgram://tok/chat"


def test_registers_urls():
    n = Notifier(["json://localhost", "json://example.com"])
    assert n.server_count() == 2


def test_no_sender_author_in_embeds():
    # Empty app_id => Discord embeds carry no author line.
    n = Notifier(["json://localhost"])
    assert n._apprise.asset.app_id == ""


def test_dry_run_does_not_send_and_returns_true():
    sent = []

    class FakeApprise:
        def notify(self, title, body):  # pragma: no cover - must not be called
            sent.append((title, body))
            return True

    n = Notifier([], dry_run=True, apprise_obj=FakeApprise())
    assert n.notify("Title", "Body") is True
    assert sent == []


def test_notify_delegates_to_apprise():
    calls = []

    class FakeApprise:
        def notify(self, title, body):
            calls.append((title, body))
            return True

    n = Notifier([], apprise_obj=FakeApprise())
    assert n.notify("Watched", "Family finished Dune") is True
    assert calls == [("Watched", "Family finished Dune")]
