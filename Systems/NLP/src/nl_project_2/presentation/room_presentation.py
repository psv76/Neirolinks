"""Reusable compact room color and multi-room presenters for Qt tables."""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)

from nl_project_2.objects.room_rules import (
    DEFAULT_ROOM_COLOR,
    ROOM_COLOR_PALETTE,
    contrast_text_color,
)

ROOM_MARKERS_ROLE = int(Qt.ItemDataRole.UserRole) + 2
ROOM_COLOR_ROLE = int(Qt.ItemDataRole.UserRole) + 2


class RoomColorComboBox(QComboBox):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        for color in ROOM_COLOR_PALETTE:
            self.addItem(_color_icon(color), "Цвет помещения", color)
            self.setItemData(self.count() - 1, color, Qt.ItemDataRole.ToolTipRole)

    def set_color(self, color: str) -> None:
        normalized = str(color or DEFAULT_ROOM_COLOR).upper()
        index = self.findData(normalized)
        if index < 0:
            self.insertItem(0, _color_icon(normalized), "Сохранённый цвет", normalized)
            self.setItemData(0, normalized, Qt.ItemDataRole.ToolTipRole)
            index = 0
        self.setCurrentIndex(index)

    def color(self) -> str:
        return str(self.currentData() or DEFAULT_ROOM_COLOR)


class RoomSwatchDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option, index) -> None:
        clean = QStyleOptionViewItem(option)
        self.initStyleOption(clean, index)
        clean.text = ""
        _paint_base_without_text(painter, clean)
        color = str(index.data(ROOM_COLOR_ROLE) or DEFAULT_ROOM_COLOR)
        swatch = QRect(
            option.rect.left() + 8,
            option.rect.top() + 5,
            max(24, min(72, option.rect.width() - 16)),
            max(12, option.rect.height() - 10),
        )
        painter.save()
        painter.setPen(QPen(QColor("#697077"), 1))
        painter.setBrush(QColor(color))
        painter.drawRoundedRect(swatch, 5, 5)
        painter.restore()


class RoomChipDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option, index) -> None:
        markers = tuple(index.data(ROOM_MARKERS_ROLE) or ())
        if not markers:
            super().paint(painter, option, index)
            return
        clean = QStyleOptionViewItem(option)
        self.initStyleOption(clean, index)
        clean.text = ""
        # QStyledItemDelegate.paint() calls initStyleOption() again and restores
        # the model text. Draw the prepared option through QStyle directly so
        # selection/focus remain native while the raw label is never painted.
        self._paint_base_without_text(painter, clean)

        painter.save()
        metrics = option.fontMetrics
        left = option.rect.left() + 5
        right = option.rect.right() - 5
        top = option.rect.top() + 4
        height = max(16, option.rect.height() - 8)
        shown = 0
        for marker in markers:
            remaining = len(markers) - shown - 1
            reserve = metrics.horizontalAdvance(f"+{remaining}") + 18 if remaining else 0
            width = min(126, metrics.horizontalAdvance(str(marker["name"])) + 18)
            if left + width + reserve > right and shown:
                break
            width = min(width, max(24, right - left - reserve))
            self._draw_chip(painter, QRect(left, top, width, height), marker)
            left += width + 4
            shown += 1
            if left >= right:
                break
        hidden = len(markers) - shown
        if hidden:
            width = min(metrics.horizontalAdvance(f"+{hidden}") + 16, max(20, right - left))
            self._draw_chip(
                painter,
                QRect(left, top, width, height),
                {"name": f"+{hidden}", "color": "#E5E7EB"},
            )
        painter.restore()

    @staticmethod
    def _draw_chip(painter: QPainter, rect: QRect, marker) -> None:
        color = str(marker.get("color") or DEFAULT_ROOM_COLOR)
        painter.setPen(QPen(QColor(color).darker(125), 1))
        painter.setBrush(QColor(color))
        painter.drawRoundedRect(rect, 7, 7)
        painter.setPen(QColor(contrast_text_color(color)))
        painter.drawText(
            rect.adjusted(7, 0, -7, 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            str(marker.get("name") or ""),
        )

    def sizeHint(self, option, index) -> QSize:
        size = super().sizeHint(option, index)
        return QSize(size.width(), max(28, size.height()))

    @staticmethod
    def _paint_base_without_text(painter: QPainter, option: QStyleOptionViewItem) -> None:
        _paint_base_without_text(painter, option)


def _color_icon(color: str) -> QIcon:
    pixmap = QPixmap(36, 18)
    pixmap.fill(QColor(color))
    return QIcon(pixmap)


def _paint_base_without_text(painter: QPainter, option: QStyleOptionViewItem) -> None:
    widget = option.widget
    style = widget.style() if widget is not None else QApplication.style()
    style.drawControl(QStyle.ControlElement.CE_ItemViewItem, option, painter, widget)
