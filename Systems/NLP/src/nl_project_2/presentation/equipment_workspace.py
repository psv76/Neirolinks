"""Minimal permanent equipment target surface for line/resource navigation."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from nl_project_2.resource_labels import (
    resource_technical_identity,
    resource_user_label,
)


class EquipmentWorkspace(QWidget):
    lineRequested = Signal(str)
    backRequested = Signal()
    engineeringDetailsRequested = Signal(str, str)
    issueRequested = Signal(str)

    def __init__(
        self,
        constructor_service,
        project_id: str,
        parent=None,
        *,
        status_service=None,
        ui_state=None,
    ) -> None:
        super().__init__(parent)
        self.constructor = constructor_service
        self.project_id = project_id
        self.status_service = status_service
        self.ui_state = ui_state
        self._restoring = ui_state is not None
        self._statuses = {}
        self._instances_by_id: dict[str, dict] = {}
        self._resources_by_id: dict[str, dict] = {}
        self._assignments: list[dict] = []
        self.setObjectName("equipmentWorkspace")

        self.back_button = QPushButton("Назад", self)
        self.back_button.setObjectName("equipmentBackButton")
        self.back_button.clicked.connect(self.backRequested)
        details = QPushButton("Инженерные подробности", self)
        details.setObjectName("equipmentEngineeringDetailsButton")
        details.clicked.connect(self._open_details)
        top = QHBoxLayout()
        top.addWidget(self.back_button)
        top.addWidget(details)
        top.addStretch(1)
        self.field_device_context = QLabel("", self)
        self.field_device_context.setObjectName("equipmentFieldDeviceContext")
        self.field_device_context.setWordWrap(True)
        self.field_device_context.hide()

        self.instances = QTableWidget(0, 5, self)
        self.instances.setObjectName("equipmentInstancesTable")
        self.instances.setHorizontalHeaderLabels(
            [
                "Обозначение",
                "Паспорт / версия",
                "Товар / версия",
                "Поставка",
                "Состояние",
            ]
        )
        self.instances.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.instances.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.instances.itemSelectionChanged.connect(self._instance_changed)
        self.resources = QTableWidget(0, 3, self)
        self.resources.setObjectName("equipmentResourcesTable")
        self.resources.setHorizontalHeaderLabels(
            ["Ресурс", "Занятость", "Связанные линии"]
        )
        self.resources.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.resources.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.resources.itemSelectionChanged.connect(self._resource_changed)
        self.related_lines = QTableWidget(0, 2, self)
        self.related_lines.setObjectName("equipmentRelatedLinesTable")
        self.related_lines.setHorizontalHeaderLabels(["Линия", "Назначенный ресурс"])
        self.related_lines.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.related_lines.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.related_lines.cellDoubleClicked.connect(lambda *_: self._open_line())
        self.status_label = QLabel("Состояние: —", self)
        self.status_label.setObjectName("equipmentStatusLabel")
        self.status_reason = QLabel("", self)
        self.status_reason.setObjectName("equipmentStatusReason")
        self.status_reason.setWordWrap(True)
        self.show_issue = QPushButton("Показать проблему", self)
        self.show_issue.setObjectName("equipmentShowIssueButton")
        self.show_issue.clicked.connect(self._show_issue)
        open_line = QPushButton("Открыть выбранную линию", self)
        open_line.setObjectName("equipmentOpenLineButton")
        open_line.clicked.connect(self._open_line)
        right = QWidget(self)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("Функциональные ресурсы", right))
        right_layout.addWidget(self.status_label)
        right_layout.addWidget(self.status_reason)
        right_layout.addWidget(self.show_issue)
        right_layout.addWidget(self.resources, 2)
        right_layout.addWidget(QLabel("Связанные линии", right))
        right_layout.addWidget(self.related_lines, 1)
        right_layout.addWidget(open_line)
        details_scroll = QScrollArea(self)
        details_scroll.setObjectName("equipmentDetailsScroll")
        details_scroll.setWidgetResizable(True)
        details_scroll.setFrameShape(QFrame.Shape.NoFrame)
        details_scroll.setMinimumSize(0, 0)
        details_scroll.setWidget(right)
        self.splitter = QSplitter(Qt.Orientation.Vertical, self)
        self.splitter.setObjectName("equipmentVerticalSplitter")
        self.splitter.addWidget(self.instances)
        self.splitter.addWidget(details_scroll)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.splitterMoved.connect(lambda *_: self._save_state())
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.field_device_context)
        layout.addWidget(self.splitter, 1)
        self._configure_tables()
        self.refresh()
        self._restore_state()

    def show_field_device(self, field_device_id: str) -> None:
        """Expose a stable permanent field-device context for source navigation."""

        self.instances.clearSelection()
        self.resources.clearSelection()
        self.field_device_context.setText(
            "Контекст полевого устройства\n"
            f"Источник спецификации: {field_device_id}\n"
            "Товарные данные и конфигурация отображаются в спецификации; "
            "физическая идентичность устройства не изменяется."
        )
        self.field_device_context.show()

    def refresh(
        self,
        *,
        selected_instance_id: str | None = None,
        selected_resource_id: str | None = None,
    ) -> None:
        self.field_device_context.hide()
        if self.constructor is None:
            self.instances.setRowCount(0)
            self.resources.setRowCount(0)
            self.related_lines.setRowCount(0)
            return
        if selected_instance_id is None:
            selected_instance_id = self._selected_instance_id()
        instances = self.constructor.list_instances(self.project_id)
        self._instances_by_id = {row["id"]: row for row in instances}
        self._statuses = (
            self.status_service.instance_statuses(self.project_id)
            if self.status_service is not None
            else {}
        )
        resources = self.constructor.list_resources(self.project_id)
        self._resources_by_id = {row["id"]: row for row in resources}
        self._assignments = self.constructor.list_cable_assignments(self.project_id)
        if selected_resource_id in self._resources_by_id:
            selected_instance_id = self._resources_by_id[selected_resource_id][
                "project_instance_id"
            ]
        self.instances.blockSignals(True)
        try:
            self.instances.clearContents()
            self.instances.setRowCount(len(instances))
            selected_row = 0 if instances else -1
            for row_index, row in enumerate(instances):
                passport = f"{row['passport_name']} (v{row['passport_version']})"
                product = (
                    "Не выбран"
                    if row.get("product_key") is None
                    else f"{row['product_name']} (v{row['product_version']})"
                )
                values = (
                    row["designation"],
                    passport,
                    product,
                    row.get("supply_scope") or "—",
                    (
                        self._statuses[row["id"]].status.value
                        if row["id"] in self._statuses
                        else "Требуется действие"
                    ),
                )
                for column, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    item.setData(Qt.ItemDataRole.UserRole, row["id"])
                    if column == 1:
                        item.setToolTip(str(row["passport_key"]))
                    elif column == 2 and row.get("product_key") is not None:
                        item.setToolTip(str(row["product_key"]))
                    self.instances.setItem(row_index, column, item)
                if row["id"] == selected_instance_id:
                    selected_row = row_index
            if selected_row >= 0:
                self.instances.setCurrentCell(selected_row, 0)
                self.instances.selectRow(selected_row)
        finally:
            self.instances.blockSignals(False)
        self._load_resources(selected_resource_id=selected_resource_id)
        self._update_status()

    def _selected_instance_id(self) -> str | None:
        row = self.instances.currentRow()
        item = None if row < 0 else self.instances.item(row, 0)
        return None if item is None else item.data(Qt.ItemDataRole.UserRole)

    def _selected_resource_id(self) -> str | None:
        row = self.resources.currentRow()
        item = None if row < 0 else self.resources.item(row, 0)
        return None if item is None else item.data(Qt.ItemDataRole.UserRole)

    def _instance_changed(self) -> None:
        self._load_resources()
        self._update_status()
        self._save_state()

    def _update_status(self) -> None:
        status = self._statuses.get(self._selected_instance_id())
        self.status_label.setText(
            "Состояние: "
            + (status.status.value if status is not None else "Требуется действие")
        )
        self.status_reason.setText(
            status.result if status is not None else "Проверьте назначения оборудования"
        )
        self.show_issue.setEnabled(status is None or status.status.value != "Готово")

    def _resource_changed(self) -> None:
        self._load_related_lines()

    def _load_resources(self, *, selected_resource_id: str | None = None) -> None:
        instance_id = self._selected_instance_id()
        rows = [
            row
            for row in self._resources_by_id.values()
            if row["project_instance_id"] == instance_id
        ]
        rows.sort(key=lambda row: (resource_user_label(row).casefold(), row["id"]))
        self.resources.blockSignals(True)
        try:
            self.resources.clearContents()
            self.resources.setRowCount(len(rows))
            selected_row = 0 if rows else -1
            for row_index, row in enumerate(rows):
                related = sum(
                    item["output_resource_id"] == row["id"]
                    for item in self._assignments
                )
                values = (
                    resource_user_label(row),
                    "Занят" if row["occupied"] else "Свободен",
                    str(related),
                )
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setData(Qt.ItemDataRole.UserRole, row["id"])
                    item.setToolTip(resource_technical_identity(row))
                    self.resources.setItem(row_index, column, item)
                if row["id"] == selected_resource_id:
                    selected_row = row_index
            if selected_row >= 0:
                self.resources.setCurrentCell(selected_row, 0)
                self.resources.selectRow(selected_row)
        finally:
            self.resources.blockSignals(False)
        self._load_related_lines()

    def _load_related_lines(self) -> None:
        resource_id = self._selected_resource_id()
        rows = [
            row for row in self._assignments if row["output_resource_id"] == resource_id
        ]
        self.related_lines.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = (row["cable_designation"], row["user_label"])
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, row["cable_line_id"])
                self.related_lines.setItem(row_index, column, item)

    def _open_line(self) -> None:
        row = self.related_lines.currentRow()
        item = None if row < 0 else self.related_lines.item(row, 0)
        if item is not None:
            self.lineRequested.emit(item.data(Qt.ItemDataRole.UserRole))

    def _open_details(self) -> None:
        self.engineeringDetailsRequested.emit(
            self._selected_instance_id() or "", self._selected_resource_id() or ""
        )

    def _show_issue(self) -> None:
        instance_id = self._selected_instance_id()
        if instance_id:
            self.issueRequested.emit(instance_id)

    def _configure_tables(self) -> None:
        defaults = (
            (self.instances, (120, 260, 300, 110, 160)),
            (self.resources, (260, 110, 150)),
            (self.related_lines, (140, 260)),
        )
        for table, widths in defaults:
            table.setAlternatingRowColors(True)
            font = table.horizontalHeader().font()
            font.setBold(True)
            table.horizontalHeader().setFont(font)
            for column, width in enumerate(widths):
                table.setColumnWidth(column, width)

    def _project_state(self) -> dict:
        if self.ui_state is None:
            return {}
        state = self.ui_state.load()
        workspace = dict(state.get("equipment_workspace") or {})
        projects = dict(workspace.get("projects") or {})
        return dict(projects.get(self.project_id) or {})

    def _save_state(self) -> None:
        if self.ui_state is None or self._restoring:
            return
        state = self.ui_state.load()
        workspace = dict(state.get("equipment_workspace") or {})
        projects = dict(workspace.get("projects") or {})
        projects[self.project_id] = {
            "selected_instance_id": self._selected_instance_id(),
            "splitter_sizes": self.splitter.sizes(),
            "instance_columns": [
                self.instances.columnWidth(column)
                for column in range(self.instances.columnCount())
            ],
        }
        workspace["projects"] = projects
        self.ui_state.update(equipment_workspace=workspace)

    def _restore_state(self) -> None:
        state = self._project_state()
        try:
            widths = state.get("instance_columns")
            if isinstance(widths, list):
                for column, width in enumerate(widths[: self.instances.columnCount()]):
                    if isinstance(width, int) and width > 20:
                        self.instances.setColumnWidth(column, width)
            sizes = state.get("splitter_sizes")
            if (
                isinstance(sizes, list)
                and len(sizes) == 2
                and all(isinstance(value, int) and value >= 0 for value in sizes)
                and sum(sizes) > 0
            ):
                self.splitter.setSizes(sizes)
            else:
                self.splitter.setSizes([750, 250])
            selected = state.get("selected_instance_id")
            if selected in self._instances_by_id:
                for row in range(self.instances.rowCount()):
                    if (
                        self.instances.item(row, 0).data(Qt.ItemDataRole.UserRole)
                        == selected
                    ):
                        self.instances.selectRow(row)
                        self._instance_changed()
                        break
        finally:
            self._restoring = False
