from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import replace

import pytest
from sqlalchemy import select

from nl_project_2.catalog.installer import CatalogInstallError, CatalogInstaller
from nl_project_2.catalog.payload import CatalogPayload, load_payload
from nl_project_2.constructor import ConstructorService
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    catalog_release, instance_resource, passport_definition, product_definition, project,
    project_instance,
)


NEW_PASSPORT = "module.wirenboard.wbe2_i_rs485_iso"
NEW_PRODUCT = "product.wirenboard.wbe2_i_rs485_iso"
PREDECESSOR = "nlp3.equipment.2026-10-05.wb-mge-v3"


def predecessor_payload(successor: CatalogPayload) -> CatalogPayload:
    passports = copy.deepcopy(successor.passports)
    products = copy.deepcopy(successor.products)
    passports["passports"] = [p for p in passports["passports"] if p["id"] != NEW_PASSPORT]
    products["products"] = [p for p in products["products"] if p["id"] != NEW_PRODUCT]
    raw = {
        "equipment_passports.json": json.dumps(passports, ensure_ascii=False).encode("utf8"),
        "products.json": json.dumps(products, ensure_ascii=False).encode("utf8"),
    }
    manifest = copy.deepcopy(successor.manifest)
    manifest["release_code"] = PREDECESSOR
    manifest["expected_counts"] = {"passports": 19, "products": 32}
    manifest["files"] = {name: hashlib.sha256(data).hexdigest() for name, data in raw.items()}
    manifest["content_sha256"] = hashlib.sha256(
        raw["equipment_passports.json"] + b"\0" + raw["products.json"]
    ).hexdigest()
    return CatalogPayload(manifest, passports, products, raw)


def test_real_additive_successor_keeps_existing_instance_resources_and_release_id(database, catalog_dir):
    successor = load_payload(catalog_dir)
    installer = CatalogInstaller(database.engine)
    old = installer.install(predecessor_payload(successor))
    pid = new_id()
    with database.engine.begin() as conn:
        conn.execute(project.insert().values(
            id=pid, project_code="ISSUE293", name="Issue 293 successor",
            card_fields_json={}, active_catalog_release_id=old.release_id, lifecycle="ACTIVE",
        ))
    ctor = ConstructorService(database.engine)
    controller = ctor.create_instance(
        project_id=pid, designation="WB85",
        passport_key="controller.wiren_board_8_5",
        product_key="product.wirenboard.wb8_4g_64g_ind",
        supply_scope="NEIROLINKS",
    )
    with database.engine.connect() as conn:
        before_passports = dict(conn.execute(
            select(passport_definition.c.passport_key, passport_definition.c.id)
        ).all())
        before_products = dict(conn.execute(
            select(product_definition.c.product_key, product_definition.c.id)
        ).all())
        resources = set(conn.execute(
            select(instance_resource.c.id).where(
                instance_resource.c.project_instance_id == controller.instance_id
            )
        ).scalars())
    installed = installer.install(successor)
    assert installed.release_id == old.release_id
    assert not installed.already_installed
    assert installer.install(successor).already_installed
    with database.engine.connect() as conn:
        after_passports = dict(conn.execute(
            select(passport_definition.c.passport_key, passport_definition.c.id)
        ).all())
        after_products = dict(conn.execute(
            select(product_definition.c.product_key, product_definition.c.id)
        ).all())
        assert all(after_passports[k] == v for k, v in before_passports.items())
        assert all(after_products[k] == v for k, v in before_products.items())
        assert len(after_passports) == 20
        assert len(after_products) == 33
        assert set(conn.execute(
            select(instance_resource.c.id).where(
                instance_resource.c.project_instance_id == controller.instance_id
            )
        ).scalars()) == resources
        assert conn.scalar(select(catalog_release.c.release_code)) == successor.manifest["release_code"]
    assert any(
        row["passport_key"] == NEW_PASSPORT
        for row in ctor.list_available_passports(pid)
    )


def test_additive_successor_denies_undeclared_passport_addition(database, catalog_dir):
    successor = load_payload(catalog_dir)
    installer = CatalogInstaller(database.engine)
    installer.install(predecessor_payload(successor))
    denied_manifest = copy.deepcopy(successor.manifest)
    denied_manifest["additive_predecessors"][PREDECESSOR] = {
        "passports": [], "products": [NEW_PRODUCT]
    }
    with pytest.raises(CatalogInstallError, match="undeclared passport changes"):
        installer.install(replace(successor, manifest=denied_manifest))
