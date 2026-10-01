from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select

from nl_project_2.field_model.service import FieldModelError, TopologyPersistenceService
from nl_project_2.persistence.database import DatabaseManager
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    cable_length_fact,
    cable_line,
    catalog_release,
    field_device,
    field_device_product_selection,
    passport_definition,
    product_definition,
)
from nl_project_2.specification import SpecificationService


def _device(database, kind: str, handle: str) -> str:
    identifier = new_id()
    with database.engine.begin() as connection:
        connection.execute(
            field_device.insert().values(
                id=identifier,
                project_id=database.test_project_id,
                block_kind=kind,
                normalized_fields_json={"DEVICE_TYPE": kind},
                entity_handle=handle,
                lifecycle="ACTIVE",
            )
        )
    return identifier


def _test_msw_product(database) -> str:
    with database.engine.connect() as connection:
        release_id = connection.scalar(
            select(catalog_release.c.id).where(catalog_release.c.status == "ACTIVE")
        )
        passport_id = connection.scalar(
            select(passport_definition.c.id)
            .where(passport_definition.c.catalog_release_id == release_id)
            .limit(1)
        )
    identifier = new_id()
    schema = {
        "field_configuration_schema": {
            "schema_version": 4,
            "field_block_kinds": ["SENSOR_MSW"],
            "options": [
                {
                    "key": "motion",
                    "label": "Движение",
                    "required": True,
                    "values": [
                        {"id": "present", "label": "Есть"},
                        {"id": "absent", "label": "Нет"},
                    ],
                },
                {
                    "key": "body_color",
                    "label": "Цвет корпуса",
                    "required": True,
                    "values": [
                        {"id": "white", "label": "Белый"},
                        {"id": "black", "label": "Чёрный"},
                    ],
                },
            ],
        }
    }
    with database.engine.begin() as connection:
        connection.execute(
            product_definition.insert().values(
                id=identifier,
                catalog_release_id=release_id,
                passport_definition_id=passport_id,
                product_key="test.wb_msw.v4",
                version=4,
                manufacturer="Test evidence fixture",
                normalized_manufacturer="test evidence fixture",
                model="MSW test fixture",
                article="TEST-MSW-4",
                normalized_article="test-msw-4",
                name="WB-MSW test-only product",
                project_parameters_json=schema,
                evidence_json={"source": "isolated automated test fixture"},
                lifecycle="ACTIVE",
            )
        )
    return identifier


def test_physical_devices_mounting_boxes_el_box_and_no_points_heuristic(database):
    sensor_msw_id = None
    for index, kind in enumerate(
        ("SOCKET", "SWITCH", "BUTTON", "SENSOR_MSW", "CONTROL_PANEL"), start=1
    ):
        identifier = _device(database, kind, f"H{index}")
        if kind == "SENSOR_MSW":
            sensor_msw_id = identifier
    _device(database, "FRAME", "F1")
    _device(database, "EL_BOX", "E1")
    _device(database, "EL_BOX", "E2")
    _device(database, "NETWORK_DEVICE", "N1")

    result = SpecificationService(database.engine).build(database.test_project_id)
    mounting = next(row for row in result["rows"] if row.item_key.startswith("MOUNTING_BOX"))
    el_box = next(row for row in result["rows"] if row.item_key == "FIELD_DEMAND:EL_BOX:UNSELECTED")
    frame = next(row for row in result["rows"] if row.item_key == "FIELD_DEMAND:FRAME:UNSELECTED")

    assert mounting.quantity == Decimal("5")
    assert mounting.article is None and mounting.unit_price is None
    assert len(mounting.source_refs) == 5
    assert el_box.quantity == Decimal("2")
    assert frame.quantity == Decimal("1")
    assert all(ref[0] != "MOUNTING_BOX_DEMAND" for ref in frame.source_refs)
    assert any(issue.code == "MOUNTING_BOX_CATALOG_DATA_REQUIRED" for issue in result["issues"])
    assert all(issue.status == "DATA_REQUIRED" for issue in result["issues"])
    capability = TopologyPersistenceService(database.engine).field_device_configuration_capability(
        project_id=database.test_project_id,
        field_device_id=sensor_msw_id,
    )
    assert capability["status"] == "CATALOG/PASSPORT_GAP"
    reopened = DatabaseManager().open_existing(database.path)
    try:
        reopened_mounting = next(
            row
            for row in SpecificationService(reopened.engine).build(database.test_project_id)["rows"]
            if row.item_key.startswith("MOUNTING_BOX")
        )
        assert reopened_mounting.quantity == Decimal("5")
    finally:
        reopened.close()


def test_shared_socket_mechanisms_and_m1w2_count_physical_insertions_once(database):
    socket_ids = [_device(database, "SOCKET", handle) for handle in ("S1", "S2", "S3")]
    sensor_ids = [_device(database, "SENSOR_M1W2", handle) for handle in ("W1", "W2")]
    _device(database, "FRAME", "F1")
    with database.engine.begin() as connection:
        connection.execute(
            field_device.update()
            .where(field_device.c.id.in_(socket_ids))
            .values(normalized_fields_json={"DEVICE_TYPE": "SOCKET", "CABLE_ID": "101.01"})
        )
        connection.execute(
            field_device.update()
            .where(field_device.c.id.in_(sensor_ids))
            .values(normalized_fields_json={"DEVICE_TYPE": "SENSOR_M1W2", "CABLE_ID": "901"})
        )
    rows = SpecificationService(database.engine).build(database.test_project_id)["rows"]
    sockets = next(row for row in rows if row.item_key == "FIELD_DEMAND:SOCKET:UNSELECTED")
    sensors = next(row for row in rows if row.item_key == "FIELD_DEMAND:SENSOR:UNSELECTED")
    mounting = next(row for row in rows if row.item_key.startswith("MOUNTING_BOX"))
    assert sockets.quantity == Decimal("3")
    assert sensors.quantity == Decimal("2")
    assert mounting.quantity == Decimal("3")
    assert sockets.source_refs == tuple(sorted(sockets.source_refs))


def test_ordinary_unselected_cable_preserves_effective_demand_without_fake_product(database):
    line_id = new_id()
    with database.engine.begin() as connection:
        connection.execute(
            cable_line.insert().values(
                id=line_id,
                project_id=database.test_project_id,
                designation="101",
                system_kind="POWER",
                cable_facts_json={"LOAD_TYPE": "SOCKET", "CABLE_TYPE": "3x2.5"},
                lifecycle="ACTIVE",
            )
        )
        connection.execute(
            cable_length_fact.insert().values(
                id=new_id(),
                project_id=database.test_project_id,
                cable_line_id=line_id,
                calculated_length_m_decimal="12",
                additional_length_m_decimal="3",
                rounding_policy="NONE",
                knowledge_status="KNOWN",
            )
        )
    row = next(
        row
        for row in SpecificationService(database.engine).build(database.test_project_id)["rows"]
        if row.source_refs == (("CABLE_LINE", line_id),)
    )
    assert row.quantity == Decimal("15")
    assert row.article is None and row.unit_price is None
    assert "Нужны данные" in (row.note or "")


def test_catalog_driven_msw_configuration_grouping_reopen_and_stale_safety(database):
    first = _device(database, "SENSOR_MSW", "M1")
    second = _device(database, "SENSOR_MSW", "M2")
    different = _device(database, "SENSOR_MSW", "M3")
    incomplete = _device(database, "SENSOR_MSW", "M4")
    product_id = _test_msw_product(database)
    topology = TopologyPersistenceService(database.engine)

    capability = topology.field_device_configuration_capability(
        project_id=database.test_project_id, field_device_id=first
    )
    assert capability["status"] == "AVAILABLE"
    assert {item["product_definition_id"] for item in capability["products"]} == {product_id}
    with pytest.raises(FieldModelError):
        topology.select_catalog_field_device_configuration(
            project_id=database.test_project_id,
            field_device_id=first,
            product_definition_id=product_id,
            configuration={"motion": "arbitrary free text", "body_color": "white"},
            supply_scope="NEIROLINKS",
        )

    common = {"motion": "present", "body_color": "white"}
    for device_id in (first, second):
        topology.select_catalog_field_device_configuration(
            project_id=database.test_project_id,
            field_device_id=device_id,
            product_definition_id=product_id,
            configuration=common,
            supply_scope="NEIROLINKS",
        )
    topology.select_catalog_field_device_configuration(
        project_id=database.test_project_id,
        field_device_id=different,
        product_definition_id=product_id,
        configuration={"motion": "absent", "body_color": "black"},
        supply_scope="NEIROLINKS",
    )

    result = SpecificationService(database.engine).build(database.test_project_id)
    confirmed = [row for row in result["rows"] if row.item_key.startswith("PRODUCT:test.wb_msw")]
    assert sorted(row.quantity for row in confirmed) == [Decimal("1"), Decimal("2")]
    grouped = next(row for row in confirmed if row.quantity == 2)
    assert set(grouped.source_refs) == {("FIELD_DEVICE", first), ("FIELD_DEVICE", second)}
    assert any(
        row.item_key == "FIELD_DEMAND:SENSOR_MSW:UNSELECTED"
        and row.source_refs == (("FIELD_DEVICE", incomplete),)
        for row in result["rows"]
    )

    with database.engine.begin() as connection:
        connection.execute(
            field_device_product_selection.update()
            .where(field_device_product_selection.c.field_device_id == different)
            .values(configuration_schema_version=3)
        )
    reopened = SpecificationService(database.engine).build(database.test_project_id)
    stale = next(
        row
        for row in reopened["rows"]
        if ("FIELD_DEVICE", different) in row.source_refs
        and row.item_key == "FIELD_DEMAND:SENSOR_MSW:UNSELECTED"
    )
    assert stale.article is None
    with database.engine.connect() as connection:
        physical = connection.execute(
            select(field_device.c.block_kind, field_device.c.normalized_fields_json).where(
                field_device.c.id == different
            )
        ).one()
    assert physical.block_kind == "SENSOR_MSW"
    assert physical.normalized_fields_json["DEVICE_TYPE"] == "SENSOR_MSW"
