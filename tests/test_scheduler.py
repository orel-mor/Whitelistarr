from types import SimpleNamespace

from apscheduler.triggers.cron import CronTrigger

from app.scheduler import build_scheduler


def _settings(**over):
    base = dict(
        feature_sweep=True,
        sweep_cron="0 * * * *",
        feature_notify=True,
        watch_scan_cron="0 3 * * *",
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_registers_both_jobs():
    sched = build_scheduler(_settings(), sweep_fn=lambda: None, watch_fn=lambda: None)
    names = {job.name for job in sched.jobs()}
    assert names == {"sweep", "watch_scan"}


def test_jobs_use_cron_trigger_and_run_on_start():
    sched = build_scheduler(_settings(), sweep_fn=lambda: None, watch_fn=lambda: None)
    sweep = next(j for j in sched.jobs() if j.name == "sweep")
    assert isinstance(sweep.trigger, CronTrigger)
    assert sweep.next_run_time is not None  # runs once immediately on start


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
