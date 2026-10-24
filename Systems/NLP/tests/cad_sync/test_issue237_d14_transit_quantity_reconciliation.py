"""D14: staged physical lengths/conduits never leak into canonical quantities."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select, update
from test_issue237_d13_transit_store import _accepted
from nl_project_2.cad_sync.transit_physical_store import (
    approved_transit_sha256,
    persist_approved_transit,
)
from nl_project_2.cables.service import CableService
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    cable_length_fact,
    cable_segment,
    cable_transit_span,
    conduit,
    conduit_segment_assignment,
    field_device,
)


def _stage(database):
    evidence = _accepted(database)
    persist_approved_transit(
        database.engine,
        evidence,
        approved_sha256=approved_transit_sha256(evidence),
        confirmed=True,
    )
    return evidence


def _canonical_rows(connection, table, project_id):
    return tuple(
        tuple(row) for row in connection.execute(
            select(table).where(table.c.project_id == project_id).order_by(table.c.id)
        ).all()
    )


def test_reconciliation_is_readonly_and_never_replaces_authoritative_length(database):
    ev = _stage(database)
    cable_service = CableService(database.engine)
    watched = (cable_segment, cable_length_fact, conduit, conduit_segment_assignment)
    with database.engine.connect() as conn:
        original = {
            table.name: _canonical_rows(conn, table, ev.project_id) for table in watched
        }
    before_cards = cable_service.line_cards(ev.project_id)
    before_canonical = {
        card["id"]: (card["effective_m"], card["automatic_m"], card["conduit_count"])
        for card in before_cards
    }
    shadow = cable_service.transit_reconciliation(ev.project_id)
    assert shadow["mode"] == "READ_ONLY_NO_CANONICAL_QUANTITY_CHANGE"
    assert shadow["review_count"] == 0
    assert len(shadow["routes"]) == 1
    entry = shadow["routes"][0]
    assert entry["status"] == "STAGED_READ_ONLY"
    assert entry["issues"] == ()
    assert entry["staged_span_count"] == 2
    assert Decimal(entry["staged_geometry_m"]) >= 0
    assert Decimal(entry["staged_corrected_m"]) >= Decimal(entry["staged_geometry_m"])
    assert entry["authoritative_cable_m"] is None
    assert entry["authoritative_conduit_m"] is None
    assert len(shadow["conduits"]) == 2
    assert all(pipe["status"] == "CANDIDATE_ONLY" for pipe in shadow["conduits"])
    assert Decimal(shadow["uncommitted_unique_conduit_geometry_m"]) >= 0
    topology = cable_service.topology(ev.project_id, ev.cable_line_id)
    assert topology["transit_reconciliation"][0]["route_id"] == entry["route_id"]
    assert len(cable_service.project_route_breakdown(ev.project_id)["staged_transit_review"]["routes"]) == 1
    after_cards = cable_service.line_cards(ev.project_id)
    assert after_cards[0]["staged_transit_review"] or any(
        card["staged_transit_review"] for card in after_cards
    )
    assert {
        card["id"]: (card["effective_m"], card["automatic_m"], card["conduit_count"])
        for card in after_cards
    } == before_canonical
    with database.engine.connect() as conn:
        assert {
            table.name: _canonical_rows(conn, table, ev.project_id) for table in watched
        } == original
        assert conn.exec_driver_sql("PRAGMA foreign_key_check").all() == []


def test_stale_approved_electrical_edge_does_not_produce_candidate_quantity(database):
    ev = _stage(database)
    with database.engine.begin() as conn:
        conn.execute(
            update(cable_segment)
            .where(cable_segment.c.id == ev.electrical_segment_id)
            .values(row_version=cable_segment.c.row_version + 1)
        )
    preview = CableService(database.engine).transit_reconciliation(ev.project_id)
    assert preview["review_count"] == 1
    assert "TRANSIT_ELECTRICAL_EDGE_CHANGED" in preview["routes"][0]["issues"]
    assert preview["conduits"]
    assert all(item["status"] == "REVIEW" for item in preview["conduits"])
    assert preview["uncommitted_unique_conduit_geometry_m"] == "0"


def test_removed_box_owner_invalidates_its_staged_span(database):
    ev = _stage(database)
    with database.engine.begin() as conn:
        box = conn.execute(
            select(field_device).where(
                field_device.c.project_id == ev.project_id,
                field_device.c.block_kind == "EL_BOX_OUT_100x100",
            )
        ).mappings().one()
        fields = dict(box["normalized_fields_json"])
        fields["CABLE_TRANSIT"] = ""
        conn.execute(
            update(field_device)
            .where(field_device.c.id == box["id"])
            .values(normalized_fields_json=fields)
        )
    preview = CableService(database.engine).transit_reconciliation(ev.project_id)
    assert "TRANSIT_BOX_ACCEPTANCE_CHANGED" in preview["routes"][0]["issues"]
    assert all(pipe["status"] == "REVIEW" for pipe in preview["conduits"])


def test_mixed_boundaries_same_gofra_are_not_merged_or_counted(database):
    ev = _stage(database)
    with database.engine.begin() as conn:
        parts = list(conn.execute(
            select(cable_transit_span)
            .where(cable_transit_span.c.project_id == ev.project_id)
            .order_by(cable_transit_span.c.ordinal)
        ).mappings())
        conn.execute(
            update(cable_transit_span)
            .where(cable_transit_span.c.id == parts[1]["id"])
            .values(proposed_gofra_id=parts[0]["proposed_gofra_id"])
        )
    preview = CableService(database.engine).transit_reconciliation(ev.project_id)
    assert preview["review_count"] == 1
    assert "TRANSIT_CONDUIT_BOUNDARY_CONFLICT" in preview["routes"][0]["issues"]
    assert preview["conduits"][0]["status"] == "REVIEW"
    assert preview["conduits"][0]["unique_geometry_m"] is None


def test_existing_canonical_conduit_collides_fail_closed(database):
    ev = _stage(database)
    with database.engine.begin() as conn:
        conn.execute(
            conduit.insert().values(
                id=new_id(),
                project_id=ev.project_id,
                designation="001.PND25",
                conduit_type="ПНД25",
                lifecycle="ACTIVE",
            )
        )
    preview = CableService(database.engine).transit_reconciliation(ev.project_id)
    assert "TRANSIT_CANONICAL_CONDUIT_BOUNDARY_UNPROVEN" in preview["routes"][0]["issues"]
    matching = [item for item in preview["conduits"] if item["designation"] == "001.PND25"]
    assert len(matching) == 1 and matching[0]["status"] == "REVIEW"
    assert preview["routes"][0]["authoritative_cable_m"] is None
    assert preview["routes"][0]["authoritative_conduit_m"] is None


def test_no_staged_routes_leave_all_normal_canonical_quantities_untouched(database):
    ev = _accepted(database)
    cable_service = CableService(database.engine)
    preview = cable_service.transit_reconciliation(ev.project_id)
    assert preview == {
        "routes": (),
        "conduits": (),
        "uncommitted_unique_conduit_geometry_m": "0",
        "review_count": 0,
        "mode": "READ_ONLY_NO_CANONICAL_QUANTITY_CHANGE",
    }
    assert cable_service.topology(ev.project_id, ev.cable_line_id)["transit_reconciliation"] == ()
    assert all(not card["staged_transit_review"] for card in cable_service.line_cards(ev.project_id))
