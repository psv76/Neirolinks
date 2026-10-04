from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QMessageBox
from sqlalchemy import func, select

from nl_project_2.cad_contract import (
    CadObservation,
    CadObservationBatch,
    IssueSeverity,
    ValidationIssue,
)
from nl_project_2.cad_sync import (
    ActiveDocumentInfo,
    ChangeClass,
    ScanProposal,
    SyncChange,
    SyncOwnerKind,
    SyncSummary,
)
from nl_project_2.cad_sync.models import DwgScanProgress
from nl_project_2.objects.models import ProjectCard
from nl_project_2.objects.runtime import ApplicationRuntime
from nl_project_2.objects.service import ObjectService
from nl_project_2.objects.time_tracking import WorkTimeService
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import project, work_session
import nl_project_2.presentation.object_workspace as object_workspace_module
from nl_project_2.presentation.object_workspace import (
    _SYNC_STATUS_TITLES,
    _VALIDATION_TITLES,
    DwgScanProgressDialog,
    DwgSyncPreviewDialog,
    ObjectWorkspace,
    _localized_sync_error,
    _validation_title,
)
from nl_project_2.presentation.room_presentation import ROOM_COLOR_ROLE


class _DwgSyncStub:
    pass


def _mixed_preview(project_id: str = "project") -> ScanProposal:
    handles = ("5FF12", "60B36", "60B61")
    observations = [
        CadObservation.from_mapping(
            effective_name="SOCKET_IN",
            layer="POWER",
            raw_attributes={
                "CABLE_ID": "101",
                "LOAD_NAME": "Розетки кухни",
                "ROOM": "5. Кухня-ниша",
                "DEVICE_NAME": "Розетка холодильника",
                "GOFRA_TYPE": "ПНД25",
            },
            x=index,
            y=0,
            handle=handle,
        )
        for index, handle in enumerate(handles)
    ]
    changes = [
        SyncChange(
            field_path=f"{handle}:$",
            handle=handle,
            field="$",
            baseline_value=None,
            project_value=None,
            dwg_value={"BLOCK_NAME": "SOCKET_IN", "CABLE_ID": "101"},
            change_class=ChangeClass.NEW_DWG_INSERTION,
            reason="DWG Handle has no confirmed Project counterpart",
        )
        for handle in handles
    ]
    issues = []
    for index in range(646):
        handle = f"ERR{index:03d}"
        observations.append(
            CadObservation.from_mapping(
                effective_name="SOCKET_IN",
                layer="0",
                raw_attributes={"CABLE_ID": f"{200 + index}.01"},
                x=index,
                y=1,
                handle=handle,
            )
        )
        issues.append(
            ValidationIssue(
                code="LAYER_FUNCTION_GROUP_MISMATCH",
                message="layer '0' is not an approved unique group for SOCKET_IN",
                severity=IssueSeverity.ERROR,
                blocks_acceptance=True,
                handle=handle,
                field="LAYER",
            )
        )
        changes.append(
            SyncChange(
                field_path=f"{handle}:$",
                handle=handle,
                field="$",
                baseline_value=None,
                project_value=None,
                dwg_value={"BLOCK_NAME": "SOCKET_IN", "CABLE_ID": f"{200 + index}.01"},
                change_class=ChangeClass.INVALID_DWG_DATA,
                reason=(
                    "LAYER_FUNCTION_GROUP_MISMATCH [LAYER]: "
                    "layer '0' is not an approved unique group for SOCKET_IN"
                ),
            )
        )
    for index in range(24):
        handle = f"EQ{index:03d}"
        field = "GOFRA_TYPE" if index % 2 else "CABLE_ID"
        value = "ПНД25" if field == "GOFRA_TYPE" else f"{300 + index}.01"
        attributes = {"CABLE_ID": f"{300 + index}.01"}
        if field == "GOFRA_TYPE":
            attributes["GOFRA_TYPE"] = "ПНД25"
        observations.append(
            CadObservation.from_mapping(
                effective_name="SOCKET_IN",
                layer="POWER",
                raw_attributes=attributes,
                x=index,
                y=2,
                handle=handle,
            )
        )
        changes.append(
            SyncChange(
                field_path=f"{handle}:{field}",
                handle=handle,
                field=field,
                baseline_value=value,
                project_value=value,
                dwg_value=value,
                change_class=ChangeClass.EQUAL,
                reason="Project, baseline and DWG values are equal",
            )
        )
    return ScanProposal(
        project_id=project_id,
        batch=CadObservationBatch("C:/fixture/working.dwg", tuple(observations)),
        changes=tuple(changes),
        issues=tuple(issues),
        summary=SyncSummary(new=3, invalid=646),
        project_revision=0,
        binding_id=None,
    )


def _visible_rows(dialog: DwgSyncPreviewDialog) -> int:
    return sum(not dialog.table.isRowHidden(row) for row in range(dialog.table.rowCount()))


def test_dwg_preview_filters_search_selection_and_russian_presentation(database, qtbot):
    objects = ObjectService(database.engine)
    project_id = objects.create_project(ProjectCard(name="Preview", project_code="PREVIEW-1"))
    proposal = _mixed_preview(project_id)
    batch_before = proposal.batch
    changes_before = proposal.changes
    with database.engine.connect() as connection:
        revision_before = connection.scalar(
            select(project.c.project_revision).where(project.c.id == project_id)
        )
    dialog = DwgSyncPreviewDialog(proposal)
    qtbot.addWidget(dialog)
    dialog.show()

    counters = dialog.summary_label.text()
    assert dialog.filter_combo.currentText() == "Действия"
    assert _visible_rows(dialog) == 3
    dialog.filter_combo.setCurrentIndex(dialog.filter_combo.findData("ERRORS"))
    assert _visible_rows(dialog) == 646
    assert dialog.summary_label.text() == counters
    dialog.filter_combo.setCurrentIndex(dialog.filter_combo.findData("EQUAL"))
    assert _visible_rows(dialog) == 24
    assert dialog.summary_label.text() == counters
    dialog.search_edit.setText("GOFRA_TYPE")
    assert _visible_rows(dialog) == 12
    dialog.search_edit.clear()

    dialog.filter_combo.setCurrentIndex(dialog.filter_combo.findData("ACTIONS"))
    dialog.search_edit.setText("60B36")
    assert _visible_rows(dialog) == 1
    dialog.search_edit.setText("101")
    assert _visible_rows(dialog) == 3
    dialog.search_edit.setText("SOCKET_IN")
    assert _visible_rows(dialog) == 3
    dialog.search_edit.setText("Розетки кухни")
    assert _visible_rows(dialog) == 3
    dialog.search_edit.setText("5. Кухня-ниша")
    assert _visible_rows(dialog) == 3
    dialog.search_edit.setText("Розетка холодильника")
    assert _visible_rows(dialog) == 3
    dialog.search_edit.clear()
    qtbot.mouseClick(dialog.select_all_button, Qt.MouseButton.LeftButton)
    assert dialog.selected_paths() == {"5FF12:$", "60B36:$", "60B61:$"}

    dialog.filter_combo.setCurrentIndex(dialog.filter_combo.findData("ERRORS"))
    dialog.search_edit.setText("Неверный слой")
    assert _visible_rows(dialog) == 646
    dialog.search_edit.clear()
    error_row = next(
        row for row in range(dialog.table.rowCount()) if not dialog.table.isRowHidden(row)
    )
    assert dialog.table.item(error_row, 5).text() == "Ошибка данных DWG"
    assert dialog.table.item(error_row, 6).text() == "Вставка устройства"
    assert "Неверный слой" in dialog.table.item(error_row, 9).text()
    assert "LAYER_FUNCTION_GROUP_MISMATCH" in dialog.table.item(error_row, 9).toolTip()
    assert [dialog.table.horizontalHeaderItem(index).text() for index in range(1, 10)] == [
        "Номер линии",
        "Назначение линии",
        "Помещение",
        "Объект",
        "Статус",
        "Поле",
        "Project",
        "DWG",
        "Причина",
    ]
    assert dialog.table.horizontalHeaderItem(10).text() == "Handle DWG"
    assert dialog.table.horizontalHeaderItem(11).text() == "BLOCK_NAME"
    assert "последней подтверждённой" in dialog.table.horizontalHeaderItem(13).toolTip()

    dialog.filter_combo.setCurrentIndex(dialog.filter_combo.findData("EQUAL"))
    equal_row = next(
        row for row in range(dialog.table.rowCount()) if not dialog.table.isRowHidden(row)
    )
    assert dialog.table.item(equal_row, 5).text() == "Совпадает"
    dialog.reject()
    assert dialog.result() == QDialog.DialogCode.Rejected
    with database.engine.connect() as connection:
        revision_after = connection.scalar(
            select(project.c.project_revision).where(project.c.id == project_id)
        )
    assert revision_after == revision_before
    assert proposal.batch == batch_before
    assert proposal.changes == changes_before


def test_preview_engineering_columns_toggle_and_atomic_line_selection(qtbot):
    dialog = DwgSyncPreviewDialog(_mixed_preview())
    qtbot.addWidget(dialog)
    assert [dialog.table.isColumnHidden(index) for index in range(10, 14)] == [
        True,
        True,
        True,
        True,
    ]
    assert dialog.engineering_details.text() == "Инженерные подробности"
    dialog.engineering_details.setChecked(True)
    assert not any(dialog.table.isColumnHidden(index) for index in range(10, 14))
    dialog.engineering_details.setChecked(False)
    assert all(dialog.table.isColumnHidden(index) for index in range(10, 14))

    selected_row = next(
        row for row, change in enumerate(dialog._row_changes) if change.handle == "60B36"
    )
    dialog.table.item(selected_row, 0).setCheckState(Qt.CheckState.Checked)
    assert dialog.selected_paths() == {"5FF12:$", "60B36:$", "60B61:$"}


def test_blocked_atomic_line_cannot_become_partial_selection(qtbot):
    proposal = _mixed_preview()
    changes = list(proposal.changes)
    changes[1] = replace(changes[1], change_class=ChangeClass.INVALID_DWG_DATA)
    blocked = replace(proposal, changes=tuple(changes))
    dialog = DwgSyncPreviewDialog(blocked)
    qtbot.addWidget(dialog)
    first_row = next(
        row for row, change in enumerate(dialog._row_changes) if change.handle == "5FF12"
    )
    dialog.table.item(first_row, 0).setCheckState(Qt.CheckState.Checked)
    assert dialog.selected_paths() == set()
    assert dialog.selection_notice.text() == (
        "Линия 101 не может быть принята: есть неразрешённые ошибки или конфликты."
    )
    qtbot.mouseClick(dialog.select_all_button, Qt.MouseButton.LeftButton)
    assert dialog.selected_paths() == set()


def test_preview_distinguishes_insertion_and_line_property_and_localizes_guard(qtbot):
    proposal = _mixed_preview()
    line_change = SyncChange(
        field_path="60B36:LOAD_NAME",
        handle="60B36",
        field="LOAD_NAME",
        baseline_value="Старое",
        project_value="Старое",
        dwg_value="Новое",
        change_class=ChangeClass.DWG_CHANGED,
        reason="Only DWG differs from the confirmed baseline",
        owner_kind=SyncOwnerKind.BASE_LINE,
        owner_key="101",
        owner_path="line:101:LOAD_NAME",
        affected_handles=("5FF12", "60B36", "60B61"),
    )
    dialog = DwgSyncPreviewDialog(replace(proposal, changes=proposal.changes + (line_change,)))
    qtbot.addWidget(dialog)
    assert dialog.table.item(0, 6).text() == "Вставка устройства"
    assert dialog.table.item(dialog.table.rowCount() - 1, 6).text() == ("Линия · Назначение линии")
    assert _localized_sync_error("Partial line import is forbidden for 101") == (
        "Линия 101 не может быть принята целиком. Проверьте ошибки и конфликты линии."
    )


def test_preview_uses_service_supplied_canonical_room_and_marks_unresolved(qtbot):
    proposal = _mixed_preview()
    canonical = replace(
        proposal.changes[0],
        display_context={"room_name": "5. Кухня-ниша", "raw_room": "Кухня"},
    )
    unresolved = replace(
        proposal.changes[1],
        display_context={"room_name": "Не разрешено: Чердак", "raw_room": "Чердак"},
    )
    dialog = DwgSyncPreviewDialog(
        replace(
            proposal,
            changes=(canonical, unresolved) + proposal.changes[2:],
        )
    )
    qtbot.addWidget(dialog)
    assert dialog.table.item(0, 3).text() == "5. Кухня-ниша"
    assert dialog.table.item(1, 3).text() == "Не разрешено: Чердак"


def test_opposite_direction_change_is_disabled_with_a_direction_hint(qtbot):
    proposal = _mixed_preview()
    project_change = SyncChange(
        field_path="5FF12:GOFRA_ID",
        handle="5FF12",
        field="GOFRA_ID",
        baseline_value="",
        project_value="105.PP25",
        dwg_value="",
        change_class=ChangeClass.PROJECT_CHANGED,
        reason="Only Project differs from the confirmed baseline",
    )
    dialog = DwgSyncPreviewDialog(replace(proposal, changes=proposal.changes + (project_change,)))
    qtbot.addWidget(dialog)
    row = dialog.table.rowCount() - 1
    selection = dialog.table.item(row, 0)
    assert not selection.flags() & Qt.ItemFlag.ItemIsUserCheckable
    assert selection.toolTip() == ("Изменение доступно в направлении Project → DWG.")

    dialog.direction.setCurrentIndex(1)
    assert selection.flags() & Qt.ItemFlag.ItemIsUserCheckable
    assert selection.toolTip() == ""


def test_dwg_scan_progress_is_indeterminate_until_real_counts_arrive(qtbot):
    dialog = DwgScanProgressDialog()
    qtbot.addWidget(dialog)
    assert dialog.windowTitle() == "Сканирование DWG"
    dialog.update_progress(DwgScanProgress("SCANNING"))
    assert dialog.stage_label.text() == "Сканирование"
    assert (dialog.progress_bar.minimum(), dialog.progress_bar.maximum()) == (0, 0)
    dialog.update_progress(DwgScanProgress("VALIDATING", processed=12, total=20))
    assert dialog.stage_label.text() == "Проверка"
    assert (dialog.progress_bar.maximum(), dialog.progress_bar.value()) == (20, 12)
    assert dialog.count_label.text() == "Обработано 12 из 20"


def test_preview_has_russian_titles_for_every_current_status_and_validation_code():
    assert set(_SYNC_STATUS_TITLES) == set(ChangeClass)
    assert all(title and title != status.value for status, title in _SYNC_STATUS_TITLES.items())
    expected_codes = {
        "DOCUMENT_IDENTITY_REQUIRED",
        "DUPLICATE_DWG_HANDLE",
        "BLOCK_NAME_FORMAT",
        "UNKNOWN_BLOCK_NAME",
        "DWG_HANDLE_REQUIRED",
        "COORDINATE_NOT_FINITE",
        "DEVICE_TYPE_MISMATCH",
        "DUPLICATE_ATTRIBUTE_TAG",
        "ATTRIBUTE_TAG_FORMAT",
        "REQUIRED_ATTRIBUTE_MISSING",
        "FORBIDDEN_ATTRIBUTE",
        "UNDECLARED_ATTRIBUTE",
        "DUPLICATE_ATTRIBUTE_DEFINITION",
        "ATTRIBUTE_DEFINITION_TAG_FORMAT",
        "FORBIDDEN_ATTRIBUTE_DEFINITION",
        "UNDECLARED_ATTRIBUTE_DEFINITION",
        "REQUIRED_ATTRIBUTE_DEFINITION_MISSING",
        "ATTRIBUTE_NOT_IN_DEFINITION",
        "MOUNT_WAY_NOT_ALLOWED",
        "GOFRA_TYPE_REQUIRED",
        "GOFRA_TYPE_NOT_EMPTY",
        "GOFRA_TYPE_FORMAT",
        "GOFRA_FIELDS_WITHOUT_CONDUIT",
        "GOFRA_ID_FORMAT",
        "GOFRA_ID_TYPE_MISMATCH",
        "LOGICAL_LAYER_MISMATCH",
        "DALI_GROUP_NOT_DYNAMIC",
        "DALI_GROUP_ID_FORMAT",
        "DUPLICATE_DALI_GROUP_ID",
        "LAYER_FUNCTION_GROUP_MISMATCH",
        "NUMERIC_ATTRIBUTE_FORMAT",
        "LOAD_TYPE_NOT_ALLOWED",
        "BOARD_AV_BLOCK_NAME",
        "POSTS_MISMATCH",
        "KEY_TARGET_FORMAT",
        "AV_BLOCK_NAME",
        "LINE_FIELDS_WITHOUT_CABLE_ID",
        "CABLE_ID_FORMAT",
        "CABLE_GROUP_PREFIX_MISMATCH",
        "DUPLICATE_BOARD_ID",
        "DUPLICATE_FULL_CABLE_ID",
        "CONDUIT_TYPE_INCONSISTENT",
        "CONDUIT_COLOR_INCONSISTENT",
        "DUPLICATE_AV_IDENTITY",
        "AV_BOARD_NOT_FOUND",
        "AV_BOARD_WRONG_ROLE",
        "KEY_TARGET_NOT_FOUND",
    }
    assert expected_codes <= set(_VALIDATION_TITLES)
    assert _validation_title("LINE_GOFRA_ID_INCONSISTENT") == (
        "Конфликт значений одной кабельной линии"
    )


def test_dwg_preview_apply_button_accepts_three_checked_insertions(qtbot):
    dialog = DwgSyncPreviewDialog(_mixed_preview())
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.mouseClick(dialog.select_all_button, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(dialog.apply_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.selected_paths() == {"5FF12:$", "60B36:$", "60B61:$"}


def test_registry_four_tabs_room_color_and_time_controls(database, qtbot):
    objects = ObjectService(database.engine)
    project_id = objects.create_project(
        ProjectCard(name="UI объект", project_code="UI-1", address="Адрес")
    )
    building_id = objects.add_building(project_id, "Корпус")
    objects.add_room(
        project_id=project_id,
        building_id=building_id,
        name="Комната",
        base_mark_mm=-100,
        height_m=Decimal("2.75"),
        marking_color="#336699",
    )
    work = WorkTimeService(
        database.engine,
        new_id(),
        clock=lambda: datetime(2026, 8, 8, 7, 0, tzinfo=UTC),
    )
    runtime = ApplicationRuntime(database, objects, work)
    widget = ObjectWorkspace(runtime)
    qtbot.addWidget(widget)
    widget.show()

    assert widget.tree.topLevelItem(0).text(0) == "Реестр объектов"
    assert widget.tree.topLevelItemCount() == 2
    assert [widget.tabs.tabText(index) for index in range(widget.tabs.count())] == [
        "Общие данные",
        "Помещения",
        "Настройки",
        "Время работы",
    ]
    widget.open_project(project_id)
    assert widget.current_object_label.text() == "UI-1 — UI объект"
    assert widget.rooms_table.rowCount() == 1
    color_item = widget.rooms_table.item(0, 4)
    assert color_item.text() == ""
    assert color_item.toolTip() == "#336699"
    assert color_item.data(ROOM_COLOR_ROLE) == "#336699"
    assert widget.time_button.text() == "Пауза"
    assert widget.time_tab_button.text() == "Пауза"
    assert widget.sync_button.text() == "Обновить"

    with database.engine.connect() as connection:
        session_id = connection.scalar(
            select(work_session.c.id).where(work_session.c.stopped_at_utc.is_(None))
        )
    widget.tabs.setCurrentIndex(1)
    widget.tabs.setCurrentIndex(2)
    with database.engine.connect() as connection:
        assert (
            connection.scalar(
                select(work_session.c.id).where(work_session.c.stopped_at_utc.is_(None))
            )
            == session_id
        )
    qtbot.mouseClick(widget.time_button, Qt.MouseButton.LeftButton)
    assert widget.time_button.text() == "Play"
    assert widget.time_tab_state.text() == "Остановлен"
    with database.engine.connect() as connection:
        assert (
            connection.scalar(
                select(func.count())
                .select_from(work_session)
                .where(work_session.c.stopped_at_utc.is_(None))
            )
            == 0
        )
    qtbot.mouseClick(widget.time_button, Qt.MouseButton.LeftButton)
    assert widget.time_button.text() == "Пауза"
    qtbot.mouseClick(widget.close_button, Qt.MouseButton.LeftButton)
    assert runtime.current_project_id is None
    assert widget.current_object_label.text() == "Объект не выбран"
    assert widget.time_button.text() == "Play"
    widget.tree.setCurrentItem(widget.tree.topLevelItem(1))
    assert runtime.current_project_id == project_id
    assert widget.time_button.text() == "Пауза"


def test_object_type_is_editable_without_unapproved_value_registry(database, qtbot):
    objects = ObjectService(database.engine)
    project_id = objects.create_project(ProjectCard(name="Тип", project_code="TYPE-1"))
    runtime = ApplicationRuntime(
        database,
        objects,
        WorkTimeService(database.engine, new_id()),
    )
    widget = ObjectWorkspace(runtime)
    qtbot.addWidget(widget)
    widget.open_project(project_id)
    field = widget.general_fields["object_type"]
    assert field.isEditable() if hasattr(field, "isEditable") else not field.isReadOnly()
    assert field.text() == ""


def test_dwg_sync_button_is_available_only_for_open_project_with_adapter(database, qtbot):
    objects = ObjectService(database.engine)
    project_id = objects.create_project(ProjectCard(name="DWG", project_code="DWG-1"))
    runtime = ApplicationRuntime(
        database,
        objects,
        WorkTimeService(database.engine, new_id()),
        _DwgSyncStub(),
    )
    widget = ObjectWorkspace(runtime)
    qtbot.addWidget(widget)
    assert not widget.sync_button.isEnabled()
    widget.open_project(project_id)
    assert widget.sync_button.isEnabled()
    widget._close_project()
    assert not widget.sync_button.isEnabled()


def test_dwg_target_identity_requires_explicit_user_confirmation(database, qtbot, monkeypatch):
    runtime = ApplicationRuntime(
        database,
        ObjectService(database.engine),
        WorkTimeService(database.engine, new_id()),
    )
    widget = ObjectWorkspace(runtime)
    qtbot.addWidget(widget)
    identity = "C:/explicit/target.dwg"
    result = SimpleNamespace(value=ActiveDocumentInfo(identity, "target.dwg", False, False, 1))
    started = []
    monkeypatch.setattr(widget, "_start_dwg_scan", started.append)
    monkeypatch.setattr(
        "nl_project_2.presentation.object_workspace.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.StandardButton.No,
    )
    widget._sync_identity_completed(result)
    assert started == []

    monkeypatch.setattr(
        "nl_project_2.presentation.object_workspace.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    widget._sync_identity_completed(result)
    assert started == [identity]


def test_local_line_room_warning_opens_direct_remediation(database, qtbot, monkeypatch):
    objects = ObjectService(database.engine)
    project_id = objects.create_project(ProjectCard(name="Local issue", project_code="LOCAL-1"))
    runtime = ApplicationRuntime(
        database,
        objects,
        WorkTimeService(database.engine, new_id()),
    )
    widget = ObjectWorkspace(runtime)
    qtbot.addWidget(widget)
    widget.open_project(project_id)

    sync_calls = []
    widget._sync_dwg = lambda: sync_calls.append("sync")
    widget.documents_workspace.show_issue_for = lambda *_args: (_ for _ in ()).throw(
        AssertionError("local warning must not open the generic validation list")
    )

    class FakeMessageBox:
        class Icon:
            Warning = object()

        class ButtonRole:
            AcceptRole = object()

        class StandardButton:
            Close = object()

        def __init__(self, _parent=None):
            self._clicked = None

        def setWindowTitle(self, _value):
            pass

        def setIcon(self, _value):
            pass

        def setText(self, _value):
            pass

        def setInformativeText(self, _value):
            pass

        def addButton(self, value, *_args):
            button = object()
            if value == "Привязать помещение":
                self._clicked = button
            return button

        def exec(self):
            return 0

        def clickedButton(self):
            return self._clicked

    monkeypatch.setattr(object_workspace_module, "QMessageBox", FakeMessageBox)

    widget._show_line_issue(
        {
            "issue_kind": "ROOM",
            "line_id": "line-106",
            "column_key": "room_names",
            "title": "BOX.011 · помещение",
            "reason": "Дет. ванная 2 не связано с каноническим помещением Project.",
            "required_action": "Выберите существующее помещение Project.",
            "fix_action": "SYNC_DWG",
        }
    )

    assert sync_calls == ["sync"]
