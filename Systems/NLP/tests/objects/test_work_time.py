from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from nl_project_2.objects.models import ProjectCard
from nl_project_2.objects.runtime import ApplicationRuntime
from nl_project_2.objects.service import ObjectService
from nl_project_2.objects.time_tracking import ActiveSessionConflict, WorkTimeService
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import work_session


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value

    def advance(self, **kwargs) -> None:
        self.value += timedelta(**kwargs)


def _projects(database):
    objects = ObjectService(database.engine)
    return (
        objects.create_project(ProjectCard(name="Первый", project_code="T-1")),
        objects.create_project(ProjectCard(name="Второй", project_code="T-2")),
    )


def test_two_project_switch_pause_navigation_return_and_close(database):
    first, second = _projects(database)
    clock = MutableClock(datetime(2026, 8, 8, 7, 0, tzinfo=UTC))
    service = WorkTimeService(
        database.engine,
        new_id(),
        clock=clock,
        local_timezone=timezone(timedelta(hours=5)),
    )
    service.switch_to(first)
    clock.advance(minutes=20)
    service.pause(first)
    clock.advance(minutes=5)
    assert service.summary(first).is_running is False
    service.play(first)
    clock.advance(minutes=10)
    service.switch_to(second)
    clock.advance(minutes=15)
    service.switch_to(first)
    clock.advance(minutes=5)
    assert service.summary(first).total_seconds == 35 * 60
    assert service.summary(second).total_seconds == 15 * 60
    service.close_application()
    with database.engine.connect() as connection:
        assert (
            connection.scalar(
                select(func.count())
                .select_from(work_session)
                .where(work_session.c.stopped_at_utc.is_(None))
            )
            == 0
        )


def test_midnight_period_is_split_by_local_calendar_day(database):
    first, _second = _projects(database)
    zone = timezone(timedelta(hours=5))
    clock = MutableClock(datetime(2026, 8, 8, 23, 50, tzinfo=zone))
    service = WorkTimeService(database.engine, new_id(), clock=clock, local_timezone=zone)
    service.switch_to(first)
    clock.advance(minutes=20)
    service.pause(first)
    totals = service.daily_totals(first)
    assert totals[datetime(2026, 8, 8).date()] == 10 * 60
    assert totals[datetime(2026, 8, 9).date()] == 10 * 60


def test_database_constraint_rejects_second_application_active_period(database):
    first, second = _projects(database)
    clock = MutableClock(datetime(2026, 8, 8, 7, 0, tzinfo=UTC))
    owner = WorkTimeService(database.engine, new_id(), clock=clock)
    other = WorkTimeService(database.engine, new_id(), clock=clock)
    owner.switch_to(first)
    with pytest.raises(ActiveSessionConflict):
        other.switch_to(second)
    assert owner.summary(first).is_running is True


def test_navigation_within_project_does_not_change_period(database):
    first, _second = _projects(database)
    clock = MutableClock(datetime(2026, 8, 8, 7, 0, tzinfo=UTC))
    work = WorkTimeService(database.engine, new_id(), clock=clock)
    runtime = ApplicationRuntime(database, ObjectService(database.engine), work)
    runtime.open_project(first)
    with database.engine.connect() as connection:
        session_id = connection.scalar(
            select(work_session.c.id).where(work_session.c.stopped_at_utc.is_(None))
        )
    runtime.navigate_within_project("Помещения")
    runtime.navigate_within_project("Настройки")
    with database.engine.connect() as connection:
        assert (
            connection.scalar(
                select(work_session.c.id).where(work_session.c.stopped_at_utc.is_(None))
            )
            == session_id
        )
    runtime.close()
