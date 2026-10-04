from __future__ import annotations

import os
import stat
from decimal import Decimal

from sqlalchemy import func, select

from nl_project_2.catalog.installer import CatalogInstaller
from nl_project_2.catalog.payload import load_packaged_payload
from nl_project_2.objects.models import ProjectCard, ProjectSettings
from nl_project_2.objects.service import ObjectService
from nl_project_2.operations.clean_seed import create_clean_seed
from nl_project_2.persistence.database import DatabaseManager
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import cable_line, project_setting, room


def test_clean_seed_copies_only_project_building_room_and_confirmed_settings(tmp_path):
    legacy = tmp_path / "legacy.sqlite"
    handle = DatabaseManager().initialize_new(legacy)
    CatalogInstaller(handle.engine).install(load_packaged_payload())
    objects = ObjectService(handle.engine)

    project_id = objects.create_project(
        ProjectCard(
            name="05 44 Богданович",
            project_code="NL.05.441.03",
            object_type="Частный дом",
            note="seed",
        )
    )
    building_id = objects.add_building(project_id, "Дом_2")
    objects.add_room(
        project_id=project_id,
        building_id=building_id,
        name="Постирочная",
        base_mark_mm=Decimal("-200"),
        height_m=Decimal("4.6"),
        marking_color="#D7E3FC",
    )
    objects.save_settings(
        project_id,
        ProjectSettings(
            project_folder="D:/legacy/project",
            output_folder="D:/legacy/output",
            initial_page_number=7,
            cable_reserve_at_board_m=Decimal("1.5"),
        ),
    )
    with handle.engine.begin() as connection:
        connection.execute(
            cable_line.insert().values(
                id=new_id(),
                project_id=project_id,
                designation="106",
                system_kind="POWER",
                cable_facts_json={"BOARD": "ЩР-21", "CABLE_TYPE": "3x2.5"},
            )
        )
    handle.close()

    target = tmp_path / "clean" / "nl_project_3.sqlite"
    receipt = create_clean_seed(
        legacy_database=legacy,
        target_database=target,
        legacy_snapshot_root=tmp_path / "backups" / "legacy_nlp2",
    )

    assert receipt.project_count == 1
    assert receipt.building_count == 1
    assert receipt.room_count == 1
    assert receipt.copied_setting_keys == ()
    assert receipt.source_excluded_counts["cable_line"] == 1
    assert all(value == 0 for value in receipt.target_forbidden_counts.values())
    snapshot = tmp_path / "backups" / "legacy_nlp2"
    snapshots = list(snapshot.glob("*.sqlite"))
    assert len(snapshots) == 1
    assert not os.stat(snapshots[0]).st_mode & stat.S_IWRITE

    reopened = DatabaseManager().open_existing(target)
    detail = ObjectService(reopened.engine).get_project(
        ObjectService(reopened.engine).list_projects()[0].id
    )
    assert detail.card.name == "05 44 Богданович"
    assert detail.card.project_code == "NL.05.441.03"
    assert [building.name for building in detail.buildings] == ["Дом_2"]
    assert [item.name for item in detail.rooms] == ["Постирочная"]
    assert detail.rooms[0].base_mark_mm == Decimal("-200")
    assert detail.rooms[0].height_m == Decimal("4.6")
    assert detail.rooms[0].marking_color == "#D7E3FC"
    with reopened.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(cable_line)) == 0
        assert connection.scalar(select(func.count()).select_from(project_setting)) == 0
        assert connection.scalar(select(func.count()).select_from(room)) == 1
    reopened.close()


def test_clean_seed_copies_only_explicitly_confirmed_setting_keys(tmp_path):
    legacy = tmp_path / "legacy.sqlite"
    handle = DatabaseManager().initialize_new(legacy)
    CatalogInstaller(handle.engine).install(load_packaged_payload())
    objects = ObjectService(handle.engine)
    project_id = objects.create_project(ProjectCard(name="Object", project_code="OBJ"))
    building_id = objects.add_building(project_id, "House")
    objects.add_room(
        project_id=project_id,
        building_id=building_id,
        name="Room",
        base_mark_mm=None,
        height_m=Decimal("3"),
        marking_color="#EEF0F2",
    )
    objects.save_settings(
        project_id,
        ProjectSettings(
            project_folder="D:/confirmed",
            output_folder="D:/not-confirmed",
            initial_page_number=12,
        ),
    )
    handle.close()

    target = tmp_path / "nl_project_3.sqlite"
    receipt = create_clean_seed(
        legacy_database=legacy,
        target_database=target,
        legacy_snapshot_root=tmp_path / "legacy",
        copied_setting_keys=("project_folder",),
    )
    assert receipt.copied_setting_keys == ("project_folder",)

    reopened = DatabaseManager().open_existing(target)
    project_id_3 = ObjectService(reopened.engine).list_projects()[0].id
    detail = ObjectService(reopened.engine).get_project(project_id_3)
    assert detail.settings.project_folder == "D:/confirmed"
    assert detail.settings.output_folder == ""
    assert detail.settings.initial_page_number is None
    reopened.close()
