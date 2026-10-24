"""D19 current CAD observations vs accepted DWG lineage; always read-only."""

from __future__ import annotations

from dataclasses import replace

import pytest
from sqlalchemy import select, update
from test_issue237_d13_transit_store import _where
from test_issue237_d14_transit_quantity_reconciliation import _canonical_rows
from test_issue237_d16_quantity_prepare import _intent, _prepare
from nl_project_2.cables.transit_activation_readiness import TransitActivationRequest
from test_issue237_passive_physical_ownership import _batch, _box, _track
from test_issue237_physical_dali_storage import _change_observation

from nl_project_2.cables.service import CableService
from nl_project_2.persistence.schema import (
    cable_length_fact,
    cable_line,
    cable_segment,
    cable_transit_line_commit,
    cable_transit_route,
    cable_transit_span,
    conduit,
    conduit_segment_assignment,
    dwg_observation,
    dwg_scan,
    field_device,
)


def _batch_now():
    return _batch(_change_observation(_box(), "CABLE_TRANSIT", "401"), _track())


def _input(database, *, match_approved_terminal=False):
    intent = _intent(database)
    if match_approved_terminal:
        ev = intent.approval.transit
        loc = dict(ev.locations)
        loc[ev.route.spans[-1].finish] = _where(100, 0)
        intent = replace(intent, approval=replace(intent.approval, transit=replace(ev, locations=loc)))
    return intent.approval


def _check(database, approval, batch=None, *, confirmed=True):
    if batch is None:
        batch = _batch_now()
    return CableService(database.engine).review_current_dwg_transit(
        approval, current_batch=batch, confirmed=confirmed
    )


def test_no_current_scan_is_never_mistaken_for_live_dwg_attestation(database):
    approval = _input(database)
    review = CableService(database.engine).review_current_dwg_transit(
        approval, current_batch=None, confirmed=True
    )
    assert review.status == "REVIEW"
    assert review.issues == ("D19_CURRENT_CAD_SCAN_REQUIRED",)
    assert review.compared_input_sha256 is None
    assert not review.proves_live_dwg_freshness
    assert not review.authorizes_quantity_publication
    assert _check(database, approval, confirmed=False).status == "REVIEW"


def test_matching_historic_observations_only_prove_input_parity_not_live_freshness(database):
    approval = _input(database, match_approved_terminal=True)
    watched = (
        field_device,
        dwg_scan,
        dwg_observation,
        cable_segment,
        cable_length_fact,
        cable_transit_line_commit,
        cable_transit_route,
        cable_transit_span,
        conduit,
        conduit_segment_assignment,
        cable_line,
    )
    with database.engine.connect() as conn:
        before = {
            table.name: _canonical_rows(conn, table, approval.transit.project_id)
            for table in watched
        }
    first = _check(database, approval)
    assert first.status == "HISTORICAL_LINEAGE_MATCH_ONLY", first.issues
    assert first.issues == ()
    assert first.accepted_scan_id
    assert first.source_binding_id
    assert first.observed_handles == ("BOX-A", "TRACK-A")
    assert first.compared_input_sha256 == first.accepted_observation_sha256
    assert len(first.compared_input_sha256) == 64
    assert not first.proves_live_dwg_freshness
    assert not first.authorizes_quantity_publication
    assert first == _check(database, approval)
    with database.engine.connect() as conn:
        assert {
            table.name: _canonical_rows(conn, table, approval.transit.project_id)
            for table in watched
        } == before
        assert conn.exec_driver_sql("PRAGMA foreign_key_check").all() == []


def test_d13_reviewed_endpoint_geometry_conflicts_with_accepted_dwg_fixture(database):
    # D13 fixture explicitly approves terminal x=1200, but actual accepted
    # TRACK-A DWG insertion is x=100. This MUST NOT pass silently.
    approval = _input(database)
    review = _check(database, approval)
    assert review.status == "REVIEW"
    assert "D19_APPROVED_ENDPOINT_GEOMETRY_DIFFERS_DWG" in review.issues
    assert not review.authorizes_quantity_publication


@pytest.mark.parametrize(
    "changed,expected",
    [
        ("box_coordinate", "D19_APPROVED_BOX_GEOMETRY_DIFFERS_DWG"),
        ("box_transit", "D19_APPROVED_BOX_ATTRIBUTES_DIFFER"),
        ("track_coordinate", "D19_APPROVED_ENDPOINT_GEOMETRY_DIFFERS_DWG"),
        ("track_mount", "D19_APPROVED_ENDPOINT_GEOMETRY_DIFFERS_DWG"),
        ("missing_track", "D19_CURRENT_DWG_OWNER_MISSING"),
        ("wrong_document", "D19_CURRENT_DOCUMENT_BINDING_MISMATCH"),
        ("duplicate_handle", "D19_DUPLICATE_DWG_HANDLE"),
    ],
)
def test_mismatching_supplied_dwg_observations_never_authorize_source(
    database, changed, expected
):
    approval = _input(database, match_approved_terminal=True)
    box = _change_observation(_box(), "CABLE_TRANSIT", "401")
    track = _track()
    if changed == "box_coordinate":
        box = replace(box, x=999)
    elif changed == "box_transit":
        box = _change_observation(box, "CABLE_TRANSIT", "999")
    elif changed == "track_coordinate":
        track = replace(track, x=999)
    elif changed == "track_mount":
        track = _change_observation(track, "MOUNT_HEIGHT", "2200")
    elif changed == "missing_track":
        track = None
    elif changed == "duplicate_handle":
        track = replace(track, handle="BOX-A")
    batch = _batch(*(x for x in (box, track) if x is not None))
    if changed == "wrong_document":
        batch = _batch(box, track, name="another-project.dwg")
    review = _check(database, approval, batch)
    assert review.status == "REVIEW"
    assert expected in review.issues
    assert not review.proves_live_dwg_freshness
    assert not review.authorizes_quantity_publication


def test_missing_latest_accepted_scan_observation_blocks_even_when_input_matches(database):
    approval = _input(database, match_approved_terminal=True)
    with database.engine.begin() as conn:
        existing = conn.execute(
            select(dwg_observation).where(
                dwg_observation.c.project_id == approval.transit.project_id,
                dwg_observation.c.entity_handle == "TRACK-A",
            )
        ).mappings().one()
        conn.execute(
            update(dwg_observation)
            .where(dwg_observation.c.id == existing["id"])
            .values(entity_handle="TRACK-OBSOLETE")
        )
    review = _check(database, approval)
    assert review.status == "REVIEW"
    assert "D19_OWNER_ABSENT_FROM_LAST_ACCEPTED_SCAN" in review.issues
    assert "D19_DWG_SELECTED_OWNER_COVERAGE_INCOMPLETE" in review.issues


def test_stale_accepted_scan_becomes_review_even_if_current_input_matches(database):
    approval = _input(database, match_approved_terminal=True)
    with database.engine.begin() as conn:
        conn.execute(
            update(dwg_scan)
            .where(dwg_scan.c.project_id == approval.transit.project_id)
            .values(status="SUPERSEDED")
        )
    review = _check(database, approval)
    assert review.status == "REVIEW"
    assert "D19_ACCEPTED_SCAN_LINEAGE_MISSING" in review.issues


def test_unrelated_project_field_device_does_not_affect_owner_subset(database):
    approval = _input(database, match_approved_terminal=True)
    before = _check(database, approval)
    with database.engine.begin() as conn:
        conn.execute(
            field_device.insert().values(
                id="00000000-0000-4000-8000-00000000d019",
                project_id=approval.transit.project_id,
                block_kind="SOCKET_1",
                normalized_fields_json={"DEVICE_NAME": "unrelated"},
                lifecycle="ACTIVE",
            )
        )
    after = _check(database, approval)
    assert before == after


def test_d19_joins_d18_readiness_without_promoting_matched_cad_input(database):
    intent = _intent(database)
    (receipt,) = _prepare(database, intent)
    ev = intent.approval.transit
    service = CableService(database.engine)
    plan = service.plan_current_dwg_transit_revalidation(
        (TransitActivationRequest(intent.approval, receipt.approved_sha256),),
        selected_line_ids=frozenset({ev.cable_line_id}),
        supplied_batches={ev.cable_line_id: _batch_now()},
        confirmed=True,
    )
    assert plan.status == "BLOCKED"
    assert not plan.can_publish
    assert plan.activation_readiness.status == "BLOCKED"
    assert not plan.activation_readiness.can_publish
    assert len(plan.dwg_comparisons) == 1
    assert plan.dwg_comparisons[0].status == "REVIEW"
    assert "D19_APPROVED_ENDPOINT_GEOMETRY_DIFFERS_DWG" in plan.issues
    assert "D19_LIVE_CAD_BATCH_PROVENANCE_NOT_ATTESTED" in plan.issues
    assert "D18_CANONICAL_RECALCULATION_SOURCE_SWITCH_NOT_IMPLEMENTED" in plan.issues


def test_d19_composition_exactly_selected_batch_scope(database):
    intent = _intent(database)
    (receipt,) = _prepare(database, intent)
    ev = intent.approval.transit
    request = TransitActivationRequest(intent.approval, receipt.approved_sha256)
    service = CableService(database.engine)
    with pytest.raises(ValueError, match="D19_CAD_BATCH_SELECTION_NOT_EXACT"):
        service.plan_current_dwg_transit_revalidation(
            (request,),
            selected_line_ids=frozenset({ev.cable_line_id}),
            supplied_batches={"some-other-line": _batch_now()},
            confirmed=True,
        )


def test_matched_scan_never_overrides_existing_canonical_manual_length(database):
    intent = _intent(database)
    (receipt,) = _prepare(database, intent)
    ev = intent.approval.transit
    before = CableService(database.engine).effective_length(ev.project_id, ev.cable_line_id)
    plan = CableService(database.engine).plan_current_dwg_transit_revalidation(
        (TransitActivationRequest(intent.approval, receipt.approved_sha256),),
        selected_line_ids=frozenset({ev.cable_line_id}),
        supplied_batches={ev.cable_line_id: _batch_now()},
        confirmed=True,
    )
    after = CableService(database.engine).effective_length(ev.project_id, ev.cable_line_id)
    assert before == after
    assert plan.activation_readiness.lines[0].authoritative_cable_m is None
    assert not plan.can_publish
