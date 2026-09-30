from __future__ import annotations

from decimal import Decimal

import pytest

from nl_project_2.automation import AutomationError, AutomationService
from nl_project_2.distribution import assess_psu_load
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import cable_line


def _instance(service, project_id, designation, passport, product):
    return service.constructor.create_instance(
        project_id=project_id,
        designation=designation,
        passport_key=passport,
        product_key=product,
        supply_scope="NEIROLINKS",
    )


def _line(database, designation, system_kind="LIGHTING_LED"):
    identifier = new_id()
    with database.engine.begin() as connection:
        connection.execute(
            cable_line.insert().values(
                id=identifier,
                project_id=database.test_project_id,
                designation=designation,
                system_kind=system_kind,
                cable_facts_json={"source": "TEST_FIELD_LINE"},
            )
        )
    return identifier


def _profile(service, database, line_id, *, lengths=("27.78",), scope="NEIROLINKS"):
    return service.create_led_profile(
        project_id=database.test_project_id,
        cable_line_id=line_id,
        led_kind="CCT",
        tape_product_key="product.arlight.045179",
        supply_scope=scope,
        segments=tuple({"segment_id": new_id(), "design_length_mm": length} for length in lengths),
    )


def test_full_canonical_automation_resources(database):
    project_id = database.test_project_id
    service = AutomationService(database.engine)
    expected = (
        (
            "MR6C",
            "controller.wb_mr6c_v2",
            "product.wirenboard.wb_mr6c_v2",
            17,
        ),
        ("LED", "controller.wb_led_v1", "product.wirenboard.wb_led_v1", 11),
        ("UPS", "power.wb_ups_v3", "product.wirenboard.wb_ups_v3", 12),
        (
            "WB8",
            "controller.wiren_board_8_5",
            "product.wirenboard.wb8_4g_64g_ind",
            29,
        ),
    )
    receipts = {}
    for designation, passport, product, count in expected:
        receipt = _instance(service, project_id, designation, passport, product)
        assert receipt.resource_count == count
        receipts[designation] = receipt
    resources = service.list_resources(project_id)
    assert len(resources) == 69
    mr6c = [row for row in resources if row["project_instance_id"] == receipts["MR6C"].instance_id]
    assert sum(row["resource_key"] == "INPUT" for row in mr6c) == 7
    assert sum(row["resource_key"] == "COM" for row in mr6c) == 2
    assert sum(row["resource_key"] == "RELAY_OUTPUT" for row in mr6c) == 6
    led = [row for row in resources if row["project_instance_id"] == receipts["LED"].instance_id]
    assert sum(row["resource_key"] == "PWM_OUTPUT" for row in led) == 4
    assert sum(row["resource_key"] == "INPUT" for row in led) == 4
    assert {row["resource_key"] for row in led} >= {
        "ELECTRONICS_POWER",
        "LED_LOAD_POWER",
        "RS485",
    }


def test_two_cct_lines_use_disjoint_pairs_and_navigate_both_ways(database):
    project_id = database.test_project_id
    service = AutomationService(database.engine)
    module = _instance(
        service,
        project_id,
        "PWM-MODULE",
        "controller.wb_led_v1",
        "product.wirenboard.wb_led_v1",
    )
    first_line = _line(database, "LED-CCT-FIRST")
    second_line = _line(database, "LED-CCT-SECOND")
    first_profile = _profile(service, database, first_line)
    second_profile = _profile(service, database, second_line)

    first = service.assign_led_channels(
        project_id=project_id,
        profile_id=first_profile,
        module_instance_id=module.instance_id,
        channel_ordinals=(0, 1),
    )
    second = service.assign_led_channels(
        project_id=project_id,
        profile_id=second_profile,
        module_instance_id=module.instance_id,
        channel_ordinals=(2, 3),
    )
    assert first.status == second.status == "VERIFIED"
    assignments = service.list_assignments(project_id)
    assert len(assignments) == 4
    assert {row["cable_line_id"] for row in assignments} == {first_line, second_line}
    assert {row["ordinal"] for row in assignments} == {0, 1, 2, 3}
    assert all(row["instance_designation"] == "PWM-MODULE" for row in assignments)
    with pytest.raises(AutomationError, match="already assigned"):
        service.assign_led_channels(
            project_id=project_id,
            profile_id=first_profile,
            module_instance_id=module.instance_id,
            channel_ordinals=(0, 1),
        )

    packing = service.calculate_project_packing(project_id)[0]["packing"]
    assert packing.status == "VERIFIED"
    assert packing.required_quantity_mm == Decimal("55.56")
    assert packing.purchased_reels == 1


def test_current_psu_limit_long_segment_manual_split_and_atomic_failure(database):
    project_id = database.test_project_id
    service = AutomationService(database.engine)
    module = _instance(
        service,
        project_id,
        "PWM-LIMIT",
        "controller.wb_led_v1",
        "product.wirenboard.wb_led_v1",
    )
    overload_line = _line(database, "LED-OVERLOAD")
    overload_profile = _profile(
        service,
        database,
        overload_line,
        lengths=("4972", "4972", "4972", "4972", "4972", "4972"),
    )
    overload = service.calculate_profile(project_id, overload_profile)
    assert overload.load is not None
    assert overload.load.channel_current_a[0] > 5
    assert (
        assess_psu_load(
            output_voltage_v=24,
            rated_power_w=60,
            rated_current_a=2.5,
            consumers=(
                {
                    "voltage_v": 24,
                    "power_w": overload.load.total_power_w,
                    "current_a": sum(overload.load.channel_current_a),
                },
            ),
        ).status
        == "LIMIT_EXCEEDED"
    )
    with pytest.raises(AutomationError, match="LIMIT_EXCEEDED"):
        service.assign_led_channels(
            project_id=project_id,
            profile_id=overload_profile,
            module_instance_id=module.instance_id,
            channel_ordinals=(0, 1),
        )
    assert service.list_assignments(project_id) == []

    long_line = _line(database, "LED-LONG")
    long_profile = _profile(service, database, long_line, lengths=("5000",))
    blocked = service.calculate_profile(project_id, long_profile)
    assert blocked.packing.status == "BLOCKED"
    assert blocked.cuts[0].error == "LED_SEGMENT_EXCEEDS_REEL"
    assert blocked.packing.reels == ()
    service.replace_segments(
        project_id=project_id,
        profile_id=long_profile,
        segments=(
            {
                "segment_id": new_id(),
                "design_length_mm": "2500",
                "explicit_split": {"user_confirmed": True, "part": 1},
            },
            {
                "segment_id": new_id(),
                "design_length_mm": "2500",
                "explicit_split": {"user_confirmed": True, "part": 2},
            },
        ),
    )
    split = service.calculate_profile(project_id, long_profile)
    assert split.packing.status == "VERIFIED"
    assert len(split.cuts) == 2


def test_switch_input_line_assignment_is_replaced_by_physical_key_model(database):
    project_id = database.test_project_id
    service = AutomationService(database.engine)
    module = _instance(
        service,
        project_id,
        "INPUT-MODULE",
        "controller.wb_mr6c_v2",
        "product.wirenboard.wb_mr6c_v2",
    )
    resources = service.list_resources(project_id)
    input_resource = next(
        row
        for row in resources
        if row["project_instance_id"] == module.instance_id
        and row["resource_key"] == "INPUT"
        and row["ordinal"] == 0
    )
    first_line = _line(database, "SWITCH-FIRST", "SWITCHES")
    with pytest.raises(AutomationError, match="per physical key"):
        service.assign_input_line(
            project_id=project_id,
            cable_line_id=first_line,
            input_resource_id=input_resource["id"],
        )
    assert service.list_assignments(project_id) == []


def test_relay_output_load_assignment_is_distinct_from_com_and_electronics(database):
    project_id = database.test_project_id
    service = AutomationService(database.engine)
    module = _instance(
        service,
        project_id,
        "RELAY-MODULE",
        "controller.wb_mr6c_v2",
        "product.wirenboard.wb_mr6c_v2",
    )
    resources = [
        row
        for row in service.list_resources(project_id)
        if row["project_instance_id"] == module.instance_id
    ]
    relay = next(
        row for row in resources if row["resource_key"] == "RELAY_OUTPUT" and row["ordinal"] == 0
    )
    line_id = _line(database, "RELAY-LOAD", "LIGHTING_230V")
    service.assign_output_line(
        project_id=project_id,
        cable_line_id=line_id,
        output_resource_id=relay["id"],
    )
    assignment = service.list_assignments(project_id)[0]
    assert assignment["resource_key"] == "RELAY_OUTPUT"
    assert assignment["assignment_role"] == "CONTROLLED_LOAD_1"
    assert {row["resource_key"] for row in resources if row["occupied"] is False} >= {
        "ELECTRONICS_POWER",
        "COM",
    }


def test_product_and_supply_scope_changes_recalculate_isolated_groups(database):
    project_id = database.test_project_id
    service = AutomationService(database.engine)
    first_line = _line(database, "MONO-FIRST")
    second_line = _line(database, "MONO-SECOND")
    first = service.create_led_profile(
        project_id=project_id,
        cable_line_id=first_line,
        led_kind="MONO",
        tape_product_key="product.arlight.048822",
        supply_scope="NEIROLINKS",
        segments=({"segment_id": new_id(), "design_length_mm": 51},),
    )
    second = service.create_led_profile(
        project_id=project_id,
        cable_line_id=second_line,
        led_kind="MONO",
        tape_product_key="product.arlight.048822",
        supply_scope="CUSTOMER",
        segments=({"segment_id": new_id(), "design_length_mm": 7000},),
    )
    assert service.calculate_profile(project_id, first).cuts[0].cut_length_mm == 100
    service.replace_led_product(
        project_id=project_id,
        profile_id=first,
        tape_product_key="product.arlight.044196",
    )
    assert service.calculate_profile(project_id, first).cuts[0].cut_length_mm == 52
    groups = service.calculate_project_packing(project_id)
    assert {(group["product_key"], group["supply_scope"]) for group in groups} == {
        ("product.arlight.044196", "NEIROLINKS"),
        ("product.arlight.048822", "CUSTOMER"),
    }
    service.set_profile_supply_scope(
        project_id=project_id,
        profile_id=second,
        supply_scope="NEIROLINKS",
    )
    assert {
        (group["product_key"], group["supply_scope"])
        for group in service.calculate_project_packing(project_id)
    } == {
        ("product.arlight.044196", "NEIROLINKS"),
        ("product.arlight.048822", "NEIROLINKS"),
    }

    service.replace_segments(
        project_id=project_id,
        profile_id=second,
        segments=({"segment_id": new_id(), "design_length_mm": 1201},),
    )
    assert service.calculate_profile(project_id, second).cuts[0].cut_length_mm == 1250
    service.replace_segments(
        project_id=project_id,
        profile_id=second,
        segments=({"segment_id": new_id(), "design_length_mm": 1251},),
    )
    assert service.calculate_profile(project_id, second).cuts[0].cut_length_mm == 1300
