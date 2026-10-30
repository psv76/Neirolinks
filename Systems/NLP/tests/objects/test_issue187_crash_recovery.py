"""Issue #187: OS process ownership and conservative crash/reboot work time."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from nl_project_2.objects.instance_lock import (
    ApplicationAlreadyRunning,
    DatabaseInstanceLock,
)
from nl_project_2.objects.models import ProjectCard
from nl_project_2.objects.service import ObjectService
from nl_project_2.objects.time_tracking import WorkTimeService
from nl_project_2.persistence.schema import work_session


class Clock:
    def __init__(self, now: datetime):
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs) -> None:
        self.now += timedelta(**kwargs)


def _project(database):
    return ObjectService(database.engine).create_project(
        ProjectCard(name="Сессия #187", project_code="W-187")
    )


def test_crash_recovery_never_charges_offline_hours(database, tmp_path):
    project = _project(database)
    clock = Clock(datetime(2026, 10, 9, 5, 0, tzinfo=UTC))
    old = WorkTimeService(database.engine, "old-process", clock=clock)
    old.switch_to(project)
    clock.advance(seconds=90)
    assert old.heartbeat() is True
    clock.advance(hours=8)  # OS crash / reboot: no activity heartbeats
    fresh = WorkTimeService(database.engine, "new-process", clock=clock)
    lock = DatabaseInstanceLock(tmp_path / "nl_project_3.sqlite")
    with pytest.raises(RuntimeError, match="requires the OS"):
        fresh.recover_abandoned_session(lock)
    with lock:
        recovered_id = fresh.recover_abandoned_session(lock)
        assert recovered_id is not None
        assert fresh.recover_abandoned_session(lock) is None
        fresh.switch_to(project)
    with database.engine.connect() as connection:
        statement = select(work_session).where(work_session.c.id == recovered_id)
        old_row = connection.execute(statement).mappings().one()
        assert old_row["close_reason"] == "RECOVERY_STALE_SESSION"
        assert "unobserved interval was excluded" in old_row["recovery_reason"]
    assert fresh.summary(project).total_seconds == 90
    assert fresh.summary(project).is_running is True
    fresh.close_application()
    assert fresh.summary(project).total_seconds == 90


def test_legacy_unclosed_period_is_recovered_at_start_not_restart(database, tmp_path):
    project = _project(database)
    clock = Clock(datetime(2026, 10, 8, 5, 0, tzinfo=UTC))
    WorkTimeService(database.engine, "legacy", clock=clock).switch_to(project)
    clock.advance(days=2)
    fresh = WorkTimeService(database.engine, "restarted", clock=clock)
    with DatabaseInstanceLock(tmp_path / "project.sqlite") as lock:
        recovered = fresh.recover_abandoned_session(lock)
    with database.engine.connect() as connection:
        statement = select(work_session).where(work_session.c.id == recovered)
        row = connection.execute(statement).mappings().one()
    assert row["close_reason"] == "RECOVERY_STALE_SESSION"
    assert fresh.summary(project).total_seconds == 0
    assert row["stopped_at_utc"] is not None


def test_os_lock_refuses_concurrent_owner_and_survives_file_reuse(tmp_path):
    path = tmp_path / "same.sqlite"
    first = DatabaseInstanceLock(path)
    second = DatabaseInstanceLock(path)
    with first:
        with pytest.raises(ApplicationAlreadyRunning):
            second.acquire()
        assert first.held
    assert not first.held
    assert first.path.exists()
    with DatabaseInstanceLock(path):
        pass


def test_os_lock_is_released_when_owner_process_is_killed(tmp_path):
    root = Path(__file__).resolve().parents[2]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(root / "src")
    code = (
        "import sys, time; "
        "from nl_project_2.objects.instance_lock import DatabaseInstanceLock; "
        "lock=DatabaseInstanceLock(sys.argv[1]); "
        "lock.acquire(); print('HELD',flush=True); time.sleep(30)"
    )
    path = tmp_path / "crash.sqlite"
    proc = subprocess.Popen(
        [sys.executable, "-c", code, str(path)],
        cwd=root,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert proc.stdout is not None
        assert proc.stdout.readline().strip() == "HELD"
        with pytest.raises(ApplicationAlreadyRunning):
            with DatabaseInstanceLock(path):
                pass
    finally:
        proc.kill()
        proc.communicate(timeout=10)
    with DatabaseInstanceLock(path) as guard:
        assert guard.held


def test_clean_close_heartbeat_has_no_recovery_work(database, tmp_path):
    project = _project(database)
    clock = Clock(datetime(2026, 10, 10, 8, 0, tzinfo=UTC))
    owner = WorkTimeService(database.engine, "first", clock=clock)
    owner.switch_to(project)
    clock.advance(minutes=2)
    owner.heartbeat()
    owner.close_application()
    clock.advance(hours=5)
    new = WorkTimeService(database.engine, "second", clock=clock)
    with DatabaseInstanceLock(tmp_path / "project.sqlite") as lock:
        assert new.recover_abandoned_session(lock) is None
    assert new.summary(project).total_seconds == 120


def test_fatal_startup_surfaces_error_and_log_path(monkeypatch, tmp_path):
    from nl_project_2 import __main__ as entrypoint

    events = []

    def raises(_argv):
        raise ValueError("startup rejected")

    monkeypatch.setattr(entrypoint.PathConfig, "from_environment", lambda: object())
    monkeypatch.setattr(
        entrypoint,
        "record_fatal_startup",
        lambda error, paths: tmp_path / "fatal-startup.jsonl",
    )
    monkeypatch.setattr(
        entrypoint,
        "show_fatal_startup",
        lambda error, location: events.append((str(error), location)),
    )
    assert entrypoint.main([], runner=raises) == 1
    assert events == [("startup rejected", tmp_path / "fatal-startup.jsonl")]
