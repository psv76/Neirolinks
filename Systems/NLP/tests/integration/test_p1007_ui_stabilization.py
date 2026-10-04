from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QRect
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QHeaderView, QMessageBox

import nl_project_2.presentation.object_workspace as object_workspace_module
from nl_project_2.cad_contract import (
    BlockDefinitionMetadata,
    CadObservation,
    CadObservationBatch,
)
from nl_project_2.cad_sync import DwgSyncError, DwgSyncService
from nl_project_2.config import PathConfig
from nl_project_2.integration import IntegratedUiService
from nl_project_2.local_state import UiStateStore
from nl_project_2.main_window import MainWindow
from nl_project_2.objects.models import ProjectCard
from nl_project_2.objects.runtime import ApplicationRuntime
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    cable_line,
    cable_point,
    cable_point_field_device,
    dwg_document_binding,
    dwg_observation,
    dwg_scan,
    field_device,
)
from nl_project_2.persistence.uow import UnitOfWork
from nl_project_2.presentation.lines_workspace import COLUMNS, LinesWorkspace
from nl_project_2.presentation.object_workspace import (
    DwgSyncPreviewDialog,
    ObjectWorkspace,
    ProjectDialog,
    RoomDialog,
)
from nl_project_2.presentation.room_presentation import ROOM_MARKERS_ROLE
from nl_project_2.presentation.validation_center import ValidationCenterWidget


def _paths(tmp_path) -> PathConfig:
    return PathConfig(
        app_root=tmp_path / "app",
        backup_root=tmp_path / "backups",
        release_root=tmp_path / "releases",
        user_projects_root=tmp_path / "projects",
        local_state_root=tmp_path / "state",
    )


def test_project_room_rename_refreshes_lines_in_same_session(qtbot, tmp_path, monkeypatch):
    runtime = ApplicationRuntime.open(_paths(tmp_path))
    project_id = runtime.objects.create_project(
        ProjectCard(name="Room rename", project_code="ROOM-RENAME")
    )
    building_id = runtime.objects.add_building(project_id, "Дом")
    room_id = runtime.objects.add_room(
        project_id=project_id,
        building_id=building_id,
        name="1. Прихожая",
        base_mark_mm=None,
        height_m=None,
        marking_color="#D7E3FC",
    )
    line_id = new_id()
    device_id = new_id()
    point_id = new_id()
    with UnitOfWork(runtime.database.engine) as uow:
        uow.execute(
            cable_line.insert().values(
                id=line_id,
                project_id=project_id,
                designation="101",
                system_kind="POWER",
                cable_facts_json={"LOAD_NAME": "Розетки прихожей"},
            )
        )
        uow.execute(
            field_device.insert().values(
                id=device_id,
                project_id=project_id,
                block_kind="SOCKET_IN",
                room_id=room_id,
                normalized_fields_json={"ROOM": "raw DWG evidence"},
            )
        )
        uow.execute(
            cable_point.insert().values(
                id=point_id,
                project_id=project_id,
                cable_line_id=line_id,
                field_device_id=None,
                point_kind="DEVICE_POINT",
                ordinal=0,
                logical_identity=f"{line_id}:0",
                origin_kind="PROJECT",
                migration_state="CONFIRMED",
            )
        )
        uow.execute(
            cable_point_field_device.insert().values(
                id=new_id(),
                project_id=project_id,
                cable_point_id=point_id,
                field_device_id=device_id,
            )
        )
        uow.commit()
    widget = ObjectWorkspace(runtime)
    qtbot.addWidget(widget)
    widget.open_project(project_id)
    room_column = next(index for index, column in enumerate(COLUMNS) if column.key == "room_names")
    assert widget.lines_workspace.table.item(0, room_column).text() == "1. Прихожая"

    original_load = RoomDialog.load_room

    def load_renamed(dialog, room):
        original_load(dialog, room)
        dialog.name.setText("1. Холл")

    monkeypatch.setattr(RoomDialog, "load_room", load_renamed)
    monkeypatch.setattr(RoomDialog, "exec", lambda _dialog: QDialog.DialogCode.Accepted)
    widget._edit_room(0, 0)
    item = widget.lines_workspace.table.item(0, room_column)
    assert item.text() == "1. Холл"
    assert item.data(ROOM_MARKERS_ROLE) == ({"id": room_id, "name": "1. Холл", "color": "#D7E3FC"},)
    runtime.close()


def test_successful_dwg_import_refreshes_lines_without_preview(
    qtbot, tmp_path, monkeypatch
):
    runtime = ApplicationRuntime.open(_paths(tmp_path))
    project_id = runtime.objects.create_project(
        ProjectCard(name="Sync refresh", project_code="SYNC-REFRESH")
    )
    widget = ObjectWorkspace(runtime)
    qtbot.addWidget(widget)
    widget.open_project(project_id)
    assert widget.lines_workspace.table.rowCount() == 0

    monkeypatch.setattr(
        object_workspace_module,
        "build_dwg_update_plan",
        lambda _proposal: SimpleNamespace(
            import_paths=frozenset({"N1201:$"}),
            write_paths=frozenset(),
            conflicts=(),
            problems=(),
            blocked_lines=(),
        ),
    )

    def import_line(_proposal, *, selected_paths, confirmed):
        assert selected_paths == frozenset({"N1201:$"})
        assert confirmed
        with UnitOfWork(runtime.database.engine) as uow:
            uow.execute(
                cable_line.insert().values(
                    id=new_id(),
                    project_id=project_id,
                    designation="120",
                    system_kind="POWER",
                    cable_facts_json={"LOAD_NAME": "Розетки 120"},
                )
            )
            uow.commit()
        return "operation-id"

    messages = []
    monkeypatch.setattr(runtime.dwg_sync, "apply_dwg_to_project", import_line)
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda _parent, title, message: messages.append((title, message)),
    )
    widget._review_sync_proposal(
        SimpleNamespace(project_id=project_id, project_revision=0)
    )

    widget.lines_workspace.search.setText("120")
    visible = [
        row
        for row in range(widget.lines_workspace.table.rowCount())
        if not widget.lines_workspace.table.isRowHidden(row)
    ]
    assert len(visible) == 1
    designation_column = next(
        index for index, column in enumerate(COLUMNS) if column.key == "designation"
    )
    assert widget.lines_workspace.table.item(visible[0], designation_column).text() == "▸ 120"
    assert widget.sync_status_label.text() == "из DWG: 1"
    assert messages == []
    widget.close()
    runtime.close()


@pytest.mark.parametrize(
    "error",
    [
        DwgSyncError("Источник BOX.021 ещё не принят в Project."),
        KeyError("111/111"),
        RuntimeError("internal materialization failure"),
    ],
)
def test_failed_automatic_dwg_apply_becomes_visible_problem(
    qtbot, tmp_path, monkeypatch, caplog, error
):
    runtime = ApplicationRuntime.open(_paths(tmp_path))
    pid = runtime.objects.create_project(ProjectCard(name="Failed sync", project_code="SYNC-ERROR"))
    widget = ObjectWorkspace(runtime)
    qtbot.addWidget(widget)
    widget.open_project(pid)

    monkeypatch.setattr(
        object_workspace_module,
        "build_dwg_update_plan",
        lambda _proposal: SimpleNamespace(
            import_paths=frozenset({"E2:$"}),
            write_paths=frozenset(),
            conflicts=(),
            problems=(),
            blocked_lines=(),
        ),
    )

    def fail(_proposal, **_kwargs):
        raise error

    class Resolution:
        def __init__(self, _proposal, _plan, runtime_errors=(), parent=None):
            del parent
            self.runtime_errors = runtime_errors
            self.open_checks_requested = False

        def exec(self):
            assert self.runtime_errors
            return QDialog.DialogCode.Rejected

        @staticmethod
        def selected_import_paths():
            return set()

        @staticmethod
        def selected_write_paths():
            return set()

        @staticmethod
        def requested_bus_roots():
            return set()

    warnings = []
    monkeypatch.setattr(object_workspace_module, "DwgSyncResolutionDialog", Resolution)
    monkeypatch.setattr(runtime.dwg_sync, "apply_dwg_to_project", fail)
    monkeypatch.setattr(
        QMessageBox, "warning", lambda _parent, title, text: warnings.append((title, text))
    )
    widget._review_sync_proposal(SimpleNamespace(project_id=pid, project_revision=0))

    assert warnings == []
    assert widget.sync_status_label.text() == "требует решения"
    assert any(
        record.exc_info
        for record in caplog.records
        if record.message == "Automatic DWG apply failed"
    )
    widget.close()
    runtime.close()


def test_project_open_preserves_normal_and_maximized_main_window(qtbot, tmp_path):
    runtime = ApplicationRuntime.open(_paths(tmp_path))
    first = runtime.objects.create_project(ProjectCard(name="First", project_code="GEO-1"))
    second = runtime.objects.create_project(ProjectCard(name="Second", project_code="GEO-2"))
    window = MainWindow(runtime)
    qtbot.addWidget(window)
    window.setGeometry(QRect(120, 90, 1050, 720))
    window.show()
    qtbot.wait(20)
    before = QRect(window.geometry())

    window.centralWidget().open_project(first)
    qtbot.wait(20)
    assert window.geometry() == before
    assert not window.isMaximized()

    window.showMaximized()
    qtbot.wait(20)
    assert window.isMaximized()
    window.centralWidget().open_project(second)
    qtbot.wait(20)
    assert window.isMaximized()
    window.close()


class _CableService:
    def __init__(self):
        self.cards = [
            {
                "id": "line-1",
                "designation": "101",
                "load_name": "Розетки кухни с длинным описанием",
                "load_type": "SOCKET",
                "board": "ЩР-1",
                "building_names": "Дом",
                "room_names": "Кухня",
                "system_kind": "POWER",
                "cable_type": "3x2,5",
                "mount_way": "По полу",
                "gofra_id": "001.PND25",
                "effective_m": "16.161687954734253",
                "length_mode": "Автоматическая",
                "length_explanation": "Сумма уникальных физических сегментов",
                "conduit_count": 1,
                "incomplete_segments": 0,
                "known_segment_m": "16.161687954734253",
                "unresolved_room_names": (),
            }
        ]

    def line_cards(self, _project_id):
        return deepcopy(self.cards)

    def topology(self, _project_id, _line_id):
        return {
            "edges": (
                {
                    "segment_id": "segment-1",
                    "depth": 0,
                    "source": {"label": "ЩР-1"},
                    "target": {
                        "label": "101.01",
                        "point_kind": "DEVICE_POINT",
                        "description": "Розетка кухни",
                        "room_names": "Кухня",
                        "building_names": "Дом",
                        "room_unresolved": False,
                    },
                    "mount_way": "По полу",
                    "gofra_type": "ПНД25",
                    "gofra_color": "Черный",
                    "gofra_id": "001.PND25",
                    "cable_length_m": "16.161687954734253",
                    "physical_length_m": "16.161687954734253",
                    "calculation_status": "READY",
                    "calculation_reason": "",
                    "conduit_length_m": None,
                    "conduit_product_name": "",
                    "conduit_product_article": "",
                },
            ),
            "route_breakdown": (),
            "board_reserve_m": "2",
            "additional_m": "0",
            "manual_full_m": None,
        }


class _Constructor:
    @staticmethod
    def list_cable_assignments(_project_id):
        return []


def _column(key: str) -> int:
    return next(index for index, value in enumerate(COLUMNS) if value.key == key)


def test_lines_default_and_persisted_layout_header_and_tree(qtbot, tmp_path):
    state = UiStateStore(tmp_path / "state")
    first = LinesWorkspace(_CableService(), _Constructor(), "project", ui_state=state)
    qtbot.addWidget(first)
    first.resize(1200, 800)
    first.show()
    qtbot.wait(10)

    visible = [
        column.key for index, column in enumerate(COLUMNS) if not first.table.isColumnHidden(index)
    ]
    assert visible == [
        "building_names",
        "board",
        "room_names",
        "designation",
        "load_name",
        "cable_type",
        "mount_way",
        "gofra_id",
        "effective_m",
    ]
    assert first.splitter.count() == 1
    header = first.table.horizontalHeader()
    assert header.font().bold()
    assert header.height() >= 32
    assert header.sectionResizeMode(0) == QHeaderView.ResizeMode.Interactive
    if header.font().pointSize() > 0 and first.table.font().pointSize() > 0:
        assert header.font().pointSize() > first.table.font().pointSize()
    assert first.table.horizontalHeaderItem(_column("building_names")).text() == "Здание"
    assert first.table.horizontalHeaderItem(_column("board")).text() == "Источник"
    assert first.table.horizontalHeaderItem(_column("room_names")).text() == "Помещение"
    assert first.table.horizontalHeaderItem(_column("designation")).text() == "ID"
    assert first.table.horizontalHeaderItem(_column("load_name")).text() == "Назначение"
    assert first.table.horizontalHeaderItem(_column("effective_m")).text() == "Длина, м"
    assert first.table.item(0, _column("designation")).text() == "▸ 101"
    assert first.table.item(0, _column("effective_m")).text() == "16.16"
    assert first.table.item(0, _column("cable_type")).text() == "ВВГнг(А)-LS 3х2,5"

    first._toggle_line_tree(0, "line-1")
    assert first.table.rowCount() == 3
    assert "101.01" in first.table.item(1, _column("designation")).text()
    assert first.table.item(1, _column("room_names")).text() == "Кухня"
    assert first.table.item(1, _column("effective_m")).text() == "16.16"
    assert first.table.item(2, _column("designation")).text() == "+ запас у щита"
    assert first.table.item(2, _column("effective_m")).text() == "2"
    first._toggle_line_tree(0, "line-1")
    assert first.table.rowCount() == 1

    first.table.setColumnWidth(_column("load_name"), 337)
    first.save_state()
    reopened = LinesWorkspace(_CableService(), _Constructor(), "project", ui_state=state)
    qtbot.addWidget(reopened)
    reopened.resize(1200, 800)
    reopened.show()
    qtbot.wait(10)
    assert reopened.table.columnWidth(_column("load_name")) == 337
    assert reopened.splitter.count() == 1
    old_font = reopened.table.horizontalHeader().font()
    reopened.resize(1500, 900)
    qtbot.wait(10)
    assert reopened.table.horizontalHeader().font() == old_font


def _socket() -> CadObservation:
    attributes = {
        "DEVICE_TYPE": "SOCKET",
        "DEVICE_NAME": "Розетка кухни",
        "BUILDING": "Дом",
        "ROOM": "Кухня",
        "MOUNT_HEIGHT": "300",
        "CABLE_ID": "101.01",
        "CABLE_TYPE": "NYM",
        "BOARD": "ЩР-1",
        "LOAD_TYPE": "SOCKET_LIVING_LOW",
        "LOAD_NAME": "Розетки кухни",
        "MOUNT_WAY": "По полу",
        "GOFRA_TYPE": "",
        "GOFRA_COLOR": "",
        "GOFRA_ID": "",
    }
    return CadObservation.from_mapping(
        effective_name="SOCKET_IN",
        layer="POWER",
        raw_attributes=attributes,
        x=10,
        y=20,
        handle="A1",
        definition=BlockDefinitionMetadata(tuple(attributes), False),
    )


def test_dwg_preview_uses_human_object_summary_and_russian_cancel(qtbot, database):
    project_id = database.test_project_id
    proposal = DwgSyncService(database.engine).preview(
        project_id=project_id,
        batch=CadObservationBatch("C:/fixture/ui.dwg", (_socket(),)),
    )
    dialog = DwgSyncPreviewDialog(proposal)
    qtbot.addWidget(dialog)
    assert dialog.table.item(0, 6).text() == "Вставка устройства"
    primary = dialog.table.item(0, 8)
    assert not primary.text().startswith("{")
    assert "SOCKET_IN" in primary.text()
    assert "линия 101.01" in primary.text()
    assert '"CABLE_ID": "101.01"' in primary.toolTip()
    assert dialog.table.horizontalHeader().font().bold()
    buttons = dialog.findChild(QDialogButtonBox)
    assert buttons.button(QDialogButtonBox.StandardButton.Cancel).text() == "Отмена"

    project_dialog = ProjectDialog()
    qtbot.addWidget(project_dialog)
    project_buttons = project_dialog.findChild(QDialogButtonBox)
    assert project_buttons.button(QDialogButtonBox.StandardButton.Cancel).text() == "Отмена"


def test_checks_primary_reason_is_human_and_raw_validator_text_is_tooltip_only(
    qtbot, database, tmp_path
):
    project_id = database.test_project_id
    binding_id = new_id()
    scan_id = new_id()
    observation_id = new_id()
    now = datetime.now(UTC)
    raw_message = "block name 'CUSTOM_UNKNOWN' is absent from the approved catalog"
    with database.engine.begin() as connection:
        connection.execute(
            dwg_document_binding.insert().values(
                id=binding_id,
                project_id=project_id,
                application_uuid=new_id(),
                normalized_last_path="fixture.dwg",
                document_signature="fixture",
                fingerprint="fixture",
                confirmed_at_utc=now,
                status="CONFIRMED",
            )
        )
        connection.execute(
            dwg_scan.insert().values(
                id=scan_id,
                project_id=project_id,
                dwg_document_binding_id=binding_id,
                adapter_version="TEST",
                protocol_version="TEST",
                contract_version="2.2.0",
                started_at_utc=now,
                completed_at_utc=now,
                document_facts_json={},
                content_sha256="0" * 64,
                status="ACCEPTED",
            )
        )
        connection.execute(
            dwg_observation.insert().values(
                id=observation_id,
                project_id=project_id,
                dwg_scan_id=scan_id,
                entity_handle="N1",
                effective_block_name="CUSTOM_UNKNOWN",
                layer_name="POWER",
                space_name="MODEL",
                geometry_json={},
                raw_attributes_json={"CABLE_ID": "101.01"},
                diagnostics_json=(
                    {
                        "code": "UNKNOWN_BLOCK_NAME",
                        "message": raw_message,
                        "severity": "ERROR",
                        "blocks_acceptance": True,
                        "field": "BLOCK_NAME",
                    },
                ),
            )
        )
    service = IntegratedUiService(
        constructor=None,
        cables=None,
        panels=None,
        specification=None,
        engine=database.engine,
    )
    issue = next(item for item in service.issues(project_id) if item.code == "UNKNOWN_BLOCK_NAME")
    assert "не распознано" in issue.reason
    assert raw_message not in issue.reason
    assert raw_message in issue.engineering.evidence

    state = UiStateStore(tmp_path / "checks-state")
    widget = ValidationCenterWidget(service, project_id, ui_state=state)
    qtbot.addWidget(widget)
    assert raw_message not in widget.table.item(0, 2).text()
    assert raw_message in widget.table.item(0, 2).toolTip()
    assert widget.table.horizontalHeader().font().bold()
    widget.table.setColumnWidth(2, 377)
    widget._save_table_state()
    restored = ValidationCenterWidget(service, project_id, ui_state=state)
    qtbot.addWidget(restored)
    assert restored.table.columnWidth(2) == 377
