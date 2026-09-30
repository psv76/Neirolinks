from __future__ import annotations

from collections.abc import Iterator

import pytest

from nl_project_2.catalog.installer import CatalogInstaller
from nl_project_2.catalog.payload import load_packaged_payload
from nl_project_2.persistence.database import DatabaseHandle, DatabaseManager


@pytest.fixture
def database(tmp_path) -> Iterator[DatabaseHandle]:
    handle = DatabaseManager().initialize_new(tmp_path / "cables.sqlite")
    CatalogInstaller(handle.engine).install(load_packaged_payload())
    try:
        yield handle
    finally:
        handle.close()
