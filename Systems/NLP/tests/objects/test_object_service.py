from __future__ import annotations

from decimal import Decimal

import pytest

from nl_project_2.objects.models import ProjectCard, ProjectSettings
from nl_project_2.objects.service import DuplicateIdentityError, ObjectService
from nl_project_2.persistence.database import DatabaseManager


def test_object_card_rooms_settings_and_semantic_reopen(database):
    service = ObjectService(database.engine)
    project_id = service.create_project(
        ProjectCard(
            name="Новый объект",
            project_code="NP-001",
            object_type="",
            address="Екатеринбург",
            total_area_m2=Decimal("1234.50"),
            customer="Заказчик",
            responsible_designer="Проектировщик",
            note="Примечание",
        )
    )
    first = service.add_building(project_id, "Главное здание")
    second = service.add_building(project_id, "Гостевой дом")
    service.add_room(
        project_id=project_id,
        building_id=first,
        name="Техническое помещение",
        base_mark_mm=Decimal("-250"),
        height_m=Decimal("3.150"),
        marking_color="#12AB34",
    )
    service.add_room(
        project_id=project_id,
        building_id=second,
        name="Техническое помещение",
        base_mark_mm=0,
        height_m="2.8",
        marking_color="#AA5500",
    )
    with pytest.raises(DuplicateIdentityError):
        service.add_room(
            project_id=project_id,
            building_id=first,
            name=" техническое   помещение ",
            base_mark_mm=0,
            height_m=2,
            marking_color="#FFFFFF",
        )
    service.save_settings(
        project_id,
        ProjectSettings(
            project_folder="D:/Projects/NP-001",
            output_folder="D:/Projects/NP-001/Output",
            versions_folder="D:/Projects/NP-001/Versions",
            initial_page_number=7,
            cable_reserve_at_board_m=Decimal("1.25"),
        ),
    )
    path = database.path
    database.close()
    reopened = DatabaseManager().open_existing(path)
    try:
        detail = ObjectService(reopened.engine).get_project(project_id)
    finally:
        reopened.close()
    assert detail.card.total_area_m2 == Decimal("1234.50")
    assert detail.card.object_type == ""
    assert len(detail.buildings) == 2
    assert [item.name for item in detail.rooms] == [
        "Техническое помещение",
        "Техническое помещение",
    ]
    assert detail.rooms[0].base_mark_mm == Decimal("-250")
    assert {item.marking_color for item in detail.rooms} == {"#12AB34", "#AA5500"}
    assert detail.settings.initial_page_number == 7
    assert detail.settings.cable_reserve_at_board_m == Decimal("1.25")


def test_project_registry_edit_and_unique_code(database):
    service = ObjectService(database.engine)
    first = service.create_project(ProjectCard(name="Первый", project_code="P-1"))
    second = service.create_project(ProjectCard(name="Второй", project_code="P-2"))
    with pytest.raises(DuplicateIdentityError):
        service.update_project(second, ProjectCard(name="Второй", project_code="p-1"))
    service.update_project(first, ProjectCard(name="Первый изменён", project_code="P-1A"))
    assert {item.project_code: item.name for item in service.list_projects()} == {
        "P-1A": "Первый изменён",
        "P-2": "Второй",
    }
