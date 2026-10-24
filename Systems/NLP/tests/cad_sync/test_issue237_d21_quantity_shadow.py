"""D21 request-scoped quantity shadow / simulated specification, never publication."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select, update
from test_issue237_d14_transit_quantity_reconciliation import _canonical_rows
from test_issue237_d16_quantity_prepare import _intent, _prepare

from nl_project_2.cables.service import CableService
from nl_project_2.cables.transit_activation_readiness import TransitActivationRequest
from nl_project_2.cables.transit_source_selection import (
    make_shadow_selection,
    selection_sha256,
)
from nl_project_2.persistence.schema import (
    cable_length_fact,
    cable_line,
    cable_segment,
    cable_transit_line_commit,
    cable_transit_route,
    conduit,
    conduit_segment_assignment,
    specification_override,
)
from nl_project_2.specification.service import SpecificationService


def _context(database):
    intent = _intent(database)
    (receipt,) = _prepare(database, intent)
    req = TransitActivationRequest(intent.approval, receipt.approved_sha256)
    ids = frozenset({intent.approval.transit.cable_line_id})
    return req, ids


def _selection(database, request, selected, mode):
    return CableService(database.engine).preview_transit_quantity_sources(
        (request,),
        selected_line_ids=selected,
        mode=mode,
        expected_selection_sha256=selection_sha256((request,), selected, mode=mode),
        confirmed=True,
    )


def test_d21_shadow_and_revoke_are_reversible_without_changing_any_legacy_data(database):
    request, ids = _context(database)
    pid = request.approval.transit.project_id
    watched = (
        cable_line,
        cable_segment,
        cable_length_fact,
        cable_transit_route,
        cable_transit_line_commit,
        conduit,
        conduit_segment_assignment,
        specification_override,
    )
    spec = SpecificationService(database.engine)
    with database.engine.connect() as conn:
        original = {t.name: _canonical_rows(conn, t, pid) for t in watched}
    canonical_before = spec.build(pid)
    shadow = _selection(database, request, ids, "PREPARED_SHADOW")
    assert shadow.status == "SHADOW_PREVIEW_ONLY"
    assert not shadow.can_publish
    assert len(shadow.selection_sha256) == 64
    line = shadow.lines[0]
    assert line.status == "SHADOW_PREVIEW_ONLY"
    assert line.preview_source == "PREPARED_SHADOW"
    assert line.prepared_candidate_m == line.preview_effective_m
    assert line.prepared_candidate_m is not None
    assert not line.authorizes_publication

    projected = spec.preview_transit_source_specification(
        pid,
        (request,),
        selected_line_ids=ids,
        mode="PREPARED_SHADOW",
        expected_selection_sha256=shadow.selection_sha256,
        confirmed=True,
    )
    assert projected["preview_only"] and not projected["can_publish"]
    assert projected["selection"] == shadow
    sources = [
        source
        for source in projected["sources"]
        if source.source_kind == "CABLE_LINE" and source.source_id in ids and source.unit == "m"
    ]
    assert len(sources) == 1
    assert sources[0].quantity == line.preview_effective_m
    assert "NOT FOR PROCUREMENT" in sources[0].trace

    reverted = _selection(database, request, ids, "LEGACY_ONLY")
    assert reverted.status == "LEGACY_ONLY"
    assert reverted.lines[0].preview_source == "LEGACY"
    assert reverted.lines[0].prepared_candidate_m is None
    revoked_spec = spec.preview_transit_source_specification(
        pid,
        (request,),
        selected_line_ids=ids,
        mode="LEGACY_ONLY",
        expected_selection_sha256=reverted.selection_sha256,
        confirmed=True,
    )
    assert revoked_spec["sources"] == revoked_spec["baseline_sources"]
    assert spec.build(pid) == canonical_before
    with database.engine.connect() as conn:
        assert {t.name: _canonical_rows(conn, t, pid) for t in watched} == original
        assert conn.exec_driver_sql("PRAGMA foreign_key_check").all() == []


def test_d21_stale_current_owner_fails_closed_and_simulated_spec_does_not_change(database):
    request, ids = _context(database)
    pid = request.approval.transit.project_id
    with database.engine.begin() as conn:
        conn.execute(
            update(cable_line)
            .where(cable_line.c.id == request.approval.transit.cable_line_id)
            .values(row_version=cable_line.c.row_version + 1)
        )
    shadow = _selection(database, request, ids, "PREPARED_SHADOW")
    assert shadow.status == "REVIEW"
    assert "TRANSIT_D16_LINE_CHANGED" in shadow.lines[0].issues
    assert shadow.lines[0].preview_source == "LEGACY"
    projection = SpecificationService(database.engine).preview_transit_source_specification(
        pid,
        (request,),
        selected_line_ids=ids,
        mode="PREPARED_SHADOW",
        expected_selection_sha256=shadow.selection_sha256,
        confirmed=True,
    )
    assert projection["sources"] == projection["baseline_sources"]
    assert not projection["can_publish"]


def test_d21_selection_must_be_exact_confirmed_and_sha_bound(database):
    req, ids = _context(database)
    service = CableService(database.engine)
    digest = selection_sha256((req,), ids, mode="PREPARED_SHADOW")
    with pytest.raises(ValueError, match="D21_EXPLICIT_SELECTION_APPROVAL_REQUIRED"):
        service.preview_transit_quantity_sources(
            (req,),
            selected_line_ids=ids,
            mode="PREPARED_SHADOW",
            expected_selection_sha256="0" * 64,
            confirmed=True,
        )
    with pytest.raises(ValueError, match="D21_EXPLICIT_SELECTION_APPROVAL_REQUIRED"):
        service.preview_transit_quantity_sources(
            (req,),
            selected_line_ids=ids,
            mode="PREPARED_SHADOW",
            expected_selection_sha256=digest,
            confirmed=False,
        )
    with pytest.raises(ValueError, match="D21_SELECTION_NOT_EXACT"):
        selection_sha256((req, req), ids, mode="PREPARED_SHADOW")
    with pytest.raises(ValueError, match="D21_SELECTION_NOT_EXACT"):
        selection_sha256((req,), frozenset(), mode="LEGACY_ONLY")
    with pytest.raises(ValueError, match="D21_SHADOW_MODE_UNKNOWN"):
        selection_sha256((req,), ids, mode="PRODUCTION")  # type: ignore[arg-type]


def test_d21_multi_line_preview_is_all_or_nothing_when_one_owner_stale():
    req1 = SimpleNamespace(
        approval=SimpleNamespace(
            transit=SimpleNamespace(project_id="project-A", cable_line_id="line-1")
        ),
        d16_batch_sha256="a" * 64,
    )
    req2 = SimpleNamespace(
        approval=SimpleNamespace(
            transit=SimpleNamespace(project_id="project-A", cable_line_id="line-2")
        ),
        d16_batch_sha256="b" * 64,
    )
    requests = (req1, req2)
    ids = frozenset({"line-1", "line-2"})
    token = selection_sha256(requests, ids, mode="PREPARED_SHADOW")
    plan = make_shadow_selection(
        requests,
        selected_line_ids=ids,
        mode="PREPARED_SHADOW",
        expected_selection_sha256=token,
        confirmed=True,
        legacy_effective_m={"line-1": Decimal("10"), "line-2": Decimal("20")},
        readbacks={
            "line-1": SimpleNamespace(
                status="VERIFIED_READBACK_ONLY", prepared_final_m=Decimal("17"), issues=()
            ),
            "line-2": SimpleNamespace(
                status="REVIEW", prepared_final_m=Decimal("18"), issues=("STALE",)
            ),
        },
    )
    assert plan.status == "REVIEW"
    assert all(line.preview_source == "LEGACY" for line in plan.lines)
    assert [line.preview_effective_m for line in plan.lines] == [Decimal("10"), Decimal("20")]
    assert not plan.can_publish


def test_d21_manual_value_remains_unchanged_after_preview_and_revoke(database):
    intent = _intent(database)
    ev = intent.approval.transit
    with database.engine.begin() as conn:
        fact = (
            conn.execute(
                select(cable_length_fact).where(
                    cable_length_fact.c.cable_line_id == ev.cable_line_id
                )
            )
            .mappings()
            .one()
        )
        conn.execute(
            update(cable_length_fact)
            .where(cable_length_fact.c.id == fact["id"])
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
    request = TransitActivationRequest(intent.approval, receipt.approved_sha256)
    ids = frozenset({ev.cable_line_id})
    selection = _selection(database, request, ids, "PREPARED_SHADOW")
    assert selection.lines[0].prepared_candidate_m == Decimal("8.3")
    assert selection.lines[0].legacy_effective_m == Decimal("8.3")
    reverted = _selection(database, request, ids, "LEGACY_ONLY")
    assert reverted.lines[0].preview_effective_m == Decimal("8.3")
    with database.engine.connect() as conn:
        unchanged = (
            conn.execute(
                select(cable_length_fact).where(
                    cable_length_fact.c.cable_line_id == ev.cable_line_id
                )
            )
            .mappings()
            .one()
        )
        assert unchanged["manual_full_length_m_decimal"] == "8.3"
