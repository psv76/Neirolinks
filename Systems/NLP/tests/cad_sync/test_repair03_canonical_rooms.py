from __future__ import annotations

from sqlalchemy import func, select, update

from nl_project_2.cables.service import CableService
from nl_project_2.cad_contract import (
    BlockDefinitionMetadata,
    CadObservation,
    CadObservationBatch,
    load_contract,
)
from nl_project_2.cad_sync import ChangeClass, DwgSyncService
from nl_project_2.objects.models import ProjectCard
from nl_project_2.objects.service import ObjectService
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    cable_line,
    conduit,
    dwg_observation,
    field_device,
    room,
)
from nl_project_2.persistence.uow import UnitOfWork


def _socket(
    *,
    room_name: str = "1. Прихожая",
    load_name: str = "Розетки прихожей",
    gofra_id: str = "001.PND25",
) -> CadObservation:
    rule = load_contract().block("SOCKET_IN")
    assert rule is not None
    attributes = {tag: "" for tag in rule.required_definition_attributes}
    attributes.update(
        {
            "DEVICE_NAME": "Розетка",
            "BUILDING": "Дом",
            "ROOM": room_name,
            "MOUNT_HEIGHT": "300",
            "CABLE_ID": "101.01",
            "CABLE_TYPE": "3x1,5",
            "BOARD": "B.01",
            "LOAD_TYPE": "SOCKET_LIVING_LOW",
            "LOAD_NAME": load_name,
            "MOUNT_WAY": "По полу",
            "GOFRA_TYPE": "ПНД25",
            "GOFRA_COLOR": "Черный",
            "GOFRA_ID": gofra_id,
        }
    )
    return CadObservation.from_mapping(
        effective_name="SOCKET_IN",
        layer="POWER",
        raw_attributes=attributes,
        x=10,
        y=20,
        handle="A1",
        definition=BlockDefinitionMetadata(tuple(attributes), False),
    )


def _batch(
    observation: CadObservation,
    identity: str = "C:/fixture/rooms.dwg",
) -> CadObservationBatch:
    return CadObservationBatch(identity, (observation,))


def _applicable(proposal) -> set[str]:
    return {
        item.field_path
        for item in proposal.changes
        if item.change_class in {ChangeClass.NEW_DWG_INSERTION, ChangeClass.DWG_CHANGED}
    }


def test_room_relation_is_canonical_for_lines_and_three_way_rename(database):
    objects = ObjectService(database.engine)
    project_id = objects.create_project(ProjectCard(name="Rooms", project_code="ROOMS"))
    building_id = objects.add_building(project_id, "Дом")
    room_id = objects.add_room(
        project_id=project_id,
        building_id=building_id,
        name="1. Прихожая",
        base_mark_mm=None,
        height_m=None,
        marking_color="#D7E3FC",
    )
    sync = DwgSyncService(database.engine)
    initial = sync.preview(project_id=project_id, batch=_batch(_socket()))
    sync.apply_dwg_to_project(initial, selected_paths=_applicable(initial), confirmed=True)

    with database.engine.connect() as connection:
        device = connection.execute(select(field_device)).mappings().one()
        assert device["room_id"] == room_id
        assert device["normalized_fields_json"]["ROOM"] == "1. Прихожая"
        assert connection.scalar(select(func.count()).select_from(dwg_observation)) == 1

    card = CableService(database.engine).line_cards(project_id)[0]
    assert card["room_names"] == "1. Прихожая"
    assert card["room_markers"] == ({"id": room_id, "name": "1. Прихожая", "color": "#D7E3FC"},)

    objects.update_room(
        project_id=project_id,
        room_id=room_id,
        building_id=building_id,
        name="1. Холл",
        base_mark_mm=None,
        height_m=None,
        marking_color="#D7E3FC",
    )
    assert CableService(database.engine).line_cards(project_id)[0]["room_names"] == "1. Холл"

    renamed = sync.preview(project_id=project_id, batch=_batch(_socket()))
    room_change = next(item for item in renamed.changes if item.field == "ROOM")
    assert room_change.project_value == "1. Холл"
    assert room_change.dwg_value == "1. Прихожая"
    assert room_change.change_class == ChangeClass.PROJECT_CHANGED

    both = sync.preview(project_id=project_id, batch=_batch(_socket(room_name="1. Фойе")))
    conflict = next(item for item in both.changes if item.field == "ROOM")
    assert conflict.change_class == ChangeClass.BOTH_CHANGED_CONFLICT


def test_unresolved_dwg_room_does_not_create_project_structure(database):
    objects = ObjectService(database.engine)
    project_id = objects.create_project(ProjectCard(name="Empty", project_code="EMPTY"))
    sync = DwgSyncService(database.engine)
    proposal = sync.preview(project_id=project_id, batch=_batch(_socket()))
    sync.apply_dwg_to_project(proposal, selected_paths=_applicable(proposal), confirmed=True)
    with database.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(room)) == 0
        assert connection.scalar(select(field_device.c.room_id)) is None


def test_preview_resolves_raw_room_to_canonical_name_without_fuzzy_matching(database):
    objects = ObjectService(database.engine)
    project_id = objects.create_project(ProjectCard(name="Preview rooms", project_code="PR"))
    building_id = objects.add_building(project_id, "Дом")
    objects.add_room(
        project_id=project_id,
        building_id=building_id,
        name="5. Кухня-ниша",
        base_mark_mm=None,
        height_m=None,
        marking_color="#D7E3FC",
    )
    sync = DwgSyncService(database.engine)
    resolved = sync.preview(
        project_id=project_id, batch=_batch(_socket(room_name="5. Старое название"))
    )
    assert resolved.changes[0].display_context == {
        "room_name": "5. Кухня-ниша",
        "raw_room": "5. Старое название",
    }
    unresolved = sync.preview(project_id=project_id, batch=_batch(_socket(room_name="Чердак")))
    assert unresolved.changes[0].display_context == {
        "room_name": "Не разрешено: Чердак",
        "raw_room": "Чердак",
    }


def test_load_name_only_apply_does_not_materialize_unselected_conduit_change(database):
    objects = ObjectService(database.engine)
    project_id = objects.create_project(ProjectCard(name="Load", project_code="LOAD"))
    sync = DwgSyncService(database.engine)
    initial = sync.preview(project_id=project_id, batch=_batch(_socket()))
    sync.apply_dwg_to_project(initial, selected_paths=_applicable(initial), confirmed=True)
    with UnitOfWork(database.engine) as uow:
        uow.execute(
            conduit.insert().values(
                id=new_id(),
                project_id=project_id,
                designation="100.PVH100",
                conduit_number=100,
                conduit_type="ПВХ100",
                color="Серый",
                path_json={"origin": "PROJECT"},
            )
        )
        uow.commit()

    changed = sync.preview(
        project_id=project_id,
        batch=_batch(
            _socket(
                load_name="Новое назначение",
                gofra_id="100.PND25",
            )
        ),
    )
    load_change = next(item for item in changed.changes if item.field == "LOAD_NAME")
    sync.apply_dwg_to_project(
        changed,
        selected_paths={load_change.field_path},
        confirmed=True,
    )

    with database.engine.connect() as connection:
        facts = connection.scalar(select(cable_line.c.cable_facts_json))
        device_fields = connection.scalar(select(field_device.c.normalized_fields_json))
        assert facts["LOAD_NAME"] == "Новое назначение"
        assert device_fields["LOAD_NAME"] == "Новое назначение"
        assert device_fields["GOFRA_ID"] == "001.PND25"
        assert connection.scalar(select(func.count()).select_from(conduit)) == 2


def test_existing_line_can_adopt_only_load_name_from_a_new_document_binding(database):
    objects = ObjectService(database.engine)
    project_id = objects.create_project(ProjectCard(name="Adopt", project_code="ADOPT"))
    sync = DwgSyncService(database.engine)
    initial = sync.preview(
        project_id=project_id,
        batch=_batch(_socket(load_name="Старое назначение"), "C:/fixture/source-a.dwg"),
    )
    sync.apply_dwg_to_project(initial, selected_paths=_applicable(initial), confirmed=True)
    with UnitOfWork(database.engine) as uow:
        row = uow.execute(select(cable_line)).mappings().one()
        facts = dict(row["cable_facts_json"])
        facts["LOAD_NAME"] = ""
        uow.execute(
            update(cable_line).where(cable_line.c.id == row["id"]).values(cable_facts_json=facts)
        )
        uow.commit()

    current = sync.preview(
        project_id=project_id,
        batch=_batch(
            _socket(load_name="Свет улица"),
            "C:/fixture/source-b.dwg",
        ),
    )
    assert any(item.field == "$" for item in current.changes)
    load_change = next(item for item in current.changes if item.field == "LOAD_NAME")
    assert load_change.change_class == ChangeClass.DWG_CHANGED
    sync.apply_dwg_to_project(
        current,
        selected_paths={load_change.field_path},
        confirmed=True,
    )

    with database.engine.connect() as connection:
        facts = connection.scalar(select(cable_line.c.cable_facts_json))
        assert facts["LOAD_NAME"] == "Свет улица"
        assert connection.scalar(select(func.count()).select_from(field_device)) == 1
