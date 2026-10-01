from __future__ import annotations

from sqlalchemy import create_engine, text

from nl_project_2.persistence.migration import (
    HEAD_REVISION,
    current_revision_read_only,
    initialize_database,
    upgrade_database,
)


def test_upgrade_0002_to_catalog_contract_creates_verified_backup(tmp_path):
    path = tmp_path / "previous.sqlite"
    initialize_database(path, target="000000000002")
    receipt = upgrade_database(path, tmp_path / "backups")
    assert receipt.source_revision == "000000000002"
    assert receipt.path.is_file()
    assert len(receipt.sha256) == 64
    assert current_revision_read_only(path) == HEAD_REVISION
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    try:
        with engine.begin() as connection:
            connection.execute(text("PRAGMA foreign_keys=ON"))
            connection.execute(
                text(
                    "INSERT INTO catalog_release "
                    "(id,release_code,schema_version,content_sha256,installed_at_utc,status) "
                    "VALUES ('00000000-0000-4000-8000-000000000001','test',1,"
                    "'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',CURRENT_TIMESTAMP,'ACTIVE')"
                )
            )
    finally:
        engine.dispose()
