from __future__ import annotations

from nl_project_2.persistence.migration import (
    HEAD_REVISION,
    KEYS_FIELD_BUS_REVISION,
    current_revision_read_only,
    initialize_database,
    upgrade_database,
)
from nl_project_2.persistence.schema import bulk_operation_receipt


def test_upgrade_from_immediate_predecessor_adds_bulk_receipt(tmp_path) -> None:
    path = tmp_path / "revision-8.sqlite"
    initialize_database(path, target=KEYS_FIELD_BUS_REVISION)
    assert current_revision_read_only(path) == KEYS_FIELD_BUS_REVISION
    receipt = upgrade_database(path, tmp_path / "backup")
    assert receipt.source_revision == KEYS_FIELD_BUS_REVISION
    assert current_revision_read_only(path) == HEAD_REVISION

    from sqlalchemy import create_engine, inspect

    engine = create_engine(f"sqlite:///{path.as_posix()}")
    try:
        assert bulk_operation_receipt.name in inspect(engine).get_table_names()
    finally:
        engine.dispose()
