"""Derived physical-bus graph workspace with minimal RS-485 write actions."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from nl_project_2.buses import BusError, QtNativeRenderer, TopologyResult


class _Rs485ResourceDialog(QDialog):
    def __init__(
        self,
        *,
        title: str,
        designation_label: str,
        candidates: list[dict],
        designation: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(480)
        self.designation_edit = QLineEdit(self)
        self.designation_edit.setObjectName("rs485DesignationEdit")
        self.designation_edit.setText(designation)
        self.resource_combo = QComboBox(self)
        self.resource_combo.setObjectName("rs485ResourceCombo")
        for candidate in candidates:
            self.resource_combo.addItem(candidate["label"], candidate["id"])
            self.resource_combo.setItemData(
                self.resource_combo.count() - 1,
                candidate.get("technical_identity", candidate["label"]),
                Qt.ItemDataRole.ToolTipRole,
            )

        form = QFormLayout()
        form.addRow(designation_label, self.designation_edit)
        form.addRow("RS-485 resource", self.resource_combo)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        save_button.setEnabled(bool(candidates))

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self) -> tuple[str, str]:
        return self.designation_edit.text().strip(), str(self.resource_combo.currentData())


class BusWorkspaceDialog(QDialog):
    def __init__(self, service, project_id: str, parent=None) -> None:
        super().__init__(parent)
        self.service = service
        self.project_id = project_id
        self._resource_labels: dict[str, str] = {}
        self._resource_tooltips: dict[str, str] = {}
        self.setWindowTitle("Шины данных")
        self.resize(1100, 820)

        self.create_rs485_button = QPushButton("Создать RS-485", self)
        self.create_rs485_button.setObjectName("createRs485BusButton")
        self.create_rs485_button.clicked.connect(self._create_rs485_bus)
        self.add_endpoint_button = QPushButton("Добавить точку", self)
        self.add_endpoint_button.setObjectName("addRs485EndpointButton")
        self.add_endpoint_button.clicked.connect(self._add_rs485_endpoint)
        self.remove_endpoint_button = QPushButton("Удалить точку", self)
        self.remove_endpoint_button.setObjectName("removeRs485EndpointButton")
        self.remove_endpoint_button.clicked.connect(self._remove_rs485_endpoint)
        self.delete_bus_button = QPushButton("Удалить шину", self)
        self.delete_bus_button.setObjectName("deleteRs485BusButton")
        self.delete_bus_button.clicked.connect(self._delete_rs485_bus)
        actions = QHBoxLayout()
        actions.addWidget(self.create_rs485_button)
        actions.addWidget(self.add_endpoint_button)
        actions.addWidget(self.remove_endpoint_button)
        actions.addWidget(self.delete_bus_button)
        actions.addStretch(1)

        self.buses_table = QTableWidget(0, 4, self)
        self.buses_table.setObjectName("busesTable")
        self.buses_table.setHorizontalHeaderLabels(["Шина", "Тип", "Правило топологии", "Источник"])
        self.buses_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.buses_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.buses_table.itemSelectionChanged.connect(self._render_selected)

        self.endpoints_table = QTableWidget(0, 2, self)
        self.endpoints_table.setObjectName("rs485EndpointsTable")
        self.endpoints_table.setHorizontalHeaderLabels(["Точка", "Устройство / ресурс"])
        self.endpoints_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.endpoints_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.endpoints_table.itemSelectionChanged.connect(self._update_action_state)

        self.graph_view = QGraphicsView(self)
        self.graph_view.setObjectName("busGraphView")
        self.groups_table = QTableWidget(0, 2, self)
        self.groups_table.setObjectName("daliGroupsTable")
        self.groups_table.setHorizontalHeaderLabels(["DALI-группа", "Участники"])
        self.states_table = QTableWidget(0, 3, self)
        self.states_table.setObjectName("busConnectionStatesTable")
        self.states_table.setHorizontalHeaderLabels(["Ресурс", "Связь", "Питание"])
        self.status_label = QLabel("Выберите шину", self)
        self.status_label.setObjectName("busTopologyStatus")
        self.status_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addLayout(actions)
        layout.addWidget(self.buses_table)
        layout.addWidget(QLabel("Точки выбранной шины", self))
        layout.addWidget(self.endpoints_table)
        layout.addWidget(self.graph_view)
        layout.addWidget(self.groups_table)
        layout.addWidget(self.states_table)
        layout.addWidget(self.status_label)
        self.refresh()

    def refresh(self, selected_bus_id: str | None = None, *, select_first: bool = True) -> None:
        bus_resource_labels = self.service.list_bus_resource_labels(self.project_id)
        self._resource_labels = {
            resource_id: item["label"] for resource_id, item in bus_resource_labels.items()
        }
        self._resource_tooltips = {
            resource_id: item["technical_identity"]
            for resource_id, item in bus_resource_labels.items()
        }
        rows = self.service.list_buses(self.project_id)
        self.buses_table.blockSignals(True)
        self.buses_table.setRowCount(len(rows))
        selected_row = None
        for index, row in enumerate(rows):
            values = (
                row["designation"],
                row["bus_kind"],
                row["topology_policy"],
                self._resource_label(row["root_resource_id"]),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, row["id"])
                if column == 3:
                    item.setToolTip(self._resource_tooltip(row["root_resource_id"]))
                self.buses_table.setItem(index, column, item)
            if row["id"] == selected_bus_id:
                selected_row = index
        if selected_row is None and select_first and rows:
            selected_row = 0
        if selected_row is None:
            self.buses_table.clearSelection()
            self.buses_table.blockSignals(False)
            self._clear_details()
            return
        self.buses_table.selectRow(selected_row)
        self.buses_table.blockSignals(False)
        self._render_selected()

    def _render_selected(self) -> None:
        bus_id = self._current_bus_id()
        if bus_id is None:
            self._clear_details()
            return
        stored = self.service.get_bus(self.project_id, bus_id)
        endpoints = stored["endpoints"]
        self.endpoints_table.blockSignals(True)
        self.endpoints_table.setRowCount(len(endpoints))
        for index, endpoint in enumerate(endpoints):
            values = (
                endpoint["address"],
                self._resource_label(endpoint["resource_id"]),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, endpoint["id"])
                if column == 1:
                    item.setToolTip(self._resource_tooltip(endpoint["resource_id"]))
                self.endpoints_table.setItem(index, column, item)
        self.endpoints_table.blockSignals(False)
        self.endpoints_table.clearSelection()

        topology = self.service.topology(
            project_id=self.project_id,
            bus_id=bus_id,
            coordinates={},
        )
        display_topology = TopologyResult(
            topology.status,
            tuple(self._resource_label(node) for node in topology.nodes),
            tuple(
                (self._resource_label(source), self._resource_label(target))
                for source, target in topology.edges
            ),
            topology.total_length_mm,
            topology.errors,
        )
        self.graph_view.setScene(QtNativeRenderer().render(display_topology))
        groups = self.service.list_dali_groups(self.project_id, bus_id)
        self.groups_table.setRowCount(len(groups))
        for index, group in enumerate(groups):
            self.groups_table.setItem(index, 0, QTableWidgetItem(group["group_key"]))
            members = group["member_resource_ids"]
            member_item = QTableWidgetItem(
                ", ".join(self._resource_label(resource_id) for resource_id in members)
            )
            member_item.setToolTip(
                ", ".join(self._resource_tooltip(resource_id) for resource_id in members)
            )
            self.groups_table.setItem(index, 1, member_item)
        states = self.service.connection_states(self.project_id, bus_id)
        field_device_labels = {
            str(endpoint.get("field_device_id")): str(
                endpoint.get("address") or endpoint.get("field_device_id")
            )
            for endpoint in endpoints
            if endpoint.get("endpoint_kind") == "FIELD_DEVICE" and endpoint.get("field_device_id")
        }
        self.states_table.setRowCount(len(states))
        for index, state in enumerate(states):
            resource_id = state.get("resource_id")
            field_device_id = state.get("field_device_id")
            if resource_id:
                owner_label = self._resource_label(resource_id)
                owner_tooltip = self._resource_tooltip(resource_id)
            else:
                owner_label = field_device_labels.get(
                    str(field_device_id), str(field_device_id or "FIELD_DEVICE")
                )
                owner_tooltip = (
                    f"FIELD_DEVICE {field_device_id}" if field_device_id else "FIELD_DEVICE"
                )
            for column, value in enumerate(
                (
                    owner_label,
                    state["communication_state"],
                    state["power_state"],
                )
            ):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setToolTip(owner_tooltip)
                self.states_table.setItem(index, column, item)
        errors = ", ".join(topology.errors) if topology.errors else "нет"
        self.status_label.setText(
            f"STATUS: {topology.status}; длина: {topology.total_length_mm} мм; проверки: {errors}"
        )
        self._update_action_state()

    def _create_rs485_bus(self) -> None:
        self.create_rs485_bus()

    def create_rs485_bus(self, designation: str = "") -> bool:
        previous_bus_id = self._current_bus_id()
        candidates = [
            candidate
            for candidate in self.service.list_rs485_resource_candidates(self.project_id)
            if candidate["source_available"]
        ]
        if not candidates:
            QMessageBox.warning(
                self,
                "Шина не создана",
                "Нет свободного физического интерфейса RS-485.",
            )
            return False
        dialog = _Rs485ResourceDialog(
            title="Создать RS-485",
            designation_label="Обозначение шины",
            candidates=candidates,
            designation=designation,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        selected_designation, resource_id = dialog.values()
        try:
            receipt = self.service.create_rs485_bus(
                project_id=self.project_id,
                designation=selected_designation,
                root_resource_id=resource_id,
                points=(),
            )
        except BusError as exc:
            QMessageBox.warning(self, "Шина не создана", str(exc))
            self.refresh(previous_bus_id)
            return False
        self.refresh(receipt.bus_id)
        return True

    def _add_rs485_endpoint(self) -> None:
        bus_id = self._current_rs485_bus_id()
        if bus_id is None:
            return
        candidates = self.service.list_rs485_resource_candidates(self.project_id)
        if not candidates:
            QMessageBox.warning(
                self,
                "Точка не добавлена",
                "В текущем объекте нет RS-485 resources.",
            )
            return
        dialog = _Rs485ResourceDialog(
            title="Добавить точку",
            designation_label="Обозначение точки",
            candidates=candidates,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        cable_id, resource_id = dialog.values()
        try:
            self.service.add_rs485_endpoint(
                project_id=self.project_id,
                bus_id=bus_id,
                resource_id=resource_id,
                cable_id=cable_id,
            )
        except BusError as exc:
            QMessageBox.warning(self, "Точка не добавлена", str(exc))
        self.refresh(bus_id)

    def _remove_rs485_endpoint(self) -> None:
        bus_id = self._current_rs485_bus_id()
        row = self.endpoints_table.currentRow()
        if bus_id is None or row < 0 or not self.endpoints_table.selectedItems():
            return
        endpoint_id = self.endpoints_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        designation = self.endpoints_table.item(row, 0).text()
        answer = QMessageBox.question(
            self,
            "Удалить точку",
            f"Удалить точку {designation}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.service.remove_rs485_endpoint(
                project_id=self.project_id,
                bus_id=bus_id,
                endpoint_id=endpoint_id,
            )
        except BusError as exc:
            QMessageBox.warning(self, "Точка не удалена", str(exc))
        self.refresh(bus_id)

    def _delete_rs485_bus(self) -> None:
        bus_id = self._current_rs485_bus_id()
        row = self.buses_table.currentRow()
        if bus_id is None or row < 0:
            return
        designation = self.buses_table.item(row, 0).text()
        answer = QMessageBox.question(
            self,
            "Удалить шину",
            f"Удалить RS-485 шину {designation} и все её точки?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.service.delete_rs485_bus(
                project_id=self.project_id,
                bus_id=bus_id,
            )
        except BusError as exc:
            QMessageBox.warning(self, "Шина не удалена", str(exc))
            self.refresh(bus_id)
            return
        self.refresh(select_first=False)

    def _current_bus_id(self) -> str | None:
        row = self.buses_table.currentRow()
        if row < 0 or not self.buses_table.selectedItems():
            return None
        item = self.buses_table.item(row, 0)
        return str(item.data(Qt.ItemDataRole.UserRole)) if item is not None else None

    def _current_rs485_bus_id(self) -> str | None:
        bus_id = self._current_bus_id()
        if bus_id is None:
            return None
        row = self.buses_table.currentRow()
        if self.buses_table.item(row, 1).text() != "RS485":
            return None
        return bus_id

    def _resource_label(self, resource_id: str) -> str:
        return self._resource_labels.get(str(resource_id), str(resource_id))

    def _resource_tooltip(self, resource_id: str) -> str:
        return self._resource_tooltips.get(str(resource_id), str(resource_id))

    def _update_action_state(self) -> None:
        is_rs485 = self._current_rs485_bus_id() is not None
        self.add_endpoint_button.setEnabled(is_rs485)
        self.delete_bus_button.setEnabled(is_rs485)
        self.remove_endpoint_button.setEnabled(
            is_rs485 and bool(self.endpoints_table.selectedItems())
        )

    def _clear_details(self) -> None:
        self.endpoints_table.setRowCount(0)
        self.groups_table.setRowCount(0)
        self.states_table.setRowCount(0)
        self.graph_view.setScene(QGraphicsScene(self.graph_view))
        self.status_label.setText("Выберите шину")
        self._update_action_state()
