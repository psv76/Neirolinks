"""Editable cable-line, conduit and cable-catalog workspace."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from nl_project_2.cables import CableError, RouteMethod
from nl_project_2.resource_labels import (
    resource_display_name,
    resource_technical_identity,
    resource_user_label,
)


class CableWorkspaceDialog(QDialog):
    """Project-scoped editor; all mutations are delegated to CableService."""

    def __init__(
        self,
        service,
        project_id: str,
        parent=None,
        *,
        constructor_service=None,
        selected_line_id: str | None = None,
        open_resource=None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.project_id = project_id
        self.constructor_service = constructor_service
        self.open_resource = open_resource
        self.setWindowTitle("Линии и трубы")
        self.resize(1250, 900)

        tabs = QTabWidget(self)
        tabs.addTab(self._build_lines_tab(), "Линии и трубы")
        tabs.addTab(self._build_routes_tab(), "Кабельные трассы")
        tabs.addTab(self._build_catalog_tab(), "Каталог кабелей / HDMI")
        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        self.refresh_all()
        if selected_line_id is not None:
            self.focus_line(selected_line_id)

    def _build_lines_tab(self) -> QWidget:
        tab = QWidget(self)
        self.system_filter = QComboBox(tab)
        self.system_filter.setObjectName("cableSystemFilter")
        self.system_filter.addItem("Все системы", "ALL")
        self.system_filter.addItem("Только AV", "AV")
        self.system_filter.currentIndexChanged.connect(self.refresh_lines)

        self.lines_table = QTableWidget(0, 11, tab)
        self.lines_table.setObjectName("cableLinesTable")
        self.lines_table.setMinimumHeight(300)
        self.lines_table.setHorizontalHeaderLabels(
            [
                "Линия",
                "Система",
                "Щит",
                "Тип кабеля",
                "Нагрузка",
                "Помещение",
                "Прокладка",
                "Авто, м",
                "Доп., м",
                "Полная ручная, м",
                "Итого, м",
            ]
        )
        self.lines_table.itemSelectionChanged.connect(self._load_selected_line)

        self.board_edit = QLineEdit(tab)
        self.cable_type_edit = QLineEdit(tab)
        self.gofra_type_edit = QLineEdit(tab)
        self.gofra_color_edit = QLineEdit(tab)
        self.gofra_id_edit = QLineEdit(tab)
        self.route_combo = QComboBox(tab)
        for method, title in (
            (RouteMethod.FLOOR, "По полу"),
            (RouteMethod.CEILING, "По потолку"),
            (RouteMethod.TIMBER, "В брусе"),
            (RouteMethod.CABLE_CHANNEL, "В кабель-канале"),
        ):
            self.route_combo.addItem(title, method)
        self.additional_edit = QLineEdit("0", tab)
        self.manual_full_edit = QLineEdit(tab)
        save_line = QPushButton("Сохранить и пересчитать", tab)
        save_line.setObjectName("saveCableLineButton")
        save_line.clicked.connect(self._save_line)
        editor = QFormLayout()
        editor.addRow("BOARD", self.board_edit)
        editor.addRow("CABLE_TYPE", self.cable_type_edit)
        editor.addRow("Способ прокладки", self.route_combo)
        editor.addRow("GOFRA_TYPE", self.gofra_type_edit)
        editor.addRow("GOFRA_COLOR", self.gofra_color_edit)
        editor.addRow("GOFRA_ID", self.gofra_id_edit)
        editor.addRow("Дополнительная длина, м", self.additional_edit)
        editor.addRow("Полная ручная длина, м", self.manual_full_edit)
        editor.addRow(save_line)

        self.assignments_table = QTableWidget(0, 3, tab)
        self.assignments_table.setObjectName("cableAssignmentsForLineTable")
        self.assignments_table.setHorizontalHeaderLabels(["Экземпляр / ресурс", "Роль", "Статус"])
        self.assignments_table.cellDoubleClicked.connect(lambda *_: self._open_selected_resource())
        self.resource_targets = QTableWidget(0, 4, tab)
        self.resource_targets.setObjectName("cableAssignmentTargetsTable")
        self.resource_targets.setHorizontalHeaderLabels(
            ["Экземпляр", "Ресурс", "Доступность", "Причина"]
        )
        assign = QPushButton("Назначить выбранный ресурс", tab)
        assign.setObjectName("assignCableResourceButton")
        assign.clicked.connect(self._assign_resource)
        unassign = QPushButton("Удалить выбранное назначение", tab)
        unassign.setObjectName("deleteCableAssignmentButton")
        unassign.clicked.connect(self._delete_assignment)
        assignment_actions = QHBoxLayout()
        assignment_actions.addWidget(assign)
        assignment_actions.addWidget(unassign)
        assignment_actions.addStretch(1)

        self.conduits_table = QTableWidget(0, 7, tab)
        self.conduits_table.setObjectName("conduitsTable")
        self.conduits_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.conduits_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.conduits_table.setHorizontalHeaderLabels(
            ["GOFRA_ID", "Тип", "Цвет", "Диаметр, мм", "Длина, м", "Источник", "Линий"]
        )
        create = QPushButton("Создать пустую трубу", tab)
        create.clicked.connect(self._create_conduit)
        move = QPushButton("Перенести выбранную линию", tab)
        move.clicked.connect(self._move_line)
        edit_length = QPushButton("Изменить длину трубы", tab)
        edit_length.clicked.connect(self._edit_conduit_length)
        bulk = QPushButton("Массово изменить тип / диаметр", tab)
        bulk.clicked.connect(self._bulk_edit)
        select_product = QPushButton("Выбрать товар трубы", tab)
        select_product.setObjectName("selectConduitProductButton")
        select_product.clicked.connect(self._select_conduit_product)
        conduit_actions = QHBoxLayout()
        for button in (create, move, edit_length, bulk, select_product):
            conduit_actions.addWidget(button)
        conduit_actions.addStretch(1)

        layout = QVBoxLayout(tab)
        layout.addWidget(self.system_filter)
        layout.addWidget(self.lines_table, 6)
        layout.addLayout(editor)
        layout.addWidget(QLabel("Назначения выбранной линии", tab))
        layout.addWidget(self.assignments_table, 1)
        layout.addWidget(QLabel("Ресурсы и причины недоступности", tab))
        layout.addWidget(self.resource_targets, 1)
        layout.addLayout(assignment_actions)
        layout.addWidget(QLabel("Экземпляры труб", tab))
        layout.addWidget(self.conduits_table, 1)
        layout.addLayout(conduit_actions)
        return tab

    def _build_routes_tab(self) -> QWidget:
        tab = QWidget(self)
        self.routes_tree = QTreeWidget(tab)
        self.routes_tree.setObjectName("cableRoutesTree")
        self.routes_tree.setColumnCount(7)
        self.routes_tree.setHeaderLabels(
            [
                "Труба / линия",
                "GOFRA_TYPE / назначение",
                "GOFRA_COLOR",
                "Длина, м",
                "Товар / тип кабеля",
                "Источник",
                "Статус",
            ]
        )
        edit = QPushButton("Изменить выбранную трубу", tab)
        edit.setObjectName("editCableRouteButton")
        edit.clicked.connect(self._edit_route)
        layout = QVBoxLayout(tab)
        layout.addWidget(self.routes_tree)
        layout.addWidget(edit)
        return tab

    def _build_catalog_tab(self) -> QWidget:
        tab = QWidget(self)
        self.catalog_table = QTableWidget(0, 8, tab)
        self.catalog_table.setObjectName("cableCatalogTable")
        self.catalog_table.setHorizontalHeaderLabels(
            [
                "Product key",
                "Версия",
                "Категория",
                "Производитель",
                "Модель",
                "Артикул",
                "Заводская длина, м",
                "Release / статус",
            ]
        )
        self.product_key = QLineEdit(tab)
        self.category = QComboBox(tab)
        for category in ("SPEAKER_CABLE", "HDMI", "OTHER_APPROVED_CABLE"):
            self.category.addItem(category)
        self.manufacturer = QLineEdit(tab)
        self.model = QLineEdit(tab)
        self.article = QLineEdit(tab)
        self.product_cable_type = QLineEdit(tab)
        self.factory_length = QLineEdit(tab)
        self.release_code = QLineEdit(tab)
        form = QFormLayout()
        form.addRow("Product key", self.product_key)
        form.addRow("Категория", self.category)
        form.addRow("Производитель", self.manufacturer)
        form.addRow("Модель", self.model)
        form.addRow("Артикул", self.article)
        form.addRow("CABLE_TYPE", self.product_cable_type)
        form.addRow("Заводская длина HDMI, м", self.factory_length)
        form.addRow("Код нового release", self.release_code)
        start = QPushButton("Начать draft", tab)
        start.clicked.connect(self._start_draft)
        add = QPushButton("Добавить validated product", tab)
        add.clicked.connect(self._add_product)
        publish = QPushButton("Опубликовать draft", tab)
        publish.clicked.connect(self._publish)
        auto_hdmi = QPushButton("Автоподбор HDMI для выбранной линии", tab)
        auto_hdmi.clicked.connect(self._auto_hdmi)
        manual = QPushButton("Выбрать товар вручную для выбранной линии", tab)
        manual.clicked.connect(self._manual_product)
        actions = QHBoxLayout()
        for button in (start, add, publish, auto_hdmi, manual):
            actions.addWidget(button)
        layout = QVBoxLayout(tab)
        layout.addWidget(self.catalog_table)
        layout.addLayout(form)
        layout.addLayout(actions)
        return tab

    def refresh_all(self) -> None:
        self.refresh_lines()
        self.refresh_assignment_context()
        self.refresh_conduits()
        self.refresh_routes()
        self.refresh_catalog()

    def refresh_lines(self) -> None:
        selected_line = self._selected_line_id() if hasattr(self, "lines_table") else None
        selected_filter = self.system_filter.currentData()
        rows = [
            row
            for row in self.service.line_cards(self.project_id)
            if selected_filter == "ALL" or row["system_kind"] == selected_filter
        ]
        self._line_cards_by_id = {row["id"]: row for row in rows}
        self.lines_table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            values = (
                row["designation"],
                row["system_kind"],
                row["board"],
                row["cable_type"],
                row["load_type"],
                row["room_names"],
                row["mount_way"],
                row["automatic_m"],
                row["additional_m"],
                row["manual_full_m"],
                row["effective_m"],
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem("" if value is None else str(value))
                item.setData(Qt.ItemDataRole.UserRole, row["id"])
                self.lines_table.setItem(index, column, item)
            if row["id"] == selected_line:
                self.lines_table.selectRow(index)

    def focus_line(self, cable_line_id: str) -> None:
        for row in range(self.lines_table.rowCount()):
            if self.lines_table.item(row, 0).data(Qt.ItemDataRole.UserRole) == cable_line_id:
                self.lines_table.selectRow(row)
                self.lines_table.scrollToItem(self.lines_table.item(row, 0))
                self.refresh_assignment_context()
                return

    def refresh_assignment_context(self) -> None:
        self.assignments_table.setRowCount(0)
        self.resource_targets.setRowCount(0)
        line_id = self._selected_line_id()
        if line_id is None or self.constructor_service is None:
            return
        assignments = [
            row
            for row in self.constructor_service.list_cable_assignments(self.project_id)
            if row["cable_line_id"] == line_id
        ]
        self.assignments_table.setRowCount(len(assignments))
        for index, row in enumerate(assignments):
            values = (
                resource_user_label(row),
                row["assignment_role"],
                "Назначено",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, row["id"])
                item.setData(Qt.ItemDataRole.UserRole + 1, row["output_resource_id"])
                if column == 0:
                    item.setToolTip(resource_technical_identity(row))
                self.assignments_table.setItem(index, column, item)
        targets = self.constructor_service.cable_assignment_targets(
            project_id=self.project_id, cable_line_id=line_id
        )
        self.resource_targets.setRowCount(len(targets))
        for index, row in enumerate(targets):
            values = (
                row["instance_designation"],
                resource_display_name(row),
                "Доступно" if row["available"] else "Недоступно",
                row["reason"],
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, row["id"])
                item.setData(Qt.ItemDataRole.UserRole + 1, row["available"])
                if column == 1:
                    item.setToolTip(resource_technical_identity(row))
                if not row["available"]:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                self.resource_targets.setItem(index, column, item)

    def refresh_conduits(self) -> None:
        rows = self.service.list_conduits(self.project_id)
        self.conduits_table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            values = (
                row["designation"],
                row["conduit_type"],
                row["color"],
                row["diameter_mm_decimal"],
                row["length_m_decimal"],
                (row["path_json"] or {}).get("origin", ""),
                row["line_count"],
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem("" if value is None else str(value))
                item.setData(Qt.ItemDataRole.UserRole, row["id"])
                self.conduits_table.setItem(index, column, item)

    def refresh_routes(self) -> None:
        self.routes_tree.clear()
        for row in self.service.list_conduit_routes(self.project_id):
            status = "Длина не задана" if row["length_m_decimal"] is None else "Готово"
            parent = QTreeWidgetItem(
                [
                    row["designation"],
                    row["conduit_type"],
                    row["color"] or "",
                    "" if row["length_m_decimal"] is None else str(row["length_m_decimal"]),
                    row["product_display"],
                    (row["path_json"] or {}).get("origin", ""),
                    status,
                ]
            )
            parent.setData(0, Qt.ItemDataRole.UserRole, row["id"])
            parent.setData(0, Qt.ItemDataRole.UserRole + 1, "CONDUIT")
            self.routes_tree.addTopLevelItem(parent)
            for line in row["lines"]:
                child = QTreeWidgetItem(
                    [
                        f"    → {line['designation']}",
                        line["load_name"],
                        "",
                        "",
                        line["cable_type"],
                        "",
                        "",
                    ]
                )
                child.setData(0, Qt.ItemDataRole.UserRole, line["id"])
                child.setData(0, Qt.ItemDataRole.UserRole + 1, "CABLE_LINE")
                parent.addChild(child)
            parent.setExpanded(True)

    def refresh_catalog(self) -> None:
        rows = self.service.list_catalog_products()
        self.catalog_table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            values = (
                row["product_key"],
                row["version"],
                row["category"],
                row["manufacturer"],
                row["model"],
                row["article"],
                row["factory_length_m_decimal"],
                f"{row['release_code']} / {row['release_status']}",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem("" if value is None else str(value))
                item.setData(Qt.ItemDataRole.UserRole, row["id"])
                self.catalog_table.setItem(index, column, item)

    def _selected_line_id(self) -> str | None:
        row = self.lines_table.currentRow()
        return None if row < 0 else self.lines_table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def _selected_conduit_ids(self) -> set[str]:
        return {
            self.conduits_table.item(index.row(), 0).data(Qt.ItemDataRole.UserRole)
            for index in self.conduits_table.selectionModel().selectedRows()
        }

    def _load_selected_line(self) -> None:
        row = self.lines_table.currentRow()
        if row < 0:
            return
        self.board_edit.setText(self.lines_table.item(row, 2).text())
        self.cable_type_edit.setText(self.lines_table.item(row, 3).text())
        route = self.lines_table.item(row, 6).text()
        index = self.route_combo.findText(route) if route else 0
        self.route_combo.setCurrentIndex(max(index, 0))
        self.additional_edit.setText(self.lines_table.item(row, 8).text() or "0")
        self.manual_full_edit.setText(self.lines_table.item(row, 9).text())
        card = self._line_cards_by_id.get(self._selected_line_id(), {})
        self.gofra_type_edit.setText(card.get("gofra_type", ""))
        self.gofra_color_edit.setText(card.get("gofra_color", ""))
        self.gofra_id_edit.setText(card.get("gofra_id", ""))
        self.refresh_assignment_context()

    def _assign_resource(self) -> None:
        line_id = self._selected_line_id()
        row = self.resource_targets.currentRow()
        if line_id is None or row < 0 or self.constructor_service is None:
            return
        item = self.resource_targets.item(row, 0)
        if not item.data(Qt.ItemDataRole.UserRole + 1):
            QMessageBox.warning(
                self, "Назначение недоступно", self.resource_targets.item(row, 3).text()
            )
            return
        try:
            self.constructor_service.assign_cable_line(
                project_id=self.project_id,
                cable_line_id=line_id,
                output_resource_id=item.data(Qt.ItemDataRole.UserRole),
            )
            self.refresh_assignment_context()
        except Exception as exc:
            QMessageBox.warning(self, "Назначение не создано", str(exc))

    def _delete_assignment(self) -> None:
        row = self.assignments_table.currentRow()
        if row < 0 or self.constructor_service is None:
            return
        self.constructor_service.delete_cable_assignment(
            project_id=self.project_id,
            assignment_id=self.assignments_table.item(row, 0).data(Qt.ItemDataRole.UserRole),
        )
        self.refresh_assignment_context()

    def _open_selected_resource(self) -> None:
        row = self.assignments_table.currentRow()
        if row < 0 or self.open_resource is None:
            return
        self.open_resource(self.assignments_table.item(row, 0).data(Qt.ItemDataRole.UserRole + 1))

    def _save_line(self) -> None:
        line_id = self._selected_line_id()
        if line_id is None:
            return
        try:
            self.service.update_line_fields(
                project_id=self.project_id,
                cable_line_id=line_id,
                cable_type=self.cable_type_edit.text(),
                board_designation=self.board_edit.text(),
                mount_way=self.route_combo.currentText(),
                gofra_type=self.gofra_type_edit.text(),
                gofra_color=self.gofra_color_edit.text(),
                gofra_id=self.gofra_id_edit.text(),
            )
            self.service.calculate_and_save_length(
                project_id=self.project_id,
                cable_line_id=line_id,
                route_method=self.route_combo.currentData(),
                additional_m=self.additional_edit.text() or 0,
                manual_full_m=self.manual_full_edit.text() or None,
            )
            self.refresh_all()
        except CableError as exc:
            QMessageBox.warning(self, "Кабельная линия не сохранена", str(exc))

    def _create_conduit(self) -> None:
        designation, ok = QInputDialog.getText(self, "Новая труба", "GOFRA_ID")
        if not ok:
            return
        conduit_type, ok = QInputDialog.getText(self, "Новая труба", "GOFRA_TYPE (например, ПНД25)")
        if not ok:
            return
        try:
            self.service.create_empty_conduit(
                project_id=self.project_id,
                designation=designation,
                conduit_type=conduit_type,
            )
            self.refresh_all()
        except CableError as exc:
            QMessageBox.warning(self, "Труба не создана", str(exc))

    def _move_line(self) -> None:
        line_id = self._selected_line_id()
        conduit_ids = self._selected_conduit_ids()
        if line_id is None or len(conduit_ids) != 1:
            QMessageBox.information(self, "Перенос", "Выберите одну линию и одну трубу")
            return
        try:
            self.service.move_line_to_conduit(
                project_id=self.project_id,
                cable_line_id=line_id,
                target_conduit_id=next(iter(conduit_ids)),
            )
            self.refresh_all()
        except CableError as exc:
            QMessageBox.warning(self, "Перенос не выполнен", str(exc))

    def _edit_conduit_length(self) -> None:
        conduit_ids = self._selected_conduit_ids()
        if len(conduit_ids) != 1:
            return
        value, ok = QInputDialog.getText(self, "Длина трубы", "Длина, м")
        if not ok:
            return
        try:
            self.service.update_conduit_length(
                project_id=self.project_id,
                conduit_id=next(iter(conduit_ids)),
                length_m=value,
            )
            self.refresh_all()
        except CableError as exc:
            QMessageBox.warning(self, "Длина не сохранена", str(exc))

    def _bulk_edit(self) -> None:
        conduit_ids = self._selected_conduit_ids()
        if not conduit_ids:
            return
        conduit_type, ok = QInputDialog.getText(self, "Массовое изменение", "Тип трубы")
        if not ok:
            return
        diameter, ok = QInputDialog.getText(self, "Массовое изменение", "Диаметр, мм")
        if not ok:
            return
        try:
            self.service.bulk_edit_conduits(
                project_id=self.project_id,
                conduit_ids=conduit_ids,
                conduit_type=conduit_type,
                diameter_mm=diameter or None,
            )
            self.refresh_all()
        except CableError as exc:
            QMessageBox.warning(self, "Изменение не выполнено", str(exc))

    def _select_conduit_product(self) -> None:
        conduit_ids = self._selected_conduit_ids()
        if len(conduit_ids) != 1:
            QMessageBox.information(self, "Товар трубы", "Выберите одну трубу")
            return
        conduit_id = next(iter(conduit_ids))
        try:
            candidates = self.service.conduit_product_candidates(
                project_id=self.project_id, conduit_id=conduit_id
            )
            labels = [
                f"{row['manufacturer']} · {row['name']} · арт. {row['article']}"
                for row in candidates
            ]
            if not labels:
                QMessageBox.information(
                    self, "Товар трубы", "Совместимые товары активного каталога не найдены"
                )
                return
            label, ok = QInputDialog.getItem(
                self, "Товар трубы", "Совместимый товар", labels, 0, False
            )
            if not ok:
                return
            candidate = candidates[labels.index(label)]
            self.service.select_conduit_product(
                project_id=self.project_id,
                conduit_id=conduit_id,
                product_definition_id=candidate["id"],
            )
            self.refresh_conduits()
            self.refresh_routes()
        except CableError as exc:
            QMessageBox.warning(self, "Товар трубы не выбран", str(exc))

    def _edit_route(self) -> None:
        item = self.routes_tree.currentItem()
        if item is None:
            return
        if item.data(0, Qt.ItemDataRole.UserRole + 1) != "CONDUIT":
            item = item.parent()
        if item is None:
            return
        designation = item.text(0)
        number, ok = QInputDialog.getInt(
            self,
            "Кабельная трасса",
            "Номер трубы",
            int(designation.split(".", 1)[0]),
            0,
            999,
        )
        if not ok:
            return
        conduit_type, ok = QInputDialog.getText(
            self, "Кабельная трасса", "GOFRA_TYPE", text=item.text(1)
        )
        if not ok:
            return
        color, ok = QInputDialog.getText(self, "Кабельная трасса", "GOFRA_COLOR", text=item.text(2))
        if not ok:
            return
        length, ok = QInputDialog.getText(self, "Кабельная трасса", "Длина, м", text=item.text(3))
        if not ok:
            return
        try:
            self.service.update_conduit_details(
                project_id=self.project_id,
                conduit_id=item.data(0, Qt.ItemDataRole.UserRole),
                conduit_number=number,
                conduit_type=conduit_type,
                color=color,
                length_m=length,
            )
            self.refresh_all()
        except CableError as exc:
            QMessageBox.warning(self, "Трасса не изменена", str(exc))

    def _start_draft(self) -> None:
        try:
            self.service.start_catalog_draft(self.release_code.text())
            self.refresh_catalog()
        except CableError as exc:
            QMessageBox.warning(self, "Draft не создан", str(exc))

    def _add_product(self) -> None:
        draft_id = self.service.current_draft_release_id()
        if draft_id is None:
            QMessageBox.information(self, "Каталог", "Сначала создайте draft release")
            return
        try:
            self.service.add_catalog_product(
                draft_release_id=draft_id,
                product_key=self.product_key.text(),
                category=self.category.currentText(),
                manufacturer=self.manufacturer.text(),
                model=self.model.text(),
                article=self.article.text(),
                cable_type=self.product_cable_type.text(),
                factory_length_m=self.factory_length.text() or None,
            )
            self.refresh_catalog()
        except CableError as exc:
            QMessageBox.warning(self, "Товар не добавлен", str(exc))

    def _publish(self) -> None:
        draft_id = self.service.current_draft_release_id()
        if draft_id is None:
            return
        try:
            self.service.publish_catalog(draft_id)
            self.refresh_catalog()
        except CableError as exc:
            QMessageBox.warning(self, "Каталог не опубликован", str(exc))

    def _auto_hdmi(self) -> None:
        line_id = self._selected_line_id()
        if line_id is None:
            return
        try:
            result = self.service.auto_select_hdmi(
                project_id=self.project_id, cable_line_id=line_id
            )
            message = f"Выбран товар {result.product_id}, {result.factory_length_m} м"
            if result.warning:
                message += f"\nПредупреждение: {result.warning}"
            QMessageBox.information(self, "Подбор HDMI", message)
        except CableError as exc:
            QMessageBox.warning(self, "Подбор не выполнен", str(exc))

    def _manual_product(self) -> None:
        line_id = self._selected_line_id()
        row = self.catalog_table.currentRow()
        if line_id is None or row < 0:
            return
        product_id = self.catalog_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        load_type = self.lines_table.item(self.lines_table.currentRow(), 4).text()
        try:
            if load_type == "HDMI":
                result = self.service.select_hdmi_manually(
                    project_id=self.project_id,
                    cable_line_id=line_id,
                    product_id=product_id,
                )
                if result.warning:
                    QMessageBox.warning(self, "Выбор HDMI", result.warning)
            elif load_type == "SPEAKER_CABLE":
                self.service.select_speaker_product(
                    project_id=self.project_id,
                    cable_line_id=line_id,
                    product_id=product_id,
                )
            else:
                raise CableError("Selected line is not an AV cable line")
        except CableError as exc:
            QMessageBox.warning(self, "Товар не выбран", str(exc))
