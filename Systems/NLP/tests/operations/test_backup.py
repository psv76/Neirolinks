from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from nl_project_2.operations import BackupError, BackupService
from nl_project_2.persistence.database import DatabaseManager
from nl_project_2.persistence.schema import project


def test_manual_pre_migration_restore_and_corruption_rejection(database, tmp_path):
    service = BackupService(tmp_path / "backups")
    manual = service.create_manual(database.path)
    pre_migration = service.create_pre_migration(database.path)
    assert manual.kind == "MANUAL" and manual.path.parent.name == "manual"
    assert pre_migration.kind == "PRE_MIGRATION"
    assert pre_migration.path.parent.name == "pre_migration"
    restored_path = tmp_path / "restore" / "restored.sqlite"
    receipt = service.restore_to(manual.path, restored_path)
    assert receipt.sha256 == hashlib.sha256(restored_path.read_bytes()).hexdigest()
    reopened = DatabaseManager().open_existing(restored_path)
    reopened.close()

    corrupt = tmp_path / "corrupt.sqlite"
    corrupt.write_bytes(manual.path.read_bytes()[:200])
    rejected_target = tmp_path / "restore" / "rejected.sqlite"
    with pytest.raises(BackupError):
        service.restore_to(corrupt, rejected_target)
    assert not rejected_target.exists()


def test_daily_runs_once_on_first_changed_close_day(database, tmp_path):
    now = datetime(2026, 8, 9, 10, tzinfo=UTC)
    service = BackupService(tmp_path / "backups", clock=lambda: now)
    opening = hashlib.sha256(database.path.read_bytes()).hexdigest()
    assert service.create_daily_if_changed(database.path, opening_sha256=opening) is None
    with database.engine.begin() as connection:
        connection.execute(
            update(project).where(project.c.id == database.test_project_id).values(name="Changed")
        )
    first = service.create_daily_if_changed(database.path, opening_sha256=opening)
    second = service.create_daily_if_changed(database.path, opening_sha256=opening)
    assert first.created is True
    assert second.created is False
    assert first.path == second.path


def test_retention_keeps_union_14_daily_8_weekly_12_monthly_and_never_manual(tmp_path):
    root = tmp_path / "backups"
    daily = root / "daily"
    manual = root / "manual"
    pre = root / "pre_migration"
    daily.mkdir(parents=True)
    manual.mkdir()
    pre.mkdir()
    start = datetime(2025, 1, 1, tzinfo=UTC)
    all_daily = []
    for day in range(430):
        stamp = (start + timedelta(days=day)).strftime("%Y%m%dT%H%M%S%fZ")
        path = daily / f"project.daily.{stamp}.aaaaaaaa.sqlite"
        path.write_bytes(b"daily")
        all_daily.append(path)
    manual_file = manual / "project.manual.20260101T000000000000Z.bbbbbbbb.sqlite"
    pre_file = pre / "project.pre_migration.20260101T000000000000Z.cccccccc.sqlite"
    manual_file.write_bytes(b"manual")
    pre_file.write_bytes(b"pre")

    result = BackupService(root).apply_retention("project")
    expected = set()
    ordered = [(path, start + timedelta(days=index)) for index, path in enumerate(all_daily)]
    expected.update(path for path, _ in ordered[-14:])
    for key, limit in (
        (lambda value: value.isocalendar()[:2], 8),
        (lambda value: (value.year, value.month), 12),
    ):
        buckets = {}
        for path, stamp in ordered:
            buckets[key(stamp)] = (path, stamp)
        expected.update(
            path for path, _ in sorted(buckets.values(), key=lambda pair: pair[1])[-limit:]
        )
    assert set(result.kept) == expected
    assert len(result.deleted) == len(all_daily) - len(expected)
    assert manual_file.exists() and pre_file.exists()
