"""#237/#227 D4: Project type-aware universal outlet and immutable accepted ID.

Only temporary SQLite and synthetic CAD observations. No production writes.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from test_issue134_box_identity import _rs485_root
from test_issue237_project_bus_context import _insert_root, _project
from test_p0003_reconciliation import _observation

from nl_project_2.cad_contract import (
    BlockDefinitionMetadata,
    CadObservation,
    CadObservationBatch,
    issue_codes,
    load_contract,
)
from nl_project_2.cad_sync import ChangeClass, DwgSyncError, DwgSyncService
from nl_project_2.cad_sync.models import ScanProposal, SyncChange, SyncSummary
from nl_project_2.persistence.schema import field_device


def _outlet(*, handle="OUTLET-1", point_id="920.001", source=""):
    rule = load_contract().block("CABLE_OUTLET_BUS")
    assert rule is not None
    attrs = {tag: "" for tag in rule.required_definition_attributes}
    attrs.update(
        DEVICE_NAME="Universal bus outlet",
        BUILDING="House",
        ROOM="Hall",
        MOUNT_HEIGHT="300",
        BUS_POINT_ID=point_id,
        BUS_SOURCE=source,
        BUS_CABLE_TYPE="FTP 5e",
        BUS_MOUNT_WAY="По потолку",
    )
    return CadObservation.from_mapping(
        effective_name=rule.name,
        layer="BUS",
        raw_attributes=attrs,
        x=100,
        y=200,
        handle=handle,
        definition=BlockDefinitionMetadata(tuple(attrs)),
    )


def _batch(*items):
    return CadObservationBatch("outlet-gate-synthetic.dwg", items)


@pytest.mark.parametrize(
    ("kind", "source"),
    [("RS485", ""), ("DALI", "920.000"), ("KNX", "920.000")],
)
def test_universal_outlet_reads_own_project_bus_kind(database, kind, source):
    pid = _project(database)
    _insert_root(database, pid, designation="920", kind=kind)
    service = DwgSyncService(database.engine)
    batch = _batch(_outlet(source=source))
    validation = service._validator_for_project(pid).validate(batch)
    payload = validation.observations[0].read_payload
    assert payload is not None
    assert payload.bus_type == kind
    assert payload.bus_point_id == "920.001"
    assert payload.bus_id == "920"
    assert payload.cable_identity is None
    assert payload.cable_link_kind is None
    assert "BUS_TYPE_REQUIRED" not in issue_codes(validation.issues)
    assert "BUS_TYPE_CONFLICT" not in issue_codes(validation.issues)
    assert "BUS_ROOT_NOT_FOUND" not in issue_codes(validation.issues)
    assert "RS485_BUS_SOURCE_FORBIDDEN" not in issue_codes(validation.issues)
    preview = service.preview(project_id=pid, batch=batch)
    assert "BUS_TYPE_REQUIRED" not in issue_codes(preview.issues)


def test_universal_outlet_never_infers_kind_from_source(database):
    pid = _project(database)
    preview = DwgSyncService(database.engine).preview(
        project_id=pid, batch=_batch(_outlet(source="920.000"))
    )
    assert "BUS_TYPE_REQUIRED" in issue_codes(preview.issues)
    assert not preview.can_apply


def test_universal_outlet_rejects_dali_source_on_rs485_bus(database):
    pid = _project(database)
    _insert_root(database, pid, designation="920", kind="RS485")
    preview = DwgSyncService(database.engine).preview(
        project_id=pid, batch=_batch(_outlet(source="920.000"))
    )
    assert "RS485_BUS_SOURCE_FORBIDDEN" in issue_codes(preview.issues)
    assert not preview.can_apply


def test_dali_universal_outlet_can_reference_physical_box(database):
    pid = _project(database)
    _insert_root(database, pid, designation="920", kind="DALI")
    box_rule = load_contract().block("EL_BOX_OUT_100x100")
    assert box_rule is not None
    attrs = {tag: "" for tag in box_rule.required_definition_attributes}
    attrs.update(BOX_ID="BOX.023", BUS_ID="920", BUS_SOURCE="920.000")
    box = CadObservation.from_mapping(
        effective_name=box_rule.name,
        layer="BUS",
        raw_attributes=attrs,
        x=0,
        y=0,
        handle="BOX-A",
        definition=BlockDefinitionMetadata(tuple(attrs)),
    )
    validated = (
        DwgSyncService(database.engine)
        ._validator_for_project(pid)
        .validate(_batch(box, _outlet(source="BOX.023")))
    )
    assert "BUS_SOURCE_NOT_FOUND" not in issue_codes(validated.issues)
    assert "BUS_SOURCE_CROSS_BUS" not in issue_codes(validated.issues)
    assert "BUS_SOURCE_UNREACHABLE" not in issue_codes(validated.issues)
    assert validated.observations[1].read_payload.bus_point_id == "920.001"


@pytest.mark.parametrize("target", ["920.002", "920.004", "921.001"])
def test_existing_bus_identity_change_cannot_apply_even_structurally(database, target):
    pid = _project(database)
    sync = DwgSyncService(database.engine)
    fact = SyncChange(
        field_path="OUTLET-1:BUS_POINT_ID",
        handle="OUTLET-1",
        field="BUS_POINT_ID",
        baseline_value="920.001",
        project_value="920.001",
        dwg_value=target,
        change_class=ChangeClass.IDENTITY_COLLISION,
        reason="BUS_POINT_ID_RENUMBER_REQUIRES_ATTENTION",
        structural=True,
        detail_status="STRUCTURAL_IDENTITY_REVIEW",
    )
    proposal = ScanProposal(
        project_id=pid,
        batch=_batch(_outlet(point_id=target)),
        changes=(fact,),
        issues=(),
        summary=SyncSummary(),
        project_revision=0,
        binding_id=None,
    )
    with pytest.raises(DwgSyncError, match="BUS_POINT_ID_RENUMBER_REQUIRES_ATTENTION"):
        sync.apply_dwg_to_project(
            proposal,
            selected_paths={fact.field_path},
            confirmed=True,
            allow_structural=True,
        )


def test_preview_detects_real_accepted_bus_identity_change(database):
    """A committed RS-485 endpoint keeps its ID even if the DWG handle stays."""
    pid = _project(database)
    _rs485_root(database, pid)
    sync = DwgSyncService(database.engine)
    initial = _observation(
        "SENSOR_MSW",
        handle="OUTLET-1",
        attributes={"BUS_POINT_ID": "902.001"},
    )
    first = sync.preview(project_id=pid, batch=_batch(initial))
    assert first.can_apply, first.issues
    insertions = {
        item.field_path
        for item in first.changes
        if item.change_class is ChangeClass.NEW_DWG_INSERTION
    }
    assert insertions
    sync.apply_dwg_to_project(first, selected_paths=insertions, confirmed=True)
    with database.engine.connect() as connection:
        accepted = connection.execute(
            select(field_device).where(
                field_device.c.project_id == pid,
                field_device.c.entity_handle == "OUTLET-1",
                field_device.c.lifecycle == "ACTIVE",
            )
        ).mappings().one()
        assert accepted["normalized_fields_json"]["BUS_POINT_ID"] == "902.001"

    changed_dwg = _observation(
        "SENSOR_MSW",
        handle="OUTLET-1",
        attributes={"BUS_POINT_ID": "902.004"},
    )
    preview = sync.preview(project_id=pid, batch=_batch(changed_dwg))
    changed = [
        item
        for item in preview.changes
        if item.handle == "OUTLET-1" and item.field == "BUS_POINT_ID"
    ]
    assert len(changed) == 1, preview.issues
    assert changed[0].change_class is ChangeClass.IDENTITY_COLLISION
    assert changed[0].detail_status == "STRUCTURAL_IDENTITY_REVIEW"
    with pytest.raises(DwgSyncError, match="BUS_POINT_ID_RENUMBER_REQUIRES_ATTENTION"):
        sync.apply_dwg_to_project(
            preview,
            selected_paths={changed[0].field_path},
            confirmed=True,
            allow_structural=True,
        )
    with database.engine.connect() as connection:
        accepted_after = connection.execute(
            select(field_device.c.normalized_fields_json).where(
                field_device.c.id == accepted["id"]
            )
        ).scalar_one()
    assert accepted_after["BUS_POINT_ID"] == "902.001"
