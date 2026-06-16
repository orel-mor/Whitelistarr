from app.core.sync import LabelSync
from app.state import StateStore

LABEL_MAP = {"niece-ok": "kids-allowed", "sister": "shared"}


class FakeNotifier:
    def __init__(self):
        self.sent = []

    def notify(self, title, body, body_format=None, notify_type=None):
        self.sent.append((title, body, body_format))
        return True


class FakePlexItem:
    def __init__(self, title, media_type, labels, guid_keys, rating_key=None):
        self.title = title
        self.media_type = media_type
        self.rating_key = rating_key
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
    def __init__(self, items):
        self._items = items

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

    def fetch_labelable(self, rating_key):
        for item in self._items:
            if getattr(item, "rating_key", None) == rating_key:
                return item
        return None


class FakeArr:
    def __init__(self, entries):
        self._entries = entries  # list of (guid_keys, tag_names)

    def iter_all_with_tags(self):
        return list(self._entries)


def make_sync(plex, radarr_entries=None, sonarr_entries=None, mode="reconcile", dry_run=False):
    return LabelSync(
        plex=plex,
        radarr=FakeArr(radarr_entries or []),
        sonarr=FakeArr(sonarr_entries or []),
        label_map=LABEL_MAP,
        managed=set(LABEL_MAP.values()),
        mode=mode,
        dry_run=dry_run,
    )


def test_sync_item_adds_label_from_movie_tag():
    item = FakePlexItem("Dune", "movie", labels=set(), guid_keys={"tmdb:603"})
    sync = make_sync(FakePlex([item]), radarr_entries=[({"tmdb:603"}, ["niece-ok"])])
    assert sync.sync_item(item) is True
    assert item.labels() == {"kids-allowed"}


def test_show_matched_by_tmdb_when_plex_has_no_tvdb():
    # Regression: new Plex agent gives only tmdb; Sonarr indexes tvdb but also exposes tmdb.
    item = FakePlexItem("Bluey", "show", labels=set(), guid_keys={"tmdb:2316"})
    sonarr = [({"tvdb:121361", "tmdb:2316"}, ["sister"])]
    sync = make_sync(FakePlex([item]), sonarr_entries=sonarr)
    assert sync.sync_item(item) is True
    assert item.labels() == {"shared"}


def test_sync_item_removes_label_when_tag_gone():
    item = FakePlexItem("Dune", "movie", labels={"kids-allowed"}, guid_keys={"tmdb:603"})
    sync = make_sync(FakePlex([item]), radarr_entries=[({"tmdb:603"}, [])])
    sync.sync_item(item)
    assert item.labels() == set()


def test_sync_item_leaves_manual_labels_untouched():
    item = FakePlexItem("Dune", "movie", labels={"favorite"}, guid_keys={"tmdb:603"})
    sync = make_sync(FakePlex([item]), radarr_entries=[({"tmdb:603"}, ["niece-ok"])])
    sync.sync_item(item)
    assert item.labels() == {"favorite", "kids-allowed"}


def test_sync_by_ids_finds_and_labels_item():
    item = FakePlexItem("Dune", "movie", labels=set(), guid_keys={"tmdb:603"})
    sync = make_sync(FakePlex([item]), radarr_entries=[({"tmdb:603"}, ["sister"])])
    assert sync.sync_by_ids("movie", tmdb_id=603) is True
    assert item.labels() == {"shared"}


def test_sync_by_ids_returns_false_when_not_found():
    sync = make_sync(FakePlex([]))
    assert sync.sync_by_ids("movie", tmdb_id=999) is False


def test_sync_by_rating_key_labels_item():
    item = FakePlexItem("Dune", "movie", labels=set(), guid_keys={"tmdb:603"}, rating_key="12345")
    sync = make_sync(FakePlex([item]), radarr_entries=[({"tmdb:603"}, ["niece-ok"])])
    assert sync.sync_by_rating_key("12345") is True
    assert item.labels() == {"kids-allowed"}


def test_sync_by_rating_key_returns_false_when_not_found():
    sync = make_sync(FakePlex([]))
    assert sync.sync_by_rating_key("nope") is False


def test_sweep_processes_all_items_and_counts_changes():
    items = [
        FakePlexItem("Dune", "movie", labels=set(), guid_keys={"tmdb:603"}),
        FakePlexItem("Bluey", "show", labels=set(), guid_keys={"tmdb:2316"}),
        FakePlexItem("Untagged", "movie", labels=set(), guid_keys={"tmdb:2"}),
    ]
    sync = make_sync(
        FakePlex(items),
        radarr_entries=[({"tmdb:603"}, ["niece-ok"]), ({"tmdb:2"}, [])],
        sonarr_entries=[({"tmdb:2316"}, ["sister"])],
    )
    summary = sync.sweep()
    assert summary["processed"] == 3
    assert summary["changed"] == 2


def test_dry_run_does_not_mutate():
    item = FakePlexItem("Dune", "movie", labels=set(), guid_keys={"tmdb:603"})
    sync = make_sync(FakePlex([item]), radarr_entries=[({"tmdb:603"}, ["niece-ok"])], dry_run=True)
    assert sync.sync_item(item) is True
    assert item.labels() == set()


def test_reverse_sweep_removes_managed_labels_only():
    items = [
        FakePlexItem("A", "movie", labels={"mika-whitelist", "favorite"}, guid_keys={"tmdb:1"}),
        FakePlexItem("B", "show", labels={"shared"}, guid_keys={"tvdb:2"}),
        FakePlexItem("C", "movie", labels={"favorite"}, guid_keys={"tmdb:3"}),
    ]
    sync = LabelSync(
        plex=FakePlex(items),
        radarr=FakeArr([]),
        sonarr=FakeArr([]),
        label_map=LABEL_MAP,
        managed={"kids-allowed", "shared", "mika-whitelist"},
        mode="reconcile",
        dry_run=False,
    )
    summary = sync.reverse_sweep()
    assert summary == {"processed": 3, "changed": 2}
    assert items[0].labels() == {"favorite"}  # managed removed, manual kept
    assert items[1].labels() == set()
    assert items[2].labels() == {"favorite"}  # untouched (no managed label)


def _labeled_sync(plex, radarr_entries, notifier, state, dry_run=False, sonarr_entries=None):
    return LabelSync(
        plex=plex,
        radarr=FakeArr(radarr_entries),
        sonarr=FakeArr(sonarr_entries or []),
        label_map=LABEL_MAP,
        managed=set(LABEL_MAP.values()),
        mode="reconcile",
        dry_run=dry_run,
        notifier=notifier,
        state=state,
        notify_labeled=True,
    )


def test_sweep_one_added_message_grouped_by_type_and_label():
    items = [
        FakePlexItem("Dune", "movie", labels=set(), guid_keys={"tmdb:1"}, rating_key="1"),
        FakePlexItem("Bluey", "movie", labels=set(), guid_keys={"tmdb:2"}, rating_key="2"),
        FakePlexItem("Wednesday", "show", labels=set(), guid_keys={"tvdb:3"}, rating_key="3"),
    ]
    notifier = FakeNotifier()
    sync = _labeled_sync(
        FakePlex(items),
        [({"tmdb:1"}, ["niece-ok"]), ({"tmdb:2"}, ["sister"])],
        notifier,
        StateStore(":memory:"),
        sonarr_entries=[({"tvdb:3"}, ["niece-ok"])],
    )
    sync.sweep()
    # one "Label Added" message covering movies + tv
    assert len(notifier.sent) == 1
    title, body, fmt = notifier.sent[0]
    assert title == "Label Added"
    assert fmt == "markdown"
    assert "**Movies**" in body and "**TV Shows**" in body
    assert "`kids-allowed`" in body and "`shared`" in body
    assert "- Dune" in body and "- Bluey" in body and "- Wednesday" in body


def test_sweep_lists_every_item_no_truncation():
    items = [
        FakePlexItem(f"Movie {i}", "movie", labels=set(), guid_keys={f"tmdb:{i}"}, rating_key=str(i))
        for i in range(40)
    ]
    notifier = FakeNotifier()
    sync = _labeled_sync(
        FakePlex(items),
        [({f"tmdb:{i}"}, ["niece-ok"]) for i in range(40)],
        notifier,
        StateStore(":memory:"),
    )
    sync.sweep()
    body = notifier.sent[0][1]
    for i in range(40):
        assert f"- Movie {i}" in body
    assert "more" not in body  # no "...and N more" truncation
    assert notifier.sent[0][0] == "Label Added"


def test_label_notification_deduped_per_item_label():
    item = FakePlexItem("Dune", "movie", labels=set(), guid_keys={"tmdb:1"}, rating_key="1")
    notifier = FakeNotifier()
    state = StateStore(":memory:")
    sync = _labeled_sync(FakePlex([item]), [({"tmdb:1"}, ["niece-ok"])], notifier, state)
    sync.sweep()
    sync.sweep()  # already notified -> no second message
    assert len(notifier.sent) == 1


def test_webhook_sync_sends_single_label_notification():
    item = FakePlexItem("Dune", "movie", labels=set(), guid_keys={"tmdb:1"}, rating_key="42")
    notifier = FakeNotifier()
    sync = _labeled_sync(FakePlex([item]), [({"tmdb:1"}, ["niece-ok"])], notifier, StateStore(":memory:"))
    sync.sync_by_rating_key("42")
    assert len(notifier.sent) == 1
    title, body, fmt = notifier.sent[0]
    assert title == "Label Added"
    assert "**Movies**" in body
    assert "`kids-allowed`" in body
    assert "- Dune" in body


def test_removal_fires_notification():
    item = FakePlexItem("Dune", "movie", labels=set(), guid_keys={"tmdb:1"}, rating_key="1")
    plex = FakePlex([item])
    state = StateStore(":memory:")
    notifier = FakeNotifier()
    # run 1: tag present -> label added
    _labeled_sync(plex, [({"tmdb:1"}, ["niece-ok"])], notifier, state).sweep()
    # run 2: tag gone -> label removed
    _labeled_sync(plex, [], notifier, state).sweep()
    assert len(notifier.sent) == 2
    title, removed_body, _ = notifier.sent[1]
    assert title == "Label Removed"
    assert "`kids-allowed`" in removed_body
    assert "- Dune" in removed_body


def test_removal_not_notified_if_never_announced():
    # Label present at first run but never announced as added -> no removal ping.
    item = FakePlexItem("Dune", "movie", labels={"kids-allowed"}, guid_keys={"tmdb:1"}, rating_key="1")
    notifier = FakeNotifier()
    _labeled_sync(FakePlex([item]), [], notifier, StateStore(":memory:")).sweep()
    assert notifier.sent == []
    assert item.labels() == set()  # still removed, just not announced


def test_no_label_notification_in_dry_run():
    item = FakePlexItem("Dune", "movie", labels=set(), guid_keys={"tmdb:1"}, rating_key="1")
    notifier = FakeNotifier()
    sync = _labeled_sync(
        FakePlex([item]), [({"tmdb:1"}, ["niece-ok"])], notifier, StateStore(":memory:"), dry_run=True
    )
    sync.sweep()
    assert notifier.sent == []


def test_reverse_sweep_removes_capitalized_label():
    # Plex stores "mika-whitelist" as "Mika-whitelist"; reverse must still remove it.
    item = FakePlexItem("A", "movie", labels={"Mika-whitelist", "favorite"}, guid_keys={"tmdb:1"})
    sync = LabelSync(
        plex=FakePlex([item]),
        radarr=FakeArr([]),
        sonarr=FakeArr([]),
        label_map=LABEL_MAP,
        managed={"mika-whitelist"},
        mode="reconcile",
        dry_run=False,
    )
    summary = sync.reverse_sweep()
    assert summary["changed"] == 1
    assert item.labels() == {"favorite"}


def test_reverse_sweep_dry_run_does_not_mutate():
    item = FakePlexItem("A", "movie", labels={"mika-whitelist"}, guid_keys={"tmdb:1"})
    sync = LabelSync(
        plex=FakePlex([item]),
        radarr=FakeArr([]),
        sonarr=FakeArr([]),
        label_map=LABEL_MAP,
        managed={"mika-whitelist"},
        mode="reconcile",
        dry_run=True,
    )
    summary = sync.reverse_sweep()
    assert summary["changed"] == 1
    assert item.labels() == {"mika-whitelist"}  # dry run: not mutated
