"""#237/#227 D4: Project type-aware universal outlet and immutable accepted ID.

Only temporary SQLite and synthetic CAD observations. No production writes.
"""

from __future__ import annotations

import pytest
from test_issue237_project_bus_context import _insert_root, _project

from nl_project_2.cad_contract import (
    BlockDefinitionMetadata,
    CadObservation,
    CadObservationBatch,
    issue_codes,
    load_contract,
)
from nl_project_2.cad_sync import ChangeClass, DwgSyncError, DwgSyncService
from nl_project_2.cad_sync.models import ScanProposal, SyncChange, SyncSummary


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
