from app.status import StatusTracker


def test_snapshot_empty_before_any_run():
    t = StatusTracker()
    assert t.snapshot() == {"sweep": None, "watch_scan": None, "reactive": None}


def test_reactive_run_is_tracked():
    t = StatusTracker()
    t.record("reactive", {"tag_changes": 2, "added": 1, "added_titles": ["Dune"]})
    snap = t.snapshot()
    assert snap["reactive"]["tag_changes"] == 2
    assert snap["reactive"]["added_titles"] == ["Dune"]


def test_history_logs_only_meaningful_runs():
    t = StatusTracker()
    t.record("reactive", {"tag_changes": 0, "added": 0})   # idle poll -> not logged
    t.record("sweep", {"processed": 50, "changed": 0})     # no-op sweep -> not logged
    assert t.history() == []
    # but snapshot (last-run liveness) still updates
    assert t.snapshot()["reactive"]["tag_changes"] == 0


def test_history_logs_runs_that_did_something():
    t = StatusTracker()
    t.record("reactive", {"tag_changes": 1, "added": 0})
    t.record("sweep", {"processed": 50, "changed": 3})
    t.record("watch_scan", {"processed": 9, "notified": 2})
    actions = [e["action"] for e in t.history()]
    assert actions == ["watch_scan", "sweep", "reactive"]  # newest first


def test_manual_action_always_logged_even_when_noop():
    t = StatusTracker()
    t.record("sweep", {"processed": 10, "changed": 0}, history=True)
    t.record("test-notification", {"ok": True}, history=True)
    actions = [e["action"] for e in t.history()]
    assert actions == ["test-notification", "sweep"]


def test_history_entries_carry_action_time_and_summary_with_id():
    t = StatusTracker()
    t.record("sweep", {"processed": 5, "changed": 2})
    e = t.history()[0]
    assert e["action"] == "sweep"
    assert e["changed"] == 2 and e["processed"] == 5
    assert isinstance(e["at"], str) and e["at"]
    assert isinstance(e["id"], int)


def test_history_capped_newest_kept():
    t = StatusTracker(history_size=3)
    for i in range(5):
        t.record("sweep", {"processed": 1, "changed": i + 1}, history=True)
    changed = [e["changed"] for e in t.history()]
    assert changed == [5, 4, 3]  # newest first, oldest dropped


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
