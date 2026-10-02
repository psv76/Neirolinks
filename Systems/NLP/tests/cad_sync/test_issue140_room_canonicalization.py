import pytest
from PySide6.QtCore import Qt
from sqlalchemy import func, select
from test_p0003_reconciliation import _observation
from test_repair03_canonical_rooms import _applicable, _batch

from nl_project_2.cables.service import CableService
from nl_project_2.cad_sync import ChangeClass, DwgSyncService
from nl_project_2.cad_sync.service import StaleProposalError
from nl_project_2.objects.models import ProjectCard
from nl_project_2.objects.service import ObjectService
from nl_project_2.persistence.database import DatabaseManager
from nl_project_2.persistence.schema import (
    building,
    cable_line,
    cable_point,
    cable_segment,
    conduit,
    dwg_baseline,
    dwg_observation,
    dwg_scan,
    dwg_sync_change,
    dwg_sync_operation,
    field_device,
    project,
    room,
)


def _socket(room_name="Постирочная", building_name="Дом_2", *, x=100, **attributes):
    return _observation(
        "SOCKET_IN",
        handle="A102",
        cable_id="102",
        attributes={"BUILDING": building_name, "ROOM": room_name, **attributes},
        x=x,
    )


def _project(database):
    objects = ObjectService(database.engine)
    project_id = objects.create_project(ProjectCard(name="Room regression", project_code="ROOM"))
    building_id = objects.add_building(project_id, "Дом_2")
    return objects, project_id, building_id


def _add_room(objects, project_id, building_id, name="Постирочная"):
    return objects.add_room(
        project_id=project_id,
        building_id=building_id,
        name=name,
        base_mark_mm=None,
        height_m=None,
        marking_color="#D7E3FC",
    )


def _import(sync, project_id, batch):
    proposal = sync.preview(project_id=project_id, batch=batch)
    sync.apply_dwg_to_project(proposal, selected_paths=_applicable(proposal), confirmed=True)


def _room_change(proposal):
    return next(item for item in proposal.changes if item.field == "ROOM")


def _state(engine):
    with engine.connect() as connection:
        return {
            table.name: [dict(row) for row in connection.execute(select(table)).mappings()]
            for table in (
                project,
                building,
                room,
                field_device,
                cable_line,
                cable_point,
                cable_segment,
                conduit,
                dwg_scan,
                dwg_observation,
                dwg_baseline,
                dwg_sync_operation,
                dwg_sync_change,
            )
        }


def test_unchanged_dwg_can_link_room_created_after_import_and_survive_reopen(database):
    objects, project_id, building_id = _project(database)
    sync = DwgSyncService(database.engine)
    batch = _batch(_socket())
    initial = sync.preview(project_id=project_id, batch=batch)
    sync.apply_dwg_to_project(initial, selected_paths=_applicable(initial), confirmed=True)
    with database.engine.connect() as connection:
        device = connection.execute(select(field_device)).mappings().one()
        assert device["room_id"] is None
        assert device["normalized_fields_json"]["BUILDING"] == "Дом_2"
        assert device["normalized_fields_json"]["ROOM"] == "Постирочная"
        assert connection.scalar(select(func.count()).select_from(room)) == 0
    assert CableService(database.engine).line_cards(project_id)[0]["room_names"] == ""

    room_id = _add_room(objects, project_id, building_id)
    repeated = sync.preview(project_id=project_id, batch=batch)
    change = next(item for item in repeated.changes if item.field == "ROOM")
    assert change.baseline_value == change.project_value == change.dwg_value == "Постирочная"
    assert change.change_class == ChangeClass.DWG_CHANGED
    sync.apply_dwg_to_project(repeated, selected_paths={change.field_path}, confirmed=True)

    with DatabaseManager().open_existing(database.path) as reopened:
        with reopened.engine.connect() as connection:
            assert connection.scalar(select(field_device.c.room_id)) == room_id
            assert connection.scalar(select(func.count()).select_from(room)) == 1
            assert connection.scalar(select(func.count()).select_from(building)) == 1
            assert connection.exec_driver_sql("PRAGMA integrity_check").scalar() == "ok"
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        assert (
            CableService(reopened.engine).line_cards(project_id)[0]["room_names"] == "Постирочная"
        )
        stable = DwgSyncService(reopened.engine).preview(project_id=project_id, batch=batch)
        assert all(item.change_class == ChangeClass.EQUAL for item in stable.changes)


@pytest.mark.parametrize("canonical_name", ["Постирочная", "5. Постирочная"])
def test_existing_canonical_relation_is_not_reassigned(database, canonical_name):
    objects, project_id, building_id = _project(database)
    room_id = _add_room(objects, project_id, building_id, canonical_name)
    sync = DwgSyncService(database.engine)
    batch = _batch(_socket())
    _import(sync, project_id, batch)
    before = _state(database.engine)
    repeated = sync.preview(project_id=project_id, batch=batch)
    assert not any(item.detail_status == "ROOM_CANONICALIZATION" for item in repeated.changes)
    assert _state(database.engine) == before
    with database.engine.connect() as connection:
        assert connection.scalar(select(field_device.c.room_id)) == room_id


@pytest.mark.parametrize(
    ("observed_room", "observed_building", "existing_rooms"),
    [
        ("Постирочная", "Дом_2", ()),
        ("1. Старое имя", "Дом_2", ("1. Постирочная", "1. Кладовая")),
        ("Постирочная", "Другой дом", ("Постирочная",)),
    ],
    ids=["unresolved", "ambiguous", "wrong-building"],
)
def test_unresolved_or_ambiguous_room_is_never_guessed_or_created(
    database, observed_room, observed_building, existing_rooms
):
    objects, project_id, building_id = _project(database)
    sync = DwgSyncService(database.engine)
    batch = _batch(_socket(observed_room, observed_building))
    _import(sync, project_id, batch)
    for name in existing_rooms:
        _add_room(objects, project_id, building_id, name)
    repeated = sync.preview(project_id=project_id, batch=batch)
    assert _room_change(repeated).change_class == ChangeClass.EQUAL
    assert _room_change(repeated).display_context["room_name"].startswith("Не разрешено")
    changed = sync.preview(
        project_id=project_id,
        batch=_batch(_socket(observed_room, observed_building, DEVICE_NAME="Новое имя")),
    )
    device_change = next(item for item in changed.changes if item.field == "DEVICE_NAME")
    sync.apply_dwg_to_project(changed, selected_paths={device_change.field_path}, confirmed=True)
    with database.engine.connect() as connection:
        assert connection.scalar(select(field_device.c.room_id)) is None
        assert connection.scalar(select(func.count()).select_from(room)) == len(existing_rooms)
        assert connection.scalar(select(func.count()).select_from(building)) == 1


def test_canonicalization_does_not_apply_unselected_dwg_changes(database):
    objects, project_id, building_id = _project(database)
    sync = DwgSyncService(database.engine)
    _import(sync, project_id, _batch(_socket()))
    room_id = _add_room(objects, project_id, building_id)
    before = _state(database.engine)
    proposal = sync.preview(
        project_id=project_id,
        batch=_batch(
            _socket(
                x=9000,
                LOAD_NAME="Непринятое назначение",
                MOUNT_WAY="По полу",
                GOFRA_TYPE="ПНД25",
                GOFRA_COLOR="Черный",
                GOFRA_ID="001.PND25",
            )
        ),
    )
    change = _room_change(proposal)
    assert change.detail_status == "ROOM_CANONICALIZATION"
    sync.apply_dwg_to_project(proposal, selected_paths={change.field_path}, confirmed=True)
    after = _state(database.engine)
    for name in ("building", "room", "cable_line", "cable_point", "cable_segment", "conduit"):
        assert after[name] == before[name]
    assert after["field_device"][0]["room_id"] == room_id
    assert (
        after["field_device"][0]["normalized_fields_json"]
        == before["field_device"][0]["normalized_fields_json"]
    )


def test_canonicalization_can_be_accepted_with_another_selected_field(database):
    objects, project_id, building_id = _project(database)
    sync = DwgSyncService(database.engine)
    _import(sync, project_id, _batch(_socket()))
    room_id = _add_room(objects, project_id, building_id)
    proposal = sync.preview(
        project_id=project_id, batch=_batch(_socket(DEVICE_NAME="Принятое имя"))
    )
    selected = {
        item.field_path for item in proposal.changes if item.field in {"ROOM", "DEVICE_NAME"}
    }
    sync.apply_dwg_to_project(proposal, selected_paths=selected, confirmed=True)
    with database.engine.connect() as connection:
        device = connection.execute(select(field_device)).mappings().one()
        assert device["room_id"] == room_id
        assert device["normalized_fields_json"]["DEVICE_NAME"] == "Принятое имя"


def test_unselected_canonicalization_does_not_link_room_implicitly(database):
    objects, project_id, building_id = _project(database)
    sync = DwgSyncService(database.engine)
    _import(sync, project_id, _batch(_socket()))
    _add_room(objects, project_id, building_id)
    proposal = sync.preview(project_id=project_id, batch=_batch(_socket(LOAD_NAME="Принятое имя")))
    assert _room_change(proposal).detail_status == "ROOM_CANONICALIZATION"
    change = next(item for item in proposal.changes if item.field == "LOAD_NAME")
    sync.apply_dwg_to_project(proposal, selected_paths={change.field_path}, confirmed=True)
    with database.engine.connect() as connection:
        assert connection.scalar(select(field_device.c.room_id)) is None


def test_late_canonicalization_uses_existing_approved_room_alias_rules(database):
    objects, project_id, building_id = _project(database)
    sync = DwgSyncService(database.engine)
    batch = _batch(_socket())
    _import(sync, project_id, batch)
    room_id = _add_room(objects, project_id, building_id, "5. Постирочная")
    proposal = sync.preview(project_id=project_id, batch=batch)
    sync.apply_dwg_to_project(
        proposal, selected_paths={_room_change(proposal).field_path}, confirmed=True
    )
    with database.engine.connect() as connection:
        assert connection.scalar(select(field_device.c.room_id)) == room_id
        assert (
            connection.scalar(select(field_device.c.normalized_fields_json))["ROOM"]
            == "Постирочная"
        )
    assert CableService(database.engine).line_cards(project_id)[0]["room_names"] == "5. Постирочная"


def test_project_and_dwg_room_renames_keep_three_way_conflict_semantics(database):
    objects, project_id, building_id = _project(database)
    original_id = _add_room(objects, project_id, building_id)
    sync = DwgSyncService(database.engine)
    _import(sync, project_id, _batch(_socket()))
    destination_id = _add_room(objects, project_id, building_id, "Кладовая")
    dwg_rename = sync.preview(project_id=project_id, batch=_batch(_socket("Кладовая")))
    assert _room_change(dwg_rename).change_class == ChangeClass.DWG_CHANGED
    assert _room_change(dwg_rename).detail_status != "ROOM_CANONICALIZATION"
    sync.apply_dwg_to_project(
        dwg_rename, selected_paths={_room_change(dwg_rename).field_path}, confirmed=True
    )
    with database.engine.connect() as connection:
        assert connection.scalar(select(field_device.c.room_id)) == destination_id
        assert original_id != destination_id
    objects.update_room(
        project_id=project_id,
        room_id=destination_id,
        building_id=building_id,
        name="Гардероб",
        base_mark_mm=None,
        height_m=None,
        marking_color="#D7E3FC",
    )
    project_rename = sync.preview(project_id=project_id, batch=_batch(_socket("Кладовая")))
    assert _room_change(project_rename).change_class == ChangeClass.PROJECT_CHANGED
    both = sync.preview(project_id=project_id, batch=_batch(_socket("Кабинет")))
    assert _room_change(both).change_class == ChangeClass.BOTH_CHANGED_CONFLICT
    assert not any(item.detail_status == "ROOM_CANONICALIZATION" for item in both.changes)


def test_dwg_building_rename_resolves_room_in_selected_building(database):
    objects, project_id, building_id = _project(database)
    _add_room(objects, project_id, building_id)
    sync = DwgSyncService(database.engine)
    _import(sync, project_id, _batch(_socket()))
    other_building = objects.add_building(project_id, "Гараж")
    other_room = _add_room(objects, project_id, other_building)
    proposal = sync.preview(project_id=project_id, batch=_batch(_socket(building_name="Гараж")))
    change = next(item for item in proposal.changes if item.field == "BUILDING")
    assert change.change_class == ChangeClass.DWG_CHANGED
    assert not any(item.detail_status == "ROOM_CANONICALIZATION" for item in proposal.changes)
    sync.apply_dwg_to_project(proposal, selected_paths={change.field_path}, confirmed=True)
    with database.engine.connect() as connection:
        assert connection.scalar(select(field_device.c.room_id)) == other_room


def test_project_building_change_and_both_changed_conflict_remain_project_owned(database):
    objects, project_id, building_id = _project(database)
    room_id = _add_room(objects, project_id, building_id)
    sync = DwgSyncService(database.engine)
    _import(sync, project_id, _batch(_socket()))
    garage_id = objects.add_building(project_id, "Гараж")
    objects.update_room(
        project_id=project_id,
        room_id=room_id,
        building_id=garage_id,
        name="Постирочная",
        base_mark_mm=None,
        height_m=None,
        marking_color="#D7E3FC",
    )
    proposal = sync.preview(project_id=project_id, batch=_batch(_socket()))
    change = next(item for item in proposal.changes if item.field == "BUILDING")
    assert change.project_value == "Гараж"
    assert change.change_class == ChangeClass.PROJECT_CHANGED
    both = sync.preview(project_id=project_id, batch=_batch(_socket(building_name="Баня")))
    assert (
        next(item for item in both.changes if item.field == "BUILDING").change_class
        == ChangeClass.BOTH_CHANGED_CONFLICT
    )
    assert not any(item.detail_status == "ROOM_CANONICALIZATION" for item in both.changes)


def test_failure_rolls_back_room_relation_and_all_sync_writes(database):
    objects, project_id, building_id = _project(database)
    sync = DwgSyncService(database.engine)
    batch = _batch(_socket())
    _import(sync, project_id, batch)
    _add_room(objects, project_id, building_id)
    proposal = sync.preview(project_id=project_id, batch=batch)
    before = _state(database.engine)

    def fail_after_relation():
        raise RuntimeError("failure after canonicalization")

    with pytest.raises(RuntimeError, match="failure after canonicalization"):
        sync.apply_dwg_to_project(
            proposal,
            selected_paths={_room_change(proposal).field_path},
            confirmed=True,
            failure_hook=fail_after_relation,
        )
    assert _state(database.engine) == before


def test_room_change_after_preview_requires_new_preview(database):
    objects, project_id, building_id = _project(database)
    sync = DwgSyncService(database.engine)
    batch = _batch(_socket())
    _import(sync, project_id, batch)
    room_id = _add_room(objects, project_id, building_id)
    proposal = sync.preview(project_id=project_id, batch=batch)
    objects.update_room(
        project_id=project_id,
        room_id=room_id,
        building_id=building_id,
        name="Кладовая",
        base_mark_mm=None,
        height_m=None,
        marking_color="#D7E3FC",
    )
    before = _state(database.engine)
    with pytest.raises(StaleProposalError):
        sync.apply_dwg_to_project(
            proposal, selected_paths={_room_change(proposal).field_path}, confirmed=True
        )
    assert _state(database.engine) == before


def test_preview_presents_canonicalization_as_explicit_selectable_room_link(database, qtbot):
    from nl_project_2.presentation.object_workspace import DwgSyncPreviewDialog

    objects, project_id, building_id = _project(database)
    sync = DwgSyncService(database.engine)
    batch = _batch(_socket())
    _import(sync, project_id, batch)
    _add_room(objects, project_id, building_id)
    proposal = sync.preview(project_id=project_id, batch=batch)
    dialog = DwgSyncPreviewDialog(proposal)
    qtbot.addWidget(dialog)
    index = next(i for i, item in enumerate(proposal.changes) if item.field == "ROOM")
    assert dialog.table.item(index, 5).text() == "Привязать помещение"
    assert "Помещение существует в Project" in dialog.table.item(index, 9).text()
    selector = dialog.table.item(index, 0)
    assert selector.flags() & Qt.ItemFlag.ItemIsUserCheckable
    assert dialog.selected_paths() == set()
    selector.setCheckState(Qt.CheckState.Checked)
    assert dialog.selected_paths() == {_room_change(proposal).field_path}
