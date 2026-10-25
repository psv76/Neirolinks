from dataclasses import replace
from types import SimpleNamespace

import pytest
from sqlalchemy import event, select

from nl_project_2.cad_contract import (
    BlockDefinitionMetadata,
    CadObservation,
    CadObservationBatch,
    load_contract,
)
from nl_project_2.cad_sync import ChangeClass, DwgSyncError, DwgSyncService
from nl_project_2.cad_sync.reconciliation_safety import is_authoritative_scan_metadata
from nl_project_2.objects.models import ProjectCard
from nl_project_2.objects.service import ObjectService
from nl_project_2.persistence.schema import dwg_scan, field_device

ALLOWED = [
    {},
    {"adapter_version": "1.1", "dbmod": 0, "custom": {"value": None}},
    {"layer_filter_applied": False},
    {"scan_is_complete_for_reconciliation": True},
    {
        "layer_filter_applied": False,
        "scan_is_complete_for_reconciliation": True,
        "skipped_block_references": 0,
    },
]
BLOCKED = [
    {"layer_filter_applied": True},
    {"scan_is_complete_for_reconciliation": False},
    {
        "layer_filter_applied": True,
        "scan_is_complete_for_reconciliation": False,
        "skipped_block_references": 0,
    },
    {"layer_filter_applied": True, "scan_is_complete_for_reconciliation": True},
    {"layer_filter_applied": False, "scan_is_complete_for_reconciliation": False},
    *[
        {key: value}
        for key in ("layer_filter_applied", "scan_is_complete_for_reconciliation")
        for value in ("false", "true", 0, 1, None, [], {}, 0.0, 1.0)
    ],
    *[{"skipped_block_references": value} for value in (1, -1, "0", None, False, 0.0)],
    None,
    [],
    "complete",
]


@pytest.mark.parametrize("metadata", ALLOWED)
def test_legacy_and_explicit_full_metadata_allowed(metadata):
    assert is_authoritative_scan_metadata(metadata) is True


@pytest.mark.parametrize("metadata", BLOCKED)
def test_partial_invalid_or_contradictory_metadata_blocked(metadata):
    assert is_authoritative_scan_metadata(metadata) is False


def fail_if_called(*args, **kwargs):
    pytest.fail("Non-authoritative scan reached validation, reconciliation or database access")


@pytest.mark.parametrize("metadata", BLOCKED)
def test_preview_rejects_before_validation_or_missing_classification(monkeypatch, metadata):
    service = DwgSyncService(SimpleNamespace(connect=fail_if_called, begin=fail_if_called))
    monkeypatch.setattr(service, "_validator_for_project", fail_if_called)
    batch = CadObservationBatch("fixture", (), metadata)
    with pytest.raises(DwgSyncError, match="SCAN_NOT_AUTHORITATIVE.*full unfiltered"):
        service.preview(project_id="project", batch=batch, progress=fail_if_called)


@pytest.mark.parametrize("metadata", BLOCKED)
def test_forged_apply_rejects_before_selection_or_database(metadata):
    service = DwgSyncService(SimpleNamespace(connect=fail_if_called, begin=fail_if_called))
    forged = SimpleNamespace(batch=CadObservationBatch("fixture", (), metadata))

    def selected_paths():
        fail_if_called()
        yield "forged:$"

    with pytest.raises(DwgSyncError, match="SCAN_NOT_AUTHORITATIVE"):
        service.apply_dwg_to_project(forged, selected_paths=selected_paths(), confirmed=True)


def socket():
    rule = load_contract().block("SOCKET_IN")
    attrs = dict.fromkeys(rule.required_definition_attributes, "")
    attrs.update(
        DEVICE_NAME="Socket",
        BUILDING="Building",
        ROOM="Room",
        MOUNT_HEIGHT="300",
        CABLE_ID="101.01",
        CABLE_TYPE="NYM",
        BOARD="B.01",
        LOAD_TYPE="SOCKET_LIVING_LOW",
        LOAD_NAME="Sockets",
        MOUNT_WAY="По полу",
        GOFRA_TYPE="ПНД25",
        GOFRA_COLOR="Черный",
        GOFRA_ID="001.PND25",
    )
    return CadObservation.from_mapping(
        effective_name="SOCKET_IN",
        layer="POWER",
        raw_attributes=attrs,
        x=10,
        y=20,
        handle="A1",
        definition=BlockDefinitionMetadata(tuple(attrs), False),
    )


@pytest.mark.parametrize("metadata", ALLOWED)
def test_full_import_repeat_missing_and_metadata_persistence_unchanged(database, metadata):
    project_id = ObjectService(database.engine).create_project(
        ProjectCard(name="C6", project_code="C6")
    )
    service = DwgSyncService(database.engine)
    batch = CadObservationBatch("fixture-C6", (socket(),), metadata)
    proposal = service.preview(project_id=project_id, batch=batch)
    paths = {
        c.field_path for c in proposal.changes if c.change_class is ChangeClass.NEW_DWG_INSERTION
    }
    assert paths
    service.apply_dwg_to_project(proposal, selected_paths=paths, confirmed=True)
    with database.engine.connect() as connection:
        assert connection.scalar(select(dwg_scan.c.document_facts_json)) == metadata
        before = list(connection.execute(select(field_device)).mappings())

    first = service.preview(project_id=project_id, batch=batch)
    second = service.preview(project_id=project_id, batch=batch)
    assert first.changes == second.changes
    assert all(
        c.change_class
        not in {
            ChangeClass.NEW_DWG_INSERTION,
            ChangeClass.DWG_CHANGED,
            ChangeClass.MISSING_DWG_INSERTION,
        }
        for c in second.changes
    )
    missing = service.preview(project_id=project_id, batch=replace(batch, observations=()))
    assert any(c.change_class is ChangeClass.MISSING_DWG_INSERTION for c in missing.changes)

    # A crafted proposal carrying the former valid selection must be stopped before ANY SQL.
    partial_batch = replace(
        batch,
        observations=(),
        source_metadata={
            "layer_filter_applied": True,
            "scan_is_complete_for_reconciliation": False,
            "skipped_block_references": 0,
        },
    )
    forged = replace(proposal, batch=partial_batch)
    event.listen(database.engine, "before_cursor_execute", fail_if_called)
    try:
        with pytest.raises(DwgSyncError, match="SCAN_NOT_AUTHORITATIVE"):
            service.preview(project_id=project_id, batch=partial_batch)
        with pytest.raises(DwgSyncError, match="SCAN_NOT_AUTHORITATIVE"):
            service.apply_dwg_to_project(forged, selected_paths=paths, confirmed=True)
        # Also recheck metadata mutated after a successful preview.
        mutated = replace(proposal, batch=replace(batch, source_metadata={}))
        mutated.batch.source_metadata["scan_is_complete_for_reconciliation"] = False
        with pytest.raises(DwgSyncError, match="SCAN_NOT_AUTHORITATIVE"):
            service.apply_dwg_to_project(mutated, selected_paths=paths, confirmed=True)
    finally:
        event.remove(database.engine, "before_cursor_execute", fail_if_called)
    with database.engine.connect() as connection:
        assert list(connection.execute(select(field_device)).mappings()) == before
