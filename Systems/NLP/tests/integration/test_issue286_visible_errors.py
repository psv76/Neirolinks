"""Live-visible import failure with explicit outbound DWG permission."""

from types import SimpleNamespace

from PySide6.QtWidgets import QMessageBox

from nl_project_2.presentation.object_workspace import DwgSyncResolutionDialog


def _proposal():
    return SimpleNamespace(
        batch=SimpleNamespace(observations=()),
        changes=(),
        issues=(),
    )


def _plan(*, inbound=(), outbound=()):
    return SimpleNamespace(
        import_paths=frozenset(inbound),
        write_paths=frozenset(outbound),
        conflicts=(),
        problems=(),
        blocked_lines=(),
        missing_bus_roots=("903", "904"),
    )


def test_failed_apply_is_first_and_untruncated_above_bus_warnings(qtbot):
    failure = (
        "DwgSyncError: Распределительная коробка BOX.024 ещё не принята "
        "в Project. Линия 114 → 125; все изменения откатились."
    )
    dialog = DwgSyncResolutionDialog(
        _proposal(),
        _plan(inbound={"858E5:CABLE_TYPE"}, outbound={"858E5:GOFRA_ID"}),
        runtime_errors=(failure,),
    )
    qtbot.addWidget(dialog)
    assert "BOX.024" in dialog.apply_error_summary.toPlainText()
    assert "НЕ ВЫПОЛНЕН" in dialog.apply_error_summary.toPlainText()
    assert dialog.table.item(0, 0).text() == "Импорт DWG → Project"
    assert failure in dialog.table.item(0, 4).text()
    assert dialog.table.cellWidget(dialog.table.rowCount() - 1, 5).isEnabled() is False
    assert dialog.selected_write_paths() == set()


def test_outbound_requires_explicit_confirmation_and_no_is_default(qtbot, monkeypatch):
    dialog = DwgSyncResolutionDialog(
        _proposal(),
        _plan(outbound={"858E5:GOFRA_ID"}),
    )
    qtbot.addWidget(dialog)
    seen = []

    def ask(_parent, _title, _message, _buttons, default):
        seen.append(default)
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", ask)
    row = dialog.table.rowCount() - 1
    button = dialog.table.cellWidget(row, 5)
    assert button.isEnabled()
    button.click()
    assert dialog.selected_write_paths() == set()
    assert seen == [QMessageBox.StandardButton.No]
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args: QMessageBox.StandardButton.Yes,
    )
    button.click()
    assert dialog.selected_write_paths() == {"858E5:GOFRA_ID"}
    assert not button.isEnabled()
