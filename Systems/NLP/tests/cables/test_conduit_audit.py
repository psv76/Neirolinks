"""Q03 read-only diagnostics for ordinary+BUS membership of one physical Conduit."""

from __future__ import annotations

import pytest

from nl_project_2.cables.conduit_audit import audit_conduit_memberships
from nl_project_2.cables.physical_conduit import PhysicalBoundary, PhysicalSpan
from nl_project_2.cables.physical_identity import (
    BoundaryResolution,
    SegmentResolution,
)


def uid(number: int) -> str:
    return f"00000000-0000-4000-8000-{number:012d}"


BOARD = PhysicalBoundary("BOARD", uid(1))
BOX = PhysicalBoundary("EL_BOX", uid(2))
DEVICE = PhysicalBoundary("FIELD_DEVICE", uid(3))
SPAN = PhysicalSpan(BOARD, BOX)
OTHER = PhysicalSpan(BOARD, DEVICE)


def resolved(kind: str, identity: str, span: PhysicalSpan | None) -> SegmentResolution:
    if span is None:
        incomplete = BoundaryResolution(None, "missing Project physical owner")
        return SegmentResolution(kind, identity, None, incomplete, incomplete)
    return SegmentResolution(
        kind,
        identity,
        span,
        BoundaryResolution(span.first),
        BoundaryResolution(span.second),
    )


def audit(segments=(), ordinary=(), buses=(), tubes=("A",)):
    return audit_conduit_memberships(
        conduit_ids=tubes,
        segments=segments,
        ordinary_memberships=ordinary,
        bus_memberships=buses,
    )


def test_shared_ordinary_and_bus_span_does_not_mean_technical_approval():
    rows = audit(
        segments=[
            resolved("CABLE", "s1", SPAN),
            resolved("CABLE", "s2", PhysicalSpan(BOX, BOARD)),
            resolved("BUS", "b1", SPAN),
        ],
        ordinary=[("A", "s1"), ("A", "s2")],
        buses=[("A", "b1")],
    )
    assert len(rows) == 1  # Physical tube is counted once.
    assert rows[0].state == "PHYSICAL_MATCH"
    assert rows[0].physical_span.key() == SPAN.key()
    assert rows[0].ordinary_count == 2
    assert rows[0].bus_count == 1
    # This report asserts physical correspondence only, not an electric compatibility check.


def test_same_physical_pair_can_belong_to_two_separate_conduits():
    reports = audit(
        segments=[resolved("CABLE", "s1", SPAN), resolved("CABLE", "s2", SPAN)],
        ordinary=[("A", "s1"), ("B", "s2")],
        tubes=("B", "A"),
    )
    assert [r.conduit_id for r in reports] == ["A", "B"]
    assert all(r.state == "PHYSICAL_MATCH" for r in reports)


def test_conflict_does_not_get_repaired_or_masked_by_segment_length():
    reports = audit(
        segments=[resolved("CABLE", "s1", SPAN), resolved("BUS", "b1", OTHER)],
        ordinary=[("A", "s1")],
        buses=[("A", "b1")],
    )
    assert reports[0].state == "BOUNDARY_CONFLICT"
    assert reports[0].physical_span is None
    assert "boundary pairs differ" in reports[0].issues[-1]


def test_missing_owners_and_orphan_members_are_explicit():
    reports = audit(
        segments=[resolved("CABLE", "s1", None)],
        ordinary=[("A", "s1"), ("A", "inactive")],
    )
    assert reports[0].state == "UNRESOLVED"
    assert len(reports[0].issues) == 2
    assert "inactive segment" in reports[0].issues[0]
    assert reports[0].physical_span is None


def test_empty_conduit_is_not_conflated_with_unknown_members():
    reports = audit(tubes=("A", "B"))
    assert all(row.state == "EMPTY" for row in reports)
    assert all(row.member_keys == () for row in reports)


def test_dangling_conduit_or_duplicate_membership_rejected_without_writes():
    with pytest.raises(ValueError, match="missing tube"):
        audit(ordinary=[("Z", "s1")])
    with pytest.raises(ValueError, match="Duplicate conduit assignment"):
        audit(ordinary=[("A", "s1"), ("A", "s1")])
    with pytest.raises(ValueError, match="Conduit IDs must be unique"):
        audit(tubes=("A", "A"))
