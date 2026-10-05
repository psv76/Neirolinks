from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from dataclasses import replace

import pytest
from sqlalchemy import func, select, update

from nl_project_2.catalog.equipment import EquipmentService
from nl_project_2.catalog.installer import CatalogInstaller
from nl_project_2.catalog.payload import CatalogPayload, load_payload
from nl_project_2.catalog.queries import CatalogQueries, ImmutableCatalogEditor
from nl_project_2.catalog.validation import CatalogValidationError, validate_payload
from nl_project_2.constructor import BlockingViolation
from nl_project_2.distribution import DistributionService
from nl_project_2.objects.models import ProjectCard
from nl_project_2.objects.service import ObjectService
from nl_project_2.persistence.schema import (
    catalog_release,
    instance_resource,
    passport_definition,
    passport_resource_definition,
    product_definition,
)


def _legacy_psu_branching_payload(catalog_dir) -> CatalogPayload:
    current = load_payload(catalog_dir)
    passports = copy.deepcopy(current.passports)
    for passport in passports["passports"]:
        if passport["id"] not in {"power.acdc.24v.din", "power.acdc.48v.din"}:
            continue
        passport["version"] = 1
        for resource in passport["resources"]:
            if resource["resource_id"] in {"DC24_OUTPUT", "DC48_OUTPUT"}:
                resource["branching"] = "ONLY_THROUGH_DISTRIBUTION_NODE"
    raw_passports = json.dumps(
        passports, ensure_ascii=False, indent=2, separators=(",", ": ")
    ).encode("utf-8")
    manifest = copy.deepcopy(current.manifest)
    manifest["release_code"] = "nlp2.mvp.equipment.legacy-psu-branching"
    manifest["files"]["equipment_passports.json"] = hashlib.sha256(raw_passports).hexdigest()
    raw_files = {
        "equipment_passports.json": raw_passports,
        "products.json": current.raw_files["products.json"],
    }
    content = hashlib.sha256(
        raw_files["equipment_passports.json"] + b"\0" + raw_files["products.json"]
    ).hexdigest()
    manifest["content_sha256"] = content
    return CatalogPayload(manifest, passports, current.products, raw_files)


def test_canonical_payload_schema_hash_and_exact_coverage(catalog_dir):
    payload = load_payload(catalog_dir)
    validate_payload(payload)
    assert (
        payload.content_sha256 == "e92935b0742367ecb83c3204fc2a49f4a67ace09ffb68d6c988c82cbde91858f"
    )
    assert len(payload.passports["passports"]) == 19
    assert len(payload.products["products"]) == 32
    passports = {item["id"]: item for item in payload.passports["passports"]}
    assert (
        sum(
            resource["quantity"]
            for resource in passports["gateway.wirenboard.wb_dali3"]["resources"]
        )
        == 13
    )
    assert (
        sum(
            resource["quantity"]
            for resource in passports["module.wirenboard.wbe2_i_knx"]["resources"]
        )
        == 2
    )
    wb_mge = passports["gateway.wirenboard.wb_mge_v3"]
    rs485 = next(item for item in wb_mge["resources"] if item["resource_id"] == "RS485")
    assert rs485["quantity"] == 2
    assert rs485["labels"] == ["RS485-1", "RS485-2"]
    assert not (
        {"vendor alpha", "vendor beta", "vendor gamma"}
        & {item["manufacturer"].casefold() for item in payload.products["products"]}
    )
    dkc = next(item for item in payload.products["products"] if item["id"] == "product.dkc.11525")
    assert dkc["article"] == "11525"
    assert (
        dkc["parameters_used_by_project"]
        | {
            "material_code": "PP",
            "nominal_diameter_mm": 25,
            "color": "BLUE",
        }
        == dkc["parameters_used_by_project"]
    )
    for passport_key, resource_key in (
        ("power.acdc.24v.din", "DC24_OUTPUT"),
        ("power.acdc.48v.din", "DC48_OUTPUT"),
    ):
        passport = passports[passport_key]
        resource = next(
            item for item in passport["resources"] if item["resource_id"] == resource_key
        )
        assert passport["version"] == 2
        assert resource["exclusive"] is False
        assert resource["branching"] == "ALLOWED"


def test_hash_failure_prevents_any_database_write(database, catalog_dir):
    payload = load_payload(catalog_dir)
    damaged = replace(payload, raw_files={**payload.raw_files, "products.json": b"{}"})
    with pytest.raises(CatalogValidationError):
        CatalogInstaller(database.engine).install(damaged)
    with database.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(catalog_release)) == 0


def test_unknown_branching_mode_is_rejected(catalog_dir):
    payload = load_payload(catalog_dir)
    passports = copy.deepcopy(payload.passports)
    passports["passports"][0]["resources"][0]["branching"] = "UNDECLARED_MODE"
    with pytest.raises(CatalogValidationError, match="BAD_BRANCHING"):
        validate_payload(replace(payload, passports=passports))


def test_install_is_atomic_immutable_idempotent_and_sqlite_queryable(
    database, catalog_dir, installed_catalog
):
    second = CatalogInstaller(database.engine).install(load_payload(catalog_dir))
    assert second.already_installed is True
    assert second.release_id == installed_catalog.release_id
    with database.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(catalog_release)) == 1
        assert connection.scalar(select(func.count()).select_from(passport_definition)) == 19
        assert connection.scalar(select(func.count()).select_from(product_definition)) == 32
        assert (
            connection.scalar(select(func.count()).select_from(passport_resource_definition)) > 14
        )
    queries = CatalogQueries(database.engine)
    assert len(queries.passports()) == 19
    assert len(queries.products()) == 32
    with pytest.raises(PermissionError, match="immutable"):
        ImmutableCatalogEditor().edit_published("anything")


def test_catalog_draft_cannot_bypass_hash_validation(catalog_dir):
    payload = load_payload(catalog_dir)
    draft = ImmutableCatalogEditor().begin_draft(payload)
    changed = dict(draft.products["products"][0])
    changed["name"] = "Unapproved edit"
    draft.replace_product(changed["id"], changed)
    with pytest.raises(CatalogValidationError, match="HASH_MISMATCH"):
        ImmutableCatalogEditor().validate_candidate(draft.candidate())


def test_explicit_reconciliation_upgrades_old_psu_snapshots_without_recreation(
    database, catalog_dir
):
    installer = CatalogInstaller(database.engine)
    legacy = installer.install(_legacy_psu_branching_payload(catalog_dir))
    project_id = ObjectService(database.engine).create_project(
        ProjectCard(name="Legacy PSU snapshot", project_code="LEGACY-PSU-SNAPSHOT")
    )
    instance = EquipmentService(database.engine).create_instance(
        project_id=project_id,
        designation="PSU-OLD",
        passport_key="power.acdc.24v.din",
        product_key="product.meanwell.hdr_60_24",
        supply_scope="NEIROLINKS",
    )
    equipment = EquipmentService(database.engine)
    consumers = [
        equipment.create_instance(
            project_id=project_id,
            designation=f"LOAD-OLD-{index}",
            passport_key="controller.wb_mr6c_v2",
            product_key="product.wirenboard.wb_mr6c_v2",
            supply_scope="NEIROLINKS",
        )
        for index in range(2)
    ]
    distribution = DistributionService(database.engine)
    resources = distribution.constructor.list_resources(project_id)
    output_id = next(
        row["id"]
        for row in resources
        if row["project_instance_id"] == instance.instance_id
        and row["resource_key"] == "DC24_OUTPUT"
    )
    target_ids = [
        next(
            row["id"]
            for row in resources
            if row["project_instance_id"] == consumer.instance_id
            and row["resource_key"] == "ELECTRONICS_POWER"
        )
        for consumer in consumers
    ]
    distribution.constructor.create_relation(
        project_id=project_id,
        relation_kind="POWER_FLOW",
        source_resource_id=output_id,
        target_resource_id=target_ids[0],
    )
    with pytest.raises(BlockingViolation, match="распределительный узел"):
        distribution.constructor.create_relation(
            project_id=project_id,
            relation_kind="POWER_FLOW",
            source_resource_id=output_id,
            target_resource_id=target_ids[1],
        )
    with database.engine.begin() as connection:
        output = (
            connection.execute(
                select(instance_resource).where(
                    instance_resource.c.project_instance_id == instance.instance_id,
                    instance_resource.c.resource_key == "DC24_OUTPUT",
                )
            )
            .mappings()
            .one()
        )
        stale_snapshot = dict(output["snapshot_json"])
        stale_snapshot["resource_definition"] = {"branching": "ONLY_THROUGH_DISTRIBUTION_NODE"}
        connection.execute(
            update(instance_resource)
            .where(instance_resource.c.id == output["id"])
            .values(snapshot_json=stale_snapshot)
        )
        original_resource_ids = tuple(
            connection.scalars(
                select(instance_resource.c.id)
                .where(instance_resource.c.project_instance_id == instance.instance_id)
                .order_by(instance_resource.c.id)
            )
        )

    receipt = installer.reconcile_active(load_payload(catalog_dir))
    assert receipt.release_id == legacy.release_id
    assert receipt.changed_passport_count == 2
    assert receipt.refreshed_resource_count == 2
    assert receipt.already_current is False
    with database.engine.connect() as connection:
        release = connection.execute(select(catalog_release)).mappings().one()
        assert release["release_code"] == load_payload(catalog_dir).manifest["release_code"]
        versions = {
            key: version
            for key, version in connection.execute(
                select(
                    passport_definition.c.passport_key,
                    passport_definition.c.version,
                ).where(
                    passport_definition.c.passport_key.in_(
                        ("power.acdc.24v.din", "power.acdc.48v.din")
                    )
                )
            )
        }
        assert versions == {"power.acdc.24v.din": 2, "power.acdc.48v.din": 2}
        restored = (
            connection.execute(
                select(
                    instance_resource.c.id,
                    instance_resource.c.snapshot_json,
                    passport_resource_definition.c.display_json,
                )
                .join(
                    passport_resource_definition,
                    passport_resource_definition.c.id
                    == instance_resource.c.passport_resource_definition_id,
                )
                .where(
                    instance_resource.c.project_instance_id == instance.instance_id,
                    instance_resource.c.resource_key == "DC24_OUTPUT",
                )
            )
            .mappings()
            .one()
        )
        current_resource_ids = tuple(
            connection.scalars(
                select(instance_resource.c.id)
                .where(instance_resource.c.project_instance_id == instance.instance_id)
                .order_by(instance_resource.c.id)
            )
        )
    assert current_resource_ids == original_resource_ids
    assert restored["display_json"]["branching"] == "ALLOWED"
    assert restored["snapshot_json"]["passport_resource"]["branching"] == "ALLOWED"
    assert "branching" not in restored["snapshot_json"]["resource_definition"]
    distribution.constructor.create_relation(
        project_id=project_id,
        relation_kind="POWER_FLOW",
        source_resource_id=output_id,
        target_resource_id=target_ids[1],
    )
    assert (
        len(
            [
                row
                for row in distribution.constructor.list_relations(project_id)
                if row["source_resource_id"] == output_id
            ]
        )
        == 2
    )
    assert installer.reconcile_active(load_payload(catalog_dir)).already_current is True

    database_path = database.path
    database.close()
    maintenance_path = catalog_dir.parents[1] / "tools" / "reconcile_equipment_catalog.py"
    spec = importlib.util.spec_from_file_location("catalog_maintenance", maintenance_path)
    assert spec is not None and spec.loader is not None
    maintenance = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(maintenance)
    expected_database_sha256 = hashlib.sha256(database_path.read_bytes()).hexdigest()
    backup_path = database_path.with_name("catalog-reconciliation.backup.sqlite")
    result = maintenance.reconcile_database(
        database_path=database_path,
        catalog_directory=catalog_dir,
        backup_path=backup_path,
        expected_database_sha256=expected_database_sha256,
    )
    assert result["already_current"] is True
    assert result["backup_sha256"] == expected_database_sha256
    assert result["sqlite_integrity"] == "ok"
    assert result["foreign_key_errors"] == 0
