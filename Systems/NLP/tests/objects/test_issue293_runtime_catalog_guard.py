from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
from sqlalchemy import select, update

from nl_project_2.catalog.installer import CatalogInstaller
from nl_project_2.catalog.payload import CatalogPayload, load_payload
from nl_project_2.config import DEFAULT_DATABASE_NAME, PathConfig
from nl_project_2.objects.runtime import ApplicationRuntime
from nl_project_2.persistence.database import DatabaseManager
from nl_project_2.persistence.schema import catalog_release, passport_definition, product_definition


def _paths(root):
    return PathConfig(
        app_root=root / "app",
        backup_root=root / "backups",
        release_root=root / "releases",
        user_projects_root=root / "projects",
        local_state_root=root / "state",
    )


def _old_release(payload):
    passports = copy.deepcopy(payload.passports)
    products = copy.deepcopy(payload.products)
    predecessor = "nlp3.equipment.2026-10-27.wbe2-rs485-iso"
    additions = payload.manifest["additive_predecessors"][predecessor]
    added_passports = set(additions["passports"])
    added_products = set(additions["products"])
    passports["passports"] = [
        row for row in passports["passports"]
        if row["id"] not in added_passports
    ]
    products["products"] = [
        row for row in products["products"]
        if row["id"] not in added_products
    ]
    raw = {
        "equipment_passports.json": json.dumps(passports,ensure_ascii=False).encode("utf-8"),
        "products.json": json.dumps(products,ensure_ascii=False).encode("utf-8"),
    }
    manifest = copy.deepcopy(payload.manifest)
    manifest["release_code"] = predecessor
    manifest["expected_counts"] = {
        "passports": len(passports["passports"]),
        "products": len(products["products"]),
    }
    manifest["files"] = {k: hashlib.sha256(v).hexdigest() for k,v in raw.items()}
    manifest["content_sha256"] = hashlib.sha256(
        raw["equipment_passports.json"] + b"\0" + raw["products.json"]
    ).hexdigest()
    return CatalogPayload(manifest,passports,products,raw)


def test_existing_predecessor_does_not_auto_upgrade_on_application_start(tmp_path):
    paths = _paths(tmp_path)
    db_path = paths.user_projects_root / DEFAULT_DATABASE_NAME
    db_path.parent.mkdir(parents=True,exist_ok=True)
    catalog = Path(__file__).resolve().parents[2] / "resources/catalogs"
    payload = load_payload(catalog)
    handle = DatabaseManager().initialize_new(db_path)
    try:
        CatalogInstaller(handle.engine).install(_old_release(payload))
    finally:
        handle.close()
    runtime = ApplicationRuntime.open(paths)
    try:
        with runtime.database.engine.connect() as conn:
            release = conn.scalar(select(catalog_release.c.release_code))
            pc = conn.execute(select(passport_definition.c.id)).all()
            pd = conn.execute(select(product_definition.c.id)).all()
        assert release == "nlp3.equipment.2026-10-27.wbe2-rs485-iso"
        assert len(pc) == 20
        assert len(pd) == 33
    finally:
        runtime.close()


def test_new_database_receives_published_successor_on_initial_start(tmp_path):
    paths = _paths(tmp_path)
    runtime = ApplicationRuntime.open(paths)
    try:
        with runtime.database.engine.connect() as conn:
            release = conn.scalar(select(catalog_release.c.release_code))
            count = len(conn.execute(select(passport_definition.c.id)).all())
        assert release == "nlp3.equipment.2026-10-27.wb-optional-modem-shared-vout"
        assert count == 51
    finally:
        runtime.close()

def test_same_release_different_hash_is_rejected_on_reopen(tmp_path):
    paths = _paths(tmp_path)
    runtime = ApplicationRuntime.open(paths)
    db_path = runtime.database.path
    runtime.close()
    handle = DatabaseManager().open_existing(db_path)
    try:
        with handle.engine.begin() as conn:
            conn.execute(update(catalog_release).values(content_sha256="0" * 64))
    finally:
        handle.close()
    with pytest.raises(RuntimeError, match="different content hash"):
        ApplicationRuntime.open(paths)
