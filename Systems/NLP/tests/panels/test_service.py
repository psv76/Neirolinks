from __future__ import annotations

import pytest

from nl_project_2.cables import CableService
from nl_project_2.catalog.equipment import EquipmentService
from nl_project_2.config import PathConfig
from nl_project_2.constructor import ConstructorService
from nl_project_2.objects.models import ProjectCard
from nl_project_2.objects.runtime import ApplicationRuntime
from nl_project_2.panels import PanelBlockingViolation, PanelService


def _instance(
    database,
    designation: str,
    passport_key: str,
    product_key: str | None,
    *,
    supply_scope: str = "NEIROLINKS",
    board_id: str | None = None,
):
    return (
        EquipmentService(database.engine)
        .create_instance(
            project_id=database.test_project_id,
            designation=designation,
            passport_key=passport_key,
            product_key=product_key,
            supply_scope=supply_scope,
            board_id=board_id,
        )
        .instance_id
    )


def _panel(database, width: str = "108"):
    service = PanelService(database.engine)
    project_id = database.test_project_id
    board_id = service.create_board(project_id=project_id, designation="BOARD.01")
    section_id = service.create_section(
        project_id=project_id, board_id=board_id, section_key="MAIN", section_order=1
    )
    rail_id = service.create_rail(
        project_id=project_id,
        section_id=section_id,
        rail_order=1,
        usable_width_mm=width,
    )
    return service, board_id, section_id, rail_id


def test_manual_layout_multiple_rails_move_order_and_reopen(database):
    service, board_id, _section_id, rail_one = _panel(database)
    project_id = database.test_project_id
    section_two = service.create_section(
        project_id=project_id, board_id=board_id, section_key="AUX", section_order=2
    )
    rail_two = service.create_rail(
        project_id=project_id,
        section_id=section_two,
        rail_order=1,
        usable_width_mm="108",
    )
    first = _instance(
        database,
        "QF.1",
        "protection.circuit_breaker.1p",
        "product.schneider.a9f84116",
        board_id=board_id,
    )
    second = _instance(
        database,
        "QF.2",
        "protection.circuit_breaker.1p",
        "product.schneider.a9f84106",
        board_id=board_id,
    )
    psu = _instance(
        database,
        "PSU.1",
        "power.acdc.24v.din",
        "product.meanwell.hdr_30_24",
        board_id=board_id,
    )
    p_first = service.place_instance(
        project_id=project_id, rail_id=rail_one, instance_id=first, start_mm="0"
    )
    p_second = service.place_instance(
        project_id=project_id, rail_id=rail_one, instance_id=second, start_mm="18"
    )
    p_psu = service.place_instance(
        project_id=project_id, rail_id=rail_two, instance_id=psu, start_mm="36"
    )
    service.move_placement(
        project_id=project_id,
        placement_id=p_second,
        rail_id=rail_two,
        start_mm="0",
        orientation="REVERSED",
    )

    reopened = PanelService(database.engine).board_layout(project_id=project_id, board_id=board_id)
    assert [row["section_key"] for row in reopened["sections"]] == ["MAIN", "AUX"]
    placements = [item for rail in reopened["rails"] for item in rail["placements"]]
    assert {item["id"] for item in placements} == {p_first, p_second, p_psu}
    assert next(item for item in placements if item["id"] == p_second)["orientation"] == "REVERSED"


def test_overlap_capacity_duplicate_and_section_delete_are_transactionally_blocked(database):
    service, board_id, section_id, rail_id = _panel(database, width="36")
    project_id = database.test_project_id
    first = _instance(
        database,
        "QF.A",
        "protection.circuit_breaker.1p",
        "product.schneider.a9f84116",
        board_id=board_id,
    )
    second = _instance(
        database,
        "QF.B",
        "protection.circuit_breaker.1p",
        "product.schneider.a9f84106",
        board_id=board_id,
    )
    service.place_instance(project_id=project_id, rail_id=rail_id, instance_id=first, start_mm="0")
    with pytest.raises(PanelBlockingViolation, match="PLACEMENT_OVERLAP"):
        service.place_instance(
            project_id=project_id, rail_id=rail_id, instance_id=second, start_mm="9"
        )
    with pytest.raises(PanelBlockingViolation, match="RAIL_CAPACITY_EXCEEDED"):
        service.place_instance(
            project_id=project_id, rail_id=rail_id, instance_id=second, start_mm="27"
        )
    with pytest.raises(PanelBlockingViolation, match="only once"):
        service.place_instance(
            project_id=project_id, rail_id=rail_id, instance_id=first, start_mm="18"
        )
    with pytest.raises(PanelBlockingViolation, match="contains placed instances"):
        service.delete_section(project_id=project_id, section_id=section_id)
    assert (
        sum(
            len(rail["placements"])
            for rail in service.board_layout(project_id=project_id, board_id=board_id)["rails"]
        )
        == 1
    )


def test_product_replacement_revalidates_width_without_losing_relation(database):
    service, board_id, _section_id, rail_id = _panel(database, width="80")
    project_id = database.test_project_id
    psu = _instance(
        database,
        "PSU.X",
        "power.acdc.24v.din",
        "product.meanwell.hdr_30_24",
        board_id=board_id,
    )
    controller = _instance(
        database,
        "CTRL.X",
        "controller.wiren_board_8_5",
        "product.wirenboard.wb8_4g_64g_ind",
        board_id=board_id,
    )
    placement_id = service.place_instance(
        project_id=project_id, rail_id=rail_id, instance_id=psu, start_mm="0"
    )
    constructor = ConstructorService(database.engine)
    resources = constructor.list_resources(project_id)
    source = next(
        row for row in resources if row["project_instance_id"] == psu and row["direction"] == "OUT"
    )
    target = next(
        row
        for row in resources
        if row["project_instance_id"] == controller and row["resource_key"] == "VPLUS_INPUT"
    )
    relation = constructor.create_relation(
        project_id=project_id,
        relation_kind="POWER_FLOW",
        source_resource_id=source["id"],
        target_resource_id=target["id"],
    )
    EquipmentService(database.engine).replace_product(
        project_id=project_id,
        instance_id=psu,
        new_product_key="product.meanwell.hdr_150_24",
        actor="test",
    )
    layout = service.board_layout(project_id=project_id, board_id=board_id)
    placed = next(
        item
        for rail in layout["rails"]
        for item in rail["placements"]
        if item["id"] == placement_id
    )
    assert placed["stored_width_mm"] != placed["current_width_mm"]
    assert placed["width_changed"] is True
    assert "RAIL_CAPACITY_EXCEEDED" in {
        issue.code for issue in layout["rails"][0]["evaluation"].issues
    }
    assert [row["id"] for row in constructor.list_relations(project_id)] == [relation.relation_id]


def test_external_board_av_unknown_product_mounting_and_internal_material_rules(database):
    service, board_id, _section_id, rail_id = _panel(database)
    project_id = database.test_project_id
    av_board = CableService(database.engine).create_board_av(
        project_id=project_id, designation="BOARD_AV"
    )
    with pytest.raises(PanelBlockingViolation, match="BOARD_AV"):
        service.create_section(
            project_id=project_id, board_id=av_board, section_key="NO", section_order=1
        )
    external = _instance(
        database,
        "LED.TAPE",
        "led_tape.constant_voltage.mono.24v",
        "product.arlight.048822",
        board_id=board_id,
    )
    with pytest.raises(PanelBlockingViolation, match="not compatible"):
        service.place_instance(
            project_id=project_id, rail_id=rail_id, instance_id=external, start_mm="0"
        )
    unknown = _instance(
        database,
        "CUSTOMER.PSU",
        "power.acdc.24v.din",
        None,
        supply_scope="CUSTOMER",
        board_id=board_id,
    )
    with pytest.raises(PanelBlockingViolation, match="Product is not selected"):
        service.place_instance(
            project_id=project_id, rail_id=rail_id, instance_id=unknown, start_mm="0"
        )
    service.record_material_fact(
        project_id=project_id,
        board_id=board_id,
        material_kind="COMB_BUSBAR",
        quantity="1",
        unit="pcs",
        reason="Feeds a sequence of compatible breakers",
    )
    layout = service.board_layout(project_id=project_id, board_id=board_id)
    assert (
        next(row for row in layout["instances"] if row["id"] == unknown)["layout_state"]
        == "PRODUCT_NOT_SELECTED"
    )
    assert layout["materials"][0]["occupies_din"] is False
    assert all(not rail["placements"] for rail in layout["rails"])


def test_application_close_and_reopen_restores_panel_layout(tmp_path):
    paths = PathConfig(
        app_root=tmp_path / "app",
        backup_root=tmp_path / "backups",
        release_root=tmp_path / "releases",
        user_projects_root=tmp_path / "projects",
        local_state_root=tmp_path / "state",
    )
    runtime = ApplicationRuntime.open(paths)
    project_id = runtime.objects.create_project(
        ProjectCard(name="Panel reopen", project_code="PANEL-REOPEN")
    )
    board_id = runtime.panels.create_board(project_id=project_id, designation="BOARD.R")
    section_id = runtime.panels.create_section(
        project_id=project_id, board_id=board_id, section_key="MAIN", section_order=1
    )
    rail_id = runtime.panels.create_rail(
        project_id=project_id,
        section_id=section_id,
        rail_order=1,
        usable_width_mm="72",
    )
    instance_id = runtime.constructor.create_instance(
        project_id=project_id,
        designation="QF.R",
        passport_key="protection.circuit_breaker.1p",
        product_key="product.schneider.a9f84116",
        supply_scope="NEIROLINKS",
        board_id=board_id,
    ).instance_id
    placement_id = runtime.panels.place_instance(
        project_id=project_id, rail_id=rail_id, instance_id=instance_id, start_mm="18"
    )
    runtime.close()

    reopened = ApplicationRuntime.open(paths)
    try:
        layout = reopened.panels.board_layout(project_id=project_id, board_id=board_id)
        placement = layout["rails"][0]["placements"][0]
        assert placement["id"] == placement_id
        assert placement["project_instance_id"] == instance_id
        assert placement["start_mm_decimal"] == "18"
        assert layout["rails"][0]["evaluation"].status == "VALID"
    finally:
        reopened.close()
