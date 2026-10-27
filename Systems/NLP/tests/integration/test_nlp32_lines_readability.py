"""NLP 3.2: compact readable table, accessible selected row and stale diagnostics."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QLabel

from nl_project_2.presentation.lines_workspace import (
    LinesWorkspace, _column_index, _segment_length_text,
    _segment_length_tooltip,
)
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))
from test_lines_workspace import FakeCableService, FakeConstructor, _row


def _luminance(color):
    vals=(color.redF(),color.greenF(),color.blueF())
    def channel(v):
        return v/12.92 if v<=0.04045 else ((v+0.055)/1.055)**2.4
    return sum(a*channel(v) for a,v in zip((0.2126,0.7152,0.0722),vals))


def test_selected_cell_has_wcag_aa_text_contrast_and_restores_normal_color(qtbot):
    w=LinesWorkspace(FakeCableService(),FakeConstructor(),"project")
    qtbot.addWidget(w)
    w.resize(1450,850)
    w.show()
    QApplication.processEvents()
    row=_row(w,"line-2")
    col=_column_index("load_name")
    w.table.selectRow(row)
    QApplication.processEvents()
    cell=w.table.item(row,col)
    assert cell.isSelected()
    assert cell.foreground().color()==QColor("#FFFFFF")
    dark=QColor("#174A75")
    ratio=(1.05)/(_luminance(dark)+0.05)
    assert ratio>=7.0  # Enhanced AAA, above the requested AA 4.5:1.
    assert w.table.verticalHeader().defaultSectionSize()<=32
    assert cell.toolTip()=="Кухонные розетки"
    w.table.clearSelection()
    QApplication.processEvents()
    assert not cell.isSelected()
    assert cell.foreground().color()!=QColor("#FFFFFF")


def test_search_label_does_not_overlap_search_field(qtbot):
    w=LinesWorkspace(FakeCableService(),FakeConstructor(),"project")
    qtbot.addWidget(w)
    w.resize(1450,850)
    w.show()
    QApplication.processEvents()
    labels=[x for x in w.findChildren(QLabel) if x.text()=="Поиск по линиям"]
    assert len(labels)==1
    assert labels[0].geometry().right()<w.search.geometry().left()
    assert w.search.width()>400


def test_stale_length_exposes_saved_value_without_pretending_it_is_current():
    edge={
        "cable_length_m":None,
        "stored_length_m":"7.6097",
        "current_geometry_length_m":"7.3209",
        "stale_calculation":True,
        "calculation_reason":"Сохранённый расчёт устарел",
    }
    value=_segment_length_text(edge)
    tooltip=_segment_length_tooltip(edge)
    assert "устар" in value
    assert "7.61" in value
    assert "7.61" in tooltip and "7.32" in tooltip
    assert _segment_length_text({"cable_length_m":None})=="⚠ нет расчёта"
