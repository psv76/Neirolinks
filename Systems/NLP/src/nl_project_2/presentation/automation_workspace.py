"""Automation and LED/PWM project workspace."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from nl_project_2.automation import AutomationError


class AutomationWorkspaceDialog(QDialog):
    def __init__(self, service, project_id: str, parent=None) -> None:
        super().__init__(parent)
        self.service = service
        self.project_id = project_id
        self.setWindowTitle("Автоматизация")
        self.resize(1280, 820)

        self.instances_table = QTableWidget(0, 4, self)
        self.instances_table.setObjectName("automationInstancesTable")
        self.instances_table.setHorizontalHeaderLabels(["Обозначение", "Класс", "Паспорт", "Товар"])
        self.resources_table = QTableWidget(0, 7, self)
        self.resources_table.setObjectName("automationResourcesTable")
        self.resources_table.setHorizontalHeaderLabels(
            ["Экземпляр", "Ресурс", "Тип", "Направление", "Группа", "Занят", "Свободно"]
        )
        self.assignments_table = QTableWidget(0, 5, self)
        self.assignments_table.setObjectName("automationAssignmentsTable")
        self.assignments_table.setHorizontalHeaderLabels(
            ["Линия", "Экземпляр", "Ресурс", "№", "Роль"]
        )

        self.line_combo = QComboBox(self)
        self.line_combo.setObjectName("automationCableLineCombo")
        self.product_combo = QComboBox(self)
        self.product_combo.setObjectName("ledTapeProductCombo")
        self.kind_combo = QComboBox(self)
        self.kind_combo.addItems(["MONO", "CCT", "RGB", "RGBW"])
        self.lengths_edit = QLineEdit(self)
        self.lengths_edit.setObjectName("ledSegmentLengthsEdit")
        self.lengths_edit.setPlaceholderText("Длины участков, мм, через запятую")
        self.supply_combo = QComboBox(self)
        for value in ("NEIROLINKS", "CUSTOMER", "ASSEMBLY_WORKSHOP", "BY_CONTRACT"):
            self.supply_combo.addItem(value, value)
        create_profile = QPushButton("Создать LED-профиль", self)
        create_profile.setObjectName("createLedProfileButton")
        create_profile.clicked.connect(self._create_profile)
        profile_form = QFormLayout()
        profile_form.addRow("Кабельная линия", self.line_combo)
        profile_form.addRow("Товар ленты", self.product_combo)
        profile_form.addRow("Тип", self.kind_combo)
        profile_form.addRow("Физические участки", self.lengths_edit)
        profile_form.addRow("Поставка", self.supply_combo)
        profile_form.addRow(create_profile)

        self.profile_combo = QComboBox(self)
        self.profile_combo.setObjectName("ledProfileCombo")
        self.module_combo = QComboBox(self)
        self.module_combo.setObjectName("pwmModuleCombo")
        self.ordinals_edit = QLineEdit(self)
        self.ordinals_edit.setObjectName("channelOrdinalsEdit")
        self.ordinals_edit.setPlaceholderText("Например: 0,1")
        assign = QPushButton("Назначить PWM-каналы", self)
        assign.setObjectName("assignLedChannelsButton")
        assign.clicked.connect(self._assign_channels)
        assign_input = QPushButton("Назначить линию выбранному ресурсу", self)
        assign_input.setObjectName("assignAutomationInputButton")
        assign_input.clicked.connect(self._assign_input)
        unassign = QPushButton("Снять назначения выбранной линии", self)
        unassign.setObjectName("unassignAutomationLineButton")
        unassign.clicked.connect(self._unassign_line)
        assignment_form = QFormLayout()
        assignment_form.addRow("LED-профиль", self.profile_combo)
        assignment_form.addRow("WB-LED", self.module_combo)
        assignment_form.addRow("Номера каналов", self.ordinals_edit)
        assignment_form.addRow(assign)
        assignment_form.addRow(assign_input)
        assignment_form.addRow(unassign)

        forms = QHBoxLayout()
        forms.addLayout(profile_form)
        forms.addLayout(assignment_form)
        self.trace_label = QLabel("Выберите данные и выполните действие", self)
        self.trace_label.setObjectName("automationValidationTrace")
        self.trace_label.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addLayout(forms)
        layout.addWidget(self.instances_table)
        layout.addWidget(self.resources_table)
        layout.addWidget(self.assignments_table)
        layout.addWidget(self.trace_label)
        self.refresh()

    def refresh(self) -> None:
        instances = self.service.list_instances(self.project_id)
        self.instances_table.setRowCount(len(instances))
        for row_index, row in enumerate(instances):
            values = (
                row["designation"],
                row["equipment_class"],
                row["passport_key"],
                row["product_key"],
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem("" if value is None else str(value))
                item.setData(Qt.ItemDataRole.UserRole, row["id"])
                self.instances_table.setItem(row_index, column, item)

        resources = self.service.list_resources(self.project_id)
        self.resources_table.setRowCount(len(resources))
        for row_index, row in enumerate(resources):
            values = (
                row["instance_designation"],
                row["resource_key"],
                row["resource_kind"],
                row["direction"],
                row["group_key"],
                "YES" if row["occupied"] else "NO",
                row["remaining_capacity"],
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem("" if value is None else str(value))
                item.setData(Qt.ItemDataRole.UserRole, row["id"])
                item.setData(Qt.ItemDataRole.UserRole + 1, row["direction"])
                self.resources_table.setItem(row_index, column, item)

        assignments = self.service.list_assignments(self.project_id)
        self.assignments_table.setRowCount(len(assignments))
        for row_index, row in enumerate(assignments):
            values = (
                row["cable_designation"],
                row["instance_designation"],
                row["resource_key"],
                row["ordinal"],
                row["assignment_role"],
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, row["cable_line_id"])
                self.assignments_table.setItem(row_index, column, item)

        self._replace_combo(
            self.line_combo,
            [
                (f"{row['designation']} ({row['system_kind']})", row["id"])
                for row in self.service.list_cable_lines(self.project_id)
            ],
        )
        self._replace_combo(
            self.product_combo,
            [
                (row["name"], row["product_key"])
                for row in self.service.list_led_products(self.project_id)
            ],
        )
        profiles = self.service.list_led_profiles(self.project_id)
        self._replace_combo(
            self.profile_combo,
            [
                (
                    f"{row['cable_designation']} — {row['led_kind']} — {row['product_name']}",
                    row["id"],
                )
                for row in profiles
            ],
        )
        self._replace_combo(
            self.module_combo,
            [
                (row["designation"], row["id"])
                for row in instances
                if row["equipment_class"] == "WB_LED_V1"
            ],
        )

    def _create_profile(self) -> None:
        try:
            lengths = tuple(
                {"design_length_mm": value.strip()}
                for value in self.lengths_edit.text().split(",")
                if value.strip()
            )
            profile_id = self.service.create_led_profile(
                project_id=self.project_id,
                cable_line_id=self.line_combo.currentData(),
                led_kind=self.kind_combo.currentText(),
                tape_product_key=self.product_combo.currentData(),
                supply_scope=self.supply_combo.currentData(),
                segments=lengths,
            )
            result = self.service.calculate_profile(self.project_id, profile_id)
            self.trace_label.setText(
                f"STATUS: {result.packing.status}; cuts="
                f"{[str(item.cut_length_mm) for item in result.cuts]}; "
                f"reels={result.packing.purchased_reels}; "
                f"remainder={result.packing.remainder_mm}"
            )
            self.refresh()
        except (AutomationError, ValueError) as exc:
            self.trace_label.setText(f"ERROR: {exc}")

    def _assign_channels(self) -> None:
        try:
            ordinals = tuple(
                int(value.strip())
                for value in self.ordinals_edit.text().split(",")
                if value.strip()
            )
            result = self.service.assign_led_channels(
                project_id=self.project_id,
                profile_id=self.profile_combo.currentData(),
                module_instance_id=self.module_combo.currentData(),
                channel_ordinals=ordinals,
            )
            self.trace_label.setText(
                f"STATUS: {result.status}\n"
                + "\n".join(f"{item.get('rule')}: {item}" for item in result.trace)
            )
            self.refresh()
        except (AutomationError, ValueError) as exc:
            self.trace_label.setText(f"ERROR: {exc}")

    def _unassign_line(self) -> None:
        row = self.assignments_table.currentRow()
        if row < 0:
            return
        cable_line_id = self.assignments_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        self.service.unassign_line(project_id=self.project_id, cable_line_id=cable_line_id)
        self.trace_label.setText("STATUS: UNASSIGNED")
        self.refresh()

    def _assign_input(self) -> None:
        row = self.resources_table.currentRow()
        if row < 0:
            return
        try:
            item = self.resources_table.item(row, 0)
            resource_id = item.data(Qt.ItemDataRole.UserRole)
            direction = item.data(Qt.ItemDataRole.UserRole + 1)
            if direction in {"IN", "BIDIRECTIONAL"}:
                role = "FIELD_INPUT"
                self.service.assign_input_line(
                    project_id=self.project_id,
                    cable_line_id=self.line_combo.currentData(),
                    input_resource_id=resource_id,
                )
            else:
                role = "CONTROLLED_LOAD"
                self.service.assign_output_line(
                    project_id=self.project_id,
                    cable_line_id=self.line_combo.currentData(),
                    output_resource_id=resource_id,
                )
            self.trace_label.setText(f"STATUS: VERIFIED; {role} assigned")
            self.refresh()
        except AutomationError as exc:
            self.trace_label.setText(f"ERROR: {exc}")

    @staticmethod
    def _replace_combo(combo, items) -> None:
        current = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        for text, data in items:
            combo.addItem(text, data)
        index = combo.findData(current)
        if index >= 0:
            combo.setCurrentIndex(index)
        combo.blockSignals(False)
