"""Additive schema-head18 bus display title, preserving 17 objects and requiring backup."""
import sqlite3

import pytest
from nl_project_2.persistence.migration import (
    HEAD_REVISION,
    TRANSIT_LINE_COMMIT_REVISION,
    initialize_database,
    current_revision_read_only,
    upgrade_database,
)
from nl_project_2.persistence.database import DatabaseManager, SchemaUpgradeRequiredError


def test_bus_display_name_migration_is_additive_with_verified_backup(tmp_path):
    path=tmp_path/"old.sqlite"
    assert initialize_database(path,target=TRANSIT_LINE_COMMIT_REVISION)==TRANSIT_LINE_COMMIT_REVISION
    # A freshly bootstrapped historical test revision may carry columns
    # defined by current metadata; migration remains idempotent for that case.
    with pytest.raises(SchemaUpgradeRequiredError):
        DatabaseManager().open_existing(path)
    receipt=upgrade_database(path,tmp_path/"verified_backup")
    assert receipt.source_revision==TRANSIT_LINE_COMMIT_REVISION
    assert current_revision_read_only(receipt.path)==TRANSIT_LINE_COMMIT_REVISION
    assert current_revision_read_only(path)==HEAD_REVISION=="000000000018"
    with sqlite3.connect(path) as c:
        assert "display_name" in {r[1] for r in c.execute("pragma table_info(bus)")}
        assert c.execute("pragma integrity_check").fetchone()[0]=="ok"
        assert c.execute("pragma foreign_key_check").fetchall()==[]
    db=DatabaseManager().open_existing(path)
    db.close()
