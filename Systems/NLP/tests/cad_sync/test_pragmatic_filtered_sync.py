from dataclasses import replace
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QMessageBox
from sqlalchemy import select, update
from test_filtered_sync_authority import DOC, applicable, socket, state

from nl_project_2.cad_contract import CadObservation, CadObservationBatch
from nl_project_2.cad_sync import DwgSyncService
from nl_project_2.cad_sync.bridge import ActiveDocumentInfo, BridgeError, LayerFilteredRead
from nl_project_2.cad_sync.service import FullScanRequired, StaleProposalError
from nl_project_2.objects.models import ProjectCard
from nl_project_2.objects.runtime import ApplicationRuntime
from nl_project_2.objects.service import ObjectService
from nl_project_2.objects.time_tracking import WorkTimeService
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import dwg_document_binding, field_device, project
from nl_project_2.presentation import object_workspace as ui


class Port:
    def __init__(self, batch):
        self.batch = batch
        self.census = tuple(sorted((o.handle, o.layer) for o in batch.observations))
        self.calls = []
        self.census_error = False
        self.on_census = None

    def inspect_active_document(self, **kwargs):
        self.calls.append("inspect")
        return ActiveDocumentInfo(DOC, "c7f.dwg", False, True, 0)

    def read_observations(self, request):
        self.calls.append("full")
        return self.batch

    def read_insert_census(self, request):
        self.calls.append("census")
        if self.on_census:
            self.on_census()
        if self.census_error:
            raise BridgeError("COM unavailable")
        return self.census

    def read_layer_filtered_observations(self, request, *, tracked_handles):
        self.calls.append("filtered")
        from nl_project_2.cad_contract.layer_names import parse_working_layer_name

        selected = tuple(
            o
            for o in self.batch.observations
            if o.handle in tracked_handles or parse_working_layer_name(o.layer) is not None
        )
        batch = replace(
            self.batch,
            observations=selected,
            source_metadata={
                "scan_mode": "FILTERED_FINGERPRINT",
                "layer_filter_applied": True,
                "scan_is_complete_for_reconciliation": False,
                "skipped_block_references": len(self.batch.observations) - len(selected),
            },
        )
        return LayerFilteredRead(
            batch,
            self.census,
            tuple(
                h
                for h, layer in self.census
                if h in tracked_handles and parse_working_layer_name(layer) is None
            ),
            tuple(sorted(set(tracked_handles) - {h for h, _ in self.census})),
        )


@pytest.fixture
def workflow(database):
    objects = ObjectService(database.engine)
    project_id = objects.create_project(ProjectCard(name="C7F", project_code="C7F"))
    initial = CadObservationBatch(DOC, (socket(), socket("A2", "101.02")))
    base_service = DwgSyncService(database.engine)
    proposal = base_service.preview(project_id=project_id, batch=initial)
    base_service.apply_dwg_to_project(proposal, selected_paths=applicable(proposal), confirmed=True)
    foreign = CadObservation.from_mapping(
        effective_name="FURNITURE", layer="ARCH", handle="F1", raw_attributes={}, x=0, y=0
    )
    port = Port(
        replace(initial, observations=(*initial.observations, socket("A3", "101.03"), foreign))
    )
    return project_id, DwgSyncService(database.engine, port), port


def checked_preview(workflow):
    project_id, service, _ = workflow
    return service.scan_active(project_id=project_id, expected_identity=DOC, verify_census=True)


def test_opt_in_requires_visible_full_retry_without_promoting_subset(database, workflow):
    project_id, service, port = workflow
    before = state(database)
    with pytest.raises(FullScanRequired, match="полное сканирование"):
        service.scan_active(project_id=project_id, expected_identity=DOC, prefer_filtered=True)
    assert port.calls == ["filtered"]
    assert state(database) == before
    proposal = checked_preview(workflow)
    service.apply_dwg_to_project(proposal, selected_paths={"A3:$"}, confirmed=True)
    assert port.calls == ["filtered", "full", "census", "census"]
    with database.engine.connect() as connection:
        assert set(connection.scalars(select(field_device.c.entity_handle))) == {"A1", "A2", "A3"}


@pytest.mark.parametrize("fault", ["layer", "deleted", "added", "error"])
def test_apply_lightweight_recheck_blocks_stale_or_failed_census(database, workflow, fault):
    _, service, port = workflow
    proposal = checked_preview(workflow)
    before = state(database)
    if fault == "layer":
        port.census = tuple((h, "ARCH" if h == "A1" else layer) for h, layer in port.census)
    elif fault == "deleted":
        port.census = tuple(row for row in port.census if row[0] != "A1")
    elif fault == "added":
        port.census += (("FF", "100_New"),)
    else:
        port.census_error = True
    with pytest.raises(StaleProposalError, match="полное сканирование"):
        service.apply_dwg_to_project(proposal, selected_paths={"A3:$"}, confirmed=True)
    assert state(database) == before
    assert port.calls.count("full") == 1


@pytest.mark.parametrize("fault", ["binding", "revision"])
def test_binding_and_revision_rechecked_in_write_transaction(database, workflow, fault):
    project_id, service, port = workflow
    proposal = checked_preview(workflow)

    def change_after_census():
        with database.engine.begin() as connection:
            if fault == "binding":
                connection.execute(
                    update(dwg_document_binding)
                    .where(dwg_document_binding.c.id == proposal.binding_id)
                    .values(row_version=dwg_document_binding.c.row_version + 1)
                )
            else:
                connection.execute(
                    update(project)
                    .where(project.c.id == project_id)
                    .values(project_revision=project.c.project_revision + 1)
                )

    port.on_census = change_after_census
    with pytest.raises(StaleProposalError, match="Project/binding changed"):
        service.apply_dwg_to_project(proposal, selected_paths={"A3:$"}, confirmed=True)
    with database.engine.connect() as connection:
        assert "A3" not in set(connection.scalars(select(field_device.c.entity_handle)))


def test_attribute_only_change_is_explicitly_accepted_residual_risk(workflow):
    _, service, port = workflow
    proposal = checked_preview(workflow)
    port.batch = replace(
        port.batch, observations=tuple(replace(o, x=999) for o in port.batch.observations)
    )
    service.apply_dwg_to_project(proposal, selected_paths={"A3:$"}, confirmed=True)
    assert port.calls == ["full", "census", "census"]  # No attribute/fingerprint reread.


def test_default_full_path_does_not_use_new_mode(workflow):
    project_id, service, port = workflow
    proposal = service.scan_active(project_id=project_id, expected_identity=DOC)
    service.apply_dwg_to_project(proposal, selected_paths={"A3:$"}, confirmed=True)
    assert port.calls == ["full"]


def test_changed_full_scan_is_rejected_before_preview_becomes_applicable(workflow):
    _, _, port = workflow
    port.census = ()
    with pytest.raises(StaleProposalError):
        checked_preview(workflow)


class ImmediateController(QObject):
    completed = Signal(object)
    failed = Signal(str, str)
    cancelled = Signal()
    progress = Signal(object)

    def __init__(self, manager, parent):
        super().__init__(parent)

    def cancel(self):
        self.cancelled.emit()

    def start(self, snapshot, worker):
        try:
            value = worker(snapshot, SimpleNamespace(checkpoint=lambda: None), self.progress.emit)
        except Exception as exc:
            self.failed.emit(type(exc).__name__, str(exc))
        else:
            self.completed.emit(SimpleNamespace(value=value))


@pytest.mark.parametrize("action", ["apply", "stale", "switch_project", "cancel_fallback"])
def test_real_ui_scan_fallback_preview_apply(database, workflow, qtbot, monkeypatch, action):
    project_id, service, port = workflow
    runtime = ApplicationRuntime(
        database,
        ObjectService(database.engine),
        WorkTimeService(database.engine, new_id()),
        dwg_sync=service,
        background_operations=object(),
    )
    widget = ui.ObjectWorkspace(runtime)
    qtbot.addWidget(widget)
    widget.open_project(project_id)
    assert not widget.filtered_sync_checkbox.isChecked()
    widget.filtered_sync_checkbox.setChecked(True)
    monkeypatch.setattr(ui, "BackgroundOperationController", ImmediateController)
    questions, warnings, dialogs = [], [], []

    def question(*args):
        questions.append(args[2])
        return (
            QMessageBox.StandardButton.Yes
            if len(questions) == 1 and action != "cancel_fallback"
            else QMessageBox.StandardButton.No
        )

    monkeypatch.setattr(QMessageBox, "question", question)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    original_exec = ui.DwgSyncPreviewDialog.exec

    def exec_preview(dialog):
        dialogs.append(dialog)

        def choose():
            dialog.select_all_button.click()
            if action == "stale":
                port.census = ()
            if action == "switch_project":
                runtime.current_project_id = "different-project"
            dialog.apply_button.click()

        QTimer.singleShot(0, choose)
        return original_exec(dialog)

    monkeypatch.setattr(ui.DwgSyncPreviewDialog, "exec", exec_preview)
    before = state(database)
    widget._sync_dwg()
    assert questions and "полное сканирование" in questions[0].lower()
    if action == "apply":
        assert dialogs
        assert port.calls == ["inspect", "filtered", "full", "census", "census"]
        with database.engine.connect() as connection:
            assert "A3" in set(connection.scalars(select(field_device.c.entity_handle)))
    else:
        assert state(database) == before
        if action == "stale":
            assert len(questions) == 2
        if action == "switch_project":
            assert warnings and "проект" in warnings[-1].lower()
        if action == "cancel_fallback":
            assert port.calls == ["inspect", "filtered"]


@pytest.mark.parametrize("change", ["moved", "deleted"])
def test_full_fallback_distinguishes_layer_mismatch_from_true_absence(workflow, change):
    from nl_project_2.cad_sync import ChangeClass

    project_id, service, port = workflow
    observations = port.batch.observations
    port.batch = replace(
        port.batch,
        observations=(
            tuple(replace(o, layer="ARCH") if o.handle == "A1" else o for o in observations)
            if change == "moved"
            else tuple(o for o in observations if o.handle != "A1")
        ),
    )
    port.census = tuple(sorted((o.handle, o.layer) for o in port.batch.observations))
    with pytest.raises(FullScanRequired):
        service.scan_active(project_id=project_id, expected_identity=DOC, prefer_filtered=True)
    proposal = checked_preview(workflow)
    assert (
        any(
            c.handle == "A1" and c.change_class is ChangeClass.MISSING_DWG_INSERTION
            for c in proposal.changes
        )
    ) is (change == "deleted")
    assert "layer_filter_applied" not in proposal.batch.source_metadata


def test_stale_census_blocks_writeback_before_any_write(workflow):
    _, service, port = workflow
    proposal = checked_preview(workflow)
    port.census = ()
    port.write_attributes = lambda **kwargs: pytest.fail("stale write-back reached CAD")
    with pytest.raises(StaleProposalError, match="Handle/Layer"):
        service.write_project_to_dwg(proposal, selected_paths={"A1:DEVICE_NAME"}, confirmed=True)
