"""D16 additive schema 16→17; verified backup, empty downgrade, no backfill."""

from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import func, select

from nl_project_2.persistence.database import DatabaseManager, SchemaUpgradeRequiredError
from nl_project_2.persistence.migration import (
    HEAD_REVISION,
    TRANSIT_LINE_COMMIT_REVISION,
    TRANSIT_PHYSICAL_STAGING_REVISION,
    current_revision_read_only,
    downgrade_database,
    initialize_database,
    upgrade_database,
)
from nl_project_2.persistence.schema import (
    TRANSIT_LINE_COMMIT_TABLE_NAMES,
    cable_transit_line_commit,
)


def _tables(path):
    with sqlite3.connect(path) as conn:
        return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_rev16_to_17_uses_verified_backup_no_legacy_backfill(tmp_path):
    dbfile = tmp_path / "before16.sqlite"
    backup_folder = tmp_path / "backup"
    assert TRANSIT_LINE_COMMIT_REVISION == "000000000017"
    assert initialize_database(dbfile, target=TRANSIT_PHYSICAL_STAGING_REVISION) == "000000000016"
    before = _tables(dbfile)
    assert not before.intersection(TRANSIT_LINE_COMMIT_TABLE_NAMES)
    with pytest.raises(SchemaUpgradeRequiredError):
        DatabaseManager().open_existing(dbfile)
    receipt = upgrade_database(dbfile, backup_folder, target=HEAD_REVISION)
    assert receipt.path.exists() and len(receipt.sha256) == 64
    assert receipt.source_revision == TRANSIT_PHYSICAL_STAGING_REVISION
    assert current_revision_read_only(receipt.path) == TRANSIT_PHYSICAL_STAGING_REVISION
    assert current_revision_read_only(dbfile) == HEAD_REVISION
    assert _tables(dbfile) == before | TRANSIT_LINE_COMMIT_TABLE_NAMES
    handle = DatabaseManager().open_existing(dbfile)
    with handle.engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(cable_transit_line_commit)) == 0
        assert conn.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        assert conn.exec_driver_sql("PRAGMA integrity_check").scalar_one() == "ok"
    handle.close()


def test_empty_rev17_downgrade_is_reversible_with_backup(tmp_path):
    dbfile = tmp_path / "fresh17.sqlite"
    back = tmp_path / "backups"
    db = DatabaseManager().initialize_new(dbfile)
    assert db.revision == HEAD_REVISION
    db.close()
    receipt = downgrade_database(dbfile, back, target=TRANSIT_PHYSICAL_STAGING_REVISION)
    assert receipt.source_revision == HEAD_REVISION
    assert current_revision_read_only(receipt.path) == HEAD_REVISION
    assert current_revision_read_only(dbfile) == TRANSIT_PHYSICAL_STAGING_REVISION
    assert not _tables(dbfile).intersection(TRANSIT_LINE_COMMIT_TABLE_NAMES)
