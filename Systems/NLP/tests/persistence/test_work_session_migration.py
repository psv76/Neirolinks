from __future__ import annotations

from sqlalchemy import create_engine, text

from nl_project_2.persistence.migration import (
    HEAD_REVISION,
    current_revision_read_only,
    initialize_database,
    upgrade_database,
)


def test_upgrade_0003_to_one_active_session_index_with_backup(tmp_path):
    path = tmp_path / "revision3.sqlite"
    initialize_database(path, target="000000000003")
    receipt = upgrade_database(path, tmp_path / "backup")
    assert receipt.source_revision == "000000000003"
    assert len(receipt.sha256) == 64
    assert current_revision_read_only(path) == HEAD_REVISION
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    try:
        with engine.connect() as connection:
            indexes = connection.execute(text("PRAGMA index_list('work_session')")).all()
            assert "uq_work_session_one_active" in {row[1] for row in indexes}
            assert connection.execute(text("PRAGMA integrity_check")).scalar_one() == "ok"
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
    finally:
        engine.dispose()
