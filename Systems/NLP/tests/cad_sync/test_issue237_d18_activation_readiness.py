"""D18 activation is fail-closed; no DWG proof or revisioned source switch."""

from __future__ import annotations

from sqlalchemy import select, update
from test_issue237_d14_transit_quantity_reconciliation import _canonical_rows
from test_issue237_d16_quantity_prepare import _intent, _prepare

import pytest

from nl_project_2.cables.service import CableService
from nl_project_2.cables.transit_activation_readiness import (
    TransitActivationRequest,
    plan_transit_activation,
)
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    cable_length_fact,
    cable_line,
    cable_segment,
    cable_transit_line_commit,
    cable_transit_route,
    cable_transit_span,
    conduit,
    conduit_segment_assignment,
    field_device,
)


def _ready_inputs(database):
    intent = _intent(database)
    (receipt,) = _prepare(database, intent)
    request = TransitActivationRequest(intent.approval, receipt.approved_sha256)
    selected = frozenset({intent.approval.transit.cable_line_id})
    return request, selected


def _plan(database, request, selected, *, confirmed=True):
    return CableService(database.engine).transit_activation_readiness(
        (request,), selected_line_ids=selected, confirmed=confirmed
    )


def test_d18_valid_d17_is_still_blocked_no_specs_or_sqlite_changes(database):
    request, selected = _ready_inputs(database)
    pid = request.approval.transit.project_id
    watched = (
        cable_line,
        cable_segment,
        cable_length_fact,
        cable_transit_route,
        cable_transit_span,
        cable_transit_line_commit,
        conduit,
        conduit_segment_assignment,
        field_device,
    )
    with database.engine.connect() as connection:
        before = {t.name: _canonical_rows(connection, t, pid) for t in watched}
    first = _plan(database, request, selected)
    second = _plan(database, request, selected)
    assert first == second
    assert first.status == "BLOCKED"
    assert first.can_publish is False
    assert first.selected_line_ids == tuple(selected)
    assert len(first.plan_sha256) == 64
    assert len(first.lines) == 1
    line = first.lines[0]
    assert line.status == "BLOCKED"
    assert len(line.project_source_sha256) == 64
    assert line.prepared_final_m is not None
    assert line.authoritative_cable_m is None
    assert line.authoritative_conduit_m is None
    assert "D18_CANONICAL_RECALCULATION_SOURCE_SWITCH_NOT_IMPLEMENTED" in line.issues
    assert "D18_CAD_LIVE_SCAN_AND_ROUNDTRIP_NOT_VERIFIED" in line.issues
    assert "D18_TERMINATION_SOURCE_FRESHNESS_NOT_VERIFIED" in line.issues
    assert "D18_ALL_QUANTITY_CONSUMERS_NOT_REVISION_AWARE" in line.issues
    assert "D18_D17_READBACK_REQUIRES_REVIEW" not in line.issues
    assert len(first.outstanding_consumers) >= 4
    assert first.outstanding_consumers == second.outstanding_consumers
    with database.engine.connect() as connection:
        assert {t.name: _canonical_rows(connection, t, pid) for t in watched} == before
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []


def test_accepted_project_fingerprint_changes_even_for_untracked_box_field(database):
    request, selected = _ready_inputs(database)
    before = _plan(database, request, selected)
    pid = request.approval.transit.project_id
    with database.engine.begin() as connection:
        box = (
            connection.execute(
                select(field_device).where(
                    field_device.c.project_id == pid,
                    field_device.c.block_kind == "EL_BOX_OUT_100x100",
                )
            )
            .mappings()
            .one()
        )
        fields = dict(box["normalized_fields_json"])
        fields["DEVICE_NAME"] = "Box changed in accepted Project"
        connection.execute(
            update(field_device)
            .where(field_device.c.id == box["id"])
            .values(
                normalized_fields_json=fields,
                row_version=field_device.c.row_version + 1,
            )
        )
    after = _plan(database, request, selected)
    assert after.status == "BLOCKED"
    assert after.lines[0].project_source_sha256 != before.lines[0].project_source_sha256
    assert after.plan_sha256 != before.plan_sha256
    assert after.lines[0].authoritative_cable_m is None


def test_changed_transit_box_membership_produces_readback_review(database):
    request, selected = _ready_inputs(database)
    pid = request.approval.transit.project_id
    with database.engine.begin() as connection:
        box = (
            connection.execute(
                select(field_device).where(
                    field_device.c.project_id == pid,
                    field_device.c.block_kind == "EL_BOX_OUT_100x100",
                )
            )
            .mappings()
            .one()
        )
        fields = dict(box["normalized_fields_json"])
        fields["CABLE_TRANSIT"] = ""
        connection.execute(
            update(field_device)
            .where(field_device.c.id == box["id"])
            .values(normalized_fields_json=fields)
        )
    plan = _plan(database, request, selected)
    assert "D18_D17_READBACK_REQUIRES_REVIEW" in plan.lines[0].issues
    assert "TRANSIT_BOX_ACCEPTANCE_CHANGED" in plan.lines[0].issues
    assert not plan.can_publish


def test_changed_canonical_length_fact_cannot_be_promoted(database):
    request, selected = _ready_inputs(database)
    line_id = next(iter(selected))
    with database.engine.begin() as connection:
        connection.execute(
            update(cable_length_fact)
            .where(cable_length_fact.c.cable_line_id == line_id)
            .values(row_version=cable_length_fact.c.row_version + 1)
        )
    plan = _plan(database, request, selected)
    assert "TRANSIT_D16_LENGTH_FACT_CHANGED" in plan.lines[0].issues
    assert "D18_D17_READBACK_REQUIRES_REVIEW" in plan.lines[0].issues
    assert plan.lines[0].authoritative_cable_m is None


@pytest.mark.parametrize("selection", ["none", "foreign", "duplicate"])
def test_wrong_selection_rejected_before_any_candidate_publication(database, selection):
    request, selected = _ready_inputs(database)
    if selection == "none":
        requests, ids = (request,), frozenset()
    elif selection == "foreign":
        requests, ids = (request,), frozenset({new_id()})
    else:
        requests, ids = (request, request), selected
    with pytest.raises(ValueError, match="D18_SELECTION_NOT_EXACT"):
        plan_transit_activation(
            database.engine,
            requests,
            selected_line_ids=ids,
            confirmed=True,
        )


def test_unconfirmed_and_wrong_batch_sha_always_block(database):
    request, selected = _ready_inputs(database)
    unconfirmed = _plan(database, request, selected, confirmed=False)
    assert unconfirmed.status == "BLOCKED"
    assert "TRANSIT_D16_RECEIPT_NOT_CONFIRMED" in unconfirmed.lines[0].issues
    altered = TransitActivationRequest(request.approval, "0" * 64)
    bad = _plan(database, altered, selected)
    assert bad.plan_sha256 != _plan(database, request, selected).plan_sha256
    assert "D18_D17_READBACK_REQUIRES_REVIEW" in bad.lines[0].issues


def test_unrelated_project_field_device_does_not_change_line_fingerprint(database):
    request, selected = _ready_inputs(database)
    before = _plan(database, request, selected)
    with database.engine.begin() as connection:
        connection.execute(
            field_device.insert().values(
                id=new_id(),
                project_id=request.approval.transit.project_id,
                block_kind="SOCKET_1",
                lifecycle="ACTIVE",
                normalized_fields_json={"DEVICE_NAME": "unrelated device"},
            )
        )
    after = _plan(database, request, selected)
    assert before.lines[0].project_source_sha256 == after.lines[0].project_source_sha256
    assert before.plan_sha256 == after.plan_sha256
