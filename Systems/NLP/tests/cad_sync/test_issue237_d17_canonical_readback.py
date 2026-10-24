"""D17: evidence-proven readback with no automatic source switching."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest
from sqlalchemy import select, update
from test_issue237_d14_transit_quantity_reconciliation import _canonical_rows
from test_issue237_d16_quantity_prepare import _intent, _prepare

from nl_project_2.cables.service import CableService
from nl_project_2.cables.transit_canonical_readback import review_prepared_transit_for_canonical
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


def _review(database, approval, digest, *, confirmed=True):
    with database.engine.connect() as connection:
        return review_prepared_transit_for_canonical(
            connection, approval, expected_batch_sha256=digest, confirmed=confirmed
        )


def test_d17_readback_agrees_with_d15_and_preserves_every_legacy_row(database):
    intent = _intent(database)
    (receipt,) = _prepare(database, intent)
    ev = intent.approval.transit
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
    service = CableService(database.engine)
    with database.engine.connect() as connection:
        before = {table.name: _canonical_rows(connection, table, ev.project_id) for table in watched}
    result = service.review_prepared_transit_line(
        intent.approval, expected_batch_sha256=receipt.approved_sha256, confirmed=True
    )
    assert result.status == "VERIFIED_READBACK_ONLY"
    assert result.issues == ()
    assert result.prepared_automatic_m is not None
    assert result.prepared_final_m is not None
    assert result.authoritative_m is None
    assert result.conduit_quantity_m is None
    assert _review(database, intent.approval, receipt.approved_sha256) == result
    with database.engine.connect() as connection:
        after = {table.name: _canonical_rows(connection, table, ev.project_id) for table in watched}
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    assert after == before


@pytest.mark.parametrize(
    "problem,issue",
    [
        ("unconfirmed", "TRANSIT_D16_RECEIPT_NOT_CONFIRMED"),
        ("digest", "TRANSIT_D16_RECEIPT_NOT_CONFIRMED"),
        ("end_change", "TRANSIT_D15_APPROVAL_STALE"),
        ("line_version", "TRANSIT_D16_LINE_CHANGED"),
        ("segment_version", "TRANSIT_D16_ELECTRICAL_EDGE_CHANGED"),
        ("fact_version", "TRANSIT_D16_LENGTH_FACT_CHANGED"),
        ("manual", "TRANSIT_D16_MANUAL_OR_ADDITIONAL_CHANGED"),
        ("box", "TRANSIT_BOX_ACCEPTANCE_CHANGED"),
        ("stored_geometry", "LINE_STORED_SPANS_CHANGED"),
        ("snapshot", "TRANSIT_D16_BREAKDOWN_MISMATCH"),
    ],
)
def test_stale_or_tampered_d16_never_becomes_a_canonical_quantity(database, problem, issue):
    intent = _intent(database)
    (receipt,) = _prepare(database, intent)
    ev = intent.approval.transit
    approval = intent.approval
    digest = receipt.approved_sha256
    if problem == "unconfirmed":
        result = _review(database, approval, digest, confirmed=False)
    elif problem == "digest":
        result = _review(database, approval, "0" * 64)
    elif problem == "end_change":
        new_end = replace(approval.ends[0], evidence="different owner evidence")
        result = _review(database, replace(approval, ends=(new_end, approval.ends[1])), digest)
    else:
        with database.engine.begin() as connection:
            if problem == "line_version":
                connection.execute(
                    update(cable_line)
                    .where(cable_line.c.id == ev.cable_line_id)
                    .values(row_version=cable_line.c.row_version + 1)
                )
            elif problem == "segment_version":
                connection.execute(
                    update(cable_segment)
                    .where(cable_segment.c.id == ev.electrical_segment_id)
                    .values(row_version=cable_segment.c.row_version + 1)
                )
            elif problem in {"fact_version", "manual"}:
                vals = (
                    {"row_version": cable_length_fact.c.row_version + 1}
                    if problem == "fact_version"
                    else {"manual_full_length_m_decimal": "25.5"}
                )
                connection.execute(
                    update(cable_length_fact)
                    .where(cable_length_fact.c.cable_line_id == ev.cable_line_id)
                    .values(**vals)
                )
            elif problem == "box":
                box = connection.execute(
                    select(field_device).where(
                        field_device.c.project_id == ev.project_id,
                        field_device.c.block_kind == "EL_BOX_OUT_100x100",
                    )
                ).mappings().one()
                fields = dict(box["normalized_fields_json"])
                fields["CABLE_TRANSIT"] = ""
                connection.execute(
                    update(field_device)
                    .where(field_device.c.id == box["id"])
                    .values(normalized_fields_json=fields)
                )
            elif problem == "stored_geometry":
                connection.execute(
                    update(cable_transit_span)
                    .where(cable_transit_span.c.project_id == ev.project_id)
                    .values(geometry_m_decimal="999")
                )
            elif problem == "snapshot":
                connection.execute(
                    update(cable_transit_line_commit)
                    .where(cable_transit_line_commit.c.project_id == ev.project_id)
                    .values(calculation_snapshot_json={"source": "AUTOMATIC", "automatic_m": "999"})
                )
        result = _review(database, approval, digest)
    assert result.status == "REVIEW"
    assert issue in result.issues
    assert result.authoritative_m is None
    assert result.conduit_quantity_m is None


def test_legacy_canonical_conduit_collision_blocks_readback(database):
    intent = _intent(database)
    (receipt,) = _prepare(database, intent)
    pid = intent.approval.transit.project_id
    with database.engine.begin() as connection:
        connection.execute(
            conduit.insert().values(
                id=new_id(),
                project_id=pid,
                designation="001.PND25",
                conduit_type="ПНД25",
                lifecycle="ACTIVE",
            )
        )
    review = _review(database, intent.approval, receipt.approved_sha256)
    assert review.status == "REVIEW"
    assert "TRANSIT_CANONICAL_CONDUIT_BOUNDARY_UNPROVEN" in review.issues


def test_an_unprepared_line_cannot_acquire_canonical_authority(database):
    intent = _intent(database)
    review = _review(database, intent.approval, "0" * 64)
    assert review.status == "REVIEW"
    assert review.issues == ("TRANSIT_D16_RECEIPT_MISSING",)
    assert review.prepared_final_m is None


def test_exact_manual_override_is_visible_but_never_adopted_by_readback(database):
    intent = _intent(database)
    ev = intent.approval.transit
    with database.engine.begin() as connection:
        existing = connection.execute(
            select(cable_length_fact).where(
                cable_length_fact.c.cable_line_id == ev.cable_line_id
            )
        ).mappings().one()
        connection.execute(
            update(cable_length_fact).where(cable_length_fact.c.id == existing["id"])
            .values(
                manual_full_length_m_decimal="8.3",
                row_version=cable_length_fact.c.row_version + 1,
            )
        )
    intent = replace(
        intent,
        approval=replace(intent.approval, manual_full_m=Decimal("8.3")),
        expected_length_fact_row_version=intent.expected_length_fact_row_version + 1,
    )
    (receipt,) = _prepare(database, intent)
    review = _review(database, intent.approval, receipt.approved_sha256)
    assert review.status == "VERIFIED_READBACK_ONLY"
    assert review.prepared_final_m == Decimal("8.3")
    assert review.legacy_manual_m == Decimal("8.3")
    assert review.authoritative_m is None
