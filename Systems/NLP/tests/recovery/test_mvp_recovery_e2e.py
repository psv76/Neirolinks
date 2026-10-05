from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select

from nl_project_2.automation import AutomationService
from nl_project_2.buses import BusService
from nl_project_2.catalog.installer import CatalogInstaller
from nl_project_2.catalog.payload import load_payload
from nl_project_2.constructor import BlockingViolation
from nl_project_2.distribution import DistributionService
from nl_project_2.objects.models import ProjectCard
from nl_project_2.objects.service import ObjectService
from nl_project_2.persistence.database import DatabaseManager
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    bus,
    cable_line,
    cable_line_assignment,
    functional_relation,
    project_instance,
)
from nl_project_2.specification import SpecificationService

CATALOG_ROOT = Path(__file__).resolve().parents[2] / "resources" / "catalogs"


def _instance(service, project_id, designation, passport, product):
    return service.create_instance(
        project_id=project_id,
        designation=designation,
        passport_key=passport,
        product_key=product,
        supply_scope="NEIROLINKS",
    )


def _resource(service, project_id, instance, key, ordinal=0):
    return next(
        row
        for row in service.list_resources(project_id)
        if row["project_instance_id"] == instance.instance_id
        and row["resource_key"] == key
        and row["ordinal"] == ordinal
    )


def _line(engine, project_id, designation, kind):
    line_id = new_id()
    with engine.begin() as connection:
        connection.execute(
            cable_line.insert().values(
                id=line_id,
                project_id=project_id,
                designation=designation,
                system_kind=kind,
                cable_facts_json={"fixture": "MVP_RECOVERY"},
            )
        )
    return line_id


def _bus_points(resource_ids, designation):
    return tuple(
        {
            "resource_id": resource_id,
            "cable_id": f"{designation}.{index:03d}",
            "x_mm": index * 1000,
            "y_mm": 0,
        }
        for index, resource_id in enumerate(resource_ids, 1)
    )


def test_whole_mvp_recovery_contour_uses_one_temporary_sqlite(tmp_path):
    database = DatabaseManager().initialize_new(tmp_path / "mvp-recovery.sqlite")
    release = CatalogInstaller(database.engine).install(load_payload(CATALOG_ROOT))
    objects = ObjectService(database.engine)
    project_id = objects.create_project(
        ProjectCard(name="Generic MVP recovery", project_code="RECOVERY-E2E")
    )
    building_id = objects.add_building(project_id, "Building A")
    objects.add_room(
        project_id=project_id,
        building_id=building_id,
        name="Engineering room",
        base_mark_mm=0,
        height_m=3,
        marking_color="#808080",
    )
    assert release.passport_count == 19
    assert release.product_count == 32

    distribution = DistributionService(database.engine)
    constructor = distribution.constructor
    automation = AutomationService(database.engine)
    buses = BusService(database.engine)

    qf = _instance(
        constructor,
        project_id,
        "E2E.QF.MAIN",
        "protection.circuit_breaker.1p",
        "product.schneider.a9f84116",
    )
    qf_control = _instance(
        constructor,
        project_id,
        "E2E.QF.CONTROL",
        "protection.circuit_breaker.1p",
        "product.schneider.a9f84106",
    )
    qf_psu = _instance(
        constructor,
        project_id,
        "E2E.QF.PSU",
        "protection.circuit_breaker.1p",
        "product.schneider.a9f84106",
    )
    xt = _instance(
        constructor,
        project_id,
        "E2E.DISTRIBUTION",
        "distribution.cross_module.3l_pen",
        "product.iek.ynd10_4_11_125",
    )
    qfd = _instance(
        constructor,
        project_id,
        "E2E.RCBO",
        "protection.rcbo.1pn",
        "product.schneider.a9d11816",
    )
    km = _instance(
        constructor,
        project_id,
        "E2E.CONTACTOR",
        "switching.modular_contactor.2no.230vac",
        "product.schneider.a9c20732",
    )
    psu = _instance(
        constructor,
        project_id,
        "E2E.PSU24",
        "power.acdc.24v.din",
        "product.meanwell.hdr_60_24",
    )
    ups = _instance(
        constructor,
        project_id,
        "E2E.UPS",
        "power.wb_ups_v3",
        "product.wirenboard.wb_ups_v3",
    )
    relay = _instance(
        constructor,
        project_id,
        "E2E.RELAY",
        "controller.wb_mr6c_v2",
        "product.wirenboard.wb_mr6c_v2",
    )
    led = _instance(
        constructor,
        project_id,
        "E2E.PWM",
        "controller.wb_led_v1",
        "product.wirenboard.wb_led_v1",
    )
    controller = _instance(
        constructor,
        project_id,
        "E2E.CONTROLLER",
        "controller.wiren_board_8_5",
        "product.wirenboard.wb8_4g_64g_ind",
    )
    dali = _instance(
        constructor,
        project_id,
        "E2E.DALI",
        "gateway.wirenboard.wb_dali3",
        "product.wirenboard.wb_dali3",
    )
    knx = _instance(
        constructor,
        project_id,
        "E2E.KNX",
        "module.wirenboard.wbe2_i_knx",
        "product.wirenboard.wbe2_i_knx",
    )

    def rid(instance, key, ordinal=0):
        return _resource(constructor, project_id, instance, key, ordinal)["id"]

    for source, target, kind in (
        (rid(qf, "PROTECTED_OUT"), rid(xt, "BUS_CONNECTION_POINT", 0), "POWER_FLOW"),
        (rid(xt, "BUS_CONNECTION_POINT", 1), rid(qfd, "LINE_IN"), "POWER_FLOW"),
        (rid(qfd, "PROTECTED_LINE_OUT"), rid(km, "POWER_CONTACT_IN", 0), "POWER_FLOW"),
        (rid(qf_control, "PROTECTED_OUT"), rid(relay, "COM", 0), "FEED_RELAY_COMMON"),
        (rid(relay, "RELAY_OUTPUT", 0), rid(km, "COIL_CONTROL"), "CONTROL"),
        (rid(qf_psu, "PROTECTED_OUT"), rid(psu, "AC_INPUT"), "POWER_FLOW"),
        (rid(psu, "DC24_OUTPUT"), rid(ups, "VIN"), "POWER_FLOW"),
        (rid(ups, "VOUT"), rid(controller, "VPLUS_INPUT", 0), "POWER_FLOW"),
        (rid(controller, "VOUT"), rid(relay, "ELECTRONICS_POWER"), "POWER_FLOW"),
    ):
        constructor.create_relation(
            project_id=project_id,
            relation_kind=kind,
            source_resource_id=source,
            target_resource_id=target,
        )

    ac_line = _line(database.engine, project_id, "E2E.AC.LOAD", "POWER")
    ac_assignment = constructor.assign_cable_line(
        project_id=project_id,
        cable_line_id=ac_line,
        output_resource_id=rid(km, "POWER_CONTACT_OUT", 0),
    )
    ac_trace = constructor.trace_cable_assignment(
        project_id=project_id, assignment_id=ac_assignment
    )
    assert ac_trace.status == "VERIFIED"
    assert any(step.behavior == "DISTRIBUTION" for step in ac_trace.steps)
    assert any(step.behavior == "CONTROLLED" for step in ac_trace.steps)
    internal_behaviors = {edge.behavior for edge in constructor.derived_internal_edges(project_id)}
    assert {"TRANSFORM", "BUFFERED_TRANSFORM"}.issubset(internal_behaviors)

    led_line = _line(database.engine, project_id, "E2E.LED.LOAD", "LIGHTING_LED")
    profile_id = automation.create_led_profile(
        project_id=project_id,
        cable_line_id=led_line,
        led_kind="CCT",
        tape_product_key="product.arlight.045179",
        supply_scope="NEIROLINKS",
        segments=({"segment_id": new_id(), "design_length_mm": "1000"},),
    )
    led_receipt = automation.assign_led_channels(
        project_id=project_id,
        profile_id=profile_id,
        module_instance_id=led.instance_id,
        channel_ordinals=(0, 1),
    )
    assert led_receipt.status == "VERIFIED"
    assert automation.calculate_profile(project_id, profile_id).packing.status == "VERIFIED"

    rs485 = buses.create_rs485_bus(
        project_id=project_id,
        designation="901",
        root_resource_id=rid(controller, "RS485", 0),
        points=_bus_points((rid(ups, "RS485"), rid(relay, "RS485"), rid(led, "RS485")), "901"),
    )
    assert (
        buses.topology(project_id=project_id, bus_id=rs485.bus_id, coordinates={}).status
        == "INCOMPATIBLE"
    )
    assert [row["address"] for row in buses.get_bus(project_id, rs485.bus_id)["endpoints"]] == [
        "901.001",
        "901.002",
        "901.003",
    ]

    dali_endpoints = []
    knx_endpoints = []
    for index in range(6):
        fixture = _instance(
            constructor,
            project_id,
            f"E2E.BUS.DEVICE.{index}",
            "controller.wb_mr6c_v2",
            "product.wirenboard.wb_mr6c_v2",
        )
        (dali_endpoints if index < 3 else knx_endpoints).append(rid(fixture, "RS485"))
    dali_points = _bus_points(tuple(dali_endpoints), "905")
    dali_bus = buses.create_branched_bus(
        project_id=project_id,
        bus_kind="DALI",
        designation="905",
        root_resource_id=rid(dali, "DALI_PORT", 0),
        points=dali_points,
        branches=((dali_endpoints[0], dali_endpoints[1]), (dali_endpoints[1], dali_endpoints[2])),
    )
    buses.create_dali_group(
        project_id=project_id,
        bus_id=dali_bus.bus_id,
        group_key="D.821",
        member_resource_ids=(dali_endpoints[0], dali_endpoints[2]),
    )
    knx_points = _bus_points(tuple(knx_endpoints), "906")
    knx_bus = buses.create_branched_bus(
        project_id=project_id,
        bus_kind="KNX",
        designation="906",
        root_resource_id=rid(knx, "KNX_PORT"),
        points=knx_points,
        branches=((knx_endpoints[0], knx_endpoints[1]), (knx_endpoints[1], knx_endpoints[2])),
    )
    assert buses.get_bus(project_id, dali_bus.bus_id)["topology_policy"] == "ORDERED_BRANCHES"
    assert buses.get_bus(project_id, knx_bus.bus_id)["topology_policy"] == "ORDERED_BRANCHES"

    # Blocking-save matrix remains atomic and does not weaken draft semantics.
    with pytest.raises(BlockingViolation):
        constructor.create_relation(
            project_id=project_id,
            relation_kind="POWER_FLOW",
            source_resource_id=rid(psu, "AC_INPUT"),
            target_resource_id=rid(qfd, "LINE_IN"),
        )
    relation_count = len(constructor.list_relations(project_id))
    assert relation_count == 9
    assert len(constructor.list_cable_assignments(project_id)) == 3
    specification = SpecificationService(database.engine, automation).build(project_id)
    assert specification["rows"]

    with database.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(functional_relation)) == 9
        assert connection.scalar(select(func.count()).select_from(cable_line_assignment)) == 3
        assert connection.scalar(select(func.count()).select_from(bus)) == 3
        assert connection.scalar(select(func.count()).select_from(project_instance)) >= 19

    database_path = database.path
    database.close()
    reopened = DatabaseManager().open_existing(database_path)
    try:
        restored_constructor = DistributionService(reopened.engine).constructor
        restored_trace = restored_constructor.trace_cable_assignment(
            project_id=project_id, assignment_id=ac_assignment
        )
        assert restored_trace == ac_trace
        assert len(BusService(reopened.engine).list_buses(project_id)) == 3
        assert SpecificationService(reopened.engine, AutomationService(reopened.engine)).build(
            project_id
        )["rows"]
    finally:
        reopened.close()


def test_production_sources_have_no_recovery_fixture_special_cases():
    source_root = Path(__file__).resolve().parents[2] / "src" / "nl_project_2"
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in source_root.rglob("*.py")
        if "__pycache__" not in path.parts
    )
    for forbidden in (
        "05 44 Богданович",
        "E2E.QF.MAIN",
        "E2E.AC.LOAD",
        "SYNTHETIC_VOLTAGE_RANGE",
    ):
        assert forbidden not in text
