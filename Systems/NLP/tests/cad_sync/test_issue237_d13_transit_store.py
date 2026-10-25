"""D13: approved physical spans in isolated SQLite, no electrical rewrites."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest
from sqlalchemy import func, select, update
from test_issue237_passive_physical_ownership import _accept, _batch, _box, _track
from test_issue237_physical_dali_storage import _change_observation
from test_issue237_project_bus_context import _insert_root, _project

from nl_project_2.cables.domain import CablePointInput
from nl_project_2.cad_sync import DwgSyncService
from nl_project_2.cad_sync.transit_physical import (
    ApprovedSpanRoute,
    TransitCalculationPolicy,
    VerifiedLocation,
)
from nl_project_2.cad_sync.transit_physical_store import (
    ApprovedTransitEvidence,
    TransitPersistenceError,
    approved_transit_sha256,
    persist_approved_transit,
    read_staged_transit,
)
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.migration import (
    HEAD_REVISION,
    PHYSICAL_DALI_GRAPH_REVISION,
    current_revision_read_only,
    downgrade_database,
)
from nl_project_2.persistence.schema import (
    cable_length_fact,
    cable_line,
    cable_segment,
    cable_transit_route,
    cable_transit_span,
    conduit,
    conduit_segment_assignment,
    field_device,
)


def _where(x, y, height=2500):
    return VerifiedLocation(
        CablePointInput.from_values(
            x_mm=x,
            y_mm=y,
            mount_height_mm=height,
            base_mark_mm=-250,
            room_height_m=3,
        ),
        evidence="synthetic-approved-Project-room-geometry",
        confirmed=True,
    )


def _accepted(database):
    pid = _project(database)
    _insert_root(database, pid)
    box = _change_observation(_box(), "CABLE_TRANSIT", "401")
    batch = _batch(box, _track())
    sync = DwgSyncService(database.engine)
    _accept(sync, pid, batch)
    proposal = sync.preview(project_id=pid, batch=batch)
    matches = [r for r in proposal.physical_transit_routes if r.cable_base == "401"]
    assert len(matches) == 1
    route = matches[0]
    assert route.status == "CANDIDATE", route.issue_codes
    assert len(route.spans) == 2
    with database.engine.connect() as conn:
        line_id = conn.scalar(
            select(cable_line.c.id).where(
                cable_line.c.project_id == pid,
                cable_line.c.designation == "401",
            )
        )
        seg = (
            conn.execute(select(cable_segment).where(cable_segment.c.cable_line_id == line_id))
            .mappings()
            .one()
        )
    locations = {
        route.spans[0].start: _where(0, 0),
        "BOX.023": _where(0, 0),
        route.spans[-1].finish: _where(1200, 0),
    }
    decisions = {
        part.physical_key: ApprovedSpanRoute(
            mount_way="В стене",
            gofra_type="ПНД25",
            gofra_color="чёрная",
            gofra_id=f"{index:03d}.PND25",
            confirmed=True,
        )
        for index, part in enumerate(route.spans, start=1)
    }
    ev = ApprovedTransitEvidence(
        project_id=pid,
        cable_line_id=line_id,
        electrical_segment_id=seg["id"],
        source_endpoint_id=seg["source_endpoint_id"],
        target_endpoint_id=seg["target_endpoint_id"],
        electrical_segment_row_version=seg["row_version"],
        route=route,
        locations=locations,
        decisions=decisions,
        policy=TransitCalculationPolicy(
            Decimal("0.05"),
            Decimal("0.10"),
            Decimal("1"),
            Decimal("3"),
            Decimal("0.3"),
            Decimal("0"),
        ),
        approval_evidence="explicit-reviewed-synthetic-geometry-v1",
    )
    return ev


def _rows(conn, table, pid):
    return tuple(
        tuple(row)
        for row in conn.execute(
            select(table).where(table.c.project_id == pid).order_by(table.c.id)
        ).all()
    )


def _count(conn, table):
    return conn.scalar(select(func.count()).select_from(table))


def test_explicit_sha_commit_persists_only_physical_spans_and_reopens(database):
    ev = _accepted(database)
    watched = (
        cable_segment,
        cable_line,
        cable_length_fact,
        conduit,
        conduit_segment_assignment,
        field_device,
    )
    with database.engine.connect() as conn:
        before = {table.name: _rows(conn, table, ev.project_id) for table in watched}
    receipt = persist_approved_transit(
        database.engine, ev, approved_sha256=approved_transit_sha256(ev), confirmed=True
    )
    assert receipt.new
    with database.engine.connect() as conn:
        assert _count(conn, cable_transit_route) == 1
        assert _count(conn, cable_transit_span) == 2
        assert conn.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        assert conn.exec_driver_sql("PRAGMA integrity_check").scalar_one() == "ok"
        rows = (
            conn.execute(
                select(cable_transit_span)
                .where(cable_transit_span.c.cable_transit_route_id == receipt.route_id)
                .order_by(cable_transit_span.c.ordinal)
            )
            .mappings()
            .all()
        )
        assert [row["start_boundary"] for row in rows] == [
            ev.route.spans[0].start,
            "BOX.023",
        ]
        assert [row["proposed_gofra_id"] for row in rows] == [
            "001.PND25",
            "002.PND25",
        ]
        assert all(row["mount_way"] == "В стене" for row in rows)
        assert all(before[table.name] == _rows(conn, table, ev.project_id) for table in watched)
        found = read_staged_transit(conn, project_id=ev.project_id)
        assert len(found) == 1
        assert found[0]["state"] == "STAGED_APPROVED"
    assert current_revision_read_only(database.path) == HEAD_REVISION
    again = persist_approved_transit(
        database.engine, ev, approved_sha256=receipt.approved_sha256, confirmed=True
    )
    assert not again.new
    assert again.route_id == receipt.route_id
    with database.engine.connect() as conn:
        assert _count(conn, cable_transit_span) == 2


def test_unconfirmed_wrong_digest_or_stale_edge_never_writes(database):
    ev = _accepted(database)
    expected = approved_transit_sha256(ev)
    with pytest.raises(TransitPersistenceError, match="TRANSIT_EXPLICIT_APPROVAL_REQUIRED"):
        persist_approved_transit(database.engine, ev, approved_sha256=expected, confirmed=False)
    with pytest.raises(TransitPersistenceError, match="TRANSIT_APPROVAL_DIGEST_MISMATCH"):
        persist_approved_transit(database.engine, ev, approved_sha256="0" * 64, confirmed=True)
    with pytest.raises(TransitPersistenceError, match="TRANSIT_CABLE_OWNER_NOT_FOUND"):
        wrong_project = replace(ev, project_id=new_id())
        persist_approved_transit(
            database.engine,
            wrong_project,
            approved_sha256=approved_transit_sha256(wrong_project),
            confirmed=True,
        )
    with database.engine.begin() as conn:
        conn.execute(
            update(cable_segment)
            .where(cable_segment.c.id == ev.electrical_segment_id)
            .values(row_version=cable_segment.c.row_version + 1)
        )
    with pytest.raises(TransitPersistenceError, match="TRANSIT_STALE_ELECTRICAL_EDGE"):
        persist_approved_transit(database.engine, ev, approved_sha256=expected, confirmed=True)
    with database.engine.connect() as conn:
        assert _count(conn, cable_transit_route) == 0
        assert _count(conn, cable_transit_span) == 0


def test_approved_route_cannot_be_silently_replaced(database):
    ev = _accepted(database)
    token = approved_transit_sha256(ev)
    persist_approved_transit(database.engine, ev, approved_sha256=token, confirmed=True)
    edited = replace(ev, approval_evidence="different review")
    with pytest.raises(TransitPersistenceError, match="TRANSIT_ACCEPTED_ROUTE_REQUIRES_REVIEW"):
        persist_approved_transit(
            database.engine,
            edited,
            approved_sha256=approved_transit_sha256(edited),
            confirmed=True,
        )
    with database.engine.connect() as conn:
        assert _count(conn, cable_transit_route) == 1
        assert _count(conn, cable_transit_span) == 2


def test_accepted_box_transit_owner_must_still_exist(database):
    ev = _accepted(database)
    with database.engine.begin() as conn:
        box = (
            conn.execute(
                select(field_device).where(
                    field_device.c.project_id == ev.project_id,
                    field_device.c.block_kind == "EL_BOX_OUT_100x100",
                )
            )
            .mappings()
            .one()
        )
        fields = dict(box["normalized_fields_json"])
        fields["CABLE_TRANSIT"] = ""
        conn.execute(
            update(field_device)
            .where(field_device.c.id == box["id"])
            .values(normalized_fields_json=fields)
        )
    with pytest.raises(TransitPersistenceError, match="TRANSIT_BOX_OWNER_NOT_ACCEPTED"):
        persist_approved_transit(
            database.engine,
            ev,
            approved_sha256=approved_transit_sha256(ev),
            confirmed=True,
        )


def test_existing_canonical_conduit_cannot_be_reused_by_staged_id(database):
    ev = _accepted(database)
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
    with pytest.raises(
        TransitPersistenceError, match="TRANSIT_CONDUIT_LEGACY_OWNERSHIP_REQUIRES_REVIEW"
    ):
        persist_approved_transit(
            database.engine,
            ev,
            approved_sha256=approved_transit_sha256(ev),
            confirmed=True,
        )
    with database.engine.connect() as conn:
        assert _count(conn, cable_transit_route) == 0
        assert _count(conn, cable_transit_span) == 0
        assert _count(conn, conduit) == 1


def test_sqlite_failure_on_second_span_rolls_back_entire_route(database):
    ev = _accepted(database)
    with database.engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TRIGGER d13_fail_second_span "
            "BEFORE INSERT ON cable_transit_span "
            "WHEN NEW.ordinal = 2 "
            "BEGIN SELECT RAISE(ABORT, 'forced D13 failure'); END"
        )
    with pytest.raises(Exception, match="forced D13 failure"):
        persist_approved_transit(
            database.engine,
            ev,
            approved_sha256=approved_transit_sha256(ev),
            confirmed=True,
        )
    with database.engine.connect() as conn:
        assert _count(conn, cable_transit_route) == 0
        assert _count(conn, cable_transit_span) == 0
        assert conn.exec_driver_sql("PRAGMA foreign_key_check").all() == []


def test_populated_downgrade_refuses_discarding_accepted_staged_facts(database, tmp_path):
    ev = _accepted(database)
    persist_approved_transit(
        database.engine,
        ev,
        approved_sha256=approved_transit_sha256(ev),
        confirmed=True,
    )
    database.engine.dispose()
    with pytest.raises(RuntimeError, match="TRANSIT_PHYSICAL_DOWNGRADE_REQUIRES_EXPLICIT_REVIEW"):
        downgrade_database(
            database.path,
            tmp_path / "verified-backups",
            target=PHYSICAL_DALI_GRAPH_REVISION,
        )
    assert current_revision_read_only(database.path) == HEAD_REVISION
    with database.engine.connect() as conn:
        assert _count(conn, cable_transit_route) == 1
        assert _count(conn, cable_transit_span) == 2
