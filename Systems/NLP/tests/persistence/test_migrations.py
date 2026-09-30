from __future__ import annotations

import sqlite3

import pytest

from nl_project_2.persistence.database import (
    DatabaseManager,
    IncompatibleSchemaError,
    NewerSchemaError,
    SchemaUpgradeRequiredError,
    UninitializedSchemaError,
)
from nl_project_2.persistence.migration import (
    DALI_GROUP_REVISION,
    FOUNDATION_REVISION,
    HEAD_REVISION,
    TOPOLOGY_AUTOCAD_CONTRACT_REVISION,
    current_revision_read_only,
    initialize_database,
    upgrade_database,
)
from nl_project_2.persistence.schema import FOUNDATION_TABLE_NAMES, HEAD_TABLE_NAMES


def table_names(path) -> set[str]:
    with sqlite3.connect(path) as connection:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }


def test_two_sequential_revisions_and_verified_backup(tmp_path) -> None:
    database = tmp_path / "project.sqlite"
    backup_directory = tmp_path / "backup"

    assert initialize_database(database, target=FOUNDATION_REVISION) == FOUNDATION_REVISION
    assert table_names(database) == set(FOUNDATION_TABLE_NAMES) | {"alembic_version"}

    receipt = upgrade_database(database, backup_directory)

    assert receipt.path.is_file()
    assert len(receipt.sha256) == 64
    assert receipt.source_revision == FOUNDATION_REVISION
    assert current_revision_read_only(receipt.path) == FOUNDATION_REVISION
    assert current_revision_read_only(database) == HEAD_REVISION
    assert table_names(database) == set(HEAD_TABLE_NAMES) | {"alembic_version"}


def test_clean_creation_close_and_reopen(tmp_path) -> None:
    path = tmp_path / "project.sqlite"
    manager = DatabaseManager()
    first = manager.initialize_new(path)
    assert first.revision == HEAD_REVISION
    first.close()
    assert first.is_closed

    second = manager.open_existing(path)
    with second.engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
    second.close()
    assert second.is_closed


def test_open_requires_explicit_upgrade(tmp_path) -> None:
    path = tmp_path / "old.sqlite"
    initialize_database(path, target=FOUNDATION_REVISION)
    with pytest.raises(SchemaUpgradeRequiredError):
        DatabaseManager().open_existing(path)
    assert current_revision_read_only(path) == FOUNDATION_REVISION


@pytest.mark.parametrize(
    ("revision", "expected_error"),
    [
        ("999999999999", NewerSchemaError),
        ("not-a-known-revision", IncompatibleSchemaError),
    ],
)
def test_incompatible_revision_is_rejected(tmp_path, revision, expected_error) -> None:
    path = tmp_path / "project.sqlite"
    handle = DatabaseManager().initialize_new(path)
    handle.close()
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE alembic_version SET version_num = ?", (revision,))
    with pytest.raises(expected_error):
        DatabaseManager().open_existing(path)


def test_uninitialized_file_is_not_repaired(tmp_path) -> None:
    path = tmp_path / "unmanaged.sqlite"
    path.touch()
    with pytest.raises(UninitializedSchemaError):
        DatabaseManager().open_existing(path)
    assert path.stat().st_size == 0


def test_upgrade_from_real_pre_conduit_contract_shape_adds_columns_and_index(tmp_path) -> None:
    path = tmp_path / "pre-conduit-contract.sqlite"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL);
            INSERT INTO alembic_version(version_num) VALUES ('000000000005');
            CREATE TABLE conduit (
                id VARCHAR(36) PRIMARY KEY,
                project_id VARCHAR(36) NOT NULL,
                designation VARCHAR(120) NOT NULL,
                conduit_type VARCHAR(64) NOT NULL,
                diameter_mm_decimal TEXT,
                length_m_decimal TEXT,
                path_json JSON,
                location_json JSON,
                supply_scope VARCHAR(20),
                lifecycle VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
                created_at_utc DATETIME,
                updated_at_utc DATETIME,
                row_version INTEGER NOT NULL DEFAULT 1,
                UNIQUE(project_id, designation)
            );
            """
        )
    receipt = upgrade_database(path, tmp_path / "backup")
    assert receipt.source_revision == DALI_GROUP_REVISION
    assert current_revision_read_only(path) == HEAD_REVISION
    with sqlite3.connect(path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(conduit)")}
        indexes = {row[1] for row in connection.execute("PRAGMA index_list(conduit)")}
    assert {"conduit_number", "color", "product_definition_id"} <= columns
    assert "uq_conduit_project_number" in indexes

def test_upgrade_from_topology_contract_allows_timber_mount_way(tmp_path) -> None:
    path = tmp_path / "pre-timber.sqlite"
    backup_directory = tmp_path / "backup"

    assert (
        initialize_database(path, target=TOPOLOGY_AUTOCAD_CONTRACT_REVISION)
        == TOPOLOGY_AUTOCAD_CONTRACT_REVISION
    )
    receipt = upgrade_database(path, backup_directory)

    assert receipt.source_revision == TOPOLOGY_AUTOCAD_CONTRACT_REVISION
    assert current_revision_read_only(path) == HEAD_REVISION
    with sqlite3.connect(path) as connection:
        cable_segment_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='cable_segment'"
        ).fetchone()[0]
    assert "В брусе" in cable_segment_sql

