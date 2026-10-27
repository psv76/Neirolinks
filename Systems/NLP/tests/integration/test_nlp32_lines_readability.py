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


def test_bulk_action_buttons_are_laid_out_below_search_not_floating(qtbot):
    from PySide6.QtCore import QPoint, QRect
    from PySide6.QtWidgets import QApplication, QPushButton
    for width in (1200, 1680):
        w=LinesWorkspace(FakeCableService(),FakeConstructor(),"project")
        qtbot.addWidget(w)
        w.resize(width,850)
        w.show()
        QApplication.processEvents()
        buttons=[
            x for x in w.findChildren(QPushButton)
            if x.text() in ("Изменить выбранные строки","Заполнить вниз (Ctrl+D)")
            or x.text().startswith("Массово:")
        ]
        assert len(buttons)>=6
        def box(widget):
            return QRect(widget.mapToGlobal(QPoint(0,0)),widget.size())
        search=box(w.search)
        filter_box=box(w.system_filter)
        table_box=box(w.table)
        for button in buttons:
            assert button.isVisible(),button.text()
            b=box(button)
            assert b.top()>=filter_box.bottom(),(width,button.text(),b,filter_box)
            assert b.bottom()<table_box.top(),(width,button.text(),b,table_box)
            assert not b.intersects(search),(width,button.text(),b,search)
        rects=[box(button) for button in buttons]
        for a in range(len(rects)):
            for b in range(a+1,len(rects)):
                assert not rects[a].intersects(rects[b]),(
                    width,buttons[a].text(),buttons[b].text(),rects[a],rects[b]
                )
        w.close()


def test_human_bus_purpose_and_source_are_visible_in_main_grid(qtbot,monkeypatch):
    from copy import deepcopy
    from nl_project_2.presentation.lines_workspace import _column_index
    from PySide6.QtWidgets import QApplication
    class BusCards:
        def journal_cards(self, _pid):
            return [{
                "id": "bus-903", "designation": "903", "network_kind": "BUS", "load_type": "BUS",
                "load_name": "Датчик MSW · Преобразователь WB-M1W2",
                "load_name_tooltip": "903.001: Датчик MSW\n903.002: Преобразователь WB-M1W2",
                "source_board": "ВРУ-20",
                "source_interface": "WB-21 / RS485-1",
                "source_tooltip": "Щит: ВРУ-20\nКонтроллер / порт: WB-21 / RS485-1",
                "board": "ВРУ-20 · WB-21 / RS485-1",
                "room_names": "Прихожая, Постирочная",
                "room_markers": (
                    {"id": "room-1", "name": "Прихожая", "color": "#AED6F1"},
                    {"id": "room-2", "name": "Постирочная", "color": "#F8D7E8"},
                ),
                "building_names": "Дом_2",
                "unresolved_room_names": (),
                "system_kind": "RS485",
                "cable_type": "FTP 5e",
                "mount_way": "По полу",
                "gofra_id": "MIXED",
                "conduit_count": 2,
                "effective_m": "15",
                "length_mode": "Автоматическая",
                "length_explanation": "Из физических участков шины",
                "known_segment_m": "15",
                "incomplete_segments": 0,
            }]
        def journal_topology(self, _pid, bus_id):
            assert bus_id == "bus-903"
            return {
                "edges": [{
                    "segment_id": "903-a",
                    "depth": 0,
                    "source": {"label":"WB-21 / RS485-1"},
                    "target": {
                        "label": "903.001","description":"Датчик MSW",
                        "room_names":"Прихожая","building_names":"Дом_2",
                        "point_kind":"SENSOR_MSW","room_unresolved":False,
                    },
                    "mount_way":"По полу","gofra_id":"310.PP20",
                    "calculation_status":"READY","cable_length_m":"5",
                }],
            }
    w=LinesWorkspace(FakeCableService(),FakeConstructor(),"project",bus_service=BusCards())
    qtbot.addWidget(w)
    w.show()
    QApplication.processEvents()
    row=_row(w,"bus-903")
    source=w.table.item(row,_column_index("board"))
    purpose=w.table.item(row,_column_index("load_name"))
    destination=w.table.item(row,_column_index("room_names"))
    assert source.text().startswith("ВРУ-20")
    assert "RS485-1" in source.toolTip()
    assert "Преобразователь WB-M1W2" in purpose.text()
    assert "903.001: Датчик MSW" in purpose.toolTip()
    assert "Прихожая" in destination.text()
    w._expand_line_tree(row,"bus-903")
    child=w.table.item(row+1,_column_index("load_name"))
    assert child.text()=="Датчик MSW"
    idx=w.board_filter.findData("ВРУ-20")
    assert idx > 0
    w.board_filter.setCurrentIndex(idx)
    assert not w.table.isRowHidden(row)
    assert w.table.isRowHidden(_row(w,"line-1"))
    # Search matches complete DWG LOAD_NAME tooltip, not only truncated header.
    w.search.setText("903.002: Преобразователь WB-M1W2")
    assert not w.table.isRowHidden(row)
    from nl_project_2.presentation.room_presentation import ROOM_MARKERS_ROLE
    assert len(destination.data(ROOM_MARKERS_ROLE)) == 2
    assert destination.data(ROOM_MARKERS_ROLE)[0]["color"] == "#AED6F1"
    from PySide6.QtWidgets import QInputDialog
    changed=[]
    def record(**kwargs):
        changed.append(kwargs)
    monkeypatch.setattr(w.buses, "set_bus_display_name", record, raising=False)
    monkeypatch.setattr(QInputDialog, "getText",lambda *args,**kwargs: ("Датчики первого этажа",True))
    w.search.clear()
    w._table_item_double_clicked(purpose)
    assert changed == [{"project_id":"project","bus_id":"bus-903","display_name":"Датчики первого этажа"}]
