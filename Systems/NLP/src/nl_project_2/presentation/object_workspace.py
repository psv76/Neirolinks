"""Qt object registry and the four-tab object card."""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from nl_project_2.cad_sync import (
    BridgeError,
    ChangeClass,
    DwgSyncError,
    SyncOwnerKind,
    atomic_line_import_groups,
    build_dwg_update_plan,
)
from nl_project_2.objects.models import ProjectCard, ProjectSettings, TimeSummary
from nl_project_2.objects.service import ObjectValidationError
from nl_project_2.operations import OperationSnapshot

from .automation_workspace import AutomationWorkspaceDialog
from .background_operation import BackgroundOperationController
from .bus_workspace import BusWorkspaceDialog
from .cable_workspace import CableWorkspaceDialog
from .constructor_workspace import ConstructorWorkspaceDialog
from .distribution_workspace import DistributionWorkspaceDialog
from .documents_workspace import DocumentsWorkspace
from .equipment_workspace import EquipmentWorkspace
from .lines_workspace import LinesWorkspace
from .panel_workspace import PanelWorkspaceDialog
from .room_presentation import ROOM_COLOR_ROLE, RoomColorComboBox, RoomSwatchDelegate
from .validation_center import ValidationCenterDialog

_SYNC_STATUS_TITLES = {
    ChangeClass.EQUAL: "Совпадает",
    ChangeClass.NEW_DWG_INSERTION: "Новое в DWG",
    ChangeClass.DWG_CHANGED: "Изменено в DWG",
    ChangeClass.PROJECT_CHANGED: "Изменено в Project",
    ChangeClass.BOTH_CHANGED_CONFLICT: "Конфликт изменений",
    ChangeClass.INVALID_DWG_DATA: "Ошибка данных DWG",
    ChangeClass.MISSING_DWG_INSERTION: "Не найдено в DWG",
    ChangeClass.IDENTITY_COLLISION: "Конфликт идентификатора",
}

_ACTIONABLE_IMPORT = {
    ChangeClass.NEW_DWG_INSERTION,
    ChangeClass.DWG_CHANGED,
    ChangeClass.BOTH_CHANGED_CONFLICT,
}
_ACTIONABLE_WRITE = {ChangeClass.PROJECT_CHANGED, ChangeClass.BOTH_CHANGED_CONFLICT}
_ACTIONABLE_ALL = _ACTIONABLE_IMPORT | _ACTIONABLE_WRITE
_NEW_OR_CHANGED = {
    ChangeClass.NEW_DWG_INSERTION,
    ChangeClass.DWG_CHANGED,
    ChangeClass.PROJECT_CHANGED,
}
_ERROR_STATUSES = {ChangeClass.INVALID_DWG_DATA, ChangeClass.IDENTITY_COLLISION}

_VALIDATION_TITLES = {
    "DOCUMENT_IDENTITY_REQUIRED": "Не определён целевой DWG",
    "DUPLICATE_DWG_HANDLE": "Handle DWG встречается несколько раз",
    "BLOCK_NAME_FORMAT": "Некорректное имя блока",
    "UNKNOWN_BLOCK_NAME": "Неизвестное имя блока",
    "DWG_HANDLE_REQUIRED": "У вставки отсутствует Handle DWG",
    "COORDINATE_NOT_FINITE": "Некорректная координата вставки",
    "DEVICE_TYPE_MISMATCH": "Тип устройства не соответствует блоку",
    "DUPLICATE_ATTRIBUTE_TAG": "Атрибут повторяется во вставке",
    "ATTRIBUTE_TAG_FORMAT": "Некорректное имя атрибута",
    "REQUIRED_ATTRIBUTE_MISSING": "Отсутствует обязательный атрибут",
    "FORBIDDEN_ATTRIBUTE": "Атрибут запрещён контрактом",
    "UNDECLARED_ATTRIBUTE": "Лишний атрибут",
    "DUPLICATE_ATTRIBUTE_DEFINITION": "Определение атрибута повторяется",
    "ATTRIBUTE_DEFINITION_TAG_FORMAT": "Некорректное имя определения атрибута",
    "FORBIDDEN_ATTRIBUTE_DEFINITION": "Определение атрибута запрещено",
    "UNDECLARED_ATTRIBUTE_DEFINITION": "Лишнее определение атрибута",
    "REQUIRED_ATTRIBUTE_DEFINITION_MISSING": "В блоке нет обязательного определения атрибута",
    "ATTRIBUTE_NOT_IN_DEFINITION": "Атрибут вставки отсутствует в определении блока",
    "MOUNT_WAY_NOT_ALLOWED": "Недопустимый способ прокладки",
    "GOFRA_TYPE_REQUIRED": "Не указан обязательный тип трубы",
    "GOFRA_TYPE_NOT_EMPTY": "Тип трубы должен быть пустым",
    "GOFRA_TYPE_FORMAT": "Некорректный тип трубы",
    "GOFRA_FIELDS_WITHOUT_CONDUIT": "Поля трубы заполнены при отсутствии трубы",
    "GOFRA_ID_FORMAT": "Некорректное обозначение трубы",
    "GOFRA_ID_TYPE_MISMATCH": "GOFRA_ID не соответствует GOFRA_TYPE",
    "LOGICAL_LAYER_MISMATCH": "Логический блок находится на неверном слое",
    "DALI_GROUP_NOT_DYNAMIC": "Блок группы DALI не является динамическим",
    "DALI_GROUP_ID_FORMAT": "Некорректный идентификатор группы DALI",
    "DUPLICATE_DALI_GROUP_ID": "Идентификатор группы DALI не уникален",
    "LAYER_FUNCTION_GROUP_MISMATCH": "Неверный слой или функциональная группа",
    "NUMERIC_ATTRIBUTE_FORMAT": "Некорректное числовое значение",
    "LOAD_TYPE_NOT_ALLOWED": "Недопустимый тип нагрузки",
    "BOARD_AV_BLOCK_NAME": "Для AV-щита выбран неверный блок",
    "POSTS_MISMATCH": "Количество постов не соответствует блоку",
    "KEY_TARGET_FORMAT": "Некорректная ссылка клавиши",
    "AV_BLOCK_NAME": "Для AV-линии выбран неверный блок",
    "LINE_FIELDS_WITHOUT_CABLE_ID": "Поля линии заполнены без CABLE_ID",
    "CABLE_ID_FORMAT": "Некорректный CABLE_ID",
    "CABLE_GROUP_PREFIX_MISMATCH": "CABLE_ID не соответствует функциональной группе",
    "DUPLICATE_BOARD_ID": "Идентификатор щита не уникален",
    "DUPLICATE_FULL_CABLE_ID": "Полный CABLE_ID точки не уникален",
    "CONDUIT_TYPE_INCONSISTENT": "Различаются типы общей трубы",
    "CONDUIT_COLOR_INCONSISTENT": "Различаются цвета общей трубы",
    "DUPLICATE_AV_IDENTITY": "Идентификатор AV-линии не уникален",
    "AV_BOARD_NOT_FOUND": "Щит AV не найден в DWG",
    "AV_BOARD_WRONG_ROLE": "У щита AV неверная роль",
    "KEY_TARGET_NOT_FOUND": "Цель клавиши не найдена",
}


def _validation_title(code: str) -> str:
    if code.startswith("LINE_") and code.endswith("_INCONSISTENT"):
        return "Конфликт значений одной кабельной линии"
    return _VALIDATION_TITLES.get(code, "Нарушено правило данных DWG")


def _observation_value(observation, field: str | None):
    if observation is None or field is None:
        return None
    direct = {
        "BLOCK_NAME": observation.effective_name,
        "LAYER": observation.layer,
        "DWG_HANDLE": observation.handle,
        "X": observation.x,
        "Y": observation.y,
    }
    if field in direct:
        return direct[field]
    return {item.tag: item.value for item in observation.raw_attributes}.get(field)


def _validation_issue_text(issue, observation) -> str:
    title = _validation_title(issue.code)
    if issue.code in {"BLOCK_NAME_FORMAT", "UNKNOWN_BLOCK_NAME"}:
        name = "" if observation is None else observation.effective_name
        expectation = (
            "Ожидается каноническое имя блока NL Project 2.0."
            if issue.code == "BLOCK_NAME_FORMAT"
            else "Имя должно присутствовать в каноническом каталоге блоков."
        )
        return f"{title}. Имя: {name or 'не указано'}. {expectation}"
    if issue.code in {"LAYER_FUNCTION_GROUP_MISMATCH", "LOGICAL_LAYER_MISMATCH"}:
        block = "" if observation is None else observation.effective_name
        layer = "" if observation is None else observation.layer
        return (
            f"{title}. Блок: {block or 'не указан'}; слой: {layer or 'не указан'}. "
            "Требуется допустимый слой этого блока по контракту."
        )
    if issue.code == "NUMERIC_ATTRIBUTE_FORMAT":
        value = _observation_value(observation, issue.field)
        return (
            f"{title}. Поле: {issue.field or 'не указано'}; "
            f"значение: {value if value not in (None, '') else 'не указано'}. "
            "Требуется число допустимого формата."
        )
    if issue.code == "GOFRA_ID_TYPE_MISMATCH":
        attributes = (
            {}
            if observation is None
            else {item.tag: item.value for item in observation.raw_attributes}
        )
        return (
            f"{title}. GOFRA_ID: {attributes.get('GOFRA_ID', 'не указано')}; "
            f"GOFRA_TYPE: {attributes.get('GOFRA_TYPE', 'не указано')}."
        )
    field = issue.field
    value = _observation_value(observation, field)
    details = []
    if field:
        details.append(f"Поле: {field}")
    if value not in (None, ""):
        details.append(f"значение: {value}")
    return title if not details else f"{title}. {'; '.join(details)}."


def _change_reason_text(change, issues, observation) -> tuple[str, str]:
    if change.detail_status == "ROOM_CANONICALIZATION":
        return (
            "Помещение существует в Project. Требуется привязать устройство к нему.",
            change.reason,
        )
    if change.change_class == ChangeClass.INVALID_DWG_DATA:
        relevant = [issue for issue in issues if issue.handle == change.handle]
        primary = "\n".join(_validation_issue_text(issue, observation) for issue in relevant)
        if not primary:
            primary = "Ошибка данных DWG. Вставка не прошла обязательную проверку."
        technical = "\n".join(
            f"{issue.code} [{issue.field or '$'}]: {issue.message}" for issue in relevant
        )
        return primary, technical or change.reason
    primary = {
        ChangeClass.EQUAL: "Значения совпадают с последней подтверждённой синхронизацией.",
        ChangeClass.NEW_DWG_INSERTION: "Вставка DWG ещё не принята в Project.",
        ChangeClass.DWG_CHANGED: "Значение изменено в DWG после последней синхронизации.",
        ChangeClass.PROJECT_CHANGED: "Значение изменено в Project после последней синхронизации.",
        ChangeClass.BOTH_CHANGED_CONFLICT: "Значение независимо изменено в Project и DWG.",
        ChangeClass.MISSING_DWG_INSERTION: "Ранее синхронизированная вставка не найдена в DWG.",
        ChangeClass.IDENTITY_COLLISION: "Один технический идентификатор относится к разным данным.",
    }.get(change.change_class, "Состояние требует внимания пользователя.")
    return primary, f"{change.change_class.value}: {change.reason}"


def _sync_object_summary(value, observation) -> str:
    if not isinstance(value, dict):
        return "—" if value is None else str(value)
    block = str(value.get("BLOCK_NAME") or getattr(observation, "effective_name", "") or "").strip()
    device = str(value.get("DEVICE_NAME") or value.get("DEVICE_TYPE") or "").strip()
    cable = str(value.get("CABLE_ID") or "").strip()
    load = str(value.get("LOAD_NAME") or "").strip()
    room = str(value.get("ROOM") or "").strip()
    parts = [
        item for item in (block, device, f"линия {cable}" if cable else "", load, room) if item
    ]
    return "; ".join(dict.fromkeys(parts)) or "Данные вставки DWG"


_SYNC_FIELD_TITLES = {
    "$": "Вставка устройства",
    "CABLE_ID": "Номер линии",
    "LOAD_NAME": "Назначение линии",
    "ROOM": "Помещение",
    "DEVICE_NAME": "Объект",
    "GOFRA_TYPE": "Тип трубы",
    "GOFRA_COLOR": "Цвет трубы",
    "GOFRA_ID": "Номер трубы",
}


def _sync_field_title(change) -> str:
    title = _SYNC_FIELD_TITLES.get(change.field, change.field)
    if change.owner_kind is SyncOwnerKind.BASE_LINE:
        return f"Линия · {title}"
    return title


def _localized_sync_error(message: str) -> str:
    prefixes = {
        "Partial line import is forbidden for ": (
            "Линия {value} не может быть принята целиком. Проверьте ошибки и конфликты линии."
        ),
        "Incomplete owner set for line-wide import ": (
            "Нельзя принять неполный набор общего свойства линии {value}."
        ),
        "Partial base CABLE_ID import is forbidden for ": (
            "Нельзя частично изменить номер линии {value}."
        ),
    }
    for prefix, template in prefixes.items():
        if message.startswith(prefix):
            return template.format(value=message[len(prefix) :])
    return message


def _sync_human_context(change, observation) -> tuple[str, str, str, str, str]:
    values = {}
    if observation is not None:
        values.update({item.tag: item.value for item in observation.raw_attributes})
        values.setdefault("BLOCK_NAME", observation.effective_name)
    for candidate in (change.baseline_value, change.project_value, change.dwg_value):
        if isinstance(candidate, dict):
            values.update(candidate)
    if change.field == "CABLE_ID":
        values["CABLE_ID"] = change.project_value or change.dwg_value or values.get("CABLE_ID")
    elif change.field == "LOAD_NAME":
        values["LOAD_NAME"] = change.project_value or change.dwg_value or values.get("LOAD_NAME")
    elif change.field == "ROOM":
        values["ROOM"] = change.project_value or change.dwg_value or values.get("ROOM")
    if change.display_context.get("room_name"):
        values["ROOM"] = change.display_context["room_name"]
    number = str(values.get("CABLE_ID") or "").strip()
    assignment = str(values.get("LOAD_NAME") or "").strip()
    room_name = str(values.get("ROOM") or "").strip()
    object_name = str(
        values.get("DEVICE_NAME") or values.get("DEVICE_TYPE") or values.get("BLOCK_NAME") or ""
    ).strip()
    block_name = str(values.get("BLOCK_NAME") or "").strip()
    return number, assignment, room_name, object_name, block_name


def _set_russian_cancel(buttons: QDialogButtonBox) -> None:
    cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
    if cancel is not None:
        cancel.setText("Отмена")


class DwgScanProgressDialog(QDialog):
    cancelRequested = Signal()

    _STAGES = {
        "CONNECTING": "Подключение",
        "SCANNING": "Сканирование",
        "VALIDATING": "Проверка",
        "FORMING_CHANGES": "Формирование изменений",
    }

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Сканирование DWG")
        self.setModal(True)
        self.setObjectName("dwgScanProgressDialog")
        self.stage_label = QLabel("Подключение", self)
        self.stage_label.setObjectName("dwgScanStage")
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setObjectName("dwgScanProgress")
        self.progress_bar.setRange(0, 0)
        self.count_label = QLabel("Точное количество объектов пока недоступно", self)
        self.count_label.setObjectName("dwgScanProcessedTotal")
        cancel = QPushButton("Отмена", self)
        cancel.setObjectName("dwgScanCancel")
        cancel.clicked.connect(self.cancelRequested.emit)
        layout = QVBoxLayout(self)
        layout.addWidget(self.stage_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.count_label)
        layout.addWidget(cancel)

    def update_progress(self, event) -> None:
        stage = getattr(event, "stage", None)
        processed = getattr(event, "processed", None)
        total = getattr(event, "total", None)
        if stage in self._STAGES:
            self.stage_label.setText(self._STAGES[stage])
        if isinstance(processed, int) and isinstance(total, int) and total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(min(processed, total))
            self.count_label.setText(f"Обработано {processed} из {total}")
        else:
            self.progress_bar.setRange(0, 0)
            self.count_label.setText("Точное количество объектов пока недоступно")


class DwgSyncPreviewDialog(QDialog):
    """Explicit selection of a direction and individual preview differences."""

    def __init__(self, proposal, parent=None) -> None:
        super().__init__(parent)
        self.proposal = proposal
        self._changing_atomic_selection = False
        self.setWindowTitle("Предпросмотр синхронизации DWG")
        self.resize(1100, 600)
        self.direction = QComboBox(self)
        self.direction.addItem("Принять выбранное из DWG в Project", "DWG_TO_PROJECT")
        self.direction.addItem("Записать выбранное из Project в DWG", "PROJECT_TO_DWG")
        self.filter_combo = QComboBox(self)
        self.filter_combo.setObjectName("dwgPreviewFilter")
        for title, value in (
            ("Действия", "ACTIONS"),
            ("Новые / изменённые", "NEW_CHANGED"),
            ("Ошибки", "ERRORS"),
            ("Совпадает", "EQUAL"),
            ("Все", "ALL"),
        ):
            self.filter_combo.addItem(title, value)
        self.search_edit = QLineEdit(self)
        self.search_edit.setObjectName("dwgPreviewSearch")
        self.search_edit.setPlaceholderText(
            "Поиск: номер, назначение, помещение, объект, Handle, BLOCK_NAME, поле"
        )
        self.select_all_button = QPushButton("Выбрать все применимые", self)
        self.select_all_button.setObjectName("dwgPreviewSelectAllApplicable")
        self.engineering_details = QCheckBox("Инженерные подробности", self)
        self.engineering_details.setObjectName("dwgPreviewEngineeringDetails")
        self.selection_notice = QLabel("", self)
        self.selection_notice.setObjectName("dwgPreviewSelectionNotice")
        self.selection_notice.setWordWrap(True)
        summary = proposal.summary
        self.summary_label = QLabel(
            f"DWG: {proposal.batch.document_identity}\n"
            f"Новые: {summary.new}; изменённые: {summary.changed}; "
            f"исчезнувшие: {summary.missing}; ошибки: {summary.invalid}; "
            f"конфликты: {summary.conflicts}",
            self,
        )
        self.table = QTableWidget(len(proposal.changes), 14, self)
        self.table.setHorizontalHeaderLabels(
            [
                "Выбор",
                "Номер линии",
                "Назначение линии",
                "Помещение",
                "Объект",
                "Статус",
                "Поле",
                "Project",
                "DWG",
                "Причина",
                "Handle DWG",
                "BLOCK_NAME",
                "Машинное поле",
                "Последняя синхронизация",
            ]
        )
        self.table.horizontalHeaderItem(13).setToolTip(
            "Значение, зафиксированное при последней подтверждённой синхронизации DWG и Project."
        )
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        header = self.table.horizontalHeader()
        header_font = header.font()
        header_font.setBold(True)
        header.setFont(header_font)
        for column, width in enumerate(
            (65, 105, 190, 155, 170, 170, 145, 190, 230, 320, 105, 150, 130, 190)
        ):
            self.table.setColumnWidth(column, width)
        observations = {item.handle: item for item in proposal.batch.observations if item.handle}
        self._row_changes = list(proposal.changes)
        for row, change in enumerate(proposal.changes):
            observation = observations.get(change.handle)
            select_item = QTableWidgetItem()
            select_item.setCheckState(Qt.CheckState.Unchecked)
            select_item.setData(Qt.ItemDataRole.UserRole, change.field_path)
            self.table.setItem(row, 0, select_item)
            number, assignment, room_name, object_name, block_name = _sync_human_context(
                change, observation
            )
            for column, value in enumerate((number, assignment, room_name, object_name), start=1):
                self.table.setItem(row, column, QTableWidgetItem(value or "—"))
            status_item = QTableWidgetItem(
                "Привязать помещение"
                if change.detail_status == "ROOM_CANONICALIZATION"
                else _SYNC_STATUS_TITLES[change.change_class]
            )
            status_item.setData(Qt.ItemDataRole.UserRole, change.change_class.value)
            status_item.setToolTip(f"Технический код: {change.change_class.value}")
            self.table.setItem(row, 5, status_item)
            reason, technical_reason = _change_reason_text(change, proposal.issues, observation)
            values = (
                _sync_field_title(change),
                change.project_value,
                change.dwg_value,
                reason,
                change.handle,
                block_name,
                change.field,
                change.baseline_value,
            )
            for column, value in enumerate(values, start=6):
                item = QTableWidgetItem(
                    _sync_object_summary(value, observation)
                    if column in {7, 8, 13}
                    else ("—" if value is None else str(value))
                )
                if isinstance(value, dict):
                    item.setToolTip(
                        "Инженерные подробности:\n"
                        + json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
                    )
                if column == 12 and change.field == "$":
                    item.setToolTip("Техническое обозначение object-level проверки: $")
                if column == 9:
                    item.setToolTip(technical_reason)
                self.table.setItem(row, column, item)
            observation_text = ""
            if observation is not None:
                observation_text = " ".join(
                    [observation.effective_name, observation.layer]
                    + [f"{item.tag} {item.value}" for item in observation.raw_attributes]
                )
            select_item.setData(
                Qt.ItemDataRole.UserRole + 1,
                " ".join(
                    str(value)
                    for value in (
                        change.handle,
                        change.field,
                        change.baseline_value,
                        change.project_value,
                        change.dwg_value,
                        reason,
                        technical_reason,
                        observation_text,
                        number,
                        assignment,
                        room_name,
                        object_name,
                        block_name,
                    )
                    if value is not None
                ).casefold(),
            )
        self.direction.currentIndexChanged.connect(self._refresh_selectable)
        self.filter_combo.currentIndexChanged.connect(self._refresh_view)
        self.search_edit.textChanged.connect(self._refresh_view)
        self.select_all_button.clicked.connect(self._select_all_applicable)
        self.engineering_details.toggled.connect(self._set_engineering_details)
        self.table.itemChanged.connect(self._selection_item_changed)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self.apply_button = buttons.button(QDialogButtonBox.StandardButton.Apply)
        self.apply_button.setText("Выполнить выбранное")
        _set_russian_cancel(buttons)
        self.apply_button.clicked.connect(self._accept_selection)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.direction)
        filters = QHBoxLayout()
        filters.addWidget(QLabel("Показывать", self))
        filters.addWidget(self.filter_combo)
        filters.addWidget(self.search_edit, 1)
        filters.addWidget(self.engineering_details)
        filters.addWidget(self.select_all_button)
        layout.addLayout(filters)
        layout.addWidget(self.selection_notice)
        layout.addWidget(self.table)
        layout.addWidget(buttons)
        self._refresh_selectable()
        self._refresh_view()
        self._set_engineering_details(False)

    def _allowed_statuses(self) -> set[ChangeClass]:
        return (
            _ACTIONABLE_IMPORT
            if self.direction.currentData() == "DWG_TO_PROJECT"
            else _ACTIONABLE_WRITE
        )

    def _refresh_view(self) -> None:
        selected_filter = self.filter_combo.currentData()
        search = self.search_edit.text().strip().casefold()
        for row, change in enumerate(self._row_changes):
            status = change.change_class
            matches_filter = {
                "ACTIONS": status in _ACTIONABLE_ALL,
                "NEW_CHANGED": status in _NEW_OR_CHANGED,
                "ERRORS": status in _ERROR_STATUSES,
                "EQUAL": status == ChangeClass.EQUAL,
                "ALL": True,
            }[selected_filter]
            haystack = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole + 1)
            self.table.setRowHidden(row, not (matches_filter and search in haystack))

    def _select_all_applicable(self) -> None:
        allowed = self._allowed_statuses()
        selected: set[str] = set()
        blocked_lines: list[str] = []
        groups = self._atomic_groups()
        grouped_paths = {path for group in groups for path in group.required_paths}
        visible_paths = {
            change.field_path
            for row, change in enumerate(self._row_changes)
            if not self.table.isRowHidden(row)
        }
        for group in groups:
            if not (group.required_paths & visible_paths):
                continue
            if group.blocked:
                blocked_lines.append(group.line_number)
            else:
                selected.update(group.required_paths)
        for row, change in enumerate(self._row_changes):
            if self.table.isRowHidden(row):
                continue
            if change.change_class in allowed and change.field_path not in grouped_paths:
                selected.add(change.field_path)
        self._set_checked_paths(selected)
        if blocked_lines:
            self.selection_notice.setText(
                "Линия "
                + ", ".join(blocked_lines)
                + " не может быть принята: есть неразрешённые ошибки или конфликты."
            )
        else:
            self.selection_notice.clear()

    def _refresh_selectable(self) -> None:
        self._set_checked_paths(set())
        self.selection_notice.clear()
        allowed = self._allowed_statuses()
        opposite = (
            _ACTIONABLE_WRITE
            if self.direction.currentData() == "DWG_TO_PROJECT"
            else _ACTIONABLE_IMPORT
        )
        for row, change in enumerate(self._row_changes):
            selection = self.table.item(row, 0)
            flags = Qt.ItemFlag.ItemIsEnabled
            if change.change_class in allowed:
                flags |= Qt.ItemFlag.ItemIsUserCheckable
                selection.setToolTip("")
            else:
                selection.setCheckState(Qt.CheckState.Unchecked)
                selection.setToolTip(
                    "Изменение доступно в направлении Project → DWG."
                    if change.change_class in opposite
                    and self.direction.currentData() == "DWG_TO_PROJECT"
                    else (
                        "Изменение доступно в направлении DWG → Project."
                        if change.change_class in opposite
                        else ""
                    )
                )
            selection.setFlags(flags)

    def _atomic_groups(self):
        if self.direction.currentData() != "DWG_TO_PROJECT":
            return ()
        return atomic_line_import_groups(self.proposal, self._allowed_statuses())

    def _set_checked_paths(self, paths: set[str]) -> None:
        self._changing_atomic_selection = True
        self.table.blockSignals(True)
        try:
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 0)
                path = item.data(Qt.ItemDataRole.UserRole)
                item.setCheckState(
                    Qt.CheckState.Checked if path in paths else Qt.CheckState.Unchecked
                )
        finally:
            self.table.blockSignals(False)
            self._changing_atomic_selection = False

    def _selection_item_changed(self, item: QTableWidgetItem) -> None:
        if self._changing_atomic_selection or item.column() != 0:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        group = next(
            (group for group in self._atomic_groups() if path in group.required_paths),
            None,
        )
        if group is None:
            return
        selected = self.selected_paths()
        if item.checkState() == Qt.CheckState.Checked:
            if group.blocked:
                selected.difference_update(group.required_paths)
                self.selection_notice.setText(
                    f"Линия {group.line_number} не может быть принята: "
                    "есть неразрешённые ошибки или конфликты."
                )
            else:
                selected.update(group.required_paths)
                self.selection_notice.clear()
        else:
            selected.difference_update(group.required_paths)
        self._set_checked_paths(selected)

    def _set_engineering_details(self, visible: bool) -> None:
        for column in range(10, 14):
            self.table.setColumnHidden(column, not visible)

    def _accept_selection(self) -> None:
        selected = self.selected_paths()
        for group in self._atomic_groups():
            selected_group = selected & set(group.required_paths)
            if selected_group and (group.blocked or selected_group != set(group.required_paths)):
                self.selection_notice.setText(
                    f"Линия {group.line_number} не может быть принята целиком. "
                    "Проверьте ошибки и конфликты линии."
                )
                return
        self.accept()

    def selected_paths(self) -> set[str]:
        return {
            self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            for row in range(self.table.rowCount())
            if self.table.item(row, 0).checkState() == Qt.CheckState.Checked
        }


class DwgSyncResolutionDialog(QDialog):
    """Only the DWG changes that still require a user decision."""

    def __init__(self, proposal, plan, runtime_errors=(), parent=None) -> None:
        super().__init__(parent)
        self.proposal = proposal
        self.plan = plan
        self._import_paths: set[str] = set()
        self._write_paths: set[str] = set()
        self._bus_roots: set[str] = set()
        self.open_checks_requested = False
        self.setWindowTitle("Требуют решения")
        self.resize(860, 520)

        rows = [("CONFLICT", item) for item in plan.conflicts]
        rows.extend(("PROBLEM", item) for item in plan.problems)
        rows.extend(("BUS_ROOT", designation) for designation in plan.missing_bus_roots)
        rows.extend(("RUNTIME", message) for message in runtime_errors)

        self.table = QTableWidget(len(rows), 6, self)
        self.table.setObjectName("dwgResolutionTable")
        self.table.setHorizontalHeaderLabels(
            ["Объект", "Поле", "Project", "DWG", "Причина", "Действие"]
        )
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self.table.horizontalHeader()
        header_font = header.font()
        header_font.setBold(True)
        header.setFont(header_font)
        for column, width in enumerate((165, 145, 150, 150, 270, 245)):
            self.table.setColumnWidth(column, width)

        observations = {
            item.handle: item for item in proposal.batch.observations if item.handle
        }
        for row, (kind, payload) in enumerate(rows):
            if kind == "RUNTIME":
                values = ("Обновление DWG", "—", "—", "—", str(payload))
                for column, value in enumerate(values):
                    self.table.setItem(row, column, QTableWidgetItem(value))
                action = QPushButton("Открыть проверки", self.table)
                action.clicked.connect(self._request_checks)
                self.table.setCellWidget(row, 5, action)
                continue
            if kind == "BUS_ROOT":
                designation = str(payload)
                values = (
                    designation,
                    "Источник",
                    "—",
                    f"{designation}.001…",
                    "В DWG найдены точки шины, но физический источник RS-485 не назначен.",
                )
                for column, value in enumerate(values):
                    self.table.setItem(row, column, QTableWidgetItem(value))
                action = QPushButton("Назначить источник", self.table)
                action.clicked.connect(
                    lambda _checked=False, value=designation, r=row: self._request_bus_root(
                        r, value
                    )
                )
                self.table.setCellWidget(row, 5, action)
                continue

            change = payload
            observation = observations.get(change.handle)
            number, assignment, room_name, object_name, _block = _sync_human_context(
                change, observation
            )
            subject = number or object_name or room_name or change.handle or "DWG"
            reason, _technical = _change_reason_text(change, proposal.issues, observation)
            values = (
                subject,
                _sync_field_title(change),
                _sync_object_summary(change.project_value, observation),
                _sync_object_summary(change.dwg_value, observation),
                reason,
            )
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(str(value or "—")))

            actions = QWidget(self.table)
            actions_layout = QHBoxLayout(actions)
            actions_layout.setContentsMargins(0, 0, 0, 0)
            actions_layout.setSpacing(4)
            if kind == "CONFLICT":
                keep_project = QPushButton("Оставить Project", actions)
                keep_dwg = QPushButton("Оставить DWG", actions)
                keep_project.clicked.connect(
                    lambda _checked=False, path=change.field_path, r=row: self._choose(
                        r, path, "PROJECT"
                    )
                )
                keep_dwg.clicked.connect(
                    lambda _checked=False, path=change.field_path, r=row: self._choose(
                        r, path, "DWG"
                    )
                )
                actions_layout.addWidget(keep_project)
                actions_layout.addWidget(keep_dwg)
            elif change.detail_status == "ROOM_CANONICALIZATION":
                link_room = QPushButton("Привязать помещение", actions)
                link_room.clicked.connect(
                    lambda _checked=False, path=change.field_path, r=row: self._choose(
                        r, path, "DWG"
                    )
                )
                actions_layout.addWidget(link_room)
            else:
                checks = QPushButton("Открыть проверки", actions)
                checks.clicked.connect(self._request_checks)
                actions_layout.addWidget(checks)
            self.table.setCellWidget(row, 5, actions)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        close = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close is not None:
            close.setText("Закрыть")

        layout = QVBoxLayout(self)
        layout.addWidget(self.table)
        layout.addWidget(buttons)

    def _choose(self, row: int, path: str, side: str) -> None:
        self._import_paths.discard(path)
        self._write_paths.discard(path)
        if side == "DWG":
            self._import_paths.add(path)
        else:
            self._write_paths.add(path)
        item = self.table.item(row, 4)
        if item is not None:
            item.setText("Решение выбрано")
        widget = self.table.cellWidget(row, 5)
        if widget is not None:
            widget.setEnabled(False)

    def _request_bus_root(self, row: int, designation: str) -> None:
        self._bus_roots.add(designation)
        item = self.table.item(row, 4)
        if item is not None:
            item.setText("Источник будет назначен")
        widget = self.table.cellWidget(row, 5)
        if widget is not None:
            widget.setEnabled(False)

    def requested_bus_roots(self) -> set[str]:
        return set(self._bus_roots)

    def _request_checks(self) -> None:
        self.open_checks_requested = True
        self.accept()

    def selected_import_paths(self) -> set[str]:
        return set(self._import_paths)

    def selected_write_paths(self) -> set[str]:
        return set(self._write_paths)


def _optional_decimal(text: str) -> Decimal | None:
    clean = text.strip().replace(",", ".")
    if not clean:
        return None
    try:
        return Decimal(clean)
    except InvalidOperation as exc:
        raise ObjectValidationError(f"Некорректное число: {text}") from exc


class ProjectDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Новый объект")
        self.name = QLineEdit(self)
        self.code = QLineEdit(self)
        self.object_type = QLineEdit(self)
        self.address = QLineEdit(self)
        self.area = QLineEdit(self)
        self.customer = QLineEdit(self)
        self.designer = QLineEdit(self)
        self.note = QTextEdit(self)
        form = QFormLayout()
        for label, widget in (
            ("Название объекта", self.name),
            ("Шифр проекта", self.code),
            ("Тип объекта", self.object_type),
            ("Адрес объекта", self.address),
            ("Общая проектируемая площадь, м²", self.area),
            ("Заказчик", self.customer),
            ("Ответственный проектировщик", self.designer),
            ("Примечание", self.note),
        ):
            form.addRow(label, widget)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        _set_russian_cancel(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def value(self) -> ProjectCard:
        return ProjectCard(
            name=self.name.text(),
            project_code=self.code.text(),
            object_type=self.object_type.text(),
            address=self.address.text(),
            total_area_m2=_optional_decimal(self.area.text()),
            customer=self.customer.text(),
            responsible_designer=self.designer.text(),
            note=self.note.toPlainText(),
        )


class RoomDialog(QDialog):
    def __init__(self, buildings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Помещение")
        self.building = QComboBox(self)
        for item in buildings:
            self.building.addItem(item.name, item.id)
        self.name = QLineEdit(self)
        self.base_mark = QLineEdit(self)
        self.height = QLineEdit(self)
        self.color = RoomColorComboBox(self)
        self.color.set_color("#FFFFFF")
        form = QFormLayout()
        form.addRow("Здание", self.building)
        form.addRow("Название помещения", self.name)
        form.addRow("Отметка основания, мм", self.base_mark)
        form.addRow("Высота помещения, м", self.height)
        form.addRow("Цвет маркировки", self.color)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        _set_russian_cancel(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def load_room(self, room) -> None:
        self.building.setCurrentIndex(self.building.findData(room.building_id))
        self.name.setText(room.name)
        self.base_mark.setText("" if room.base_mark_mm is None else str(room.base_mark_mm))
        self.height.setText("" if room.height_m is None else str(room.height_m))
        self.color.set_color(room.marking_color)


class ObjectWorkspace(QWidget):
    MAIN_SECTIONS = (
        "Проект",
        "Линии",
        "Оборудование",
        "Щиты",
        "Трассы",
        "Документы",
        "DWG",
    )

    def __init__(self, runtime, parent=None) -> None:
        super().__init__(parent)
        self.runtime = runtime
        self._detail = None
        self._sync_operation = None
        self._sync_in_progress = False
        self._sync_progress_dialog = None
        self._navigation_history: list[dict] = []
        self.lines_workspace = None
        self.equipment_workspace = None
        self.documents_workspace = None

        self.current_object_label = QLabel("Объект не выбран", self)
        self.current_object_label.setObjectName("currentObjectLabel")
        self.today_label = QLabel("Сегодня 0 ч 0 мин", self)
        self.today_label.setObjectName("todayTimeLabel")
        self.total_label = QLabel("Всего 0 ч 0 мин", self)
        self.total_label.setObjectName("totalTimeLabel")
        self.time_button = QPushButton("Play", self)
        self.time_button.setObjectName("timeToggleButton")
        self.time_button.clicked.connect(self._toggle_time)
        self.sync_button = QPushButton("Обновить", self)
        self.sync_button.setObjectName("dwgSyncButton")
        self.sync_button.setEnabled(False)
        self.sync_status_label = QLabel("", self)
        self.sync_status_label.setObjectName("dwgSyncStatusLabel")
        self.sync_button.clicked.connect(self._sync_dwg)
        self.cables_button = QPushButton("Кабельные линии", self)
        self.cables_button.setObjectName("cableWorkspaceButton")
        self.cables_button.setEnabled(False)
        self.cables_button.clicked.connect(self._open_cables)
        self.constructor_button = QPushButton("Конструктор", self)
        self.constructor_button.setObjectName("constructorWorkspaceButton")
        self.constructor_button.setEnabled(False)
        self.constructor_button.clicked.connect(self._open_constructor)
        self.distribution_button = QPushButton("Распределение", self)
        self.distribution_button.setObjectName("distributionWorkspaceButton")
        self.distribution_button.setEnabled(False)
        self.distribution_button.clicked.connect(self._open_distribution)
        self.automation_button = QPushButton("Автоматизация", self)
        self.automation_button.setObjectName("automationWorkspaceButton")
        self.automation_button.setEnabled(False)
        self.automation_button.clicked.connect(self._open_automation)
        self.buses_button = QPushButton("Шины", self)
        self.buses_button.setObjectName("busWorkspaceButton")
        self.buses_button.setEnabled(False)
        self.buses_button.clicked.connect(self._open_buses)
        self.panels_button = QPushButton("Щиты", self)
        self.panels_button.setObjectName("panelWorkspaceButton")
        self.panels_button.setEnabled(False)
        self.panels_button.clicked.connect(self._open_panels)
        self.specification_button = QPushButton("Спецификация", self)
        self.specification_button.setObjectName("specificationWorkspaceButton")
        self.specification_button.setEnabled(False)
        self.specification_button.clicked.connect(self._open_specification)
        self.validation_button = QPushButton("Проверки", self)
        self.validation_button.setObjectName("validationCenterButton")
        self.validation_button.setEnabled(False)
        self.validation_button.clicked.connect(self._open_validation_center)
        self.self_check_button = QPushButton("Self-check", self)
        self.self_check_button.setObjectName("selfCheckButton")
        self.self_check_button.clicked.connect(self._run_self_check)
        self.backup_button = QPushButton("Ручной backup", self)
        self.backup_button.setObjectName("manualBackupButton")
        self.backup_button.clicked.connect(self._manual_backup)
        for button in (
            self.cables_button,
            self.constructor_button,
            self.distribution_button,
            self.automation_button,
            self.buses_button,
            self.panels_button,
            self.specification_button,
            self.validation_button,
            self.self_check_button,
            self.backup_button,
        ):
            button.hide()

        self.service_button = QToolButton(self)
        self.service_button.setObjectName("serviceMenuButton")
        self.service_button.setText("Сервис / Инженерные подробности")
        self.service_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        service_menu = QMenu(self.service_button)
        for title, callback in (
            ("Кабельные линии и каталог (expert)", self._open_cables),
            ("Конструктор связей (expert)", self._open_constructor),
            ("Распределение", self._open_distribution),
            ("Автоматизация", self._open_automation),
            ("Шины", self._open_buses),
            ("Self-check", self._run_self_check),
            ("Ручной backup", self._manual_backup),
        ):
            service_menu.addAction(QAction(title, service_menu, triggered=callback))
        self.service_button.setMenu(service_menu)

        top = QVBoxLayout()
        top.addWidget(self.current_object_label)
        top.addWidget(self.today_label)
        second = QHBoxLayout()
        second.addWidget(self.total_label)
        second.addWidget(self.time_button)
        second.addWidget(self.sync_button)
        second.addWidget(self.sync_status_label)
        second.addStretch(1)
        second.addWidget(self.service_button)
        top.addLayout(second)

        self.navigation_group = QButtonGroup(self)
        self.navigation_group.setExclusive(True)
        self.navigation_buttons = {}
        navigation = QHBoxLayout()
        for section in self.MAIN_SECTIONS:
            button = QPushButton(section, self)
            button.setObjectName(f"mainNavigation{section}Button")
            button.setCheckable(True)
            button.setEnabled(section == "Проект")
            button.clicked.connect(lambda _checked=False, name=section: self._switch_section(name))
            self.navigation_group.addButton(button)
            self.navigation_buttons[section] = button
            navigation.addWidget(button)
        navigation.addStretch(1)
        top.addLayout(navigation)

        self.create_button = QPushButton("Создать объект", self)
        self.create_button.setObjectName("createProjectButton")
        self.create_button.clicked.connect(self._create_project)
        self.close_button = QPushButton("Закрыть объект", self)
        self.close_button.setObjectName("closeProjectButton")
        self.close_button.clicked.connect(self._close_project)
        self.tree = QTreeWidget(self)
        self.tree.setObjectName("objectRegistryTree")
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(False)
        self.tree.itemSelectionChanged.connect(self._tree_selection_changed)
        left = QWidget(self)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.create_button)
        left_layout.addWidget(self.close_button)
        left_layout.addWidget(self.tree)

        self.tabs = QTabWidget(self)
        self.tabs.setObjectName("objectCardTabs")
        self.general_tab = self._build_general_tab()
        self.rooms_tab = self._build_rooms_tab()
        self.settings_tab = self._build_settings_tab()
        self.time_tab = self._build_time_tab()
        self.tabs.addTab(self.general_tab, "Общие данные")
        self.tabs.addTab(self.rooms_tab, "Помещения")
        self.tabs.addTab(self.settings_tab, "Настройки")
        self.tabs.addTab(self.time_tab, "Время работы")
        self.tabs.currentChanged.connect(self.runtime.navigate_within_project)
        if self.runtime.ui_state is not None:
            state = self.runtime.ui_state.load()
            index = state.get("last_object_tab", 0)
            if isinstance(index, int) and 0 <= index < self.tabs.count():
                self.tabs.setCurrentIndex(index)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(left)
        splitter.addWidget(self.tabs)
        splitter.setStretchFactor(1, 1)
        self.project_page = QWidget(self)
        project_layout = QVBoxLayout(self.project_page)
        project_layout.setContentsMargins(0, 0, 0, 0)
        project_layout.addWidget(splitter)
        self.section_stack = QStackedWidget(self)
        self.section_stack.setObjectName("mainSectionStack")
        self.section_stack.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self.section_stack.setMinimumSize(0, 0)
        self.section_pages = {"Проект": self.project_page}
        self.section_stack.addWidget(self.project_page)
        for section in self.MAIN_SECTIONS[1:]:
            page = self._build_section_adapter(section)
            self.section_pages[section] = page
            self.section_stack.addWidget(page)
        root = QVBoxLayout(self)
        root.addLayout(top)
        root.addWidget(self.section_stack)
        self.navigation_buttons["Проект"].setChecked(True)

        self.refresh_registry()
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self.refresh_time)
        self._timer.start()

    def _build_section_adapter(self, section: str) -> QWidget:
        page = QWidget(self)
        page.setObjectName(f"{section}SectionAdapter")
        layout = QVBoxLayout(page)
        actions = {
            "Линии": (),
            "Оборудование": (),
            "Щиты": (("Открыть щиты", self._open_panels),),
            "Трассы": (("Открыть трассы и трубы", self._open_cables),),
            "Документы": (
                ("Открыть спецификацию", self._open_specification),
                ("Открыть проверки", self._open_validation_center),
            ),
            "DWG": (("Обновить", self._sync_dwg),),
        }[section]
        for index, (title, callback) in enumerate(actions):
            button = QPushButton(title, page)
            button.setObjectName(f"{section}AdapterAction{index}")
            button.clicked.connect(callback)
            layout.addWidget(button)
        layout.addStretch(1)
        return page

    def _replace_section_page(self, section: str, page: QWidget) -> None:
        old = self.section_pages[section]
        index = self.section_stack.indexOf(old)
        self.section_stack.removeWidget(old)
        old.deleteLater()
        self.section_stack.insertWidget(index, page)
        self.section_pages[section] = page

    def _install_working_pages(self, project_id: str) -> None:
        lines = LinesWorkspace(
            self.runtime.cables,
            self.runtime.constructor,
            project_id,
            ui_state=self.runtime.ui_state,
            guided_service=self.runtime.guided_actions,
            bulk_service=self.runtime.bulk_actions,
            status_service=self.runtime.integrated_ui,
            bus_service=self.runtime.buses,
            parent=self,
        )
        lines.resourceRequested.connect(self._navigate_line_to_resource)
        lines.issueRequested.connect(self._show_line_issue)
        lines.busRequested.connect(self._show_bus_issue)
        lines.projectChanged.connect(self._refresh_related_working_views)
        equipment = EquipmentWorkspace(
            self.runtime.constructor,
            project_id,
            self,
            status_service=self.runtime.integrated_ui,
            ui_state=self.runtime.ui_state,
        )
        equipment.lineRequested.connect(self._navigate_equipment_to_line)
        equipment.backRequested.connect(self._navigate_back)
        equipment.engineeringDetailsRequested.connect(self._open_equipment_details)
        equipment.issueRequested.connect(self._show_instance_issue)
        documents = DocumentsWorkspace(
            self.runtime.integrated_ui,
            project_id,
            ui_state=self.runtime.ui_state,
            specification_service=self.runtime.specification,
            parent=self,
        )
        documents.lineRequested.connect(self._navigate_documents_to_line)
        documents.issueRequested.connect(self._navigate_issue)
        documents.specificationRequested.connect(self._open_specification)
        documents.specificationSourceRequested.connect(self._navigate_specification_source)
        self._replace_section_page("Линии", lines)
        self._replace_section_page("Оборудование", equipment)
        self._replace_section_page("Документы", documents)
        self.lines_workspace = lines
        self.equipment_workspace = equipment
        self.documents_workspace = documents

    def _switch_section(self, section: str, *, save: bool = True) -> None:
        if section not in self.section_pages:
            return
        if section != "Проект" and self.runtime.current_project_id is None:
            return
        self.section_stack.setCurrentWidget(self.section_pages[section])
        self.navigation_buttons[section].setChecked(True)
        if save and self.runtime.ui_state is not None:
            self.runtime.ui_state.update(active_main_section=section)

    def _navigate_line_to_resource(self, resource_id: str) -> None:
        if self.lines_workspace is None or self.equipment_workspace is None:
            return
        self.lines_workspace.save_state()
        self._navigation_history.append(
            {"section": "Линии", "line_id": self.lines_workspace.current_line_id()}
        )
        self.equipment_workspace.refresh(selected_resource_id=resource_id)
        self._switch_section("Оборудование")

    def _navigate_equipment_to_line(self, line_id: str) -> None:
        if self.lines_workspace is None or self.equipment_workspace is None:
            return
        self._navigation_history.append(
            {
                "section": "Оборудование",
                "instance_id": self.equipment_workspace._selected_instance_id(),
                "resource_id": self.equipment_workspace._selected_resource_id(),
            }
        )
        self.lines_workspace.select_line(line_id)
        self._switch_section("Линии")

    def _navigate_documents_to_line(self, line_id: str) -> None:
        if self.lines_workspace is None:
            return
        self._navigation_history.append({"section": "Документы"})
        self.lines_workspace.select_line(line_id)
        self._switch_section("Линии")

    def _navigate_specification_source(self, source_kind: str, source_id: str) -> None:
        if source_kind == "CABLE_LINE" and self.lines_workspace is not None:
            self._navigation_history.append({"section": "Документы"})
            self.lines_workspace.select_line(source_id)
            self._switch_section("Линии")
        elif source_kind == "PROJECT_INSTANCE" and self.equipment_workspace is not None:
            self._navigation_history.append({"section": "Документы"})
            self.equipment_workspace.refresh(selected_instance_id=source_id)
            self._switch_section("Оборудование")
        elif (
            source_kind in {"FIELD_DEVICE", "MOUNTING_BOX_DEMAND"}
            and self.equipment_workspace is not None
        ):
            self._navigation_history.append({"section": "Документы"})
            self.equipment_workspace.show_field_device(source_id)
            self._switch_section("Оборудование")
        elif source_kind == "CONDUIT":
            self._navigation_history.append({"section": "Документы"})
            self._switch_section("Трассы")
            self._open_cables()
        elif source_kind == "ASSEMBLY_MATERIAL":
            self._navigation_history.append({"section": "Документы"})
            self._switch_section("Щиты")
            self._open_panels()
        elif source_kind == "LED_PROFILE":
            self._navigation_history.append({"section": "Документы"})
            self._switch_section("Автоматика")
            self._open_automation()

    def _show_line_issue(self, issue) -> None:
        if isinstance(issue, str):
            if self.documents_workspace is None:
                return
            self.documents_workspace.show_issue_for("CABLE_LINE", issue)
            self._switch_section("Документы")
            return

        if not isinstance(issue, dict):
            return
        line_id = str(issue.get("line_id") or "")
        title = str(issue.get("title") or "Требует внимания")
        reason = str(issue.get("reason") or "Проблема требует исправления.")
        required_action = str(issue.get("required_action") or "")
        fix_action = str(issue.get("fix_action") or "")
        segment_id = str(issue.get("segment_id") or "")

        dialog = QMessageBox(self)
        dialog.setWindowTitle(title)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setText(reason)
        if required_action:
            dialog.setInformativeText(required_action)

        fix_button = None
        if fix_action == "SYNC_DWG":
            fix_button = dialog.addButton(
                "Обновить DWG",
                QMessageBox.ButtonRole.AcceptRole,
            )
        elif fix_action == "RECALCULATE":
            fix_button = dialog.addButton(
                "Пересчитать",
                QMessageBox.ButtonRole.AcceptRole,
            )
        elif fix_action == "OPEN_BUS":
            fix_button = dialog.addButton(
                "Открыть шину",
                QMessageBox.ButtonRole.AcceptRole,
            )
        elif fix_action == "OPEN_LINE":
            fix_button = dialog.addButton(
                "Открыть линию",
                QMessageBox.ButtonRole.AcceptRole,
            )
        dialog.addButton(QMessageBox.StandardButton.Close)
        dialog.exec()

        if fix_button is None or dialog.clickedButton() is not fix_button:
            return
        if fix_action == "SYNC_DWG":
            self._sync_dwg()
            return
        if fix_action == "OPEN_BUS":
            self._show_bus_issue(line_id)
            return
        if fix_action == "OPEN_LINE":
            if self.lines_workspace is not None:
                self.lines_workspace._open_line_details(line_id)
            return
        if fix_action == "RECALCULATE":
            project_id = self.runtime.current_project_id
            service = self.runtime.cables
            if project_id is None or service is None:
                return
            try:
                if segment_id:
                    service.recalculate(project_id=project_id, segment_ids={segment_id})
                else:
                    service.recalculate(project_id=project_id, cable_line_ids={line_id})
            except Exception as exc:
                QMessageBox.warning(self, "Пересчёт не выполнен", str(exc))
                return
            if self.lines_workspace is not None:
                self.lines_workspace.refresh(selected_line_id=line_id)
            self._refresh_related_working_views()

    def _show_bus_issue(self, bus_id: str) -> None:
        project_id = self.runtime.current_project_id
        service = self.runtime.buses
        if project_id is None or service is None:
            return
        dialog = BusWorkspaceDialog(service, project_id, self)
        dialog.refresh(bus_id)
        dialog.exec()

    def _show_instance_issue(self, instance_id: str) -> None:
        if self.documents_workspace is None:
            return
        self.documents_workspace.show_issue_for("PROJECT_INSTANCE", instance_id)
        self._switch_section("Документы")

    def _refresh_related_working_views(self) -> None:
        if self.equipment_workspace is not None:
            self.equipment_workspace.refresh(
                selected_instance_id=self.equipment_workspace._selected_instance_id(),
                selected_resource_id=self.equipment_workspace._selected_resource_id(),
            )
        if self.documents_workspace is not None:
            self.documents_workspace.refresh()

    def _navigate_issue(self, item) -> None:
        target = getattr(item, "navigation", None)
        if target is None:
            return self._navigate_legacy_issue(item)
        if target.entity_kind == "CABLE_LINE" and self.lines_workspace is not None:
            self.lines_workspace.select_line(target.entity_id)
            self._switch_section("Линии")
        elif target.entity_kind == "RESOURCE" and self.equipment_workspace is not None:
            self.equipment_workspace.refresh(selected_resource_id=target.entity_id)
            self._switch_section("Оборудование")
        elif target.entity_kind == "PROJECT_INSTANCE" and self.equipment_workspace is not None:
            self.equipment_workspace.refresh(selected_instance_id=target.entity_id)
            self._switch_section("Оборудование")
        elif target.section == "Щиты":
            self._switch_section("Щиты")
            self._open_panels()
        elif target.section == "Трассы":
            self._switch_section("Трассы")
            self._open_cables()
        elif target.section == "DWG":
            self._switch_section("DWG")
        elif target.context == "SPECIFICATION":
            self._open_specification()
        elif target.entity_kind == "BUS":
            self._open_buses()

    def _navigate_legacy_issue(self, item) -> None:
        project_id = self.runtime.current_project_id
        if project_id is None:
            return
        if item.source_kind == "CABLE_LINE":
            self._show_cables(project_id, item.source_id)
        elif item.source_kind == "RESOURCE":
            self._show_constructor(project_id, selected_resource_id=item.source_id)
        elif item.source_kind == "PROJECT_INSTANCE":
            self._show_constructor(project_id, selected_instance_id=item.source_id)
        elif item.section == "PANELS":
            self._open_panels()
        elif item.section == "SPECIFICATION":
            self._open_specification()

    def _navigate_back(self) -> None:
        if not self._navigation_history:
            self._switch_section("Линии")
            return
        target = self._navigation_history.pop()
        if target["section"] == "Линии" and self.lines_workspace is not None:
            self.lines_workspace.select_line(target.get("line_id"))
        elif target["section"] == "Оборудование" and self.equipment_workspace is not None:
            self.equipment_workspace.refresh(
                selected_instance_id=target.get("instance_id"),
                selected_resource_id=target.get("resource_id"),
            )
        self._switch_section(target["section"])

    def _open_equipment_details(self, instance_id: str, resource_id: str) -> None:
        project_id = self.runtime.current_project_id
        if project_id is None:
            return
        self._show_constructor(
            project_id,
            selected_instance_id=instance_id or None,
            selected_resource_id=resource_id or None,
        )

    def _build_general_tab(self) -> QWidget:
        tab = QWidget(self)
        self.general_fields = {
            key: QLineEdit(tab)
            for key in (
                "name",
                "project_code",
                "object_type",
                "address",
                "total_area_m2",
                "customer",
                "responsible_designer",
            )
        }
        self.general_note = QTextEdit(tab)
        form = QFormLayout()
        labels = {
            "name": "Название объекта",
            "project_code": "Шифр проекта",
            "object_type": "Тип объекта",
            "address": "Адрес объекта",
            "total_area_m2": "Общая проектируемая площадь, м²",
            "customer": "Заказчик",
            "responsible_designer": "Ответственный проектировщик",
        }
        for key, widget in self.general_fields.items():
            widget.setObjectName(f"project_{key}")
            form.addRow(labels[key], widget)
        form.addRow("Примечание", self.general_note)
        save = QPushButton("Сохранить общие данные", tab)
        save.clicked.connect(self._save_general)
        layout = QVBoxLayout(tab)
        layout.addLayout(form)
        layout.addWidget(save)
        layout.addStretch(1)
        return tab

    def _build_rooms_tab(self) -> QWidget:
        tab = QWidget(self)
        add_building = QPushButton("Добавить здание", tab)
        add_building.clicked.connect(self._add_building)
        add_room = QPushButton("Добавить помещение", tab)
        add_room.clicked.connect(self._add_room)
        delete_room = QPushButton("Удалить помещение", tab)
        delete_room.clicked.connect(self._delete_room)
        controls = QHBoxLayout()
        controls.addWidget(add_building)
        controls.addWidget(add_room)
        controls.addWidget(delete_room)
        controls.addStretch(1)
        self.rooms_table = QTableWidget(0, 5, tab)
        self.rooms_table.setObjectName("roomsTable")
        self.rooms_table.setHorizontalHeaderLabels(
            ["Здание", "Название", "Отметка, мм", "Высота, м", "Цвет"]
        )
        self.rooms_table.setItemDelegateForColumn(4, RoomSwatchDelegate(self.rooms_table))
        self.rooms_table.cellDoubleClicked.connect(self._edit_room)
        layout = QVBoxLayout(tab)
        layout.addLayout(controls)
        layout.addWidget(self.rooms_table)
        return tab

    def _build_settings_tab(self) -> QWidget:
        tab = QWidget(self)
        self.setting_fields = {
            "project_folder": QLineEdit(tab),
            "output_folder": QLineEdit(tab),
            "versions_folder": QLineEdit(tab),
            "cable_reserve_at_board_m": QLineEdit(tab),
        }
        self.initial_page = QSpinBox(tab)
        self.initial_page.setRange(0, 999999)
        self.initial_page.setSpecialValueText("Не задан")
        form = QFormLayout()
        form.addRow("Папка проекта", self.setting_fields["project_folder"])
        form.addRow("Папка вывода", self.setting_fields["output_folder"])
        form.addRow("Папка версий", self.setting_fields["versions_folder"])
        form.addRow("Начальный номер страниц", self.initial_page)
        form.addRow("Запас кабеля у щита, м", self.setting_fields["cable_reserve_at_board_m"])
        save = QPushButton("Сохранить настройки", tab)
        save.clicked.connect(self._save_settings)
        layout = QVBoxLayout(tab)
        layout.addLayout(form)
        layout.addWidget(save)
        layout.addStretch(1)
        return tab

    def _build_time_tab(self) -> QWidget:
        tab = QWidget(self)
        self.time_tab_today = QLabel("Сегодня 0 ч 0 мин", tab)
        self.time_tab_total = QLabel("Всего 0 ч 0 мин", tab)
        self.time_tab_state = QLabel("Остановлен", tab)
        self.time_tab_button = QPushButton("Play", tab)
        self.time_tab_button.clicked.connect(self._toggle_time)
        layout = QVBoxLayout(tab)
        layout.addWidget(self.time_tab_today)
        layout.addWidget(self.time_tab_total)
        layout.addWidget(self.time_tab_state)
        layout.addWidget(self.time_tab_button)
        layout.addStretch(1)
        return tab

    def refresh_registry(self) -> None:
        selected = self.runtime.current_project_id
        self.tree.clear()
        registry = QTreeWidgetItem(["Реестр объектов"])
        registry.setData(0, Qt.ItemDataRole.UserRole, None)
        self.tree.addTopLevelItem(registry)
        for item in self.runtime.objects.list_projects():
            node = QTreeWidgetItem([f"{item.project_code} — {item.name}"])
            node.setData(0, Qt.ItemDataRole.UserRole, item.id)
            self.tree.addTopLevelItem(node)
            if item.id == selected:
                self.tree.setCurrentItem(node)

    def open_project(self, project_id: str) -> None:
        top_level = self.window()
        preserve_window = isinstance(top_level, QMainWindow)
        geometry = top_level.geometry() if preserve_window else None
        was_maximized = top_level.isMaximized() if preserve_window else False
        self._detail = self.runtime.open_project(project_id)
        self._load_detail()
        self.refresh_registry()
        self.refresh_time()
        self.sync_button.setEnabled(self.runtime.dwg_sync is not None)
        self.cables_button.setEnabled(self.runtime.cables is not None)
        self.constructor_button.setEnabled(self.runtime.constructor is not None)
        self.distribution_button.setEnabled(self.runtime.distribution is not None)
        self.automation_button.setEnabled(self.runtime.automation is not None)
        self.buses_button.setEnabled(self.runtime.buses is not None)
        self.panels_button.setEnabled(self.runtime.panels is not None)
        self.specification_button.setEnabled(self.runtime.specification is not None)
        self.validation_button.setEnabled(self.runtime.integrated_ui is not None)
        for button in self.navigation_buttons.values():
            button.setEnabled(True)
        if self.runtime.cables is not None and self.runtime.constructor is not None:
            self._install_working_pages(project_id)
        self._navigation_history.clear()
        self._switch_section("Линии")
        if preserve_window:
            self._restore_top_level_window(top_level, geometry, was_maximized)
            QTimer.singleShot(
                0,
                lambda: self._restore_top_level_window(top_level, geometry, was_maximized),
            )

    @staticmethod
    def _restore_top_level_window(window, geometry, was_maximized: bool) -> None:
        if was_maximized:
            if not window.isMaximized():
                window.showMaximized()
        elif geometry is not None:
            if window.isMaximized():
                window.showNormal()
            window.setGeometry(geometry)

    def _tree_selection_changed(self) -> None:
        item = self.tree.currentItem()
        project_id = None if item is None else item.data(0, Qt.ItemDataRole.UserRole)
        if project_id and project_id != self.runtime.current_project_id:
            self.open_project(project_id)

    def _create_project(self) -> None:
        dialog = ProjectDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            project_id = self.runtime.objects.create_project(dialog.value())
            self.open_project(project_id)
        except ObjectValidationError as exc:
            QMessageBox.warning(self, "Объект не сохранён", str(exc))

    def _close_project(self) -> None:
        if self.lines_workspace is not None:
            self.lines_workspace.save_state()
        self.runtime.close_project()
        self._detail = None
        self.tree.blockSignals(True)
        self.tree.clearSelection()
        self.tree.setCurrentItem(None)
        self.tree.blockSignals(False)
        self.current_object_label.setText("Объект не выбран")
        self.sync_button.setEnabled(False)
        self.cables_button.setEnabled(False)
        self.constructor_button.setEnabled(False)
        self.distribution_button.setEnabled(False)
        self.automation_button.setEnabled(False)
        self.buses_button.setEnabled(False)
        self.panels_button.setEnabled(False)
        self.specification_button.setEnabled(False)
        self.validation_button.setEnabled(False)
        for section, button in self.navigation_buttons.items():
            button.setEnabled(section == "Проект")
        self._navigation_history.clear()
        self._switch_section("Проект")
        for field in self.general_fields.values():
            field.clear()
        self.general_note.clear()
        self.rooms_table.setRowCount(0)
        self.refresh_time()

    def _load_detail(self) -> None:
        if self._detail is None:
            return
        card = self._detail.card
        values = {
            "name": card.name,
            "project_code": card.project_code,
            "object_type": card.object_type,
            "address": card.address,
            "total_area_m2": "" if card.total_area_m2 is None else str(card.total_area_m2),
            "customer": card.customer,
            "responsible_designer": card.responsible_designer,
        }
        for key, value in values.items():
            self.general_fields[key].setText(value)
        self.general_note.setPlainText(card.note)
        self.current_object_label.setText(f"{card.project_code} — {card.name}")
        settings = self._detail.settings
        for key in ("project_folder", "output_folder", "versions_folder"):
            self.setting_fields[key].setText(getattr(settings, key))
        self.setting_fields["cable_reserve_at_board_m"].setText(
            ""
            if settings.cable_reserve_at_board_m is None
            else str(settings.cable_reserve_at_board_m)
        )
        self.initial_page.setValue(settings.initial_page_number or 0)
        self.rooms_table.setRowCount(len(self._detail.rooms))
        for row_index, item in enumerate(self._detail.rooms):
            values = (
                item.building_name,
                item.name,
                "" if item.base_mark_mm is None else str(item.base_mark_mm),
                "" if item.height_m is None else str(item.height_m),
                "",
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setData(Qt.ItemDataRole.UserRole, item.id)
                if column == 4:
                    cell.setData(ROOM_COLOR_ROLE, item.marking_color)
                    cell.setToolTip(item.marking_color)
                self.rooms_table.setItem(row_index, column, cell)

    def _save_general(self) -> None:
        if self._detail is None:
            return
        try:
            card = ProjectCard(
                name=self.general_fields["name"].text(),
                project_code=self.general_fields["project_code"].text(),
                object_type=self.general_fields["object_type"].text(),
                address=self.general_fields["address"].text(),
                total_area_m2=_optional_decimal(self.general_fields["total_area_m2"].text()),
                customer=self.general_fields["customer"].text(),
                responsible_designer=self.general_fields["responsible_designer"].text(),
                note=self.general_note.toPlainText(),
            )
            self.runtime.objects.update_project(self._detail.id, card)
            self._detail = self.runtime.objects.get_project(self._detail.id)
            self._load_detail()
            self.refresh_registry()
        except ObjectValidationError as exc:
            QMessageBox.warning(self, "Данные не сохранены", str(exc))

    def _add_building(self) -> None:
        if self._detail is None:
            return
        name, accepted = QInputDialog.getText(self, "Здание", "Название здания")
        if not accepted:
            return
        try:
            self.runtime.objects.add_building(self._detail.id, name)
            self._detail = self.runtime.objects.get_project(self._detail.id)
            self._load_detail()
        except ObjectValidationError as exc:
            QMessageBox.warning(self, "Здание не сохранено", str(exc))

    def _add_room(self) -> None:
        if self._detail is None or not self._detail.buildings:
            QMessageBox.information(self, "Помещения", "Сначала добавьте здание")
            return
        dialog = RoomDialog(self._detail.buildings, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.runtime.objects.add_room(
                project_id=self._detail.id,
                building_id=dialog.building.currentData(),
                name=dialog.name.text(),
                base_mark_mm=_optional_decimal(dialog.base_mark.text()),
                height_m=_optional_decimal(dialog.height.text()),
                marking_color=dialog.color.color(),
            )
            self._detail = self.runtime.objects.get_project(self._detail.id)
            self._load_detail()
        except ObjectValidationError as exc:
            QMessageBox.warning(self, "Помещение не сохранено", str(exc))

    def _delete_room(self) -> None:
        if self._detail is None or self.rooms_table.currentRow() < 0:
            return
        room_id = self.rooms_table.item(self.rooms_table.currentRow(), 0).data(
            Qt.ItemDataRole.UserRole
        )
        self.runtime.objects.delete_room(self._detail.id, room_id)
        self._detail = self.runtime.objects.get_project(self._detail.id)
        self._load_detail()

    def _edit_room(self, row: int, _column: int) -> None:
        if self._detail is None:
            return
        room_id = self.rooms_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        room = next(item for item in self._detail.rooms if item.id == room_id)
        dialog = RoomDialog(self._detail.buildings, self)
        dialog.load_room(room)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.runtime.objects.update_room(
                project_id=self._detail.id,
                room_id=room.id,
                building_id=dialog.building.currentData(),
                name=dialog.name.text(),
                base_mark_mm=_optional_decimal(dialog.base_mark.text()),
                height_m=_optional_decimal(dialog.height.text()),
                marking_color=dialog.color.color(),
            )
            self._detail = self.runtime.objects.get_project(self._detail.id)
            self._load_detail()
            if self.lines_workspace is not None:
                self.lines_workspace.refresh()
        except ObjectValidationError as exc:
            QMessageBox.warning(self, "Помещение не сохранено", str(exc))

    def _save_settings(self) -> None:
        if self._detail is None:
            return
        try:
            settings = ProjectSettings(
                project_folder=self.setting_fields["project_folder"].text(),
                output_folder=self.setting_fields["output_folder"].text(),
                versions_folder=self.setting_fields["versions_folder"].text(),
                initial_page_number=self.initial_page.value() or None,
                cable_reserve_at_board_m=_optional_decimal(
                    self.setting_fields["cable_reserve_at_board_m"].text()
                ),
            )
            self.runtime.objects.save_settings(self._detail.id, settings)
            self._detail = self.runtime.objects.get_project(self._detail.id)
        except ObjectValidationError as exc:
            QMessageBox.warning(self, "Настройки не сохранены", str(exc))

    def _toggle_time(self) -> None:
        self.runtime.toggle_time()
        self.refresh_time()

    def _sync_dwg(self) -> None:
        if self._sync_in_progress:
            self._sync_operation.cancel()
            return
        project_id = self.runtime.current_project_id
        service = self.runtime.dwg_sync
        manager = self.runtime.background_operations
        if project_id is None or service is None or manager is None:
            return
        self._sync_operation = BackgroundOperationController(manager, self)
        self._sync_operation.completed.connect(self._sync_identity_completed)
        self._sync_operation.failed.connect(self._sync_scan_failed)
        self._sync_operation.cancelled.connect(self._sync_scan_cancelled)
        self._sync_in_progress = True
        self.sync_button.setText("Отменить определение DWG")

        def worker(_snapshot, token, progress):
            token.checkpoint()
            progress(25)
            document = service.inspect_active_document()
            token.checkpoint()
            progress(100)
            return document

        self._sync_operation.start(
            OperationSnapshot.create(project_id, 0, {"operation": "DWG_IDENTIFY"}),
            worker,
        )

    def _sync_identity_completed(self, result) -> None:
        self._finish_sync_scan()
        document = result.value
        self._start_dwg_scan(document.document_identity)

    def _start_dwg_scan(self, document_identity: str) -> None:
        project_id = self.runtime.current_project_id
        service = self.runtime.dwg_sync
        manager = self.runtime.background_operations
        if project_id is None or service is None or manager is None:
            return
        self._sync_operation = BackgroundOperationController(manager, self)
        self._sync_operation.completed.connect(self._sync_scan_completed)
        self._sync_operation.failed.connect(self._sync_scan_failed)
        self._sync_operation.cancelled.connect(self._sync_scan_cancelled)
        self._sync_in_progress = True
        self.sync_button.setText("Отменить сканирование DWG")
        self._sync_progress_dialog = DwgScanProgressDialog(self)
        self._sync_progress_dialog.cancelRequested.connect(self._sync_operation.cancel)
        self._sync_operation.progress.connect(self._sync_progress_dialog.update_progress)
        self._sync_progress_dialog.show()

        def worker(_snapshot, token, progress):
            token.checkpoint()
            proposal = service.scan_active(
                project_id=project_id,
                expected_identity=document_identity,
                progress=progress,
            )
            token.checkpoint()
            return proposal

        self._sync_operation.start(
            OperationSnapshot.create(
                project_id,
                0,
                {"operation": "DWG_SCAN", "document_identity": document_identity},
            ),
            worker,
        )

    def _finish_sync_scan(self) -> None:
        self._sync_in_progress = False
        self.sync_button.setText("Обновить")
        if self._sync_progress_dialog is not None:
            self._sync_progress_dialog.close()
            self._sync_progress_dialog.deleteLater()
            self._sync_progress_dialog = None

    def _sync_scan_cancelled(self) -> None:
        self._finish_sync_scan()
        QMessageBox.information(self, "Синхронизация DWG", "Сканирование отменено")

    def _sync_scan_failed(self, category: str, message: str) -> None:
        self._finish_sync_scan()
        QMessageBox.warning(self, "Синхронизация DWG не выполнена", f"{category}: {message}")

    def _sync_scan_completed(self, result) -> None:
        self._finish_sync_scan()
        self._review_sync_proposal(result.value)

    def _review_sync_proposal(self, proposal) -> None:
        service = self.runtime.dwg_sync
        existing_buses = (
            frozenset(
                row["designation"]
                for row in self.runtime.buses.list_buses(proposal.project_id)
            )
            if self.runtime.buses is not None
            else frozenset()
        )
        plan = build_dwg_update_plan(
            proposal,
            existing_bus_designations=existing_buses,
        )
        working = proposal
        imported = 0
        written = 0
        dwg_unsaved = False
        runtime_errors: list[str] = []

        if plan.import_paths:
            try:
                service.apply_dwg_to_project(
                    working,
                    selected_paths=plan.import_paths,
                    confirmed=True,
                )
                imported = len(plan.import_paths)
                working = replace(working, project_revision=working.project_revision + 1)
            except Exception as exc:
                logging.getLogger(__name__).exception("Automatic DWG apply failed")
                runtime_errors.append(
                    _localized_sync_error(str(exc))
                    if isinstance(exc, (BridgeError, DwgSyncError))
                    else "Не удалось применить изменения DWG в Project."
                )

        if plan.write_paths:
            try:
                write_result = service.write_project_to_dwg(
                    working,
                    selected_paths=plan.write_paths,
                    confirmed=True,
                )
                written = len(plan.write_paths)
                dwg_unsaved = bool(write_result.no_save_confirmed)
            except Exception as exc:
                logging.getLogger(__name__).exception("Automatic Project to DWG write failed")
                runtime_errors.append(
                    _localized_sync_error(str(exc))
                    if isinstance(exc, (BridgeError, DwgSyncError))
                    else "Не удалось передать изменения Project в DWG."
                )

        needs_resolution = bool(
            plan.conflicts
            or plan.problems
            or plan.blocked_lines
            or plan.missing_bus_roots
            or runtime_errors
        )
        if needs_resolution:
            blocked = tuple(
                f"Линия {number}: связанные изменения не применены автоматически."
                for number in plan.blocked_lines
            )
            dialog = DwgSyncResolutionDialog(
                working,
                plan,
                runtime_errors=(*blocked, *runtime_errors),
                parent=self,
            )
            dialog.exec()

            created_bus_root = False
            if self.runtime.buses is not None:
                for designation in sorted(dialog.requested_bus_roots()):
                    bus_dialog = BusWorkspaceDialog(
                        self.runtime.buses,
                        proposal.project_id,
                        self,
                    )
                    created_bus_root = (
                        bus_dialog.create_rs485_bus(designation) or created_bus_root
                    )

            selected_import = dialog.selected_import_paths()
            if selected_import:
                try:
                    service.apply_dwg_to_project(
                        working,
                        selected_paths=selected_import,
                        confirmed=True,
                    )
                    imported += len(selected_import)
                    working = replace(working, project_revision=working.project_revision + 1)
                except Exception as exc:
                    logging.getLogger(__name__).exception("DWG decision apply failed")
                    QMessageBox.warning(
                        self,
                        "Изменение не применено",
                        _localized_sync_error(str(exc))
                        if isinstance(exc, (BridgeError, DwgSyncError))
                        else "Не удалось применить выбранное решение.",
                    )

            selected_write = dialog.selected_write_paths()
            if selected_write:
                try:
                    write_result = service.write_project_to_dwg(
                        working,
                        selected_paths=selected_write,
                        confirmed=True,
                    )
                    written += len(selected_write)
                    dwg_unsaved = dwg_unsaved or bool(write_result.no_save_confirmed)
                except Exception as exc:
                    logging.getLogger(__name__).exception("DWG conflict write failed")
                    QMessageBox.warning(
                        self,
                        "Изменение не применено",
                        _localized_sync_error(str(exc))
                        if isinstance(exc, (BridgeError, DwgSyncError))
                        else "Не удалось применить выбранное решение.",
                    )

            if dialog.open_checks_requested:
                self._open_validation_center()
            if created_bus_root:
                QTimer.singleShot(0, self._sync_dwg)

        self._detail = self.runtime.objects.get_project(proposal.project_id)
        self._load_detail()
        if self.lines_workspace is not None:
            self.lines_workspace.refresh()
        if self.equipment_workspace is not None:
            self.equipment_workspace.refresh()

        if imported == 0 and written == 0 and not needs_resolution:
            self.sync_status_label.setText("Актуально")
        else:
            parts = []
            if imported:
                parts.append(f"из DWG: {imported}")
            if written:
                parts.append(f"в DWG: {written}")
            if needs_resolution:
                parts.append("требует решения")
            if dwg_unsaved:
                parts.append("DWG не сохранён")
            self.sync_status_label.setText(" · ".join(parts) or "Обновлено")


    def _open_cables(self) -> None:
        project_id = self.runtime.current_project_id
        service = self.runtime.cables
        if project_id is None or service is None:
            return
        self._show_cables(project_id, None)

    def _show_cables(self, project_id: str, selected_line_id: str | None) -> None:
        def open_resource(resource_id: str) -> None:
            self._show_constructor(project_id, selected_resource_id=resource_id)

        CableWorkspaceDialog(
            self.runtime.cables,
            project_id,
            self,
            constructor_service=self.runtime.constructor,
            selected_line_id=selected_line_id,
            open_resource=open_resource,
        ).exec()

    def _open_constructor(self) -> None:
        project_id = self.runtime.current_project_id
        service = self.runtime.constructor
        if project_id is None or service is None:
            return
        self._show_constructor(project_id)

    def _show_constructor(
        self,
        project_id: str,
        *,
        selected_instance_id: str | None = None,
        selected_resource_id: str | None = None,
    ) -> None:
        def open_cable(cable_line_id: str) -> None:
            self._show_cables(project_id, cable_line_id)

        ConstructorWorkspaceDialog(
            self.runtime.constructor,
            project_id,
            self,
            selected_instance_id=selected_instance_id,
            selected_resource_id=selected_resource_id,
            open_cable=open_cable,
        ).exec()

    def _open_distribution(self) -> None:
        project_id = self.runtime.current_project_id
        service = self.runtime.distribution
        if project_id is None or service is None:
            return
        DistributionWorkspaceDialog(service, project_id, self).exec()

    def _open_automation(self) -> None:
        project_id = self.runtime.current_project_id
        service = self.runtime.automation
        if project_id is None or service is None:
            return
        AutomationWorkspaceDialog(service, project_id, self).exec()

    def _open_buses(self) -> None:
        project_id = self.runtime.current_project_id
        service = self.runtime.buses
        if project_id is None or service is None:
            return
        BusWorkspaceDialog(service, project_id, self).exec()

    def _open_panels(self) -> None:
        project_id = self.runtime.current_project_id
        service = self.runtime.panels
        if project_id is None or service is None:
            return
        PanelWorkspaceDialog(service, self.runtime.constructor, project_id, self).exec()

    def _open_specification(self) -> None:
        if self.documents_workspace is None:
            return
        self.documents_workspace.show_specification()
        self._switch_section("Документы")

    def _open_validation_center(self) -> None:
        project_id = self.runtime.current_project_id
        service = self.runtime.integrated_ui
        if project_id is None or service is None:
            return

        ValidationCenterDialog(service, project_id, self, navigate=self._navigate_issue).exec()

    def _run_self_check(self) -> None:
        report = self.runtime.self_check()
        details = "\n".join(
            f"{check.status}: {check.code} — {check.message}" for check in report.checks
        )
        if report.ok:
            QMessageBox.information(self, "Self-check: PASS", details)
        else:
            QMessageBox.warning(self, "Self-check: FAIL", details)

    def _manual_backup(self) -> None:
        try:
            receipt = self.runtime.manual_backup()
            QMessageBox.information(
                self,
                "Backup создан",
                f"{receipt.path}\nSHA-256: {receipt.sha256}",
            )
        except Exception as exc:
            QMessageBox.warning(self, "Backup не создан", type(exc).__name__)

    def refresh_time(self) -> None:
        project_id = self.runtime.current_project_id
        if project_id is None:
            summary = TimeSummary(0, 0, False)
        else:
            summary = self.runtime.work_time.summary(project_id)
        today = f"Сегодня {TimeSummary.format_seconds(summary.today_seconds)}"
        total = f"Всего {TimeSummary.format_seconds(summary.total_seconds)}"
        state = "Выполняется" if summary.is_running else "Остановлен"
        action = "Пауза" if summary.is_running else "Play"
        self.today_label.setText(today)
        self.total_label.setText(total)
        self.time_button.setText(action)
        self.time_tab_today.setText(today)
        self.time_tab_total.setText(total)
        self.time_tab_state.setText(state)
        self.time_tab_button.setText(action)
