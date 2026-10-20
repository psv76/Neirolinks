"""Q01/Q03/Q06 regression cases for side-effect-free physical Conduit validation."""

from __future__ import annotations

import pytest

from nl_project_2.cables.physical_conduit import (
    AssignmentChange,
    ConduitFact,
    PhysicalAssignmentError,
    PhysicalBoundary,
    PhysicalSpan,
    SegmentFact,
    plan_conduit_assignments,
)


BOARD = PhysicalBoundary("BOARD", "00000000-0000-4000-8000-000000000001")
BOX = PhysicalBoundary("EL_BOX", "00000000-0000-4000-8000-000000000002")
DEVICE = PhysicalBoundary("FIELD_DEVICE", "00000000-0000-4000-8000-000000000003")
SPAN = PhysicalSpan(BOARD, BOX)
REVERSED = PhysicalSpan(BOX, BOARD)
OTHER_SPAN = PhysicalSpan(BOX, DEVICE)


def tube(
    identity: str,
    *,
    span: PhysicalSpan | None = SPAN,
    approved: frozenset[str] | None = None,
    mixed: bool = False,
    mount: str | None = None,
) -> ConduitFact:
    return ConduitFact(identity, span, mount, approved, mixed)


def segment(
    identity: str,
    *,
    span: PhysicalSpan | None = SPAN,
    conduit: str | None = None,
    kind: str = "CABLE",
    cable_class: str | None = "AC_230",
    mount: str | None = "По полу",
) -> SegmentFact:
    return SegmentFact(kind, identity, span, mount, cable_class, conduit)


def move(identity: str, target: str | None, *, kind: str = "CABLE") -> AssignmentChange:
    return AssignmentChange(kind, identity, target)


def plan(*, conduits, members, changes):
    return plan_conduit_assignments(
        conduits=tuple(conduits),
        segments=tuple(members),
        changes=tuple(changes),
    )


def test_unordered_bounds_are_equal_without_coordinates_or_gofra_id():
    assert SPAN.key() == REVERSED.key()
    assert SPAN.key() != OTHER_SPAN.key()
    assert PhysicalSpan(BOARD, DEVICE).key() != SPAN.key()
    assert SPAN.first.kind == "BOARD"
    with pytest.raises(PhysicalAssignmentError):
        PhysicalSpan(BOARD, BOARD)


def test_two_distinct_tubes_may_have_identical_physical_span():
    result = plan(
        conduits=[tube("tube-a"), tube("tube-b")],
        members=[segment("s1", conduit="tube-a"), segment("s2", span=REVERSED)],
        changes=[move("s2", "tube-b")],
    )
    assert result.affected_conduit_ids == ("tube-b",)
    assert result.changes[0].target_conduit_id == "tube-b"


def test_shared_cable_segments_require_explicit_technical_approval():
    s1 = segment("s1", conduit="tube-a")
    s2 = segment("s2", span=REVERSED)
    with pytest.raises(PhysicalAssignmentError, match="compatibility"):
        plan(conduits=[tube("tube-a")], members=[s1, s2], changes=[move("s2", "tube-a")])
    result = plan(
        conduits=[tube("tube-a", approved=frozenset({"AC_230"}))],
        members=[s1, s2],
        changes=[move("s2", "tube-a")],
    )
    assert result.affected_conduit_ids == ("tube-a",)


def test_mixed_ordinary_and_bus_must_be_explicitly_allowed_even_with_same_bounds():
    members = [
        segment("s1", conduit="tube-a", cable_class="DATA"),
        segment("b1", kind="BUS", cable_class="DATA"),
    ]
    with pytest.raises(PhysicalAssignmentError, match="sharing not approved"):
        plan(
            conduits=[tube("tube-a", approved=frozenset({"DATA"}))],
            members=members,
            changes=[move("b1", "tube-a", kind="BUS")],
        )
    result = plan(
        conduits=[tube("tube-a", approved=frozenset({"DATA"}), mixed=True)],
        members=members,
        changes=[move("b1", "tube-a", kind="BUS")],
    )
    assert len(result.changes) == 1
    assert result.changes[0].network_kind == "BUS"


@pytest.mark.parametrize(
    "unproven",
    [
        OTHER_SPAN,
        PhysicalSpan(BOARD, DEVICE),
    ],
)
def test_different_or_partial_intervals_never_share_a_tube(unproven):
    with pytest.raises(PhysicalAssignmentError, match="physical boundaries differ"):
        plan(
            conduits=[tube("tube-a", approved=frozenset({"AC_230"}))],
            members=[
                segment("s1", conduit="tube-a"),
                segment("s2", span=unproven),
            ],
            changes=[move("s2", "tube-a")],
        )


def test_unknown_endpoint_geometry_or_route_class_fails_closed():
    for broken in (
        segment("s2", span=None),
        segment("s2", mount=None),
        segment("s2", cable_class=None),
    ):
        with pytest.raises(PhysicalAssignmentError):
            plan(
                conduits=[tube("tube-a")],
                members=[broken],
                changes=[move("s2", "tube-a")],
            )


def test_move_between_tubes_prevalidates_both_affected_tubes():
    members = [
        segment("s1", conduit="tube-a"),
        segment("s2", conduit="tube-a"),
        segment("s3", conduit="tube-b", span=OTHER_SPAN),
    ]
    with pytest.raises(PhysicalAssignmentError, match="physical boundaries differ"):
        plan(
            conduits=[
                tube("tube-a", approved=frozenset({"AC_230"})),
                tube("tube-b", span=OTHER_SPAN, approved=frozenset({"AC_230"})),
            ],
            members=members,
            changes=[move("s2", "tube-b")],
        )
    # No mutation occurred to these input facts during the rejected plan.
    assert members[1].conduit_id == "tube-a"


def test_batch_all_or_none_rejects_one_incompatible_member():
    members = [
        segment("s1", conduit="tube-a"),
        segment("s2", span=REVERSED),
        segment("s3", span=OTHER_SPAN),
    ]
    with pytest.raises(PhysicalAssignmentError, match="physical boundaries differ"):
        plan(
            conduits=[tube("tube-a", approved=frozenset({"AC_230"}))],
            members=members,
            changes=[move("s2", "tube-a"), move("s3", "tube-a")],
        )
    assert all(m.conduit_id is None for m in members[1:])


def test_removal_can_leave_a_valid_shared_tube():
    result = plan(
        conduits=[tube("tube-a", approved=frozenset({"AC_230"}))],
        members=[segment("s1", conduit="tube-a"), segment("s2", conduit="tube-a")],
        changes=[move("s2", None)],
    )
    assert result.affected_conduit_ids == ("tube-a",)


def test_mismatched_mount_methods_and_cable_classes_rejected():
    with pytest.raises(PhysicalAssignmentError, match="mount methods differ"):
        plan(
            conduits=[tube("tube-a", approved=frozenset({"AC_230"}))],
            members=[
                segment("s1", conduit="tube-a"),
                segment("s2", mount="По потолку"),
            ],
            changes=[move("s2", "tube-a")],
        )
    with pytest.raises(PhysicalAssignmentError, match="cable class not permitted"):
        plan(
            conduits=[tube("tube-a", approved=frozenset({"AC_230"}))],
            members=[segment("s1", cable_class="DATA")],
            changes=[move("s1", "tube-a")],
        )


def test_unknown_objects_and_duplicate_requests_rejected():
    for changes in ([move("unknown", "tube-a")], [move("s1", "missing")]):
        with pytest.raises(PhysicalAssignmentError):
            plan(
                conduits=[tube("tube-a")],
                members=[segment("s1")],
                changes=changes,
            )
    with pytest.raises(PhysicalAssignmentError, match="Duplicate assignment change"):
        plan(
            conduits=[tube("tube-a")],
            members=[segment("s1")],
            changes=[move("s1", "tube-a"), move("s1", None)],
        )


def test_unidentified_physical_boundary_or_box_is_not_accepted():
    with pytest.raises(PhysicalAssignmentError):
        PhysicalBoundary("EL_BOX", "Гостиная")
    with pytest.raises(PhysicalAssignmentError):
        PhysicalBoundary("EL_BOX", "BOX.001")  # display designation is not owner ID
    with pytest.raises(PhysicalAssignmentError):
        PhysicalBoundary("EL_BOX", "")
    with pytest.raises(PhysicalAssignmentError):
        PhysicalBoundary("UNKNOWN", "point-1")


def test_cable_channel_cannot_be_assigned_to_protective_conduit():
    with pytest.raises(PhysicalAssignmentError, match="Cable channel"):
        plan(
            conduits=[tube("tube-a")],
            members=[segment("s1", mount="В кабель-канале")],
            changes=[move("s1", "tube-a")],
        )
