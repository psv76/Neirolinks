from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from nl_project_2.automation import AutomationError, AutomationService
from nl_project_2.buses import BusError, BusService
from nl_project_2.catalog.equipment import EquipmentService
from nl_project_2.catalog.installer import CatalogInstaller
from nl_project_2.catalog.payload import load_packaged_payload
from nl_project_2.field_model import FieldModelError, TopologyPersistenceService
from nl_project_2.persistence.database import DatabaseManager
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.migration import (
    HEAD_REVISION,
    PERSISTENCE_TOPOLOGY_REVISION,
    current_revision_read_only,
    downgrade_database,
    initialize_database,
    upgrade_database,
)
from nl_project_2.persistence.schema import (
    bus_endpoint,
    cable_line,
    control_key_input_assignment,
    field_device,
    functional_relation,
    instance_resource,
    project,
)


@pytest.fixture
def p0005_database(tmp_path):
    handle = DatabaseManager().initialize_new(tmp_path / "p0005.sqlite")
    release = CatalogInstaller(handle.engine).install(load_packaged_payload())
    project_id = new_id()
    with handle.engine.begin() as connection:
        connection.execute(
            project.insert().values(
                id=project_id,
                project_code="P0-005",
                name="P0 005",
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


def _line(database, designation, system_kind="SWITCHES", facts=None):
    identifier = new_id()
    with database.engine.begin() as connection:
        connection.execute(
            cable_line.insert().values(
                id=identifier,
                project_id=database.test_project_id,
                designation=designation,
                system_kind=system_kind,
                cable_facts_json=facts or {},
            )
        )
    return identifier


def _field_device(database, *, cable_id, handle, block_kind="WB_MRM2_MINI"):
    identifier = new_id()
    with database.engine.begin() as connection:
        connection.execute(
            field_device.insert().values(
                id=identifier,
                project_id=database.test_project_id,
                block_kind=block_kind,
                normalized_fields_json={"CABLE_ID": cable_id},
                entity_handle=handle,
            )
        )
    return identifier


def _mcm8(database, designation="MCM8.1"):
    receipt = EquipmentService(database.engine).create_instance(
        project_id=database.test_project_id,
        designation=designation,
        passport_key="module.wirenboard.wb_mcm8",
        product_key="product.wirenboard.wb_mcm8",
        supply_scope="NEIROLINKS",
    )
    with database.engine.connect() as connection:
        resources = list(
            connection.execute(
                select(instance_resource).where(
                    instance_resource.c.project_instance_id == receipt.instance_id
                )
            ).mappings()
        )
    return receipt, resources


def test_packaged_catalog_exact_repair05_18_31_and_mcm8_materialization(p0005_database):
    root = Path(__file__).resolve().parents[2] / "docs" / "product" / "catalogs"
    payload = load_packaged_payload()
    assert len(payload.passports["passports"]) == 18
    assert len(payload.products["products"]) == 31
    assert payload.passports == json.loads(
        (root / "equipment_passports.json").read_text(encoding="utf-8-sig")
    )
    assert payload.products == json.loads(
        (root / "products.json").read_text(encoding="utf-8-sig")
    )

    receipt, resources = _mcm8(p0005_database)
    assert receipt.resource_count == 10
    kinds = [row["resource_kind"] for row in resources]
    assert kinds.count("DC_POWER_INPUT") == 1
    assert kinds.count("RS485_INTERFACE") == 1
    assert kinds.count("DRY_CONTACT_INPUT") == 8
    candidates = TopologyPersistenceService(
        p0005_database.engine
    ).list_control_input_candidates(p0005_database.test_project_id)
    assert [row["label"] for row in candidates] == [f"MCM8.1 / Input {n}" for n in range(1, 9)]


def test_key_level_assignment_reserve_exclusivity_unassign_and_reopen(p0005_database):
    project_id = p0005_database.test_project_id
    line = _line(p0005_database, "201", facts={"CABLE_STANDARD": "UTP_8"})
    device = _field_device(p0005_database, cable_id="201.01", handle="A1")
    _receipt, resources = _mcm8(p0005_database)
    inputs = sorted(
        (row for row in resources if row["resource_kind"] == "DRY_CONTACT_INPUT"),
        key=lambda row: row["ordinal"],
    )
    service = TopologyPersistenceService(p0005_database.engine)
    key1 = service.create_control_key(
        project_id=project_id,
        field_device_id=device,
        key_tag="KEY_1",
        target_kind="CABLE_LINE",
        target_id=line,
        target_text="Same target",
    )
    key2 = service.create_control_key(
        project_id=project_id,
        field_device_id=device,
        key_tag="KEY_2",
        target_kind="CABLE_LINE",
        target_id=line,
        target_text="Same target",
    )
    service.set_user_reserve(
        project_id=project_id,
        target_kind="INSTANCE_RESOURCE",
        target_id=inputs[1]["id"],
        actor="test",
    )
    assert inputs[1]["id"] not in {
        row["id"] for row in service.list_control_input_candidates(project_id)
    }
    service.assign_control_key_input(
        project_id=project_id,
        field_control_key_id=key1,
        input_resource_id=inputs[0]["id"],
    )
    with pytest.raises(FieldModelError, match="already assigned"):
        service.assign_control_key_input(
            project_id=project_id,
            field_control_key_id=key2,
            input_resource_id=inputs[0]["id"],
        )
    service.assign_control_key_input(
        project_id=project_id,
        field_control_key_id=key2,
        input_resource_id=inputs[2]["id"],
    )
    model = service.control_key_read_model(project_id)
    assert [row["status"] for row in model] == ["ASSIGNED", "ASSIGNED"]
    assert len({row["input_id"] for row in model}) == 2

    path = p0005_database.path
    p0005_database.close()
    reopened = DatabaseManager().open_existing(path)
    try:
        restored = TopologyPersistenceService(reopened.engine).control_key_read_model(project_id)
        assert {row["physical_identity"] for row in restored} == {"A1:KEY_1", "A1:KEY_2"}
        TopologyPersistenceService(reopened.engine).unassign_control_key_input(
            project_id=project_id, field_control_key_id=key1
        )
        with reopened.engine.connect() as connection:
            assert connection.scalar(
                select(func.count()).select_from(control_key_input_assignment)
            ) == 1
    finally:
        reopened.close()


def test_grouped_utp_numeric_order_and_distinct_shortages(p0005_database):
    project_id = p0005_database.test_project_id
    service = TopologyPersistenceService(p0005_database.engine)
    line = _line(p0005_database, "201", facts={"CABLE_STANDARD": "UTP_8"})
    devices = [
        _field_device(p0005_database, cable_id=cable_id, handle=handle)
        for cable_id, handle in (("201.03", "H3"), ("201.01", "H1"))
    ]
    for index, device in enumerate(devices):
        point = service.create_topology_point(
            project_id=project_id,
            cable_line_id=line,
            point_kind="DEVICE_POINT",
            logical_identity=f"P{index}",
        )
        service.add_field_device_to_point(
            project_id=project_id, cable_point_id=point, field_device_id=device
        )
    def add_key(device, key_number):
        service.create_control_key(
            project_id=project_id,
            field_device_id=device,
            key_tag=f"KEY_{key_number}",
            target_kind="CABLE_LINE",
            target_id=line,
            target_text="Target",
        )

    add_key(devices[0], 1)
    one_key = service.grouped_switch_capacity(
        project_id=project_id, cable_line_id=line, available_input_count=8
    )
    assert one_key["required_conductors"] == 2
    assert one_key["status"] == "VERIFIED"
    for key_number in range(2, 5):
        add_key(devices[0], key_number)
    for key_number in range(1, 4):
        add_key(devices[1], key_number)
    seven_keys = service.grouped_switch_capacity(
        project_id=project_id, cable_line_id=line, available_input_count=8
    )
    assert seven_keys["required_conductors"] == 8
    assert seven_keys["status"] == "VERIFIED"
    add_key(devices[1], 4)
    result = service.grouped_switch_capacity(
        project_id=project_id, cable_line_id=line, available_input_count=8
    )
    assert result["device_order"] == ("201.01", "201.03")
    assert result["required_conductors"] == 9
    assert result["reasons"] == ("CONDUCTOR_SHORTAGE",)
    input_shortage = service.grouped_switch_capacity(
        project_id=project_id, cable_line_id=line, available_input_count=7
    )
    assert set(input_shortage["reasons"]) == {"CONDUCTOR_SHORTAGE", "INPUT_SHORTAGE"}

    unknown = _line(p0005_database, "202", facts={"CABLE_TYPE": "mystery 12-wire"})
    unknown_result = service.grouped_switch_capacity(
        project_id=project_id, cable_line_id=unknown, available_input_count=99
    )
    assert unknown_result["status"] == "INCOMPLETE"
    assert unknown_result["available_conductors"] is None


def test_field_ports_independent_links_reopen_and_downgrade_guard(
    p0005_database, tmp_path
):
    project_id = p0005_database.test_project_id
    service = TopologyPersistenceService(p0005_database.engine)
    output_line = _line(p0005_database, "301", "RELAYS")
    target_line = _line(p0005_database, "201", "SWITCHES")
    mrm = _field_device(p0005_database, cable_id="901.01", handle="M1")
    sensor = _field_device(
        p0005_database, cable_id="501.01", handle="S1", block_kind="WB_M1W2"
    )
    ports = {
        name: service.create_field_port(
            project_id=project_id, field_device_id=device, port_tag=name
        )
        for device, name in (
            (mrm, "K1"),
            (mrm, "K2"),
            (mrm, "IN_1"),
            (mrm, "IN_2"),
            (sensor, "W1"),
            (sensor, "W2"),
        )
    }
    key = service.create_control_key(
        project_id=project_id,
        field_device_id=mrm,
        key_tag="KEY_1",
        target_kind="CABLE_LINE",
        target_id=target_line,
        target_text="Target",
    )
    service.assign_line_to_field_port(
        project_id=project_id,
        cable_line_id=output_line,
        field_port_id=ports["K1"],
        assignment_role="PHYSICAL_SOURCE",
    )
    service.assign_control_key_field_port(
        project_id=project_id, field_control_key_id=key, field_port_id=ports["IN_1"]
    )
    model = {row["port_tag"]: row for row in service.field_port_read_model(project_id)}
    assert model["K1"]["status"] == "LINKED"
    assert model["K2"]["status"] == "UNUSED"
    assert model["IN_1"]["linked_key_id"] == key
    assert model["W1"]["status"] == model["W2"]["status"] == "UNUSED"

    path = p0005_database.path
    p0005_database.close()
    reopened = DatabaseManager().open_existing(path)
    try:
        restored = TopologyPersistenceService(reopened.engine).field_port_read_model(project_id)
        assert len(restored) == 6
        assert next(row for row in restored if row["port_tag"] == "IN_1")["linked_key_id"] == key
    finally:
        reopened.close()
    with pytest.raises(RuntimeError, match="typed field facts"):
        downgrade_database(
            path,
            tmp_path / "typed-downgrade-backup",
            target=PERSISTENCE_TOPOLOGY_REVISION,
        )


def test_rs485_typed_field_endpoints_numeric_order_and_no_relations(p0005_database):
    project_id = p0005_database.test_project_id
    _receipt, resources = _mcm8(p0005_database)
    root = next(row["id"] for row in resources if row["resource_kind"] == "RS485_INTERFACE")
    device_03 = _field_device(p0005_database, cable_id="901.003", handle="B3")
    device_01 = _field_device(p0005_database, cable_id="901.001", handle="B1")
    service = BusService(p0005_database.engine)
    bus_receipt = service.create_rs485_bus(
        project_id=project_id,
        designation="901",
        root_resource_id=root,
        points=(
            {"field_device_id": device_03, "cable_id": "901.003", "x_mm": 3, "y_mm": 0},
            {"field_device_id": device_01, "cable_id": "901.001", "x_mm": 1, "y_mm": 0},
        ),
    )
    stored = service.get_bus(project_id, bus_receipt.bus_id)
    assert [row["address"] for row in stored["endpoints"]] == ["901.001", "901.003"]
    assert {row["endpoint_kind"] for row in stored["endpoints"]} == {"FIELD_DEVICE"}
    assert service.topology(
        project_id=project_id,
        bus_id=bus_receipt.bus_id,
        coordinates={root: (0, 0), device_01: (1, 0), device_03: (3, 0)},
    ).status == "VERIFIED"
    with p0005_database.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(functional_relation)) == 0
    with pytest.raises(BusError, match="WRONG_BUS"):
        service.add_rs485_field_endpoint(
            project_id=project_id,
            bus_id=bus_receipt.bus_id,
            field_device_id=_field_device(p0005_database, cable_id="902.002", handle="B2"),
            cable_id="902.002",
        )


def test_rgb_assignment_reopen_mix_reject_and_switch_line_guard(p0005_database):
    project_id = p0005_database.test_project_id
    automation = AutomationService(p0005_database.engine)
    pwm = automation.constructor.create_instance(
        project_id=project_id,
        designation="PWM.1",
        passport_key="controller.wb_led_v1",
        product_key="product.wirenboard.wb_led_v1",
        supply_scope="NEIROLINKS",
    )
    line = _line(p0005_database, "LED-RGB", "LED")
    profile = automation.create_led_profile(
        project_id=project_id,
        cable_line_id=line,
        led_kind="RGB",
        tape_product_key="product.arlight.046937",
        supply_scope="NEIROLINKS",
        segments=({"design_length_mm": 1000},),
    )
    assigned = automation.assign_led_channels(
        project_id=project_id,
        profile_id=profile,
        module_instance_id=pwm.instance_id,
        channel_ordinals=(0, 1, 2),
    )
    assert assigned.status == "VERIFIED"
    calculated = automation.calculate_profile(project_id, profile)
    assert calculated.load.channels == 3
    assert calculated.load.conductors == 4
    assert sum(calculated.load.channel_power_w) == calculated.load.total_power_w
    with pytest.raises(Exception, match="Unsupported canonical LED kind"):
        automation.create_led_profile(
            project_id=project_id,
            cable_line_id=_line(p0005_database, "LED-MIX", "LED"),
            led_kind="MIX",
            tape_product_key="product.arlight.045179",
            supply_scope="NEIROLINKS",
            segments=({"design_length_mm": 1000},),
        )
    switch_line = _line(p0005_database, "203", "SWITCHES")
    input_resource = next(
        row
        for row in automation.list_resources(project_id)
        if row["project_instance_id"] == pwm.instance_id and row["direction"] == "IN"
    )
    with pytest.raises(AutomationError, match="per physical key"):
        automation.assign_input_line(
            project_id=project_id,
            cable_line_id=switch_line,
            input_resource_id=input_resource["id"],
        )

    path = p0005_database.path
    p0005_database.close()
    reopened = DatabaseManager().open_existing(path)
    try:
        assert len(AutomationService(reopened.engine).list_assignments(project_id)) == 3
    finally:
        reopened.close()


def test_revision_8_blank_roundtrip_and_typed_downgrade_guard(tmp_path):
    path = tmp_path / "roundtrip.sqlite"
    initialize_database(path, target=PERSISTENCE_TOPOLOGY_REVISION)
    upgrade_database(path, tmp_path / "up")
    assert current_revision_read_only(path) == HEAD_REVISION
    downgrade_database(path, tmp_path / "down", target=PERSISTENCE_TOPOLOGY_REVISION)
    assert current_revision_read_only(path) == PERSISTENCE_TOPOLOGY_REVISION
    upgrade_database(path, tmp_path / "up-again")
    assert current_revision_read_only(path) == HEAD_REVISION
    with DatabaseManager().open_existing(path) as handle:
        with handle.engine.connect() as connection:
            assert connection.scalar(select(func.count()).select_from(bus_endpoint)) == 0
