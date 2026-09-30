from __future__ import annotations

import pytest
from sqlalchemy import func, select

from nl_project_2.catalog.equipment import (
    EquipmentError,
    EquipmentService,
    IncompatibleReplacementError,
)
from nl_project_2.catalog.payload import load_payload
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    functional_relation,
    instance_resource,
    product_selection_history,
    project_instance,
)


def _products_by_passport(payload):
    result = {}
    for product in payload.products["products"]:
        result.setdefault(product["passport_id"], []).append(product)
    return result


def _expected_count(passport, product):
    total = 0
    for resource in passport["resources"]:
        if resource["quantity"] == "PRODUCT_DEFINED":
            grouping = resource["grouping"]
            params = product["parameters_used_by_project"]
            total += int(params[grouping["bus_count_field"]]) * int(
                params[grouping["points_per_bus_field"]]
            )
        else:
            total += int(resource["quantity"])
    return total


def test_every_passport_materializes_declared_resources(database, project_id, catalog_dir):
    payload = load_payload(catalog_dir)
    products = _products_by_passport(payload)
    service = EquipmentService(database.engine)
    for index, passport in enumerate(payload.passports["passports"]):
        product = products[passport["id"]][0]
        receipt = service.create_instance(
            project_id=project_id,
            designation=f"E.{index + 1}",
            passport_key=passport["id"],
            product_key=product["id"],
            supply_scope="NEIROLINKS",
        )
        assert receipt.resource_count == _expected_count(passport, product)
        with database.engine.connect() as connection:
            rows = (
                connection.execute(
                    select(instance_resource).where(
                        instance_resource.c.project_instance_id == receipt.instance_id
                    )
                )
                .mappings()
                .all()
            )
        assert len(rows) == receipt.resource_count
        assert {row["resource_key"] for row in rows} == {
            resource["resource_id"] for resource in passport["resources"]
        }
        assert all(row["snapshot_json"]["passport_resource"] for row in rows)


def test_customer_supply_can_omit_product_but_other_scopes_cannot(database, project_id):
    service = EquipmentService(database.engine)
    receipt = service.create_instance(
        project_id=project_id,
        designation="QF.CUSTOMER",
        passport_key="protection.circuit_breaker.1p",
        product_key=None,
        supply_scope="CUSTOMER",
    )
    assert receipt.product_key is None
    assert receipt.resource_count == 2
    with pytest.raises(EquipmentError, match="only for CUSTOMER"):
        service.create_instance(
            project_id=project_id,
            designation="QF.BAD",
            passport_key="protection.circuit_breaker.1p",
            product_key=None,
            supply_scope="ASSEMBLY_WORKSHOP",
        )


def test_compatible_product_replacement_preserves_resource_ids_and_assignments(
    database, project_id
):
    service = EquipmentService(database.engine)
    cross = service.create_instance(
        project_id=project_id,
        designation="XT.01",
        passport_key="distribution.cross_module.3l_pen",
        product_key="product.iek.ynd10_4_11_125",
        supply_scope="NEIROLINKS",
    )
    breaker = service.create_instance(
        project_id=project_id,
        designation="QF.01",
        passport_key="protection.circuit_breaker.1p",
        product_key="product.schneider.a9f84116",
        supply_scope="NEIROLINKS",
    )
    with database.engine.begin() as connection:
        cross_resource = (
            connection.execute(
                select(instance_resource).where(
                    instance_resource.c.project_instance_id == cross.instance_id,
                    instance_resource.c.ordinal == 0,
                )
            )
            .mappings()
            .one()
        )
        breaker_resource = (
            connection.execute(
                select(instance_resource).where(
                    instance_resource.c.project_instance_id == breaker.instance_id
                )
            )
            .mappings()
            .first()
        )
        relation_id = new_id()
        connection.execute(
            functional_relation.insert().values(
                id=relation_id,
                project_id=project_id,
                relation_kind="TEST_ASSIGNMENT",
                source_resource_id=breaker_resource["id"],
                target_resource_id=cross_resource["id"],
                parameters_json={},
                command_id=new_id(),
            )
        )
    service.replace_product(
        project_id=project_id,
        instance_id=cross.instance_id,
        new_product_key="product.iek.ynd10_4_07_100",
        actor="pytest",
    )
    with database.engine.connect() as connection:
        kept = (
            connection.execute(
                select(instance_resource).where(
                    instance_resource.c.project_instance_id == cross.instance_id,
                    instance_resource.c.ordinal == 0,
                )
            )
            .mappings()
            .one()
        )
        relation = (
            connection.execute(
                select(functional_relation).where(functional_relation.c.id == relation_id)
            )
            .mappings()
            .one()
        )
        assert (
            connection.scalar(
                select(func.count())
                .select_from(instance_resource)
                .where(instance_resource.c.project_instance_id == cross.instance_id)
            )
            == 28
        )
        assert connection.scalar(select(func.count()).select_from(product_selection_history)) == 1
    assert kept["id"] == cross_resource["id"]
    assert relation["target_resource_id"] == kept["id"]


def test_incompatible_passport_replacement_is_blocked_with_assignments(database, project_id):
    service = EquipmentService(database.engine)
    first = service.create_instance(
        project_id=project_id,
        designation="QF.02",
        passport_key="protection.circuit_breaker.1p",
        product_key="product.schneider.a9f84116",
        supply_scope="NEIROLINKS",
    )
    second = service.create_instance(
        project_id=project_id,
        designation="PSU.01",
        passport_key="power.acdc.24v.din",
        product_key="product.meanwell.hdr_60_24",
        supply_scope="NEIROLINKS",
    )
    with database.engine.begin() as connection:
        a = (
            connection.execute(
                select(instance_resource.c.id).where(
                    instance_resource.c.project_instance_id == first.instance_id
                )
            )
            .scalars()
            .first()
        )
        b = (
            connection.execute(
                select(instance_resource.c.id).where(
                    instance_resource.c.project_instance_id == second.instance_id
                )
            )
            .scalars()
            .first()
        )
        connection.execute(
            functional_relation.insert().values(
                id=new_id(),
                project_id=project_id,
                relation_kind="TEST_ASSIGNMENT",
                source_resource_id=a,
                target_resource_id=b,
                parameters_json={},
                command_id=new_id(),
            )
        )
    with pytest.raises(IncompatibleReplacementError, match="assignments"):
        service.replace_passport(
            project_id=project_id,
            instance_id=first.instance_id,
            new_passport_key="power.acdc.24v.din",
        )
    with database.engine.connect() as connection:
        row = (
            connection.execute(
                select(project_instance).where(project_instance.c.id == first.instance_id)
            )
            .mappings()
            .one()
        )
    assert row["product_definition_id"] is not None


def test_cross_passport_replacement_succeeds_after_assignments_removed(database, project_id):
    service = EquipmentService(database.engine)
    original = service.create_instance(
        project_id=project_id,
        designation="QF.03",
        passport_key="protection.circuit_breaker.1p",
        product_key="product.schneider.a9f84116",
        supply_scope="NEIROLINKS",
    )
    receipt = service.replace_passport(
        project_id=project_id,
        instance_id=original.instance_id,
        new_passport_key="power.acdc.24v.din",
        new_product_key="product.meanwell.hdr_60_24",
        actor="pytest",
    )
    assert receipt.instance_id == original.instance_id
    assert receipt.resource_count == 2
    with database.engine.connect() as connection:
        rows = (
            connection.execute(
                select(instance_resource).where(
                    instance_resource.c.project_instance_id == original.instance_id
                )
            )
            .mappings()
            .all()
        )
    assert {row["resource_key"] for row in rows} == {"AC_INPUT", "DC24_OUTPUT"}
