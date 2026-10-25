"""D15 previews use pure spans once and leave all persisted quantities intact."""

from dataclasses import replace
from decimal import Decimal

import pytest
from sqlalchemy import select, update
from test_issue237_d14_transit_quantity_reconciliation import _canonical_rows, _stage

from nl_project_2.cables.length_policy import ActualCableEnd, LengthPolicy
from nl_project_2.cables.transit_line_preview import (
    TransitLineApproval,
    VerifiedLineEnd,
    preview_transit_line,
    transit_line_approval_sha256,
)
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    cable_length_fact,
    cable_segment,
    cable_transit_route,
    cable_transit_span,
    conduit,
    conduit_segment_assignment,
)


def _approval(database):
    ev = _stage(database)
    return TransitLineApproval(
        ev,
        (
            VerifiedLineEnd(
                ev.source_endpoint_id,
                ActualCableEnd("physical-feed", "BOARD"),
                "reviewed physical board cable",
            ),
            VerifiedLineEnd(
                ev.target_endpoint_id,
                ActualCableEnd("physical-load", "ENDPOINT"),
                "reviewed external track termination",
            ),
        ),
        LengthPolicy(),
        Decimal("0.4"),
        None,
        "reviewed entire single-edge line",
    )


def _preview(database, approval, **kwargs):
    with database.engine.connect() as conn:
        return preview_transit_line(
            conn,
            approval,
            approved_sha256=kwargs.get("sha", transit_line_approval_sha256(approval)),
            confirmed=kwargs.get("confirmed", True),
        )


def test_one_line_geometry_reserves_rounding_and_readonly(database):
    approval = _approval(database)
    watched = (
        cable_segment,
        cable_length_fact,
        conduit,
        conduit_segment_assignment,
        cable_transit_route,
        cable_transit_span,
    )
    with database.engine.connect() as conn:
        before = {t.name: _canonical_rows(conn, t, approval.transit.project_id) for t in watched}
    result = _preview(database, approval)
    assert result.status == "APPROVED_PREVIEW_ONLY"
    q = result.quantity
    assert q.geometry_m == Decimal("1.2")
    assert q.routed_m == Decimal("1.38")
    assert q.board_outputs_m == 3
    assert q.box_outputs_m == 0  # continuous BOX is not an electrical splice
    assert q.endpoint_outputs_m == Decimal("0.3")
    assert q.additional_m == Decimal("0.4")
    assert q.raw_m == Decimal("5.08")
    assert q.final_m == 6
    assert result.authoritative_cable_m is result.authoritative_conduit_m is None
    assert _preview(database, approval) == result
    with database.engine.connect() as conn:
        assert {
            t.name: _canonical_rows(conn, t, approval.transit.project_id) for t in watched
        } == before


@pytest.mark.parametrize("quantum,expected", [("0.5", "5.5"), ("0.1", "5.1")])
def test_line_quantum(database, quantum, expected):
    a = _approval(database)
    a = replace(a, policy=replace(a.policy, rounding_step_m=Decimal(quantum)))
    assert _preview(database, a).quantity.final_m == Decimal(expected)


def test_full_manual_replaces_and_per_end_override_is_not_a_transit_reserve(database):
    a = _approval(database)
    a = replace(
        a,
        ends=(
            replace(a.ends[0], end=ActualCableEnd("physical-feed", "ENDPOINT", Decimal("0.7"))),
            a.ends[1],
        ),
    )
    q = _preview(database, a).quantity
    assert q.board_outputs_m == 0
    assert q.endpoint_outputs_m == 1
    assert q.final_m == 3
    a = replace(a, manual_full_m=Decimal("0.13"))
    assert _preview(database, a).quantity.final_m == Decimal("0.13")


@pytest.mark.parametrize("kind", ["missing", "duplicate", "transit", "no_evidence"])
def test_unproven_end_inventory_rejected_even_with_manual(database, kind):
    a = _approval(database)
    ends = a.ends
    if kind == "missing":
        ends = ends[:1]
    elif kind == "duplicate":
        ends = (ends[0], replace(ends[1], end=ends[0].end))
    elif kind == "transit":
        ends = (*ends, VerifiedLineEnd("BOX.023", ActualCableEnd("fake", "EL_BOX"), "fake"))
    else:
        ends = (replace(ends[0], evidence=""), ends[1])
    result = _preview(database, replace(a, ends=ends, manual_full_m=Decimal(99)))
    assert result.quantity is None
    assert "LINE_REAL_ENDS_UNPROVEN" in result.issues


def test_sha_and_explicit_confirmation_bind_all_line_inputs(database):
    a = _approval(database)
    assert _preview(database, a, confirmed=False).quantity is None
    old = transit_line_approval_sha256(a)
    changed = replace(a, additional_m=Decimal(9))
    assert _preview(database, changed, sha=old).issues == ("LINE_APPROVAL_REQUIRED",)
    changed = replace(a, transit=replace(a.transit, approval_evidence="different"))
    assert "LINE_TRANSIT_APPROVAL_CHANGED" in _preview(database, changed).issues


@pytest.mark.parametrize("field,value", [("geometry_m_decimal", "9"), ("gofra_color", "red")])
def test_stored_span_tamper_rejected(database, field, value):
    a = _approval(database)
    with database.engine.begin() as conn:
        part = conn.scalar(
            select(cable_transit_span.c.id).where(
                cable_transit_span.c.project_id == a.transit.project_id
            )
        )
        conn.execute(
            update(cable_transit_span)
            .where(cable_transit_span.c.id == part)
            .values(**{field: value})
        )
    assert _preview(database, a).quantity is None


def test_stale_edge_rejected(database):
    a = _approval(database)
    with database.engine.begin() as conn:
        conn.execute(
            update(cable_segment)
            .where(cable_segment.c.id == a.transit.electrical_segment_id)
            .values(row_version=99)
        )
    result = _preview(database, a)
    assert result.quantity is None
    assert "TRANSIT_ELECTRICAL_EDGE_CHANGED" in result.issues


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "0"])
def test_invalid_rounding_rejected(database, value):
    a = _approval(database)
    a = replace(a, policy=replace(a.policy, rounding_step_m=Decimal(value)))
    assert _preview(database, a).issues == ("LINE_NUMERIC_EVIDENCE_INVALID",)


def test_canonical_conduit_collision_blocks_line_preview(database):
    a = _approval(database)
    with database.engine.begin() as conn:
        conn.execute(
            conduit.insert().values(
                id=new_id(),
                project_id=a.transit.project_id,
                designation="001.PND25",
                conduit_type="ПНД25",
                lifecycle="ACTIVE",
            )
        )
    result = _preview(database, a)
    assert result.quantity is None
    assert "TRANSIT_CANONICAL_CONDUIT_BOUNDARY_UNPROVEN" in result.issues


def test_d13_per_edge_preview_total_is_never_used(database):
    a = _approval(database)
    with database.engine.begin() as conn:
        conn.execute(
            update(cable_transit_route)
            .where(cable_transit_route.c.project_id == a.transit.project_id)
            .values(preview_cable_length_m_decimal="999999")
        )
    assert _preview(database, a).quantity.final_m == 6


def test_additional_electrical_edge_blocks_partial_line_total(database):
    a = _approval(database)
    with database.engine.begin() as conn:
        original = dict(
            conn.execute(
                select(cable_segment).where(cable_segment.c.id == a.transit.electrical_segment_id)
            )
            .mappings()
            .one()
        )
        original["id"] = new_id()
        original["source_endpoint_id"], original["target_endpoint_id"] = (
            original["target_endpoint_id"],
            original["source_endpoint_id"],
        )
        conn.execute(cable_segment.insert().values(**original))
    result = _preview(database, a)
    assert result.quantity is None
    assert "TRANSIT_LINE_COVERAGE_REQUIRES_REVIEW" in result.issues


def test_bus_conduit_collision_blocks_preview(database):
    from nl_project_2.persistence.schema import bus, bus_endpoint, bus_segment, field_device

    a = _approval(database)
    pid = a.transit.project_id
    with database.engine.begin() as conn:
        bus_id = conn.scalar(
            select(bus.c.id).where(bus.c.project_id == pid, bus.c.designation == "905")
        )
        owner = conn.scalar(
            select(field_device.c.id).where(
                field_device.c.project_id == pid, field_device.c.block_kind == "TRACK_DALI"
            )
        )
        endpoint = new_id()
        conn.execute(
            bus_endpoint.insert().values(
                id=endpoint,
                project_id=pid,
                bus_id=bus_id,
                endpoint_kind="FIELD_DEVICE",
                field_device_id=owner,
                endpoint_role="DEVICE",
                address="905.999",
            )
        )
        conn.execute(
            bus_segment.insert().values(
                id=new_id(),
                project_id=pid,
                bus_id=bus_id,
                source_endpoint_id=None,
                target_endpoint_id=endpoint,
                connection_kind="CABLE",
                gofra_id="001.PND25",
            )
        )
    result = _preview(database, a)
    assert result.quantity is None
    assert "TRANSIT_BUS_CONDUIT_BOUNDARY_UNPROVEN" in result.issues
