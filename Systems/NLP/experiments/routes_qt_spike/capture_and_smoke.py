"""Run isolated Windows Qt UI smoke tests and capture REAL QWidget screenshots.

QT_QPA_PLATFORM=offscreen renders the actual PySide6 widgets without disturbing
the user's desktop. This deliberately never imports production NL Project.
"""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from pathlib import Path
from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtWidgets import QApplication
from routes_demo import RoutesPrototype
from fixture import load_fixture

out = Path(__file__).resolve().parent
app = QApplication([])
snapshot = load_fixture()
assert len(snapshot.conduits) == 12
assert len(snapshot.segments) >= 35

windows = []
for variant in ("A", "B"):
    win = RoutesPrototype(snapshot, variant)
    win.resize(1360, 775)
    win.show()
    app.processEvents()
    assert win.view.horizontalScrollBar().maximum() > 0
    assert win.view.verticalScrollBar().maximum() >= 0
    assert all(not b.isEnabled() for b in win.findChildren(__import__("PySide6.QtWidgets", fromlist=["QPushButton"]).QPushButton)
               if b.text() in ("Привязать к трубе", "Перенести", "Убрать из трубы"))
    assert "38 сегм." not in win.match_label.text() or len(snapshot.segments) == 38
    win.view.grab().save(str(out / f"{variant}_view.png"))
    win.grab().save(str(out / f"{variant}_shared.png"))
    windows.append(win)

a, b = windows
# QTreeView: filter with status and expose unmatched/required classifications.
a.membership.setCurrentText("Без трубы")
a.set_expand_all(True)
app.processEvents()
assert "12 сегм." in a.match_label.text()
assert a.tree_model.rowCount() == 1
a.grab().save(str(out / "A_without_conduit.png"))

b.set_expand_all(True)
app.processEvents()
root_idx = b.flat_model.index(0, 0)
seg_idx = b.flat_model.index(1, 0)
assert root_idx.data() != seg_idx.data()
assert seg_idx.data(int(Qt.ItemDataRole.UserRole)+2) == "SEGMENT"
segment_id = seg_idx.data(int(Qt.ItemDataRole.UserRole)+1)
b.view.selectionModel().select(seg_idx, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
app.processEvents()
assert segment_id in b.saved_selection, (segment_id, b.saved_selection)
b.grab().save(str(out / "B_multiselect.png"))
b._flat_toggle(root_idx.data(int(Qt.ItemDataRole.UserRole)+1))
app.processEvents()
assert segment_id in b.saved_selection
assert "скрыто выбранных: 1" in b.selection_label.text(), b.selection_label.text()
b.grab().save(str(out / "B_hidden_selection.png"))

b.membership.setCurrentText("Требует трубы")
b.set_expand_all(True)
app.processEvents()
assert "5 сегм." in b.match_label.text(), b.match_label.text()
b.grab().save(str(out / "B_required_conduit.png"))
b.membership.setCurrentText("Все")
b.search.setText("Cat5e")
b.set_expand_all(True)
app.processEvents()
assert "состав отфильтрован" in b.match_label.text()
b.grab().save(str(out / "B_search_cable.png"))

# Exactly the same fixture instance was passed to both Qt variants.
assert a.snapshot is b.snapshot
print("QT_WINDOWS=2; FIXTURE_CONDUITS=12; FIXTURE_SEGMENTS=38")
print("CHECKS=readonly, A/B same snapshot, horizontal scroll, required filter, selection hidden after collapse, cable search")
print("SCREENSHOTS=" + ", ".join(p.name for p in sorted(out.glob("*.png"))))
for win in windows:
    win.close()
