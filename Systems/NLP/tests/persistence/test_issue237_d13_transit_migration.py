"""D13 isolated schema 15→16: verified backup and guarded evidence rollback."""

from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import func, select

from nl_project_2.persistence.database import DatabaseManager, SchemaUpgradeRequiredError
from nl_project_2.persistence.migration import (
    HEAD_REVISION,
    PHYSICAL_DALI_GRAPH_REVISION,
    TRANSIT_PHYSICAL_STAGING_REVISION,
    current_revision_read_only,
    downgrade_database,
    initialize_database,
    upgrade_database,
)
from nl_project_2.persistence.schema import (
    TRANSIT_PHYSICAL_TABLE_NAMES,
    cable_transit_route,
    cable_transit_span,
)


def _tables(path):
    with sqlite3.connect(path) as conn:
        return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_schema_15_to_16_requires_verified_backup_no_legacy_backfill(tmp_path):
    path = tmp_path / "version15.sqlite"
    backups = tmp_path / "backups"
    assert TRANSIT_PHYSICAL_STAGING_REVISION == "000000000016"
    assert initialize_database(path, target=PHYSICAL_DALI_GRAPH_REVISION) == "000000000015"
    old = _tables(path)
    assert not old.intersection(TRANSIT_PHYSICAL_TABLE_NAMES)
    with pytest.raises(SchemaUpgradeRequiredError):
        DatabaseManager().open_existing(path)
    receipt = upgrade_database(path, backups, target=TRANSIT_PHYSICAL_STAGING_REVISION)
    assert receipt.path.exists()
    assert len(receipt.sha256) == 64
    assert receipt.source_revision == "000000000015"
    assert current_revision_read_only(receipt.path) == "000000000015"
    assert current_revision_read_only(path) == TRANSIT_PHYSICAL_STAGING_REVISION
    assert _tables(path) == old | TRANSIT_PHYSICAL_TABLE_NAMES
    with pytest.raises(SchemaUpgradeRequiredError):
        DatabaseManager().open_existing(path)
    upgrade_database(path, backups, target=HEAD_REVISION)
    handle = DatabaseManager().open_existing(path)
    with handle.engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(cable_transit_route)) == 0
        assert conn.scalar(select(func.count()).select_from(cable_transit_span)) == 0
        assert conn.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        assert conn.exec_driver_sql("PRAGMA integrity_check").scalar_one() == "ok"
    handle.close()


def test_16_to_15_empty_downgrade_preserves_verified_backup(tmp_path):
    path = tmp_path / "fresh.sqlite"
    backup = tmp_path / "backups"
    assert initialize_database(path, target=TRANSIT_PHYSICAL_STAGING_REVISION) == "000000000016"
    receipt = downgrade_database(path, backup, target=PHYSICAL_DALI_GRAPH_REVISION)
    assert receipt.source_revision == TRANSIT_PHYSICAL_STAGING_REVISION
    assert current_revision_read_only(receipt.path) == TRANSIT_PHYSICAL_STAGING_REVISION
    assert current_revision_read_only(path) == PHYSICAL_DALI_GRAPH_REVISION
    assert not _tables(path).intersection(TRANSIT_PHYSICAL_TABLE_NAMES)
