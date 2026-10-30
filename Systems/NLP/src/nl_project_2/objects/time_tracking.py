"""Automatic one-project-at-a-time work-period lifecycle with midnight splitting."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta, tzinfo

from sqlalchemy import Engine, select, update
from sqlalchemy.exc import IntegrityError

from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import work_session
from nl_project_2.persistence.uow import UnitOfWork

from .instance_lock import DatabaseInstanceLock
from .models import TimeSummary

Clock = Callable[[], datetime]


class ActiveSessionConflict(RuntimeError):
    """A different running application owns the only active period."""


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Clock must return a timezone-aware datetime")
    return value.astimezone(UTC)


def _split_interval(start_utc: datetime, end_utc: datetime, zone: tzinfo) -> list[dict[str, str]]:
    if end_utc < start_utc:
        raise ValueError("Work interval cannot end before it starts")
    result: list[dict[str, str]] = []
    cursor = start_utc
    while cursor < end_utc:
        local = cursor.astimezone(zone)
        next_day = local.date() + timedelta(days=1)
        boundary = datetime.combine(next_day, time.min, tzinfo=zone).astimezone(UTC)
        segment_end = min(end_utc, boundary)
        result.append(
            {
                "start_utc": cursor.isoformat(),
                "end_utc": segment_end.isoformat(),
                "local_date": local.date().isoformat(),
            }
        )
        cursor = segment_end
    if start_utc == end_utc:
        result.append(
            {
                "start_utc": start_utc.isoformat(),
                "end_utc": end_utc.isoformat(),
                "local_date": start_utc.astimezone(zone).date().isoformat(),
            }
        )
    return result


def _seconds(interval: dict[str, str]) -> int:
    start = datetime.fromisoformat(interval["start_utc"])
    end = datetime.fromisoformat(interval["end_utc"])
    return max(0, int((end - start).total_seconds()))


class WorkTimeService:
    def __init__(
        self,
        engine: Engine,
        application_instance_id: str,
        *,
        clock: Clock | None = None,
        local_timezone: tzinfo | None = None,
    ) -> None:
        self._engine = engine
        self.application_instance_id = application_instance_id
        self._clock = clock or (lambda: datetime.now(UTC))
        self._zone = local_timezone or datetime.now().astimezone().tzinfo
        if self._zone is None:
            self._zone = UTC

    def _now(self) -> datetime:
        return _aware_utc(self._clock())

    def heartbeat(self) -> bool:
        """Persist the last known *working* instant, not elapsed wall-clock idle time.

        The GUI calls this at a fixed cadence while an active period exists.
        After a process crash, only work through this timestamp is recoverable.
        """
        now = self._now()
        with UnitOfWork(self._engine) as uow:
            active = (
                uow.execute(select(work_session).where(work_session.c.stopped_at_utc.is_(None)))
                .mappings()
                .one_or_none()
            )
            if active is None:
                uow.commit()
                return False
            if active["application_instance_id"] != self.application_instance_id:
                raise ActiveSessionConflict("Another application owns the active period")
            uow.execute(
                update(work_session)
                .where(work_session.c.id == active["id"])
                .values(
                    updated_at_utc=now,
                    row_version=work_session.c.row_version + 1,
                )
            )
            uow.commit()
            return True

    def recover_abandoned_session(self, lock: DatabaseInstanceLock) -> str | None:
        """Close an orphan at its last persisted heartbeat, never at reboot time.

        The caller MUST hold the OS database-lifetime lock before inspecting
        work_session. This protects against recovering a genuinely live owner.
        Pre-heartbeat legacy sessions recover at their last recorded update
        (usually their start), conservatively excluding unverified downtime.
        """
        if not lock.held:
            raise RuntimeError("Stale session recovery requires the OS database lock")
        now = self._now()
        with UnitOfWork(self._engine) as uow:
            active = (
                uow.execute(select(work_session).where(work_session.c.stopped_at_utc.is_(None)))
                .mappings()
                .one_or_none()
            )
            if active is None or active["application_instance_id"] == self.application_instance_id:
                uow.commit()
                return None
            row = dict(active)
            start = datetime.fromisoformat(row["intervals_json"][0]["start_utc"])
            if now < start:
                raise ActiveSessionConflict("System clock precedes the abandoned work period")
            last_seen = row["updated_at_utc"] or row["started_at_utc"]
            if isinstance(last_seen, str):
                last_seen = datetime.fromisoformat(last_seen)
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=UTC)
            last_seen = last_seen.astimezone(UTC)
            stop = min(now, max(start, last_seen))
            self._stop_row(uow, row, stop, "RECOVERY_STALE_SESSION")
            uow.execute(
                update(work_session)
                .where(work_session.c.id == row["id"])
                .values(
                    recovery_reason=(
                        "OS instance lock was available; previous process no longer owns "
                        "the database. Recovery endpoint is the last persisted activity "
                        f"{stop.isoformat()}, not the restart time {now.isoformat()}. "
                        "The unobserved interval was excluded."
                    )
                )
            )
            uow.commit()
            return row["id"]

    def switch_to(self, project_id: str) -> str:
        """End the previous project and automatically start the selected one atomically."""
        now = self._now()
        with UnitOfWork(self._engine) as uow:
            active = (
                uow.execute(select(work_session).where(work_session.c.stopped_at_utc.is_(None)))
                .mappings()
                .one_or_none()
            )
            if active and active["application_instance_id"] != self.application_instance_id:
                raise ActiveSessionConflict("Another application instance owns the active period")
            if active and active["project_id"] == project_id:
                uow.commit()
                return active["id"]
            if active:
                self._stop_row(uow, dict(active), now, "PROJECT_SWITCH")
            identifier = self._insert_active(uow, project_id, now)
            uow.commit()
            return identifier

    def pause(self, project_id: str, *, reason: str = "USER_PAUSE") -> bool:
        now = self._now()
        with UnitOfWork(self._engine) as uow:
            active = (
                uow.execute(select(work_session).where(work_session.c.stopped_at_utc.is_(None)))
                .mappings()
                .one_or_none()
            )
            if active is None:
                uow.commit()
                return False
            if (
                active["application_instance_id"] != self.application_instance_id
                or active["project_id"] != project_id
            ):
                raise ActiveSessionConflict("The active period belongs to another context")
            self._stop_row(uow, dict(active), now, reason)
            uow.commit()
            return True

    def play(self, project_id: str) -> str:
        now = self._now()
        with UnitOfWork(self._engine) as uow:
            active = (
                uow.execute(select(work_session).where(work_session.c.stopped_at_utc.is_(None)))
                .mappings()
                .one_or_none()
            )
            if active:
                if (
                    active["application_instance_id"] == self.application_instance_id
                    and active["project_id"] == project_id
                ):
                    uow.commit()
                    return active["id"]
                raise ActiveSessionConflict("Another context already has an active period")
            identifier = self._insert_active(uow, project_id, now)
            uow.commit()
            return identifier

    def close_application(self) -> bool:
        now = self._now()
        with UnitOfWork(self._engine) as uow:
            active = (
                uow.execute(
                    select(work_session).where(
                        work_session.c.stopped_at_utc.is_(None),
                        work_session.c.application_instance_id == self.application_instance_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if active is None:
                uow.commit()
                return False
            self._stop_row(uow, dict(active), now, "APPLICATION_CLOSE")
            uow.commit()
            return True

    def summary(self, project_id: str) -> TimeSummary:
        now = self._now()
        today = now.astimezone(self._zone).date().isoformat()
        total = 0
        today_total = 0
        running = False
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(work_session).where(work_session.c.project_id == project_id)
            ).mappings()
            for row in rows:
                intervals = list(row["intervals_json"] or [])
                if row["stopped_at_utc"] is None:
                    running = row["application_instance_id"] == self.application_instance_id
                    intervals = _split_interval(
                        datetime.fromisoformat(intervals[0]["start_utc"]), now, self._zone
                    )
                for interval in intervals:
                    duration = _seconds(interval)
                    total += duration
                    if interval["local_date"] == today:
                        today_total += duration
        return TimeSummary(today_total, total, running)

    def daily_totals(self, project_id: str) -> dict[date, int]:
        now = self._now()
        totals: dict[date, int] = {}
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(work_session).where(work_session.c.project_id == project_id)
            ).mappings()
            for row in rows:
                intervals = list(row["intervals_json"] or [])
                if row["stopped_at_utc"] is None:
                    intervals = _split_interval(
                        datetime.fromisoformat(intervals[0]["start_utc"]), now, self._zone
                    )
                for interval in intervals:
                    day = date.fromisoformat(interval["local_date"])
                    totals[day] = totals.get(day, 0) + _seconds(interval)
        return totals

    def _insert_active(self, uow: UnitOfWork, project_id: str, now: datetime) -> str:
        identifier = new_id()
        try:
            uow.execute(
                work_session.insert().values(
                    id=identifier,
                    project_id=project_id,
                    application_instance_id=self.application_instance_id,
                    started_at_utc=now,
                    stopped_at_utc=None,
                    intervals_json=[
                        {
                            "start_utc": now.isoformat(),
                            "end_utc": None,
                            "local_date": now.astimezone(self._zone).date().isoformat(),
                        }
                    ],
                    updated_at_utc=now,
                )
            )
        except IntegrityError as exc:
            raise ActiveSessionConflict("Only one active work period is allowed") from exc
        return identifier

    def _stop_row(self, uow: UnitOfWork, row: dict, now: datetime, reason: str) -> None:
        start = datetime.fromisoformat(row["intervals_json"][0]["start_utc"])
        intervals = _split_interval(start, now, self._zone)
        uow.execute(
            update(work_session)
            .where(work_session.c.id == row["id"])
            .values(
                stopped_at_utc=now,
                intervals_json=intervals,
                close_reason=reason,
                updated_at_utc=now,
                row_version=work_session.c.row_version + 1,
            )
        )
