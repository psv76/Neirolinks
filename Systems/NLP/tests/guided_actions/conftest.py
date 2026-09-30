from __future__ import annotations

import pytest

from nl_project_2.catalog.installer import CatalogInstaller
from nl_project_2.catalog.payload import load_packaged_payload
from nl_project_2.persistence.database import DatabaseManager
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import project


@pytest.fixture
def database(tmp_path):
    handle = DatabaseManager().initialize_new(tmp_path / "guided-actions.sqlite")
    release = CatalogInstaller(handle.engine).install(load_packaged_payload())
    project_id = new_id()
    with handle.engine.begin() as connection:
        connection.execute(
            project.insert().values(
                id=project_id,
                project_code="P1-001",
                name="Guided actions",
                card_fields_json={},
                active_catalog_release_id=release.release_id,
                lifecycle="ACTIVE",
            )
        )
    handle.test_project_id = project_id
    try:
        yield handle
    finally:
        if not handle.is_closed:
            handle.close()

