"""Basic user workflow for instances, resources and functional relations."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from nl_project_2.constructor import BlockingViolation, ConstructorError
from nl_project_2.resource_labels import (
    resource_display_name,
    resource_technical_identity,
    resource_user_label,
)


class ConstructorWorkspaceDialog(QDialog):
    def __init__(
        self,
        service,
        project_id: str,
        parent=None,
        selected_instance_id: str | None = None,
        *,
        selected_resource_id: str | None = None,
        open_cable=None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.project_id = project_id
        self._target_previews = {}
        self.open_cable = open_cable
        self.setWindowTitle("Инженерные подробности — проектный конструктор")
        self.resize(1300, 800)
        self.context_label = QLabel(
            "Проектный expert-инструмент: таблицы ниже показывают весь проект. "
            "Форма «Новый экземпляр» не редактирует выбранную строку.",
            self,
        )
        self.context_label.setObjectName("constructorProjectScopeNotice")
        self.context_label.setWordWrap(True)
        tabs = QTabWidget(self)
        tabs.addTab(self._build_instances_tab(), "Экземпляры и ресурсы")
        tabs.addTab(self._build_relations_tab(), "Связи")
        layout = QVBoxLayout(self)
        layout.addWidget(self.context_label)
        layout.addWidget(tabs)
        self.refresh_all()
        if selected_instance_id is not None:
            self.focus_instance(selected_instance_id)
        if selected_resource_id is not None:
            self.focus_resource(selected_resource_id)

    def _build_instances_tab(self) -> QWidget:
        tab = QWidget(self)
        self.instances_table = QTableWidget(0, 4, tab)
        self.instances_table.setObjectName("constructorInstancesTable")
        self.instances_table.setHorizontalHeaderLabels(
            ["Обозначение", "Паспорт", "Товар", "Поставка"]
        )
        self.resources_table = QTableWidget(0, 9, tab)
        self.resources_table.setObjectName("constructorResourcesTable")
        self.resources_table.setHorizontalHeaderLabels(
            [
                "Экземпляр",
                "Функциональная точка",
                "Инженерный тип",
                "Направление",
                "Группа",
                "Обязательный",
                "Назначений",
                "Занят",
                "Остаток",
            ]
        )
        self.designation_edit = QLineEdit(tab)
        self.passport_combo = QComboBox(tab)
        self.passport_combo.currentIndexChanged.connect(self._refresh_products)
        self.product_combo = QComboBox(tab)
        create = QPushButton("Создать экземпляр", tab)
        create.setObjectName("createConstructorInstanceButton")
        create.clicked.connect(self._create_instance)
        remove = QPushButton("Удалить выбранный экземпляр", tab)
        remove.clicked.connect(self._delete_instance)
        form = QFormLayout()
        form.addRow("Обозначение", self.designation_edit)
        form.addRow("Паспорт", self.passport_combo)
        form.addRow("Товар", self.product_combo)
        actions = QHBoxLayout()
        actions.addWidget(create)
        actions.addWidget(remove)
        actions.addStretch(1)
        layout = QVBoxLayout(tab)
        layout.addWidget(self.instances_table)
        layout.addWidget(QLabel("Новый экземпляр (отдельное действие)", tab))
        layout.addLayout(form)
        layout.addLayout(actions)
        layout.addWidget(QLabel("Полный набор ресурсов", tab))
        layout.addWidget(self.resources_table)
        return tab

    def _build_relations_tab(self) -> QWidget:
        tab = QWidget(self)
        self.source_combo = QComboBox(tab)
        self.source_combo.setObjectName("relationSourceCombo")
        self.source_combo.currentIndexChanged.connect(self.refresh_targets)
        self.relation_kind_combo = QComboBox(tab)
        for relation_kind in self.service.relation_kinds:
            self.relation_kind_combo.addItem(_relation_label(relation_kind), relation_kind)
        self.relation_kind_combo.currentIndexChanged.connect(self.refresh_targets)
        selector = QFormLayout()
        selector.addRow("Исходный ресурс", self.source_combo)
        selector.addRow("Тип связи", self.relation_kind_combo)

        self.targets_table = QTableWidget(0, 4, tab)
        self.targets_table.setObjectName("compatibleTargetsTable")
        self.targets_table.setHorizontalHeaderLabels(
            ["Целевой ресурс", "Тип", "Доступность", "Причина"]
        )
        self.targets_table.itemSelectionChanged.connect(self._show_preview)
        self.preview_label = QLabel("Выберите исходный и целевой ресурс", tab)
        self.preview_label.setObjectName("relationPreviewTrace")
        self.preview_label.setWordWrap(True)
        create = QPushButton("Создать связь", tab)
        create.setObjectName("commitRelationButton")
        create.clicked.connect(self._create_relation)

        self.relations_table = QTableWidget(0, 4, tab)
        self.relations_table.setObjectName("functionalRelationsTable")
        self.relations_table.setHorizontalHeaderLabels(
            ["Тип", "Исходный ресурс", "Целевой ресурс", "Параметры"]
        )
        remove = QPushButton("Удалить выбранную связь", tab)
        remove.clicked.connect(self._delete_relation)

        self.assignments_table = QTableWidget(0, 3, tab)
        self.assignments_table.setObjectName("cableResourceAssignmentsTable")
        self.assignments_table.setHorizontalHeaderLabels(
            ["Кабельная линия", "Экземпляр / ресурс", "Роль"]
        )
        self.assignments_table.cellDoubleClicked.connect(lambda *_: self._open_selected_cable())
        self.assignments_table.itemSelectionChanged.connect(self.refresh_chain_trace)
        self.chain_trace_table = QTableWidget(0, 6, tab)
        self.chain_trace_table.setObjectName("functionalChainTraceTable")
        self.chain_trace_table.setHorizontalHeaderLabels(
            ["Шаг", "Переход", "Откуда", "Куда", "Статус", "Инженерный смысл"]
        )
        self.chain_trace_status = QLabel(
            "Выберите назначение кабельной линии для проверки полной трассы", tab
        )
        self.chain_trace_status.setObjectName("functionalChainTraceStatus")
        self.chain_trace_status.setWordWrap(True)

        layout = QVBoxLayout(tab)
        layout.addLayout(selector)
        layout.addWidget(self.targets_table)
        layout.addWidget(self.preview_label)
        layout.addWidget(create)
        layout.addWidget(QLabel("Сохранённые внутренние связи", tab))
        layout.addWidget(self.relations_table)
        layout.addWidget(remove)
        layout.addWidget(QLabel("Отдельные назначения кабельных линий", tab))
        layout.addWidget(self.assignments_table)
        layout.addWidget(QLabel("Полная функциональная трасса выбранной линии", tab))
        layout.addWidget(self.chain_trace_status)
        layout.addWidget(self.chain_trace_table)
        return tab

    def refresh_all(self) -> None:
        self._refresh_passports()
        self.refresh_instances()
        self.refresh_resources()
        self.refresh_relations()
        self.refresh_assignments()

    def focus_instance(self, instance_id: str) -> None:
        """Keep navigation anchored to the same ProjectInstance across views."""
        selected_designation = None
        for row in range(self.instances_table.rowCount()):
            if self.instances_table.item(row, 0).data(Qt.ItemDataRole.UserRole) == instance_id:
                self.instances_table.selectRow(row)
                selected_designation = self.instances_table.item(row, 0).text()
                break
        self.context_label.setText(
            "Проектный expert-инструмент: таблицы показывают весь проект. "
            f"Контекст перехода — {selected_designation or instance_id}. "
            "Форма «Новый экземпляр» не редактирует выбранную строку."
        )
        resources = {row["id"]: row for row in self.service.list_resources(self.project_id)}
        for row in range(self.resources_table.rowCount()):
            resource_id = self.resources_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            resource = resources.get(resource_id)
            if resource and resource["project_instance_id"] == instance_id:
                self.resources_table.selectRow(row)
                break

    def focus_resource(self, resource_id: str) -> None:
        resources = {row["id"]: row for row in self.service.list_resources(self.project_id)}
        resource = resources.get(resource_id)
        if resource is not None:
            self.focus_instance(resource["project_instance_id"])
        for row in range(self.resources_table.rowCount()):
            if self.resources_table.item(row, 0).data(Qt.ItemDataRole.UserRole) == resource_id:
                self.resources_table.selectRow(row)
                self.resources_table.scrollToItem(self.resources_table.item(row, 0))
                return

    def _refresh_passports(self) -> None:
        selected = self.passport_combo.currentData()
        self.passport_combo.blockSignals(True)
        self.passport_combo.clear()
        for row in self.service.list_available_passports(self.project_id):
            self.passport_combo.addItem(f"{row['name']} (v{row['version']})", row["passport_key"])
        index = self.passport_combo.findData(selected)
        self.passport_combo.setCurrentIndex(max(index, 0))
        self.passport_combo.blockSignals(False)
        self._refresh_products()

    def _refresh_products(self) -> None:
        passport_key = self.passport_combo.currentData()
        self.product_combo.clear()
        if not passport_key:
            return
        for row in self.service.list_compatible_products(self.project_id, passport_key):
            self.product_combo.addItem(f"{row['manufacturer']} — {row['name']}", row["product_key"])

    def refresh_instances(self) -> None:
        rows = self.service.list_instances(self.project_id)
        self.instances_table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            values = (
                row["designation"],
                f"{row['passport_name']} (v{row['passport_version']})",
                (
                    "Не выбран"
                    if row.get("product_key") is None
                    else f"{row['product_name']} (v{row['product_version']})"
                ),
                row["supply_scope"],
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem("" if value is None else str(value))
                item.setData(Qt.ItemDataRole.UserRole, row["id"])
                self.instances_table.setItem(index, column, item)

    def refresh_resources(self) -> None:
        rows = self.service.list_resources(self.project_id)
        self.resources_table.setRowCount(len(rows))
        self.source_combo.blockSignals(True)
        selected_source = self.source_combo.currentData()
        self.source_combo.clear()
        for index, row in enumerate(rows):
            resource_name = resource_display_name(row)
            display = resource_user_label(row)
            self.source_combo.addItem(display, row["id"])
            self.source_combo.setItemData(
                self.source_combo.count() - 1,
                resource_technical_identity(row),
                Qt.ItemDataRole.ToolTipRole,
            )
            values = (
                row["instance_designation"],
                resource_name,
                row["resource_kind"],
                row["direction"],
                row["group_key"],
                "YES" if row["required"] else "NO",
                row["assignment_count"],
                "YES" if row["occupied"] else "NO",
                row["remaining_capacity"],
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem("" if value is None else str(value))
                item.setData(Qt.ItemDataRole.UserRole, row["id"])
                if column == 1:
                    item.setToolTip(resource_technical_identity(row))
                self.resources_table.setItem(index, column, item)
        index = self.source_combo.findData(selected_source)
        self.source_combo.setCurrentIndex(max(index, 0))
        self.source_combo.blockSignals(False)
        self.refresh_targets()

    def refresh_targets(self) -> None:
        source_id = self.source_combo.currentData()
        relation_kind = self.relation_kind_combo.currentData()
        self._target_previews = {}
        self.targets_table.setRowCount(0)
        if source_id is None or relation_kind is None:
            return
        rows = self.service.compatible_targets(
            project_id=self.project_id,
            relation_kind=relation_kind,
            source_resource_id=source_id,
        )
        self.targets_table.setRowCount(len(rows))
        for index, (row, preview) in enumerate(rows):
            self._target_previews[row["id"]] = preview
            errors = [
                result.message
                for result in preview.results
                if result.blocking and result.outcome == "ERROR"
            ]
            values = (
                resource_user_label(row),
                row["resource_kind"],
                "Доступно" if preview.allowed else "Недоступно",
                "; ".join(errors) if errors else "Совместимо; см. trace",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, row["id"])
                if column == 0:
                    item.setToolTip(resource_technical_identity(row))
                if column == 2 and not preview.allowed:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                self.targets_table.setItem(index, column, item)

    def refresh_relations(self) -> None:
        resources = {row["id"]: row for row in self.service.list_resources(self.project_id)}
        rows = self.service.list_relations(self.project_id)
        self.relations_table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            source = resources.get(row["source_resource_id"], {})
            target = resources.get(row["target_resource_id"], {})
            values = (
                row["relation_kind"],
                _resource_label(source),
                _resource_label(target),
                row["parameters_json"],
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, row["id"])
                if column in {1, 2}:
                    endpoint = source if column == 1 else target
                    item.setToolTip(resource_technical_identity(endpoint))
                self.relations_table.setItem(index, column, item)

    def refresh_assignments(self) -> None:
        rows = self.service.list_cable_assignments(self.project_id)
        self.assignments_table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            values = (
                row["cable_designation"],
                resource_user_label(row),
                row["assignment_role"],
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, row["id"])
                item.setData(Qt.ItemDataRole.UserRole + 1, row["cable_line_id"])
                if column == 1:
                    item.setToolTip(resource_technical_identity(row))
                self.assignments_table.setItem(index, column, item)
        self.refresh_chain_trace()

    def refresh_chain_trace(self) -> None:
        self.chain_trace_table.setRowCount(0)
        row = self.assignments_table.currentRow()
        if row < 0:
            self.chain_trace_status.setText(
                "Выберите назначение кабельной линии для проверки полной трассы"
            )
            return
        assignment_id = self.assignments_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        try:
            trace = self.service.trace_cable_assignment(
                project_id=self.project_id, assignment_id=assignment_id
            )
        except ConstructorError as exc:
            self.chain_trace_status.setText(str(exc))
            return
        self.chain_trace_status.setText(f"{trace.status}: {trace.message}")
        self.chain_trace_table.setRowCount(len(trace.steps))
        for index, step in enumerate(trace.steps):
            values = (
                index + 1,
                _edge_label(step.edge_kind, step.behavior),
                step.source_label,
                step.target_label,
                step.status,
                step.message,
            )
            for column, value in enumerate(values):
                self.chain_trace_table.setItem(index, column, QTableWidgetItem(str(value)))

    def _open_selected_cable(self) -> None:
        row = self.assignments_table.currentRow()
        if row < 0 or self.open_cable is None:
            return
        self.open_cable(self.assignments_table.item(row, 0).data(Qt.ItemDataRole.UserRole + 1))

    def _show_preview(self) -> None:
        row = self.targets_table.currentRow()
        if row < 0:
            return
        target_id = self.targets_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        preview = self._target_previews[target_id]
        visible = [result for result in preview.results if result.outcome in {"ERROR", "WARNING"}]
        if not visible:
            incomplete_count = sum(result.outcome == "INCOMPLETE" for result in preview.results)
            self.preview_label.setText(
                "Связь допустима: обязательные проверки пройдены"
                + (
                    f"; для {incomplete_count} дополнительных проверок нужны данные"
                    if incomplete_count
                    else ""
                )
            )
        else:
            self.preview_label.setText(
                "\n".join(f"{result.outcome}: {result.message}" for result in visible)
            )
        self.preview_label.setToolTip(
            "\n".join(
                f"{result.rule_id} v{result.rule_version}: {result.outcome}; "
                f"actual={result.actual}; required={result.required}"
                for result in preview.results
            )
        )

    def _create_instance(self) -> None:
        try:
            self.service.create_instance(
                project_id=self.project_id,
                designation=self.designation_edit.text().strip(),
                passport_key=self.passport_combo.currentData(),
                product_key=self.product_combo.currentData(),
                supply_scope="NEIROLINKS",
            )
            self.designation_edit.clear()
            self.refresh_all()
        except (BlockingViolation, ConstructorError, RuntimeError) as exc:
            QMessageBox.warning(self, "Экземпляр не создан", str(exc))

    def _delete_instance(self) -> None:
        row = self.instances_table.currentRow()
        if row < 0:
            return
        if (
            QMessageBox.question(
                self,
                "Удаление экземпляра",
                "Удалить экземпляр вместе со всеми его связями и назначениями?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        instance_id = self.instances_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        try:
            self.service.delete_instance(
                project_id=self.project_id,
                instance_id=instance_id,
                confirmed=True,
            )
            self.refresh_all()
        except ConstructorError as exc:
            QMessageBox.warning(self, "Экземпляр не удалён", str(exc))

    def _create_relation(self) -> None:
        row = self.targets_table.currentRow()
        if row < 0:
            return
        target_id = self.targets_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        preview = self._target_previews[target_id]
        if not preview.allowed:
            QMessageBox.warning(self, "Связь недоступна", self.preview_label.text())
            return
        try:
            self.service.create_relation(
                project_id=self.project_id,
                relation_kind=self.relation_kind_combo.currentData(),
                source_resource_id=self.source_combo.currentData(),
                target_resource_id=target_id,
            )
            self.refresh_resources()
            self.refresh_relations()
        except BlockingViolation as exc:
            QMessageBox.warning(self, "Связь не создана", str(exc))

    def _delete_relation(self) -> None:
        row = self.relations_table.currentRow()
        if row < 0:
            return
        relation_id = self.relations_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        try:
            self.service.delete_relation(project_id=self.project_id, relation_id=relation_id)
            self.refresh_resources()
            self.refresh_relations()
        except ConstructorError as exc:
            QMessageBox.warning(self, "Связь не удалена", str(exc))


def _resource_label(row: dict) -> str:
    return resource_user_label(row)


def _relation_label(kind: str) -> str:
    return {
        "POWER_FLOW": "Питание",
        "FEED_RELAY_COMMON": "Питание общей группы реле",
        "CONTROL": "Управление",
        "SIGNAL": "Сигнал",
        "ANALOG_SIGNAL": "Аналоговый сигнал",
        "INTERFACE": "Интерфейс",
        "BUS_LINK": "Логическая связь шины",
    }.get(kind, kind)


def _edge_label(edge_kind: str, behavior: str) -> str:
    if edge_kind == "FUNCTIONAL_RELATION":
        return _relation_label(behavior)
    if edge_kind == "CABLE_LINE_ASSIGNMENT":
        return "Назначение кабельной линии"
    return {
        "PASS_THROUGH": "Внутренний проход",
        "TRANSFORM": "Преобразование питания",
        "BUFFERED_TRANSFORM": "Резервированное питание",
        "DISTRIBUTION": "Соединение внутри шины",
        "CONTROLLED": "Управляемый внутренний путь",
    }.get(behavior, behavior)
