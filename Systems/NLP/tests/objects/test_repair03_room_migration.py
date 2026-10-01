from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from nl_project_2.objects.models import ProjectCard
from nl_project_2.objects.service import ObjectService
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import field_device
from nl_project_2.persistence.uow import UnitOfWork


def test_canonical_room_migration_previews_reuses_preserves_and_reassigns(database):
    service = ObjectService(database.engine)
    project_id = service.create_project(
        ProjectCard(name="05 44 Богданович", project_code="ПСВ.05.44.01")
    )
    building_id = service.add_building(project_id, "Дом")
    first_id = service.add_room(
        project_id=project_id,
        building_id=building_id,
        name="1. Старое название",
        base_mark_mm="15",
        height_m="3.2",
        marking_color="#123456",
    )
    alias_id = service.add_room(
        project_id=project_id,
        building_id=building_id,
        name="Гардероб",
        base_mark_mm=None,
        height_m=None,
        marking_color="#FFFFFF",
    )
    street_id = service.add_room(
        project_id=project_id,
        building_id=building_id,
        name="Улица",
        base_mark_mm=None,
        height_m=None,
        marking_color="#ABCDEF",
    )
    device_id = new_id()
    with UnitOfWork(database.engine) as uow:
        uow.execute(
            field_device.insert().values(
                id=device_id,
                project_id=project_id,
                block_kind="SOCKET_IN",
                room_id=alias_id,
                normalized_fields_json={"BUILDING": "Дом", "ROOM": "Гардероб"},
            )
        )
        uow.commit()

    names = ("1. Прихожая", "2. Гардероб")
    preview = service.preview_room_migration(
        project_id=project_id,
        building_id=building_id,
        canonical_names=names,
    )
    assert not preview.ambiguities
    assert [(item.action, item.canonical_name) for item in preview.actions] == [
        ("RENAME", "1. Прихожая"),
        ("CREATE", "2. Гардероб"),
    ]
    assert preview.device_reassignments == ((device_id, "2. Гардероб"),)

    result = service.migrate_rooms(
        project_id=project_id,
        building_id=building_id,
        canonical_names=names,
    )
    detail = service.get_project(project_id)
    by_name = {item.name: item for item in detail.rooms}
    assert by_name["1. Прихожая"].id == first_id
    assert by_name["1. Прихожая"].base_mark_mm == 15
    assert by_name["1. Прихожая"].height_m == Decimal("3.2")
    assert by_name["1. Прихожая"].marking_color == "#123456"
    assert by_name["2. Гардероб"].marking_color != "#FFFFFF"
    assert by_name["Улица"].id == street_id
    with database.engine.connect() as connection:
        assert (
            connection.scalar(select(field_device.c.room_id).where(field_device.c.id == device_id))
            == by_name["2. Гардероб"].id
        )
    assert result.device_reassignments == ((device_id, "2. Гардероб"),)

    repeated = service.migrate_rooms(
        project_id=project_id,
        building_id=building_id,
        canonical_names=names,
    )
    assert {item.action for item in repeated.actions} == {"KEEP"}
    assert repeated.device_reassignments == ()
