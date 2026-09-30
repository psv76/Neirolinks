"""Table-based DIN panel layout over the shared ProjectInstance model."""

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
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from nl_project_2.panels import PanelError

from .constructor_workspace import ConstructorWorkspaceDialog


class PanelWorkspaceDialog(QDialog):
    def __init__(self, service, constructor_service, project_id: str, parent=None) -> None:
        super().__init__(parent)
        self.service = service
        self.constructor_service = constructor_service
        self.project_id = project_id
        self._layout = None
        self.setWindowTitle("Щиты — DIN-компоновка")
        self.resize(1300, 820)

        self.board_combo = QComboBox(self)
        self.board_combo.setObjectName("panelBoardCombo")
        self.board_combo.currentIndexChanged.connect(self.refresh_layout)
        self.board_designation = QLineEdit(self)
        self.board_title = QLineEdit(self)
        create_board = QPushButton("Создать электрический щит", self)
        create_board.setObjectName("createPanelBoardButton")
        create_board.clicked.connect(self._create_board)
        board_form = QFormLayout()
        board_form.addRow("Щит", self.board_combo)
        board_form.addRow("Новое обозначение", self.board_designation)
        board_form.addRow("Название", self.board_title)
        board_form.addRow("", create_board)

        self.sections_table = QTableWidget(0, 4, self)
        self.sections_table.setObjectName("panelSectionsRailsTable")
        self.sections_table.setHorizontalHeaderLabels(
            ["Секция", "Порядок секции", "Рейка", "Полезная ширина, мм"]
        )
        self.section_key = QLineEdit(self)
        self.section_order = QSpinBox(self)
        self.section_order.setRange(0, 999)
        create_section = QPushButton("Добавить секцию", self)
        create_section.setObjectName("createPanelSectionButton")
        create_section.clicked.connect(self._create_section)
        delete_section = QPushButton("Удалить выбранную секцию", self)
        delete_section.clicked.connect(self._delete_section)
        self.rail_section_combo = QComboBox(self)
        self.rail_order = QSpinBox(self)
        self.rail_order.setRange(0, 999)
        self.rail_width = QLineEdit(self)
        create_rail = QPushButton("Добавить DIN-рейку", self)
        create_rail.setObjectName("createPanelRailButton")
        create_rail.clicked.connect(self._create_rail)

        self.instances_table = QTableWidget(0, 7, self)
        self.instances_table.setObjectName("panelInstancesTable")
        self.instances_table.setHorizontalHeaderLabels(
            ["Экземпляр", "Товар", "Щит", "Монтаж", "Ширина, мм", "Состояние", "Размещён"]
        )
        assign = QPushButton("Назначить экземпляр выбранному щиту", self)
        assign.setObjectName("assignInstanceToPanelButton")
        assign.clicked.connect(self._assign_instance)
        open_instance = QPushButton("Открыть карточку / цепь экземпляра", self)
        open_instance.setObjectName("openPanelInstanceButton")
        open_instance.clicked.connect(self._open_instance)

        self.rail_combo = QComboBox(self)
        self.start_mm = QLineEdit(self)
        self.orientation_combo = QComboBox(self)
        self.orientation_combo.addItem("Обычная", "NORMAL")
        self.orientation_combo.addItem("Обратная", "REVERSED")
        place = QPushButton("Разместить выбранный экземпляр", self)
        place.setObjectName("placePanelInstanceButton")
        place.clicked.connect(self._place)

        self.placements_table = QTableWidget(0, 9, self)
        self.placements_table.setObjectName("panelPlacementsTable")
        self.placements_table.setHorizontalHeaderLabels(
            [
                "Секция",
                "Рейка",
                "Порядок",
                "Экземпляр",
                "Товар",
                "Начало, мм",
                "Ширина, мм",
                "Статус",
                "Проверки",
            ]
        )
        move = QPushButton("Перенести выбранное размещение", self)
        move.setObjectName("movePanelPlacementButton")
        move.clicked.connect(self._move)
        remove = QPushButton("Убрать с DIN-рейки", self)
        remove.setObjectName("removePanelPlacementButton")
        remove.clicked.connect(self._remove)

        self.materials_table = QTableWidget(0, 5, self)
        self.materials_table.setObjectName("panelMaterialsTable")
        self.materials_table.setHorizontalHeaderLabels(
            ["Внутренний материал", "Количество", "Ед.", "Основание", "DIN-место"]
        )
        self.status_label = QLabel("Выберите или создайте электрический щит", self)
        self.status_label.setObjectName("panelLayoutStatus")
        self.status_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addLayout(board_form)
        layout.addWidget(QLabel("Секции и DIN-рейки", self))
        layout.addWidget(self.sections_table)
        section_form = QFormLayout()
        section_form.addRow("Ключ секции", self.section_key)
        section_form.addRow("Порядок секции", self.section_order)
        layout.addLayout(section_form)
        actions = QHBoxLayout()
        actions.addWidget(create_section)
        actions.addWidget(delete_section)
        actions.addStretch(1)
        layout.addLayout(actions)
        rail_form = QFormLayout()
        rail_form.addRow("Секция рейки", self.rail_section_combo)
        rail_form.addRow("Порядок рейки", self.rail_order)
        rail_form.addRow("Полезная ширина, мм", self.rail_width)
        rail_form.addRow("", create_rail)
        layout.addLayout(rail_form)
        layout.addWidget(QLabel("Экземпляры общей модели Project", self))
        layout.addWidget(self.instances_table)
        actions = QHBoxLayout()
        actions.addWidget(assign)
        actions.addWidget(open_instance)
        actions.addStretch(1)
        layout.addLayout(actions)
        placement_form = QFormLayout()
        placement_form.addRow("DIN-рейка", self.rail_combo)
        placement_form.addRow("Начало, мм", self.start_mm)
        placement_form.addRow("Ориентация", self.orientation_combo)
        placement_form.addRow("", place)
        layout.addLayout(placement_form)
        layout.addWidget(QLabel("Сохранённые размещения", self))
        layout.addWidget(self.placements_table)
        actions = QHBoxLayout()
        actions.addWidget(move)
        actions.addWidget(remove)
        actions.addStretch(1)
        layout.addLayout(actions)
        layout.addWidget(QLabel("Внутренние материалы (DIN-место не занимают)", self))
        layout.addWidget(self.materials_table)
        layout.addWidget(self.status_label)
        self.refresh_boards()

    def refresh_boards(self) -> None:
        selected = self.board_combo.currentData()
        self.board_combo.blockSignals(True)
        self.board_combo.clear()
        for row in self.service.list_boards(self.project_id):
            if row["board_kind"] != "BOARD_AV":
                self.board_combo.addItem(row["designation"], row["id"])
        index = self.board_combo.findData(selected)
        self.board_combo.setCurrentIndex(max(index, 0))
        self.board_combo.blockSignals(False)
        self.refresh_layout()

    def refresh_layout(self) -> None:
        board_id = self.board_combo.currentData()
        for table in (
            self.sections_table,
            self.instances_table,
            self.placements_table,
            self.materials_table,
        ):
            table.setRowCount(0)
        self.rail_section_combo.clear()
        self.rail_combo.clear()
        if not board_id:
            self._layout = None
            self.status_label.setText("Выберите или создайте электрический щит")
            return
        self._layout = self.service.board_layout(project_id=self.project_id, board_id=board_id)
        sections = {row["id"]: row for row in self._layout["sections"]}
        for section in self._layout["sections"]:
            self.rail_section_combo.addItem(section["section_key"], section["id"])
        self.sections_table.setRowCount(len(self._layout["rails"]))
        placement_rows = []
        issue_codes = []
        for row_index, rail in enumerate(self._layout["rails"]):
            section = sections[rail["panel_section_id"]]
            self.rail_combo.addItem(f"{section['section_key']} / {rail['rail_order']}", rail["id"])
            for column, value in enumerate(
                (
                    section["section_key"],
                    section["section_order"],
                    rail["rail_order"],
                    rail["usable_width_mm_decimal"],
                )
            ):
                item = QTableWidgetItem("" if value is None else str(value))
                item.setData(Qt.ItemDataRole.UserRole, section["id"])
                self.sections_table.setItem(row_index, column, item)
            issues = "; ".join(issue.code for issue in rail["evaluation"].issues)
            issue_codes.extend(issue.code for issue in rail["evaluation"].issues)
            for order, placement in enumerate(rail["placements"], start=1):
                placement_rows.append(
                    (
                        placement,
                        section["section_key"],
                        rail["rail_order"],
                        order,
                        rail["evaluation"].status,
                        issues,
                    )
                )
        self.instances_table.setRowCount(len(self._layout["instances"]))
        for row_index, row in enumerate(self._layout["instances"]):
            values = (
                row["designation"],
                row["product_key"] or "Не выбран",
                row["board_state"],
                row["mounting"] or "Не определён",
                row["width_mm"],
                row["layout_state"],
                "YES" if row["placed"] else "NO",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem("" if value is None else str(value))
                item.setData(Qt.ItemDataRole.UserRole, row["id"])
                self.instances_table.setItem(row_index, column, item)
        self.placements_table.setRowCount(len(placement_rows))
        for row_index, (row, section_key, rail_order, order, status, issues) in enumerate(
            placement_rows
        ):
            values = (
                section_key,
                rail_order,
                order,
                row["designation"],
                row["product_key"],
                row["start_mm_decimal"],
                row["current_width_mm"],
                status,
                ("PRODUCT_WIDTH_CHANGED; " if row["width_changed"] else "") + issues,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem("" if value is None else str(value))
                item.setData(Qt.ItemDataRole.UserRole, row["id"])
                self.placements_table.setItem(row_index, column, item)
        self.materials_table.setRowCount(len(self._layout["materials"]))
        for row_index, row in enumerate(self._layout["materials"]):
            for column, value in enumerate(
                (row["material_kind"], row["quantity_decimal"], row["unit"], row["reason"], "NO")
            ):
                self.materials_table.setItem(row_index, column, QTableWidgetItem(str(value)))
        incomplete = sum(row["layout_state"] != "READY" for row in self._layout["instances"])
        checks = ", ".join(issue_codes) if issue_codes else "VALID"
        self.status_label.setText(
            f"Размещений: {len(placement_rows)}; "
            f"незавершённых экземпляров: {incomplete}; проверки: {checks}"
        )

    def _create_board(self) -> None:
        self._run(
            lambda: self.service.create_board(
                project_id=self.project_id,
                designation=self.board_designation.text(),
                title=self.board_title.text(),
            ),
            self.refresh_boards,
        )

    def _create_section(self) -> None:
        board_id = self.board_combo.currentData()
        if board_id:
            self._run(
                lambda: self.service.create_section(
                    project_id=self.project_id,
                    board_id=board_id,
                    section_key=self.section_key.text(),
                    section_order=self.section_order.value(),
                ),
                self.refresh_layout,
            )

    def _delete_section(self) -> None:
        row = self.sections_table.currentRow()
        if row >= 0:
            section_id = self.sections_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            self._run(
                lambda: self.service.delete_section(
                    project_id=self.project_id, section_id=section_id
                ),
                self.refresh_layout,
            )

    def _create_rail(self) -> None:
        section_id = self.rail_section_combo.currentData()
        if section_id:
            self._run(
                lambda: self.service.create_rail(
                    project_id=self.project_id,
                    section_id=section_id,
                    rail_order=self.rail_order.value(),
                    usable_width_mm=self.rail_width.text(),
                ),
                self.refresh_layout,
            )

    def _selected_instance_id(self):
        row = self.instances_table.currentRow()
        return None if row < 0 else self.instances_table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def _assign_instance(self) -> None:
        instance_id, board_id = self._selected_instance_id(), self.board_combo.currentData()
        if instance_id and board_id:
            self._run(
                lambda: self.service.assign_instance_to_board(
                    project_id=self.project_id, instance_id=instance_id, board_id=board_id
                ),
                self.refresh_layout,
            )

    def _place(self) -> None:
        instance_id, rail_id = self._selected_instance_id(), self.rail_combo.currentData()
        if instance_id and rail_id:
            self._run(
                lambda: self.service.place_instance(
                    project_id=self.project_id,
                    rail_id=rail_id,
                    instance_id=instance_id,
                    start_mm=self.start_mm.text(),
                    orientation=self.orientation_combo.currentData(),
                ),
                self.refresh_layout,
            )

    def _selected_placement_id(self):
        row = self.placements_table.currentRow()
        return (
            None if row < 0 else self.placements_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        )

    def _move(self) -> None:
        placement_id, rail_id = self._selected_placement_id(), self.rail_combo.currentData()
        if placement_id and rail_id:
            self._run(
                lambda: self.service.move_placement(
                    project_id=self.project_id,
                    placement_id=placement_id,
                    rail_id=rail_id,
                    start_mm=self.start_mm.text(),
                    orientation=self.orientation_combo.currentData(),
                ),
                self.refresh_layout,
            )

    def _remove(self) -> None:
        placement_id = self._selected_placement_id()
        if placement_id:
            self._run(
                lambda: self.service.remove_placement(
                    project_id=self.project_id, placement_id=placement_id
                ),
                self.refresh_layout,
            )

    def _open_instance(self) -> None:
        instance_id = self._selected_instance_id()
        if instance_id and self.constructor_service is not None:
            ConstructorWorkspaceDialog(
                self.constructor_service, self.project_id, self, selected_instance_id=instance_id
            ).exec()

    def _run(self, command, refresh) -> None:
        try:
            command()
            refresh()
        except PanelError as exc:
            QMessageBox.warning(self, "DIN-компоновка", str(exc))
