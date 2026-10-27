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
    assert not labels
    assert "Номер" in w.search.placeholderText()
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


def test_hover_and_current_cell_render_white_text_on_dark_blue(qtbot):
    from PySide6.QtTest import QTest
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QApplication
    service=FakeCableService()
    w=LinesWorkspace(service,FakeConstructor(),"project")
    qtbot.addWidget(w)
    w.resize(1450,850)
    w.show()
    QApplication.processEvents()
    col=_column_index("designation")
    first=_row(w,"line-1")
    second=_row(w,"line-2")
    w.table.setCurrentCell(first,col)
    QTest.mouseMove(w.table.viewport(),w.table.visualItemRect(w.table.item(second,col)).center())
    QApplication.processEvents()
    for row in (first,second):
        rect=w.table.visualItemRect(w.table.item(row,col))
        image=w.table.viewport().grab(rect).toImage()
        # The painted item contains actual blue background AND visible
        # near-white antialiased pixels from text glyphs.
        blue=white=0
        for y in range(3,image.height()-3):
            for x in range(2,min(75,image.width()-3)):
                c=image.pixelColor(x,y)
                if c.blue()>c.red()*1.4 and c.blue()>c.green()*1.1 and c.red()<100:
                    blue+=1
                if c.red()>220 and c.green()>220 and c.blue()>220:
                    white+=1
        assert blue>30,(row,blue,white)
        assert white>5,(row,blue,white)


def test_review_stale_lengths_requires_confirmation_and_verified_backup(
    qtbot,monkeypatch,tmp_path,
):
    from types import SimpleNamespace
    from PySide6.QtWidgets import QMessageBox
    from nl_project_2.persistence import migration
    class Stub(FakeCableService):
        def __init__(self):
            super().__init__()
            self.recalculated = []
            self._engine = SimpleNamespace(
                url=SimpleNamespace(database=str(tmp_path/"working.sqlite"))
            )
        def stale_length_report(self,pid):
            return () if self.recalculated else ({
                "segment_id":"seg-1","cable_line_id":"line-1",
                "designation":"1","stored_m":"7.6097",
                "new_m":"7.3209","delta_m":"-0.2888",
            },)
        def recalculate(self,**kwargs):
            self.recalculated.append(kwargs)
    (tmp_path/"working.sqlite").write_bytes(b"test-file")
    service=Stub()
    w=LinesWorkspace(service,FakeConstructor(),"project")
    qtbot.addWidget(w)
    decisions=[]
    monkeypatch.setattr(QMessageBox,"question",lambda *a,**kw:(
        decisions.append(a[2]) or QMessageBox.StandardButton.No
    ))
    monkeypatch.setattr(QMessageBox,"information",lambda *a,**k:None)
    copied=[]
    def fake_backup(path,folder):
        copied.append((path,folder))
        return SimpleNamespace(path=folder/"nlp.sqlite")
    monkeypatch.setattr(migration,"create_verified_backup",fake_backup)
    w._review_stale_lengths()
    assert not service.recalculated and not copied
    assert "7.61" in decisions[0] and "7.32" in decisions[0]
    monkeypatch.setattr(QMessageBox,"question",
        lambda *a,**kw:QMessageBox.StandardButton.Yes)
    w._review_stale_lengths()
    assert len(copied)==1
    assert service.recalculated==[{
        "project_id":"project","segment_ids":{"seg-1"},
    }]
    assert w.recalculate_stale_button.objectName()=="reviewStaleLengthsButton"
