from app.clients.plex import PlexItem, configure_plex_identity


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
