from types import SimpleNamespace

from app.scheduler import build_scheduler


def _settings(**over):
    base = dict(
        feature_sweep=True,
        sweep_interval_minutes=60,
        feature_notify=True,
        watch_scan_interval_minutes=360,
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_registers_both_jobs():
    sched = build_scheduler(_settings(), sweep_fn=lambda: None, watch_fn=lambda: None)
    names = {job.name for job in sched.jobs()}
    assert names == {"sweep", "watch_scan"}


def test_only_sweep_when_notify_disabled():
    sched = build_scheduler(_settings(feature_notify=False), sweep_fn=lambda: None, watch_fn=lambda: None)
    assert {job.name for job in sched.jobs()} == {"sweep"}


def test_no_jobs_when_all_disabled():
    sched = build_scheduler(
        _settings(feature_sweep=False, feature_notify=False),
        sweep_fn=lambda: None,
        watch_fn=lambda: None,
    )
    assert sched.jobs() == []
