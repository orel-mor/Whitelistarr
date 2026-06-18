from datetime import datetime, timedelta

from app.clients.plex import PlexClient, PlexItem, configure_plex_identity


def test_configure_plex_identity_sets_headers():
    headers = configure_plex_identity(
        product="Whitelistarr", device_name="PAL-prod", identifier="pal-id-xyz"
    )
    assert headers["X-Plex-Product"] == "Whitelistarr"
    assert headers["X-Plex-Device-Name"] == "PAL-prod"
    assert headers["X-Plex-Client-Identifier"] == "pal-id-xyz"


class FakeGuid:
    def __init__(self, gid):
        self.id = gid


class FakeLabel:
    def __init__(self, tag):
        self.tag = tag


class FakeVideo:
    def __init__(self, title, guids, labels, rating_key=1):
        self.title = title
        self.guids = [FakeGuid(g) for g in guids]
        self.labels = [FakeLabel(t) for t in labels]
        self.ratingKey = rating_key
        self.added = []
        self.removed = []
        self.reloaded = False

    def addLabel(self, labels):
        self.added.append(labels)

    def removeLabel(self, labels):
        self.removed.append(labels)

    def reload(self):
        self.reloaded = True


def test_tmdb_and_tvdb_parsed_from_guids():
    v = FakeVideo("Dune", ["tmdb://603", "imdb://tt1"], [])
    item = PlexItem(v, "movie")
    assert item.tmdb_id == 603
    assert item.tvdb_id is None
    assert item.media_type == "movie"
    assert item.title == "Dune"


def test_labels_returns_tag_set():
    v = FakeVideo("Dune", ["tmdb://603"], ["kids-allowed", "favorite"])
    assert PlexItem(v, "movie").labels() == {"kids-allowed", "favorite"}


def test_add_and_remove_labels_delegate_to_video():
    v = FakeVideo("Dune", ["tmdb://603"], [])
    item = PlexItem(v, "movie")
    item.add_labels(["shared"])
    item.remove_labels(["old"])
    assert v.added == [["shared"]]
    assert v.removed == [["old"]]


def test_reloads_when_guids_missing():
    v = FakeVideo("Dune", [], [])
    item = PlexItem(v, "movie")
    # accessing an id triggers a reload attempt to populate guids
    assert item.tmdb_id is None
    assert v.reloaded is True


def test_rating_key_is_string():
    v = FakeVideo("Dune", ["tvdb://12345"], [], rating_key=987)
    item = PlexItem(v, "show")
    assert item.rating_key == "987"
    assert item.tvdb_id == 12345


class FakeAddedVideo(FakeVideo):
    def __init__(self, title, added_at, rating_key=1):
        super().__init__(title, ["tmdb://1"], [], rating_key=rating_key)
        self.addedAt = added_at


class FakeSection:
    def __init__(self, type_, title, videos):
        self.type = type_
        self.title = title
        self._videos = videos

    def search(self, sort=None, maxresults=None):
        ordered = sorted(self._videos, key=lambda v: v.addedAt, reverse=True)
        return ordered[:maxresults] if maxresults else ordered


class FakeServer:
    def __init__(self, sections):
        self.library = type("Lib", (), {"sections": lambda self: sections})()


def _client_with(sections):
    client = object.__new__(PlexClient)
    client._server = FakeServer(sections)
    client._section_filter = set()
    return client


def test_list_libraries_returns_movie_and_show_only():
    # Music/photo libraries can't be labelled or scanned, so the picker never
    # lists them. The section filter is ignored: every pickable library is shown.
    sections = [
        FakeSection("movie", "Movies", []),
        FakeSection("show", "TV Shows", []),
        FakeSection("movie", "General Videos", []),
        FakeSection("artist", "Music", []),
        FakeSection("photo", "Photos", []),
    ]
    client = _client_with(sections)
    client._section_filter = {"Movies"}  # must NOT restrict the listing
    libs = client.list_libraries()
    assert libs == [
        {"title": "Movies", "type": "movie"},
        {"title": "TV Shows", "type": "show"},
        {"title": "General Videos", "type": "movie"},
    ]


def test_recently_added_returns_items_newer_than_watermark():
    t0 = datetime(2026, 1, 1)
    section = FakeSection("movie", "Movies", [
        FakeAddedVideo("New", t0 + timedelta(hours=2), rating_key=2),
        FakeAddedVideo("Old", t0 - timedelta(hours=2), rating_key=1),
    ])
    items = _client_with([section]).recently_added(since=t0)
    assert [i.title for i in items] == ["New"]


def test_recently_added_none_since_returns_all():
    section = FakeSection("movie", "Movies", [
        FakeAddedVideo("A", datetime(2026, 1, 2)),
        FakeAddedVideo("B", datetime(2026, 1, 1)),
    ])
    items = _client_with([section]).recently_added(since=None)
    assert {i.title for i in items} == {"A", "B"}
