from __future__ import annotations

from sqlalchemy import func, select

from nl_project_2.objects.models import ProjectCard
from nl_project_2.objects.service import ObjectService
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    board,
    field_device,
    passport_definition,
    project_instance,
    room,
)
from nl_project_2.persistence.uow import UnitOfWork

ALIASES = {
    "Прихожая": "1. Прихожая",
    "Кухня": "5. Кухня-ниша",
    "25. Тех. помещение": "21. Тех. помещения",
}


def _add_room(service, project_id, building_id, name):
    return service.add_room(
        project_id=project_id,
        building_id=building_id,
        name=name,
        base_mark_mm=None,
        height_m=None,
        marking_color="#D7E3FC",
    )


def test_explicit_alias_merge_reassigns_every_reference_then_retires_aliases(database):
    service = ObjectService(database.engine)
    project_id = service.create_project(
        ProjectCard(name="05 44 Богданович", project_code="ПСВ.05.44.01")
    )
    building_id = service.add_building(project_id, "Дом")
    targets = {
        name: _add_room(service, project_id, building_id, name)
        for name in ALIASES.values()
    }
    sources = {
        name: _add_room(service, project_id, building_id, name) for name in ALIASES
    }
    street_id = _add_room(service, project_id, building_id, "Улица")

    with UnitOfWork(database.engine) as uow:
        passport_id = uow.execute(
            select(passport_definition.c.id).limit(1)
        ).scalar_one()
        board_id = new_id()
        instance_id = new_id()
        device_id = new_id()
        uow.execute(
            board.insert().values(
                id=board_id,
                project_id=project_id,
                designation="ЩР-1",
                board_kind="DISTRIBUTION",
                room_id=sources["Прихожая"],
            )
        )
        uow.execute(
            project_instance.insert().values(
                id=instance_id,
                project_id=project_id,
                designation="A01",
                room_id=sources["Кухня"],
                passport_definition_id=passport_id,
                parameters_json={},
            )
        )
        uow.execute(
            field_device.insert().values(
                id=device_id,
                project_id=project_id,
                block_kind="SOCKET_IN",
                room_id=sources["25. Тех. помещение"],
                normalized_fields_json={"ROOM": "25. Тех. помещение"},
            )
        )
        uow.commit()

    preview = service.preview_room_alias_merge(
        project_id=project_id, building_id=building_id, aliases=ALIASES
    )
    assert [(a.source_name, a.target_name) for a in preview.actions] == list(
        ALIASES.items()
    )
    assert [a.reference_count for a in preview.actions] == [1, 1, 1]
    assert preview.actions[0].board_reassignments == 1
    assert preview.actions[1].project_instance_reassignments == 1
    assert preview.actions[2].field_device_reassignments == 1

    result = service.merge_room_aliases(
        project_id=project_id, building_id=building_id, aliases=ALIASES
    )
    assert [a.reference_count for a in result.actions] == [1, 1, 1]

    reopened = ObjectService(database.engine).get_project(project_id)
    names = [item.name for item in reopened.rooms]
    assert all(source not in names for source in ALIASES)
    assert all(names.count(target) == 1 for target in ALIASES.values())
    assert names.count("Улица") == 1
    assert next(item.id for item in reopened.rooms if item.name == "Улица") == street_id

    with database.engine.connect() as connection:
        assert (
            connection.scalar(select(board.c.room_id).where(board.c.id == board_id))
            == targets["1. Прихожая"]
        )
        assert (
            connection.scalar(
                select(project_instance.c.room_id).where(
                    project_instance.c.id == instance_id
                )
            )
            == targets["5. Кухня-ниша"]
        )
        assert (
            connection.scalar(
                select(field_device.c.room_id).where(field_device.c.id == device_id)
            )
            == targets["21. Тех. помещения"]
        )
        for source_id in sources.values():
            assert (
                connection.scalar(
                    select(func.count()).select_from(room).where(room.c.id == source_id)
                )
                == 0
            )
        for table in (board, project_instance, field_device):
            assert (
                connection.scalar(
                    select(func.count())
                    .select_from(table)
                    .where(table.c.room_id.in_(sources.values()))
                )
                == 0
            )


def test_room_list_uses_leading_number_natural_order_then_external_zone(database):
    service = ObjectService(database.engine)
    project_id = service.create_project(ProjectCard(name="Object", project_code="P-04"))
    building_id = service.add_building(project_id, "Дом")
    names = ["Улица", *(f"{number}. Помещение {number}" for number in range(21, 0, -1))]
    for name in names:
        _add_room(service, project_id, building_id, name)

    assert [item.name for item in service.get_project(project_id).rooms] == [
        *(f"{number}. Помещение {number}" for number in range(1, 22)),
        "Улица",
    ]
