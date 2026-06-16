from datetime import datetime

from app.clients.seerr import RequestInfo
from app.core.watch_monitor import (
    WatchMonitor,
    is_stale,
    last_watched_at,
    max_watched_percent,
)
from app.state import StateStore

NOW = datetime(2026, 6, 14, 12, 0, 0)


def _epoch(dt: datetime) -> int:
    return int(dt.timestamp())


class TestPureHelpers:
    def test_max_watched_percent(self):
        rows = [{"percent_complete": 40}, {"percent_complete": 92}, {"percent_complete": 10}]
        assert max_watched_percent(rows) == 92

    def test_max_watched_percent_empty(self):
        assert max_watched_percent([]) == 0

    def test_last_watched_at_picks_latest(self):
        old = _epoch(datetime(2026, 1, 1))
        recent = _epoch(datetime(2026, 6, 1))
        rows = [{"date": old}, {"date": recent}]
        assert last_watched_at(rows) == datetime.fromtimestamp(recent)

    def test_last_watched_at_none_when_empty(self):
        assert last_watched_at([]) is None

    def test_is_stale_true_when_old_and_never_watched(self):
        added = datetime(2025, 1, 1)  # >180 days before NOW
        assert is_stale(added, NOW, 180, None, 90) is True

    def test_is_stale_false_when_recently_added(self):
        added = datetime(2026, 6, 1)  # <180 days
        assert is_stale(added, NOW, 180, None, 90) is False

    def test_is_stale_false_when_watched_recently(self):
        added = datetime(2025, 1, 1)
        last = datetime(2026, 6, 1)  # within 90 days of NOW
        assert is_stale(added, NOW, 180, last, 90) is False

    def test_is_stale_true_when_watched_long_ago(self):
        added = datetime(2025, 1, 1)
        last = datetime(2025, 2, 1)  # >90 days before NOW
        assert is_stale(added, NOW, 180, last, 90) is True


class FakePlexItem:
    def __init__(self, title, rating_key, added_at):
        self.title = title
        self.rating_key = rating_key
        self.added_at = added_at
        self.media_type = "movie"
        self.tmdb_id = 603
        self.tvdb_id = None


class FakePlex:
    def __init__(self, item):
        self._item = item

    def find_item(self, media_type, tmdb_id=None, tvdb_id=None):
        return self._item


class FakeTautulli:
    def __init__(self, rows):
        self._rows = rows

    def get_history(self, rating_key=None, user=None, length=100):
        return self._rows


class FakeNotifier:
    def __init__(self):
        self.sent = []

    def notify(self, title, body):
        self.sent.append((title, body))
        return True


def _request():
    return RequestInfo(
        media_type="movie", tmdb_id=603, tvdb_id=None,
        requester="sister", requester_name="Sister", rating_key=None,
    )


def _monitor(plex, tautulli, notifier, state, events=("watched", "stale")):
    return WatchMonitor(
        overseerr=type("O", (), {"iter_requests": lambda self: [_request()]})(),
        tautulli=tautulli,
        plex=plex,
        notifier=notifier,
        state=state,
        events=list(events),
        watched_percent=85,
        stale_after_days=180,
        unwatched_after_days=90,
        now_fn=lambda: NOW,
    )


def test_notifies_when_requester_watched():
    item = FakePlexItem("Dune", "111", added_at=datetime(2026, 6, 1))
    plex = FakePlex(item)
    tautulli = FakeTautulli([{"percent_complete": 95, "date": _epoch(datetime(2026, 6, 10))}])
    notifier = FakeNotifier()
    state = StateStore(":memory:")
    _monitor(plex, tautulli, notifier, state).scan()
    assert len(notifier.sent) == 1
    assert "Sister" in notifier.sent[0][1]
    assert "Dune" in notifier.sent[0][1]


def test_watched_notification_deduped():
    item = FakePlexItem("Dune", "111", added_at=datetime(2026, 6, 1))
    plex = FakePlex(item)
    tautulli = FakeTautulli([{"percent_complete": 95, "date": _epoch(datetime(2026, 6, 10))}])
    notifier = FakeNotifier()
    state = StateStore(":memory:")
    mon = _monitor(plex, tautulli, notifier, state)
    mon.scan()
    mon.scan()
    assert len(notifier.sent) == 1


def test_notifies_stale_when_old_and_unwatched():
    item = FakePlexItem("Old Movie", "222", added_at=datetime(2025, 1, 1))
    plex = FakePlex(item)
    tautulli = FakeTautulli([])  # never watched
    notifier = FakeNotifier()
    state = StateStore(":memory:")
    _monitor(plex, tautulli, notifier, state, events=("stale",)).scan()
    assert len(notifier.sent) == 1
    assert "Old Movie" in notifier.sent[0][1]


def test_no_notification_when_not_watched_and_not_stale():
    item = FakePlexItem("Fresh", "333", added_at=datetime(2026, 6, 1))
    plex = FakePlex(item)
    tautulli = FakeTautulli([{"percent_complete": 10}])
    notifier = FakeNotifier()
    state = StateStore(":memory:")
    _monitor(plex, tautulli, notifier, state).scan()
    assert notifier.sent == []
