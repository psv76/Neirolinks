from __future__ import annotations

import sqlite3

from nl_project_2.persistence.migration import (
    HEAD_REVISION,
    WORK_SESSION_REVISION,
    current_revision_read_only,
    initialize_database,
    upgrade_database,
)


def test_dali_group_revision_upgrades_with_verified_backup(tmp_path):
    path = tmp_path / "before-dali-groups.sqlite"
    assert initialize_database(path, target=WORK_SESSION_REVISION) == WORK_SESSION_REVISION
    with sqlite3.connect(path) as connection:
        before = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "dali_group" not in before
    assert "dali_group_member" not in before

    receipt = upgrade_database(path, tmp_path / "backups")
    assert receipt.source_revision == WORK_SESSION_REVISION
    assert current_revision_read_only(receipt.path) == WORK_SESSION_REVISION
    assert current_revision_read_only(path) == HEAD_REVISION
    with sqlite3.connect(path) as connection:
        after = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {"dali_group", "dali_group_member"} <= after
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
