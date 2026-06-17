from app.status import StatusTracker


def test_snapshot_empty_before_any_run():
    t = StatusTracker()
    assert t.snapshot() == {"sweep": None, "watch_scan": None}


def test_record_stores_summary_with_timestamp():
    t = StatusTracker()
    t.record("sweep", {"processed": 10, "changed": 3})
    snap = t.snapshot()
    assert snap["sweep"]["processed"] == 10
    assert snap["sweep"]["changed"] == 3
    assert isinstance(snap["sweep"]["at"], str) and snap["sweep"]["at"]
    assert snap["watch_scan"] is None


def test_latest_run_wins():
    t = StatusTracker()
    t.record("sweep", {"processed": 1, "changed": 0})
    t.record("sweep", {"processed": 2, "changed": 2})
    assert t.snapshot()["sweep"]["processed"] == 2


def test_wrap_runs_records_and_returns():
    t = StatusTracker()
    wrapped = t.wrap("watch_scan", lambda: {"processed": 5, "notified": 1})
    result = wrapped()
    assert result == {"processed": 5, "notified": 1}
    assert t.snapshot()["watch_scan"]["notified"] == 1
