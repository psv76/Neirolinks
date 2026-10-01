from __future__ import annotations

from sqlalchemy import select

from nl_project_2.cables import CableService
from nl_project_2.cad_contract import (
    BlockDefinitionMetadata,
    CadContractValidator,
    CadObservation,
    CadObservationBatch,
    load_contract,
)
from nl_project_2.cad_sync import ChangeClass, DwgSyncService
from nl_project_2.cad_sync.models import SyncOwnerKind
from nl_project_2.cad_sync.reconciliation import normalize_validated_snapshot
from nl_project_2.objects.models import ProjectCard
from nl_project_2.objects.service import ObjectService
from nl_project_2.persistence.database import DatabaseManager
from nl_project_2.persistence.schema import cable_line, field_device
from nl_project_2.presentation.lines_workspace import COLUMNS, LinesWorkspace


class _NoAssignments:
    @staticmethod
    def list_cable_assignments(_project_id):
        return []


def _line_301(load_name: str) -> CadObservation:
    attributes = {
        "DEVICE_NAME": "Светильник, IP44",
        "BUILDING": "Дом",
        "ROOM": "Улица",
        "MOUNT_HEIGHT": "300",
        "CABLE_ID": "301",
        "CABLE_TYPE": "3x1,5",
        "BOARD": "ЩС-1",
        "CABLE_SOURCE": "",
        "LOAD_TYPE": "LIGHT_MAIN",
        "LOAD_NAME": load_name,
        "CALC_POWER": "",
        "MOUNT_WAY": "По потолку",
        "GOFRA_TYPE": "ПВХ20",
        "GOFRA_COLOR": "Серый",
        "GOFRA_ID": "001.PVH20",
        "COMMENT_1": "",
        "COMMENT_2": "",
    }
    return CadObservation.from_mapping(
        effective_name="LIGHT_IN_230V",
        layer="LIGHTING_STREET",
        raw_attributes=attributes,
        x=10,
        y=20,
        handle="A301",
        definition=BlockDefinitionMetadata(tuple(attributes), False),
    )


def _batch(load_name: str) -> CadObservationBatch:
    return CadObservationBatch(
        "C:/fixture/repair-02-lines.dwg",
        (_line_301(load_name),),
        {"adapter_version": "fixture", "protocol_version": "1.0"},
    )


def _column(key: str) -> int:
    return next(index for index, column in enumerate(COLUMNS) if column.key == key)


def test_load_name_survives_selected_apply_reopen_read_model_and_lines_ui(qtbot, database):
    project_id = ObjectService(database.engine).create_project(
        ProjectCard(name="Repair 02", project_code="P1-007-R02")
    )
    service = DwgSyncService(database.engine)

    validated = CadContractValidator(load_contract()).validate(_batch("Свет улица"))
    snapshot = normalize_validated_snapshot(validated.observations)
    load_fact = next(fact for fact in snapshot.facts if fact.field == "LOAD_NAME")
    assert load_fact.owner_kind is SyncOwnerKind.BASE_LINE
    assert load_fact.owner_path == "base_line:301:LOAD_NAME"
    assert load_fact.value == "Свет улица"

    initial = service.preview(project_id=project_id, batch=_batch("Старое назначение"))
    service.apply_dwg_to_project(
        initial,
        selected_paths={
            change.field_path
            for change in initial.changes
            if change.change_class is ChangeClass.NEW_DWG_INSERTION
        },
        confirmed=True,
    )
    changed = service.preview(project_id=project_id, batch=_batch("Свет улица"))
    load_change = next(change for change in changed.changes if change.field == "LOAD_NAME")
    assert load_change.owner_kind is SyncOwnerKind.BASE_LINE
    assert load_change.change_class is ChangeClass.DWG_CHANGED
    assert load_change.project_value == "Старое назначение"
    assert load_change.dwg_value == "Свет улица"
    service.apply_dwg_to_project(
        changed,
        selected_paths={load_change.field_path},
        confirmed=True,
    )

    database.close()
    reopened = DatabaseManager().open_existing(database.path)
    try:
        with reopened.engine.connect() as connection:
            line_facts = connection.execute(select(cable_line.c.cable_facts_json)).scalar_one()
            device_facts = connection.execute(
                select(field_device.c.normalized_fields_json)
            ).scalar_one()
        assert line_facts["LOAD_NAME"] == "Свет улица"
        assert device_facts["LOAD_NAME"] == "Свет улица"
        assert device_facts["DEVICE_NAME"] == "Светильник, IP44"
        assert line_facts["LOAD_NAME"] != device_facts["DEVICE_NAME"]

        cards = CableService(reopened.engine).line_cards(project_id)
        assert cards[0]["load_name"] == "Свет улица"
        workspace = LinesWorkspace(CableService(reopened.engine), _NoAssignments(), project_id)
        qtbot.addWidget(workspace)
        workspace.show()
        assert workspace.table.item(0, _column("load_name")).text() == "Свет улица"
        assert workspace.table.item(0, _column("cable_type")).text() == ("ВВГнг(А)-LS 3х1,5")
        assert "Свет улица" in workspace.card_title.text()
        assert "Светильник, IP44" not in workspace.card_title.text()
    finally:
        reopened.close()
