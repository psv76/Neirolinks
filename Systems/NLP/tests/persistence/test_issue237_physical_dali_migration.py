"""D7 schema revision 15: additive, backup-verified and no legacy guessing."""

from __future__ import annotations

import sqlite3

import pytest

from nl_project_2.persistence.database import (
    DatabaseManager,
    SchemaUpgradeRequiredError,
)
from nl_project_2.persistence.migration import (
    HEAD_REVISION,
    PHYSICAL_DALI_GRAPH_REVISION,
    SHARED_BOX_ENDPOINT_REVISION,
    current_revision_read_only,
    downgrade_database,
    initialize_database,
    upgrade_database,
)
from nl_project_2.persistence.schema import PHYSICAL_DALI_TABLE_NAMES


def _tables(path):
    with sqlite3.connect(path) as connection:
        return {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }


def test_explicit_14_to_15_requires_verified_backup_and_keeps_existing_schema(tmp_path):
    path = tmp_path / "original.sqlite"
    backup = tmp_path / "verified-backups"
    assert PHYSICAL_DALI_GRAPH_REVISION == "000000000015"
    assert initialize_database(path, target=SHARED_BOX_ENDPOINT_REVISION) == "000000000014"
    before = _tables(path)
    assert not (before & PHYSICAL_DALI_TABLE_NAMES)
    with pytest.raises(SchemaUpgradeRequiredError):
        DatabaseManager().open_existing(path)
    receipt = upgrade_database(path, backup, target=PHYSICAL_DALI_GRAPH_REVISION)
    assert receipt.source_revision == SHARED_BOX_ENDPOINT_REVISION
    assert receipt.path.is_file()
    assert len(receipt.sha256) == 64
    assert current_revision_read_only(receipt.path) == "000000000014"
    assert current_revision_read_only(path) == PHYSICAL_DALI_GRAPH_REVISION
    assert _tables(path) == before | PHYSICAL_DALI_TABLE_NAMES
    with pytest.raises(SchemaUpgradeRequiredError):
        DatabaseManager().open_existing(path)
    upgrade_database(path, backup, target=HEAD_REVISION)
    handle = DatabaseManager().open_existing(path)
    with handle.engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA integrity_check").scalar_one() == "ok"
        assert conn.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM bus_physical_node").scalar_one() == 0
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM bus_physical_link").scalar_one() == 0
    handle.close()


def test_clean_15_and_empty_downgrade_are_reversible_with_backup(tmp_path):
    path = tmp_path / "fresh.sqlite"
    backup = tmp_path / "backups"
    assert initialize_database(path, target=PHYSICAL_DALI_GRAPH_REVISION) == "000000000015"
    assert PHYSICAL_DALI_TABLE_NAMES <= _tables(path)
    receipt = downgrade_database(path, backup, target=SHARED_BOX_ENDPOINT_REVISION)
    assert receipt.source_revision == PHYSICAL_DALI_GRAPH_REVISION
    assert current_revision_read_only(receipt.path) == PHYSICAL_DALI_GRAPH_REVISION
    assert current_revision_read_only(path) == SHARED_BOX_ENDPOINT_REVISION
    assert not (_tables(path) & PHYSICAL_DALI_TABLE_NAMES)
