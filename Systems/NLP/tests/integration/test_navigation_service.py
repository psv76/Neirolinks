from __future__ import annotations

import hashlib

from nl_project_2.automation import AutomationService
from nl_project_2.cables import CableService
from nl_project_2.catalog.equipment import EquipmentService
from nl_project_2.constructor import ConstructorService
from nl_project_2.integration import IntegratedUiService
from nl_project_2.panels import PanelService
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import cable_line
from nl_project_2.specification import SpecificationService


def _services(database):
    constructor = ConstructorService(database.engine)
    cables = CableService(database.engine)
    panels = PanelService(database.engine)
    automation = AutomationService(database.engine)
    specification = SpecificationService(database.engine, automation)
    integrated = IntegratedUiService(
        constructor=constructor,
        cables=cables,
        panels=panels,
        specification=specification,
    )
    return constructor, cables, panels, integrated


def test_validation_center_unifies_sources_without_read_side_write(database):
    project_id = database.test_project_id
    constructor, _cables, panels, integrated = _services(database)
    board_id = panels.create_board(project_id=project_id, designation="BOARD.1")
    EquipmentService(database.engine).create_instance(
        project_id=project_id,
        designation="CUSTOMER.PSU",
        passport_key="power.acdc.24v.din",
        product_key=None,
        supply_scope="CUSTOMER",
        board_id=board_id,
    )
    EquipmentService(database.engine).create_instance(
        project_id=project_id,
        designation="QF.UNPRICED",
        passport_key="protection.circuit_breaker.1p",
        product_key="product.schneider.a9f84116",
        supply_scope="NEIROLINKS",
        board_id=board_id,
    )
    with database.engine.begin() as connection:
        line_id = new_id()
        connection.execute(
            cable_line.insert().values(
                id=line_id,
                project_id=project_id,
                designation="LINE.INCOMPLETE",
                system_kind="POWER",
                cable_facts_json={},
                lifecycle="ACTIVE",
            )
        )
    before = hashlib.sha256(database.path.read_bytes()).hexdigest()
    items = integrated.validation_items(project_id)
    after = hashlib.sha256(database.path.read_bytes()).hexdigest()
    assert before == after
    assert "CABLE_LENGTH_INCOMPLETE" in {item.code for item in items}
    assert "PRODUCT_NOT_SELECTED" in {item.code for item in items}
    assert {item.section for item in items} >= {"CABLES", "PANELS", "SPECIFICATION"}


def test_cable_assignment_targets_explain_availability_and_delete(database):
    project_id = database.test_project_id
    constructor, _cables, _panels, _integrated = _services(database)
    instance = (
        EquipmentService(database.engine)
        .create_instance(
            project_id=project_id,
            designation="CTRL.1",
            passport_key="controller.wiren_board_8_5",
            product_key="product.wirenboard.wb8_4g_64g_ind",
            supply_scope="NEIROLINKS",
        )
        .instance_id
    )
    with database.engine.begin() as connection:
        line_id = new_id()
        connection.execute(
            cable_line.insert().values(
                id=line_id,
                project_id=project_id,
                designation="LINE.1",
                system_kind="CONTROL",
                cable_facts_json={},
                lifecycle="ACTIVE",
            )
        )
    targets = constructor.cable_assignment_targets(project_id=project_id, cable_line_id=line_id)
    available = next(row for row in targets if row["available"])
    unavailable = next(row for row in targets if not row["available"])
    assert unavailable["reason"] != ""
    assignment_id = constructor.assign_cable_line(
        project_id=project_id,
        cable_line_id=line_id,
        output_resource_id=available["id"],
    )
    assert constructor.list_cable_assignments(project_id)[0]["project_instance_id"] == instance
    assert all(
        not row["available"]
        for row in constructor.cable_assignment_targets(
            project_id=project_id, cable_line_id=line_id
        )
    )
    constructor.delete_cable_assignment(project_id=project_id, assignment_id=assignment_id)
    assert constructor.list_cable_assignments(project_id) == []
