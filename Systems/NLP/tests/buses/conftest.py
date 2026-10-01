from __future__ import annotations

from pathlib import Path

import pytest

from nl_project_2.catalog.installer import CatalogInstaller
from nl_project_2.catalog.payload import load_payload
from nl_project_2.persistence.database import DatabaseManager
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import project


@pytest.fixture
def database(tmp_path):
    handle = DatabaseManager().initialize_new(tmp_path / "buses.sqlite")
    catalog_dir = Path(__file__).resolve().parents[2] / "resources" / "catalogs"
    release = CatalogInstaller(handle.engine).install(load_payload(catalog_dir))
    project_id = new_id()
    with handle.engine.begin() as connection:
        connection.execute(
            project.insert().values(
                id=project_id,
                project_code="BUS-TEST",
                name="Bus test",
                card_fields_json={},
                active_catalog_release_id=release.release_id,
                lifecycle="ACTIVE",
            )
        )
    handle.test_project_id = project_id
    try:
        yield handle
    finally:
        handle.close()
