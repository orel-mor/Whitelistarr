from app.core.labeler import apply_labels, describe_item, desired_labels, reconcile


class ItemWithGuids:
    def __init__(self, title, guid_keys):
        self.title = title
        self._keys = set(guid_keys)

    def guid_keys(self):
        return set(self._keys)


class TestDescribeItem:
    def test_prefers_tmdb(self):
        item = ItemWithGuids("Aladdin", {"imdb:tt1", "tmdb:812", "tvdb:9"})
        assert describe_item(item) == "Aladdin [tmdb:812]"

    def test_falls_back_to_tvdb_then_imdb(self):
        assert describe_item(ItemWithGuids("Show", {"tvdb:9", "imdb:tt1"})) == "Show [tvdb:9]"
        assert describe_item(ItemWithGuids("Old", {"imdb:tt1"})) == "Old [imdb:tt1]"

    def test_no_guid_keys_method_returns_title(self):
        class Plain:
            title = "Plain"

        assert describe_item(Plain()) == "Plain"

    def test_empty_guids_returns_title(self):
        assert describe_item(ItemWithGuids("Empty", set())) == "Empty"


class FakeItem:
    def __init__(self, title, labels):
        self.title = title
        self._labels = set(labels)
        self.added = []
        self.removed = []

    def labels(self):
        return set(self._labels)

    def add_labels(self, labels):
        for label in labels:
            self._labels.add(label)
            self.added.append(label)

    def remove_labels(self, labels):
        for label in labels:
            self._labels.discard(label)
            self.removed.append(label)


LABEL_MAP = {"niece-ok": "kids-allowed", "sister": "shared"}
MANAGED = {"kids-allowed", "shared"}


class TestDesiredLabels:
    def test_maps_known_tags(self):
        assert desired_labels(["niece-ok", "sister"], LABEL_MAP) == {"kids-allowed", "shared"}

    def test_ignores_unmapped_tags(self):
        assert desired_labels(["niece-ok", "random-tag"], LABEL_MAP) == {"kids-allowed"}

    def test_no_tags_is_empty(self):
        assert desired_labels([], LABEL_MAP) == set()


class TestReconcile:
    def test_adds_missing_labels(self):
        add, remove = reconcile(current=set(), desired={"kids-allowed"}, managed=MANAGED, mode="reconcile")
        assert add == {"kids-allowed"}
        assert remove == set()

    def test_removes_managed_label_no_longer_desired(self):
        add, remove = reconcile(
            current={"kids-allowed", "shared"}, desired={"shared"}, managed=MANAGED, mode="reconcile"
        )
        assert add == set()
        assert remove == {"kids-allowed"}

    def test_never_removes_unmanaged_labels(self):
        # "favorite" is not in the managed set -> must be left alone
        add, remove = reconcile(
            current={"favorite", "kids-allowed"}, desired=set(), managed=MANAGED, mode="reconcile"
        )
        assert remove == {"kids-allowed"}
        assert "favorite" not in remove

    def test_add_only_mode_never_removes(self):
        add, remove = reconcile(
            current={"kids-allowed"}, desired=set(), managed=MANAGED, mode="add-only"
        )
        assert remove == set()

    def test_noop_when_already_in_sync(self):
        add, remove = reconcile(
            current={"shared"}, desired={"shared"}, managed=MANAGED, mode="reconcile"
        )
        assert add == set() and remove == set()

    def test_case_insensitive_does_not_readd_existing(self):
        # Plex stores "kids-allowed" as "Kids-allowed" -> must not re-add.
        add, remove = reconcile(
            current={"Kids-allowed"}, desired={"kids-allowed"}, managed=MANAGED, mode="reconcile"
        )
        assert add == set()
        assert remove == set()

    def test_case_insensitive_removes_actual_stored_string(self):
        # reverse-style: desired empty, managed present in capitalized form.
        add, remove = reconcile(
            current={"Kids-allowed", "favorite"}, desired=set(), managed=MANAGED, mode="reconcile"
        )
        assert add == set()
        assert remove == {"Kids-allowed"}  # the real Plex string, not "kids-allowed"


class TestApplyLabels:
    def test_applies_add_and_remove(self):
        item = FakeItem("Dune", labels={"kids-allowed"})
        changed = apply_labels(item, to_add={"shared"}, to_remove={"kids-allowed"}, dry_run=False)
        assert changed is True
        assert item.labels() == {"shared"}

    def test_dry_run_does_not_mutate(self):
        item = FakeItem("Dune", labels={"kids-allowed"})
        changed = apply_labels(item, to_add={"shared"}, to_remove={"kids-allowed"}, dry_run=True)
        assert changed is True  # would have changed
        assert item.labels() == {"kids-allowed"}
        assert item.added == [] and item.removed == []

    def test_noop_returns_false(self):
        item = FakeItem("Dune", labels={"kids-allowed"})
        changed = apply_labels(item, to_add=set(), to_remove=set(), dry_run=False)
        assert changed is False
