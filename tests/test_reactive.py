from datetime import datetime, timedelta

from app.core.reactive import ReactivePoller
from app.core.sync import LabelSync

LABEL_MAP = {"kids": "kids-allowed", "family": "shared"}
MANAGED = set(LABEL_MAP.values())


class FakePlexItem:
    def __init__(self, title, media_type, labels, guid_keys, rating_key=None, added_at=None):
        self.title = title
        self.media_type = media_type
        self.rating_key = rating_key
        self.added_at = added_at
        self._labels = set(labels)
        self._guid_keys = set(guid_keys)

    def guid_keys(self):
        return set(self._guid_keys)

    def labels(self):
        return set(self._labels)

    def add_labels(self, labels):
        self._labels.update(labels)

    def remove_labels(self, labels):
        for label in labels:
            self._labels.discard(label)


class FakePlex:
    def __init__(self, items=None, recent=None):
        self._items = items or []
        self._recent = recent if recent is not None else []

    def iter_items(self):
        return list(self._items)

    def find_item(self, media_type, tmdb_id=None, tvdb_id=None):
        targets = set()
        if tmdb_id is not None:
            targets.add(f"tmdb:{tmdb_id}")
        if tvdb_id is not None:
            targets.add(f"tvdb:{tvdb_id}")
        for item in self._items:
            if item.media_type == media_type and (item.guid_keys() & targets):
                return item
        return None

    def recently_added(self, since, cap=100):
        out = [
            it for it in self._recent
            if since is None or (it.added_at is not None and it.added_at > since)
        ]
        out.sort(key=lambda it: it.added_at, reverse=True)
        return out[:cap]


class FakeArr:
    def __init__(self, entries=None):
        self._entries = entries or []  # list of (guid_keys, tag_names)

    def set(self, entries):
        self._entries = entries

    def iter_all_with_tags(self):
        return list(self._entries)


def make_poller(plex, radarr=None, sonarr=None, now=None):
    radarr = radarr or FakeArr()
    sonarr = sonarr or FakeArr()
    ls = LabelSync(
        plex=plex, radarr=radarr, sonarr=sonarr,
        label_map=LABEL_MAP, managed=MANAGED, mode="reconcile",
    )
    now_fn = (lambda: now) if now is not None else None
    return ReactivePoller(plex=plex, label_sync=ls, radarr=radarr, sonarr=sonarr, now_fn=now_fn)


# --- arr tag-change diffing -------------------------------------------------

def test_first_poll_baselines_arr_and_changes_nothing():
    item = FakePlexItem("Dune", "movie", set(), {"tmdb:603"}, rating_key="1")
    radarr = FakeArr([({"tmdb:603"}, ["kids"])])
    poller = make_poller(FakePlex([item]), radarr=radarr, now=datetime(2026, 1, 1))
    summary = poller.poll()
    assert item.labels() == set()           # baseline does not label
    assert summary["tag_changes"] == 0


def test_tag_added_to_existing_item_reacts_on_next_poll():
    item = FakePlexItem("Dune", "movie", set(), {"tmdb:603"}, rating_key="1")
    radarr = FakeArr([({"tmdb:603"}, [])])  # untagged at baseline
    poller = make_poller(FakePlex([item]), radarr=radarr, now=datetime(2026, 1, 1))
    poller.poll()                            # baseline
    radarr.set([({"tmdb:603"}, ["kids"])])   # tag added in Radarr
    summary = poller.poll()
    assert item.labels() == {"kids-allowed"}
    assert summary["tag_changes"] >= 1


def test_tag_removed_reconciles_removal():
    item = FakePlexItem("Dune", "movie", {"kids-allowed"}, {"tmdb:603"}, rating_key="1")
    radarr = FakeArr([({"tmdb:603"}, ["kids"])])
    poller = make_poller(FakePlex([item]), radarr=radarr, now=datetime(2026, 1, 1))
    poller.poll()                            # baseline
    radarr.set([({"tmdb:603"}, [])])         # tag removed
    poller.poll()
    assert item.labels() == set()


def test_no_arr_change_means_no_reaction():
    item = FakePlexItem("Dune", "movie", set(), {"tmdb:603"}, rating_key="1")
    radarr = FakeArr([({"tmdb:603"}, ["kids"])])
    poller = make_poller(FakePlex([item]), radarr=radarr, now=datetime(2026, 1, 1))
    poller.poll()
    summary = poller.poll()
    assert summary["tag_changes"] == 0
    # baseline never labeled it, and nothing changed since
    assert item.labels() == set()


def test_show_tag_change_uses_sonarr_media_type():
    show = FakePlexItem("Wednesday", "show", set(), {"tvdb:111"}, rating_key="9")
    sonarr = FakeArr([({"tvdb:111"}, [])])
    poller = make_poller(FakePlex([show]), sonarr=sonarr, now=datetime(2026, 1, 1))
    poller.poll()
    sonarr.set([({"tvdb:111"}, ["family"])])
    poller.poll()
    assert show.labels() == {"shared"}


# --- recently-added polling -------------------------------------------------

def test_recently_added_baselines_then_labels_new_item():
    t0 = datetime(2026, 1, 1, 0, 0, 0)
    show = FakePlexItem(
        "Wednesday", "show", set(), {"tvdb:111"}, rating_key="9",
        added_at=t0 + timedelta(minutes=5),
    )
    plex = FakePlex(items=[show], recent=[])
    sonarr = FakeArr([({"tvdb:111"}, ["family"])])
    poller = make_poller(plex, sonarr=sonarr, now=t0)
    poller.poll()                            # baseline: watermark = t0
    plex._recent = [show]                    # show appears after baseline
    summary = poller.poll()
    assert show.labels() == {"shared"}
    assert summary["added"] == 1
    assert "Wednesday" in summary["added_titles"]


def test_recently_added_ignores_items_at_or_before_watermark():
    t0 = datetime(2026, 1, 1)
    old = FakePlexItem(
        "Old", "movie", set(), {"tmdb:1"}, rating_key="1",
        added_at=t0 - timedelta(days=1),
    )
    plex = FakePlex(items=[old], recent=[old])
    radarr = FakeArr([({"tmdb:1"}, ["kids"])])
    poller = make_poller(plex, radarr=radarr, now=t0)
    poller.poll()                            # baseline watermark t0; old is before it
    summary = poller.poll()
    assert summary["added"] == 0
    assert old.labels() == set()
