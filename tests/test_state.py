from app.state import StateStore


def test_unknown_key_not_notified():
    store = StateStore(":memory:")
    assert store.already_notified("111:watched") is False


def test_mark_then_already_notified():
    store = StateStore(":memory:")
    store.mark_notified("111:watched")
    assert store.already_notified("111:watched") is True


def test_keys_are_independent():
    store = StateStore(":memory:")
    store.mark_notified("111:watched")
    assert store.already_notified("111:stale") is False


def test_mark_is_idempotent():
    store = StateStore(":memory:")
    store.mark_notified("111:watched")
    store.mark_notified("111:watched")  # must not raise
    assert store.already_notified("111:watched") is True


def test_persists_across_instances(tmp_path):
    db = str(tmp_path / "state.db")
    StateStore(db).mark_notified("111:watched")
    assert StateStore(db).already_notified("111:watched") is True


def test_clear_removes_key():
    store = StateStore(":memory:")
    store.mark_notified("111:watched")
    store.clear("111:watched")
    assert store.already_notified("111:watched") is False


def test_clear_missing_key_is_noop():
    store = StateStore(":memory:")
    store.clear("nope")  # must not raise


def test_concurrent_access_does_not_crash():
    import threading

    store = StateStore(":memory:")
    errors = []

    def worker(n):
        try:
            for i in range(200):
                key = f"k{n}:{i}"
                store.mark_notified(key)
                store.already_notified(key)
                store.clear(key)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
