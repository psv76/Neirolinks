"""Power distribution read/write view over constructor facts."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from nl_project_2.resource_labels import resource_display_name, resource_technical_identity


class DistributionWorkspaceDialog(QDialog):
    def __init__(self, service, project_id: str, parent=None) -> None:
        super().__init__(parent)
        self.service = service
        self.project_id = project_id
        self.setWindowTitle("Распределение")
        self.resize(1200, 760)
        self.instances_table = QTableWidget(0, 5, self)
        self.instances_table.setObjectName("distributionInstancesTable")
        self.instances_table.setHorizontalHeaderLabels(
            ["Обозначение", "Класс", "Паспорт", "Товар", "Роль"]
        )
        self.resources_table = QTableWidget(0, 7, self)
        self.resources_table.setObjectName("distributionResourcesTable")
        self.resources_table.setHorizontalHeaderLabels(
            ["Экземпляр", "Ресурс", "Тип", "Направление", "Группа", "Занят", "Остаток"]
        )
        assess = QPushButton("Проверить выбранный узел / БП / ICL", self)
        assess.setObjectName("assessDistributionButton")
        assess.clicked.connect(self._assess_selected)
        self.assessment_label = QLabel("Выберите экземпляр для проверки", self)
        self.assessment_label.setObjectName("distributionAssessmentTrace")
        self.assessment_label.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(self.instances_table)
        layout.addWidget(self.resources_table)
        layout.addWidget(assess)
        layout.addWidget(self.assessment_label)
        self.refresh()

    def refresh(self) -> None:
        instances = self.service.list_instances(self.project_id)
        self.instances_table.setRowCount(len(instances))
        for index, row in enumerate(instances):
            values = (
                row["designation"],
                row["equipment_class"],
                row["passport_key"],
                row["product_key"],
                row["functional_role"],
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem("" if value is None else str(value))
                item.setData(Qt.ItemDataRole.UserRole, row["id"])
                item.setData(Qt.ItemDataRole.UserRole + 1, row["equipment_class"])
                self.instances_table.setItem(index, column, item)
        resources = self.service.distribution_resources(self.project_id)
        self.resources_table.setRowCount(len(resources))
        for index, row in enumerate(resources):
            values = (
                row["instance_designation"],
                resource_display_name(row),
                row["resource_kind"],
                row["direction"],
                row["group_key"],
                "YES" if row["occupied"] else "NO",
                row["remaining_capacity"],
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem("" if value is None else str(value))
                if column == 1:
                    item.setToolTip(resource_technical_identity(row))
                self.resources_table.setItem(index, column, item)

    def _assess_selected(self) -> None:
        row = self.instances_table.currentRow()
        if row < 0:
            return
        item = self.instances_table.item(row, 0)
        instance_id = item.data(Qt.ItemDataRole.UserRole)
        equipment_class = item.data(Qt.ItemDataRole.UserRole + 1)
        if equipment_class.startswith("AC_DC_POWER_SUPPLY"):
            result = self.service.assess_psu_instance(self.project_id, instance_id)
        elif equipment_class == "DISTRIBUTION_BLOCK":
            result = self.service.assess_cross_module_instance(self.project_id, instance_id)
        elif equipment_class == "INRUSH_CURRENT_LIMITER":
            result = self.service.assess_linked_icl(
                project_id=self.project_id,
                icl_instance_id=instance_id,
            )
        else:
            self.assessment_label.setText(
                "Для выбранного аппарата отдельная assessment policy не требуется; "
                "его ресурсы проверяются relation engine."
            )
            return
        self.assessment_label.setText(
            f"STATUS: {result.status}\n"
            + "\n".join(
                f"{step.get('rule')}: {step.get('result', '')}; {step}" for step in result.trace
            )
            + (f"\nMissing: {', '.join(result.missing_fields)}" if result.missing_fields else "")
        )
