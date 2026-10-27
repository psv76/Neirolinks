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
        tabs.addTab(self._build_module_installation_tab(), "Установка модулей")
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

    def _build_module_installation_tab(self) -> QWidget:
        """Physical host/slot/module workflow; the generic relation editor stays available."""
        tab = QWidget(self)
        self.install_host_combo = QComboBox(tab)
        self.install_host_combo.setObjectName("installationControllerCombo")
        self.install_host_combo.currentIndexChanged.connect(self._refresh_installation_slots)
        self.install_slot_combo = QComboBox(tab)
        self.install_slot_combo.setObjectName("installationSlotCombo")
        self.install_slot_combo.currentIndexChanged.connect(self._refresh_installation_modules)
        self.install_module_combo = QComboBox(tab)
        self.install_module_combo.setObjectName("installationModuleCombo")
        self.install_module_combo.currentIndexChanged.connect(self._preview_installation)
        self.install_slot_table = QTableWidget(0, 3, tab)
        self.install_slot_table.setObjectName("installationSlotsTable")
        self.install_slot_table.setHorizontalHeaderLabels(
            ["Слот контроллера", "Состояние", "Установленный модуль"]
        )
        self.install_slot_table.itemSelectionChanged.connect(self._select_installation_table_slot)
        self.install_status = QLabel(tab)
        self.install_status.setObjectName("installationCompatibilityStatus")
        self.install_status.setWordWrap(True)
        self.install_button = QPushButton("Установить модуль", tab)
        self.install_button.setObjectName("installModuleButton")
        self.install_button.clicked.connect(self._install_module)
        self.uninstall_button = QPushButton("Снять модуль", tab)
        self.uninstall_button.setObjectName("uninstallModuleButton")
        self.uninstall_button.clicked.connect(self._uninstall_module)
        form = QFormLayout()
        form.addRow("Контроллер", self.install_host_combo)
        form.addRow("Физический слот", self.install_slot_combo)
        form.addRow("Модуль", self.install_module_combo)
        actions = QHBoxLayout()
        actions.addWidget(self.install_button)
        actions.addWidget(self.uninstall_button)
        actions.addStretch(1)
        layout = QVBoxLayout(tab)
        description = QLabel(
            "Выберите контроллер, свободный слот и уже созданный модуль. "
            "Модуль создаётся на вкладке «Экземпляры и ресурсы». "
            "MOD1–MOD4 и отдельный слот MODEM не взаимозаменяемы.",
            tab,
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        layout.addLayout(form)
        layout.addWidget(self.install_status)
        layout.addLayout(actions)
        layout.addWidget(QLabel("Слоты выбранного контроллера", tab))
        layout.addWidget(self.install_slot_table)
        return tab

    @staticmethod
    def _slot_display(row: dict) -> str:
        if row["resource_kind"] == "INTERNAL_MODEM_SLOT":
            return "MODEM"
        return f"MOD{int(row['ordinal']) + 1}"

    def refresh_installation(self) -> None:
        """Refresh display from persisted instances/resources/relations, never from guesses."""
        self._install_resources = self.service.list_resources(self.project_id)
        self._install_instances = {
            row["id"]: row for row in self.service.list_instances(self.project_id)
        }
        self._install_relations = {
            row["source_resource_id"]: row
            for row in self.service.list_relations(self.project_id)
            if row["relation_kind"] in {"MODULE_INSTALLATION", "MODEM_INSTALLATION"}
        }
        selected_host = self.install_host_combo.currentData()
        self.install_host_combo.blockSignals(True)
        self.install_host_combo.clear()
        hosts = {
            row["project_instance_id"]
            for row in self._install_resources
            if row["resource_kind"] in {"INTERNAL_EXPANSION_SLOT", "INTERNAL_MODEM_SLOT"}
        }
        for host_id in sorted(
            hosts,
            key=lambda ident: self._install_instances[ident]["designation"],
        ):
            name = self._install_instances[host_id]["designation"]
            self.install_host_combo.addItem(name, host_id)
        index = self.install_host_combo.findData(selected_host)
        self.install_host_combo.setCurrentIndex(index if index >= 0 else 0)
        self.install_host_combo.blockSignals(False)
        self._refresh_installation_slots()

    def _refresh_installation_slots(self) -> None:
        host_id = self.install_host_combo.currentData()
        selected_slot = self.install_slot_combo.currentData()
        self.install_slot_combo.blockSignals(True)
        self.install_slot_combo.clear()
        self._install_slots = sorted(
            (
                row for row in getattr(self, "_install_resources", ())
                if row["project_instance_id"] == host_id
                and row["resource_kind"] in {"INTERNAL_EXPANSION_SLOT", "INTERNAL_MODEM_SLOT"}
            ),
            key=lambda row: (row["resource_kind"] == "INTERNAL_MODEM_SLOT", row["ordinal"]),
        )
        targets = {
            row["id"]: row for row in getattr(self, "_install_resources", ())
        }
        self.install_slot_table.blockSignals(True)
        self.install_slot_table.setRowCount(len(self._install_slots))
        for index, slot in enumerate(self._install_slots):
            installed = self._install_relations.get(slot["id"])
            target = targets.get(installed["target_resource_id"]) if installed else None
            module = (
                self._install_instances.get(target["project_instance_id"]) if target else None
            )
            label = self._slot_display(slot)
            module_name = module["designation"] if module else "—"
            self.install_slot_combo.addItem(
                f"{label} — {module_name if installed else 'свободен'}", slot["id"]
            )
            cells = (label, "Занят" if installed else "Свободен", module_name)
            for column, value in enumerate(cells):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, slot["id"])
                self.install_slot_table.setItem(index, column, item)
        index = self.install_slot_combo.findData(selected_slot)
        self.install_slot_combo.setCurrentIndex(index if index >= 0 else 0)
        self.install_slot_combo.blockSignals(False)
        self.install_slot_table.blockSignals(False)
        self._refresh_installation_modules()

    def _select_installation_table_slot(self) -> None:
        row = self.install_slot_table.currentRow()
        if row < 0:
            return
        slot_id = self.install_slot_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        index = self.install_slot_combo.findData(slot_id)
        if index >= 0:
            self.install_slot_combo.setCurrentIndex(index)

    def _refresh_installation_modules(self) -> None:
        slot_id = self.install_slot_combo.currentData()
        slot = next(
            (row for row in getattr(self, "_install_slots", ()) if row["id"] == slot_id),
            None,
        )
        previous = self.install_module_combo.currentData()
        self._installation_candidates = {}
        self.install_module_combo.blockSignals(True)
        self.install_module_combo.clear()
        if slot and slot_id not in self._install_relations:
            target_kind = (
                "INTERNAL_MODEM_SLOT_ATTACHMENT"
                if slot["resource_kind"] == "INTERNAL_MODEM_SLOT"
                else "INTERNAL_EXPANSION_MODULE_ATTACHMENT"
            )
            relation_kind = (
                "MODEM_INSTALLATION"
                if slot["resource_kind"] == "INTERNAL_MODEM_SLOT"
                else "MODULE_INSTALLATION"
            )
            for resource in self._install_resources:
                if resource["resource_kind"] != target_kind:
                    continue
                preview = self.service.preview_relation(
                    project_id=self.project_id,
                    relation_kind=relation_kind,
                    source_resource_id=slot_id,
                    target_resource_id=resource["id"],
                )
                if not preview.allowed:
                    continue
                instance = self._install_instances[resource["project_instance_id"]]
                self._installation_candidates[resource["id"]] = (relation_kind, preview)
                self.install_module_combo.addItem(
                    f"{instance['designation']} — {instance['passport_name']}", resource["id"]
                )
        index = self.install_module_combo.findData(previous)
        self.install_module_combo.setCurrentIndex(index if index >= 0 else 0)
        self.install_module_combo.blockSignals(False)
        self._preview_installation()

    def _preview_installation(self) -> None:
        slot_id = self.install_slot_combo.currentData()
        host = self.install_host_combo.currentText()
        slot = next(
            (r for r in getattr(self, "_install_slots", ()) if r["id"] == slot_id), None
        )
        installed = self._install_relations.get(slot_id)
        target_id = self.install_module_combo.currentData()
        self.install_button.setEnabled(
            bool(slot and not installed and target_id in self._installation_candidates)
        )
        self.uninstall_button.setEnabled(bool(installed))
        if slot is None:
            self.install_status.setText("В проекте нет контроллеров с доступными слотами.")
        elif installed:
            self.install_status.setText(
                f"{host} / {self._slot_display(slot)}: модуль уже установлен. "
                "Чтобы освободить слот, сначала снимите его; используемые активными шинами "
                "модули не могут быть сняты."
            )
        elif target_id in self._installation_candidates:
            self.install_status.setText(
                f"{host} / {self._slot_display(slot)}: слот свободен, "
                "выбранный модуль совместим."
            )
        else:
            self.install_status.setText(
                f"{host} / {self._slot_display(slot)}: слот свободен, "
                "но совместимых неустановленных модулей пока нет. "
                "Создайте экземпляр на первой вкладке."
            )

    def _install_module(self) -> None:
        slot_id = self.install_slot_combo.currentData()
        target_id = self.install_module_combo.currentData()
        candidate = self._installation_candidates.get(target_id)
        if not candidate or not self.install_button.isEnabled():
            return
        try:
            self.service.create_relation(
                project_id=self.project_id,
                relation_kind=candidate[0],
                source_resource_id=slot_id,
                target_resource_id=target_id,
            )
            self.refresh_all()
        except (ConstructorError, RuntimeError) as exc:
            QMessageBox.warning(self, "Установка не выполнена", str(exc))

    def _uninstall_module(self) -> None:
        relation = self._install_relations.get(self.install_slot_combo.currentData())
        if relation is None:
            return
        if QMessageBox.question(
            self, "Снятие модуля",
            "Снять модуль с выбранного слота? Активные шины и защищённые связи "
            "должны быть отключены заранее.",
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.service.delete_relation(
                project_id=self.project_id, relation_id=relation["id"]
            )
            self.refresh_all()
        except (ConstructorError, RuntimeError) as exc:
            QMessageBox.warning(self, "Модуль не снят", str(exc))

    def refresh_all(self) -> None:
        self._refresh_passports()
        self.refresh_instances()
        self.refresh_resources()
        self.refresh_relations()
        self.refresh_assignments()
        self.refresh_installation()

    def focus_instance(self, instance_id: str) -> None:
        """Keep navigation anchored to the same ProjectInstance across views."""
        selected_designation = None
        for row in range(self.instances_table.rowCount()):
            if self.instances_table.item(row, 0).data(Qt.ItemDataRole.UserRole) == instance_id:
                self.instances_table.selectRow(row)
                selected_designation = self.instances_table.item(row, 0).text()
                break
        if hasattr(self, "install_host_combo"):
            index = self.install_host_combo.findData(instance_id)
            if index >= 0:
                self.install_host_combo.setCurrentIndex(index)
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
                ("Общее включение Vout-1 и Vout-2"
                 if row["group_key"] == "VOUT_SHARED_SWITCH"
                 else row["group_key"]),
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
            self.refresh_installation()
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
            self.refresh_installation()
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
        "MODULE_INSTALLATION": "Установка модуля в MOD-слот",
        "MODEM_INSTALLATION": "Установка 4G-модема в слот MODEM",
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
