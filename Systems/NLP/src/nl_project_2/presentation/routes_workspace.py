"""NL Project 3.1 physical Routes workspace: accepted flat variant B.

This is a production PySide6 view over the existing Project-owned cable and
BUS topology. The read model is derived at refresh; there is no second route
storage, migration, CAD interaction or implicit DB write. Segment assignment
commands remain unavailable until Q03/Q06 compatibility is enforced inside
a single transactional domain service (Issue #216).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QAbstractTableModel, QItemSelectionModel, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from .lines_workspace import ContrastCellDelegate

_ID_ROLE = Qt.ItemDataRole.UserRole + 1
_KIND_ROLE = Qt.ItemDataRole.UserRole + 2
_COLS = (
    "Вид",
    "Обозначение",
    "Начало",
    "Конец",
    "Труба",
    "Тип / цвет трубы",
    "Кабель / состав",
    "Длина, м",
    "Состояние",
    "Прокладка",
    "Расчёт сегмента",
    "ID",
)
_COL_WIDTHS = (100, 215, 160, 210, 145, 165, 225, 100, 260, 160, 220, 285)
_GROUP_COLOR = QColor("#eef2f6")
_ISSUE_COLOR = QColor("#fff4d6")
_ERROR_COLOR = QColor("#feeceb")


def _length(value: object) -> str:
    if value is None or str(value).strip() == "":
        return "—"
    try:
        number = Decimal(str(value))
        if not number.is_finite():
            return "—"
        # A table cell must never silently round a stored physical G.
        result = format(number, "f")
        return result.rstrip("0").rstrip(".") if "." in result else result
    except (InvalidOperation, ValueError):
        return "—"


def _sort_key(value: str) -> tuple:
    return tuple(
        (1, int(chunk)) if chunk.isdigit() else (0, chunk.casefold())
        for chunk in re.split(r"(\d+)", value)
    )


def _need_for_tube(edge: dict) -> str:
    """Classify a missing assignment, not the legality of a route."""

    mount = str(edge.get("mount_way") or "").strip()
    existing_tube_data = bool(
        str(edge.get("gofra_type") or "").strip() or str(edge.get("gofra_id") or "").strip()
    )
    if mount in {"По полу", "В стяжке", "В брусе"}:
        return "Требуется"
    if mount in {"По потолку", "В стене"}:
        return "Требуется" if existing_tube_data else "Не требуется"
    if mount == "В кабель-канале":
        return "Не определено" if existing_tube_data else "Не требуется"
    return "Не определено"


@dataclass(frozen=True, slots=True)
class RouteConduit:
    id: str
    designation: str
    conduit_type: str
    color: str
    length_m: str | None
    length_source: str
    product_display: str


@dataclass(frozen=True, slots=True)
class RouteSegment:
    id: str
    cable_line_id: str
    network_kind: str
    line: str
    source: str
    target: str
    conduit_id: str | None
    geometry_m: str | None
    mount_way: str
    cable_type: str
    tube_need: str
    calculation_status: str
    reason: str


@dataclass(frozen=True, slots=True)
class RouteLoadProblem:
    line_id: str
    line: str
    network_kind: str
    details: str


@dataclass(frozen=True, slots=True)
class RouteSnapshot:
    conduits: tuple[RouteConduit, ...]
    segments: tuple[RouteSegment, ...]
    problems: tuple[RouteLoadProblem, ...] = ()


def load_routes_snapshot(cables, buses, project_id: str) -> RouteSnapshot:
    """Project data only; all reads go through existing service contracts."""

    conduits = tuple(
        RouteConduit(
            id=str(row["id"]),
            designation=str(row.get("designation") or ""),
            conduit_type=str(row.get("conduit_type") or ""),
            color=str(row.get("color") or ""),
            length_m=row.get("length_m_decimal"),
            length_source=str((row.get("path_json") or {}).get("length_source") or ""),
            product_display=str(row.get("product_name") or ""),
        )
        for row in cables.list_conduits(project_id)
    )
    known_conduits = {tube.id for tube in conduits}
    segments = []
    identities: set[tuple[str, str]] = set()
    problems: list[RouteLoadProblem] = []

    def add_edges(card: dict, topology: dict, kind: str) -> None:
        for edge in topology.get("edges", ()):
            if kind == "BUS" and edge.get("connection_kind") != "CABLE":
                continue  # Nonphysical TRACK connections do not get protective conduits.
            segment_id = str(edge.get("segment_id") or "")
            if not segment_id:
                raise ValueError(f"Physical segment lacks an ID: {card.get('designation')}")
            key = (kind, segment_id)
            if key in identities:
                raise ValueError(f"Duplicate physical segment: {kind}/{segment_id}")
            identities.add(key)
            conduit_id = str(edge.get("conduit_id") or "") or None
            if conduit_id is not None and conduit_id not in known_conduits:
                # Do not silently display a broken assignment as "Без трубы".
                raise ValueError(f"Segment {segment_id}: conduit {conduit_id} is missing")
            source = dict(edge.get("source") or {})
            target = dict(edge.get("target") or {})
            need = _need_for_tube(edge) if conduit_id is None else ""
            segments.append(
                RouteSegment(
                    id=segment_id,
                    cable_line_id=str(card["id"]),
                    network_kind=kind,
                    line=str(card.get("designation") or ""),
                    source=str(source.get("label") or "—"),
                    target=str(target.get("label") or "—"),
                    conduit_id=conduit_id,
                    geometry_m=edge.get("physical_length_m"),
                    mount_way=str(edge.get("mount_way") or ""),
                    cable_type=str(card.get("cable_type") or ""),
                    tube_need=need,
                    calculation_status=str(edge.get("calculation_status") or "INCOMPLETE"),
                    reason=str(edge.get("calculation_reason") or ""),
                )
            )

    def add_card(card: dict, topology_reader, kind: str) -> None:
        # Existing Project may contain a dangling endpoint reference. Keep the
        # other lines visible but do not present incomplete graph data as valid.
        before = len(segments)
        before_ids = identities.copy()
        try:
            add_edges(card, topology_reader(project_id, str(card["id"])), kind)
        except (KeyError, ValueError) as exc:
            del segments[before:]
            identities.clear()
            identities.update(before_ids)
            problems.append(
                RouteLoadProblem(
                    line_id=str(card["id"]),
                    line=str(card.get("designation") or card["id"]),
                    network_kind=kind,
                    details=f"{type(exc).__name__}: {exc}",
                )
            )

    for card in cables.line_cards(project_id):
        add_card(card, cables.topology, "CABLE")
    if buses is not None:
        for card in buses.journal_cards(project_id):
            add_card(card, buses.journal_topology, "BUS")
    return RouteSnapshot(conduits, tuple(segments), tuple(problems))


@dataclass(frozen=True, slots=True)
class VisibleRouteRow:
    kind: str  # CONDUIT / SEGMENT
    identity: str
    conduit: RouteConduit | None = None
    segment: RouteSegment | None = None
    count: int = 0
    indented: bool = False


def _matches(query: str, *parts: object) -> bool:
    return not query or any(query in str(part).casefold() for part in parts)


def build_visible_rows(
    snapshot: RouteSnapshot,
    expanded: set[str],
    *,
    query: str = "",
    scope: str = "Все",
    sort: str = "Обозначение",
) -> tuple[list[VisibleRouteRow], int, int]:
    """Variant B: physical conduit roots plus inline children, orphan flat rows."""

    query = query.strip().casefold()
    grouped: dict[str, list[RouteSegment]] = {t.id: [] for t in snapshot.conduits}
    unassigned = []
    for segment in snapshot.segments:
        if segment.conduit_id is None:
            unassigned.append(segment)
        else:
            grouped[segment.conduit_id].append(segment)

    tubes = list(snapshot.conduits)
    if sort == "Длина трубы ↓":

        def numeric(tube: RouteConduit) -> Decimal:
            try:
                value = Decimal(str(tube.length_m))
                return value if value.is_finite() else Decimal("-1")
            except InvalidOperation:
                return Decimal("-1")

        tubes.sort(key=lambda tube: (-numeric(tube), _sort_key(tube.designation)))
    else:
        tubes.sort(key=lambda tube: _sort_key(tube.designation))

    visible: list[VisibleRouteRow] = []
    count = 0
    tube_count = 0
    if scope in {"Все", "В трубе"}:
        for tube in tubes:
            all_children = sorted(grouped[tube.id], key=lambda seg: (_sort_key(seg.line), seg.id))
            tube_match = _matches(
                query, tube.designation, tube.conduit_type, tube.color, tube.product_display
            )
            children = [
                seg
                for seg in all_children
                if tube_match
                or _matches(
                    query, seg.line, seg.source, seg.target, seg.cable_type, seg.mount_way, seg.id
                )
            ]
            if query and not tube_match and not children:
                continue
            tube_count += 1
            count += len(children)
            visible.append(VisibleRouteRow("CONDUIT", tube.id, conduit=tube, count=len(children)))
            if tube.id in expanded:
                for segment in children:
                    visible.append(
                        VisibleRouteRow(
                            "SEGMENT",
                            f"CABLE:{segment.id}"
                            if segment.network_kind == "CABLE"
                            else f"BUS:{segment.id}",
                            segment=segment,
                            conduit=tube,
                            indented=True,
                        )
                    )

    if scope != "В трубе":
        for segment in sorted(unassigned, key=lambda seg: (_sort_key(seg.line), seg.id)):
            if scope == "Требует трубы" and segment.tube_need != "Требуется":
                continue
            if not _matches(
                query,
                segment.line,
                segment.source,
                segment.target,
                segment.cable_type,
                segment.mount_way,
                segment.id,
                "Без трубы",
                segment.tube_need,
            ):
                continue
            count += 1
            visible.append(
                VisibleRouteRow("SEGMENT", f"{segment.network_kind}:{segment.id}", segment=segment)
            )
    return visible, count, tube_count


class RoutesTableModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: list[VisibleRouteRow] = []
        self.expanded: set[str] = set()

    def replace(self, rows: list[VisibleRouteRow], expanded: set[str]) -> None:
        self.beginResetModel()
        self.rows = rows
        self.expanded = set(expanded)
        self.endResetModel()

    def rowCount(self, parent=None) -> int:
        return 0 if parent is not None and parent.isValid() else len(self.rows)

    def columnCount(self, parent=None) -> int:
        return 0 if parent is not None and parent.isValid() else len(_COLS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return _COLS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        if row.kind == "CONDUIT":
            tube = row.conduit
            assert tube is not None
            name = ("▾ " if tube.id in self.expanded else "▸ ") + "Труба"
            values = (
                name,
                tube.designation,
                "—",
                "—",
                tube.designation,
                " / ".join(v for v in (tube.conduit_type, tube.color) if v),
                f"{row.count} сегм.",
                _length(tube.length_m),
                "Длина не рассчитана"
                if tube.length_m is None
                else (
                    "Ручная длина"
                    if tube.length_source == "USER_CONFIRMED"
                    else "Сохранённая длина"
                ),
                "—",
                "—",
                tube.id,
            )
        else:
            seg = row.segment
            assert seg is not None
            tube = row.conduit
            values = (
                "   ↳ Сегмент" if row.indented else "Сегмент",
                f"{seg.line} / {seg.network_kind}",
                seg.source,
                seg.target,
                tube.designation if tube else "Без трубы",
                f"{tube.conduit_type} / {tube.color}" if tube else "—",
                seg.cable_type or "—",
                _length(seg.geometry_m),
                seg.tube_need
                if seg.conduit_id is None
                else (
                    seg.reason if seg.calculation_status != "READY" else seg.mount_way or "Назначен"
                ),
                seg.mount_way or "Не указано",
                "Рассчитан" if seg.calculation_status == "READY" else seg.reason or "Не рассчитан",
                seg.id,
            )
        value = values[index.column()]
        if role == Qt.ItemDataRole.DisplayRole:
            return value
        if role == Qt.ItemDataRole.ToolTipRole:
            if index.column() == 7:
                return (
                    "Чистая геометрия G этого сегмента; без выводов и округления"
                    if row.kind == "SEGMENT"
                    else (
                        "Сохранённая длина трубы в Project; "
                        + {
                            "USER_CONFIRMED": "задана пользователем",
                            "SEGMENT_GEOMETRY": "из геометрии сегмента",
                            "INCOMPLETE_SHARED": "общая труба: длина не определена",
                            "STALE_OR_INCOMPLETE_GEOMETRY": "геометрия неполна или устарела",
                        }.get(row.conduit.length_source, "источник не указан")
                        + ". Полная формула Q08 не применяется этим экраном."
                    )
                )
            if row.kind == "SEGMENT" and index.column() == 1:
                return f"{row.segment.network_kind} segment_id: {row.segment.id}"
            if row.kind == "CONDUIT" and index.column() == 5:
                return (
                    f"{value} · {row.conduit.product_display}"
                    if row.conduit.product_display
                    else str(value)
                )
            return str(value)
        if role == _ID_ROLE:
            return row.identity
        if role == _KIND_ROLE:
            return row.kind
        if role == Qt.ItemDataRole.BackgroundRole:
            if row.kind == "CONDUIT":
                return QBrush(_GROUP_COLOR)
            if row.segment and row.segment.calculation_status != "READY":
                return QBrush(_ERROR_COLOR) if index.column() == 7 else None
            if row.segment and row.segment.tube_need == "Требуется" and index.column() == 8:
                return QBrush(_ISSUE_COLOR)
        if role == Qt.ItemDataRole.FontRole and row.kind == "CONDUIT":
            font = QFont()
            font.setBold(True)
            return font
        if role == Qt.ItemDataRole.TextAlignmentRole and index.column() == 7:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable


class RoutesTable(QTableView):
    toggleRequested = Signal(str)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            index = self.currentIndex()
            if index.isValid() and index.data(_KIND_ROLE) == "CONDUIT":
                self.toggleRequested.emit(str(index.data(_ID_ROLE)))
                return
        if event.key() == Qt.Key.Key_Delete:
            return
        super().keyPressEvent(event)


class RoutesWorkspace(QWidget):
    """One full-width Routes section with no side panel and no implicit writes."""

    lineRequested = Signal(str)

    def __init__(self, cables, buses, project_id: str, *, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("routesWorkspace")
        self.cables = cables
        self.buses = buses
        self.project_id = project_id
        self.snapshot: RouteSnapshot | None = None
        self._expanded: set[str] = set()
        self._selected: set[str] = set()
        self._restoring = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Фильтр / поиск", self))
        self.search = QLineEdit(self)
        self.search.setObjectName("routesSearch")
        self.search.setPlaceholderText("Труба, линия, сегмент, источник, приёмник, кабель")
        self.search.setMinimumWidth(280)
        toolbar.addWidget(self.search, 2)
        self.scope = QComboBox(self)
        self.scope.setObjectName("routesScope")
        self.scope.addItems(("Все", "В трубе", "Без трубы", "Требует трубы"))
        toolbar.addWidget(self.scope)
        self.sort = QComboBox(self)
        self.sort.setObjectName("routesSort")
        self.sort.addItems(("Обозначение", "Длина трубы ↓"))
        toolbar.addWidget(self.sort)
        self.clear_search = QPushButton("Сброс", self)
        toolbar.addWidget(self.clear_search)
        self.expand_all = QPushButton("Раскрыть всё", self)
        self.collapse_all = QPushButton("Свернуть всё", self)
        toolbar.addWidget(self.expand_all)
        toolbar.addWidget(self.collapse_all)
        root.addLayout(toolbar)
        self.read_only_info = QLabel(
            "Только просмотр. Изменение труб и назначений станет доступно после проверки "
            "физических границ и атомарных операций для кабелей и BUS.",
            self,
        )
        self.read_only_info.setWordWrap(True)
        self._read_only_intro = self.read_only_info.text()
        root.addWidget(self.read_only_info)

        self.table = RoutesTable(self)
        self.table.setObjectName("routesFlatTable")
        self.model = RoutesTableModel(self)
        self.table.setModel(self.model)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setMouseTracking(True)
        self.table.viewport().setMouseTracking(True)
        self.table.setItemDelegate(ContrastCellDelegate(self.table))
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setStyleSheet(
            "QTableView::item:selected {background: #2f6fab; color: white;}"
            "QTableView::item:selected:!active {background: #607d99; color: white;}"
        )
        header = self.table.horizontalHeader()
        header.setSectionsMovable(True)
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setMinimumHeight(32)
        header.setStyleSheet(
            "QHeaderView::section {border-right: 1px solid #d9dee7; padding: 5px 7px;}"
        )
        header_font = header.font()
        header_font.setBold(True)
        header.setFont(header_font)
        for index, width in enumerate(_COL_WIDTHS):
            self.table.setColumnWidth(index, width)
        # UUID stays in the read model and row roles, not in the operator table.
        self.table.setColumnHidden(len(_COLS) - 1, True)
        self.table.selectionModel().selectionChanged.connect(self._selection_changed)
        self.table.clicked.connect(self._clicked)
        self.table.doubleClicked.connect(self._double_clicked)
        self.table.toggleRequested.connect(self.toggle_conduit)
        root.addWidget(self.table, 1)

        actions = QHBoxLayout()
        for label in ("Назначить трубу", "Перенести", "Убрать из трубы"):
            button = QPushButton(label, self)
            button.setEnabled(False)
            button.setToolTip(
                "Назначения появятся после транзакционной проверки физических границ и "
                "совместимости ordinary/BUS (Issue #216)."
            )
            actions.addWidget(button)
        actions.addStretch(1)
        self.reload_button = QPushButton("Обновить список", self)
        self.reload_button.setObjectName("routesRefresh")
        actions.addWidget(self.reload_button)
        self.matches = QLabel("", self)
        actions.addWidget(self.matches)
        root.addLayout(actions)
        self.selection_info = QLabel(self)
        self.selection_info.setObjectName("routesSelectionInfo")
        root.addWidget(self.selection_info)

        self.search.textChanged.connect(self._change_filter)
        self.scope.currentIndexChanged.connect(self._change_filter)
        self.sort.currentIndexChanged.connect(self._change_filter)
        self.clear_search.clicked.connect(self._reset_filters)
        self.expand_all.clicked.connect(lambda: self.set_expanded(True))
        self.collapse_all.clicked.connect(lambda: self.set_expanded(False))
        self.reload_button.clicked.connect(self.refresh)
        self._update_selection_info()

    def _reset_filters(self) -> None:
        self.search.clear()
        self.scope.setCurrentIndex(0)
        self.sort.setCurrentIndex(0)
        self.rebuild()

    def _change_filter(self, *_args) -> None:
        if self.snapshot is None:
            return
        # Search hits need to be visible without manually expanding each conduit.
        if self.search.text().strip():
            self._expanded.update(t.id for t in self.snapshot.conduits)
        self.rebuild()

    def refresh(self) -> None:
        """Explicit Project read. No side effects, no live DWG interaction."""

        try:
            snapshot = load_routes_snapshot(self.cables, self.buses, self.project_id)
        except Exception as exc:
            QMessageBox.warning(self, "Трассы не загружены", str(exc))
            return
        self.snapshot = snapshot
        self.read_only_info.setText(self._read_only_intro)
        self.read_only_info.setToolTip("")
        if snapshot.problems:
            names = ", ".join(problem.line for problem in snapshot.problems[:6])
            extra = "…" if len(snapshot.problems) > 6 else ""
            self.read_only_info.setText(
                self._read_only_intro
                + "\n⚠ Не отображены участки линий с ошибками топологии "
                + f"({len(snapshot.problems)}): {names}{extra}. "
                + "Остальные физические участки показаны; данные не исправлялись."
            )
            self.read_only_info.setToolTip(
                "\n".join(
                    f"{problem.network_kind} {problem.line} ({problem.line_id}): {problem.details}"
                    for problem in snapshot.problems
                )
            )
        valid_ids = {t.id for t in snapshot.conduits}
        valid_ids.update(f"{s.network_kind}:{s.id}" for s in snapshot.segments)
        self._selected.intersection_update(valid_ids)
        self._expanded.intersection_update(t.id for t in snapshot.conduits)
        self.rebuild()

    def rebuild(self) -> None:
        if self.snapshot is None:
            return
        rows, count, tubes = build_visible_rows(
            self.snapshot,
            self._expanded,
            query=self.search.text(),
            scope=self.scope.currentText(),
            sort=self.sort.currentText(),
        )
        self._restoring = True
        selected = self.table.selectionModel()
        widths = [self.table.columnWidth(i) for i in range(len(_COLS))]
        current = self.table.currentIndex()
        current_id = current.data(_ID_ROLE)
        current_column = current.column()
        vertical = self.table.verticalScrollBar().value()
        horizontal = self.table.horizontalScrollBar().value()
        self.model.replace(rows, self._expanded)
        for col, width in enumerate(widths):
            self.table.setColumnWidth(col, width)
        selected.blockSignals(True)
        selected.clearSelection()
        for index in range(self.model.rowCount()):
            item = self.model.index(index, 0)
            if item.data(_ID_ROLE) == current_id:
                selected.setCurrentIndex(
                    self.model.index(index, current_column),
                    QItemSelectionModel.SelectionFlag.NoUpdate,
                )
            if item.data(_ID_ROLE) in self._selected:
                selected.select(
                    item,
                    QItemSelectionModel.SelectionFlag.Select
                    | QItemSelectionModel.SelectionFlag.Rows,
                )
        selected.blockSignals(False)
        self.table.verticalScrollBar().setValue(vertical)
        self.table.horizontalScrollBar().setValue(horizontal)
        self._restoring = False
        self.matches.setText(f"Найдено: {count} сегм. · {tubes} труб")
        self._update_selection_info()

    def set_expanded(self, expand: bool) -> None:
        if self.snapshot is None:
            return
        if expand:
            self._expanded.update(t.id for t in self.snapshot.conduits)
        else:
            self._expanded.clear()
        self.rebuild()

    def toggle_conduit(self, identity: str) -> None:
        if identity in self._expanded:
            self._expanded.remove(identity)
        else:
            self._expanded.add(identity)
        self.rebuild()

    def _clicked(self, index) -> None:
        if index.column() == 0 and index.data(_KIND_ROLE) == "CONDUIT":
            self.toggle_conduit(str(index.data(_ID_ROLE)))

    def _double_clicked(self, index) -> None:
        if index.data(_KIND_ROLE) == "CONDUIT" and index.column() != 0:
            self.toggle_conduit(str(index.data(_ID_ROLE)))
            return
        if index.data(_KIND_ROLE) == "SEGMENT":
            row = self.model.rows[index.row()]
            if row.segment:
                self.lineRequested.emit(row.segment.cable_line_id)

    def _selection_changed(self, *_args) -> None:
        if self._restoring:
            return
        visible = {r.identity for r in self.model.rows}
        chosen = {x.data(_ID_ROLE) for x in self.table.selectionModel().selectedRows(0)}
        self._selected.difference_update(visible - chosen)
        self._selected.update(chosen)
        self._update_selection_info()

    def _update_selection_info(self) -> None:
        visible = {r.identity for r in self.model.rows}
        segments = sum(key.startswith(("CABLE:", "BUS:")) for key in self._selected)
        tubes = sum(not key.startswith(("CABLE:", "BUS:")) for key in self._selected)
        hidden = len(self._selected - visible)
        self.selection_info.setText(
            f"Выбрано: {segments} сегм. · {tubes} труб · скрыто выбранных: {hidden}"
        )

    def select_conduit(self, conduit_id: str) -> bool:
        """Navigate from specification without opening legacy expert dialog."""

        if self.snapshot is None:
            self.refresh()
        self.scope.setCurrentIndex(0)
        self.search.clear()
        for index, row in enumerate(self.model.rows):
            if row.kind == "CONDUIT" and row.identity == conduit_id:
                item = self.model.index(index, 0)
                self.table.selectionModel().setCurrentIndex(
                    item,
                    QItemSelectionModel.SelectionFlag.ClearAndSelect
                    | QItemSelectionModel.SelectionFlag.Rows,
                )
                self.table.scrollTo(item)
                return True
        return False
