"""Fail-closed physical-boundary contracts for Conduit reassignment (Issue #216).

These pure, side-effect-free checks are a prerequisite for a single database
transaction; they DO NOT write assignments, infer physical points from labels,
or decide whether different electrical circuits are permitted in one tube.
The persistence adapter must resolve *confirmed* physical owners/points before
calling this planner. Its result is not permission to skip database validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

NetworkKind = Literal["CABLE", "BUS"]
PhysicalKind = Literal["BOARD", "EL_BOX", "FIELD_DEVICE", "FIELD_PORT", "INSTANCE_RESOURCE"]
_VALID_KINDS = frozenset({"BOARD", "EL_BOX", "FIELD_DEVICE", "FIELD_PORT", "INSTANCE_RESOURCE"})
_VALID_NETWORKS = frozenset({"CABLE", "BUS"})
_VALID_MOUNT_WAYS = frozenset(
    {"По полу", "В стяжке", "По потолку", "В стене", "В брусе", "В кабель-канале"}
)


class PhysicalAssignmentError(ValueError):
    """A proposed physical Conduit assignment is not proven safe."""


@dataclass(frozen=True, slots=True)
class PhysicalBoundary:
    """Project-wide physical identity, NOT line-local endpoint UUID or label."""

    kind: PhysicalKind
    identity: str

    def __post_init__(self) -> None:
        if self.kind not in _VALID_KINDS or not isinstance(self.identity, str):
            raise PhysicalAssignmentError("Unknown physical boundary identity")
        if not self.identity.strip() or self.identity != self.identity.strip():
            raise PhysicalAssignmentError("Physical boundary identity is missing")
        # Every accepted kind refers to a persisted Project physical-owner UUID.
        # BOX.001 is a *display designation*, not the shared cable_point.id.
        # Migration 000000000014 permits one cable_point.id in several CableLines.
        try:
            if str(UUID(self.identity)) != self.identity:
                raise ValueError("Not a canonical UUID")
        except (ValueError, AttributeError) as exc:
            raise PhysicalAssignmentError(
                "Physical boundary needs a confirmed canonical Project owner ID"
            ) from exc

    def key(self) -> tuple[str, str]:
        return self.kind, self.identity


@dataclass(frozen=True, slots=True)
class PhysicalSpan:
    """An unordered pair: A→B and B→A denote the same physical interval."""

    first: PhysicalBoundary
    second: PhysicalBoundary

    def __post_init__(self) -> None:
        if self.first == self.second:
            raise PhysicalAssignmentError("A physical interval must have distinct boundaries")

    def key(self) -> tuple[tuple[str, str], tuple[str, str]]:
        return tuple(sorted((self.first.key(), self.second.key())))


@dataclass(frozen=True, slots=True)
class ConduitFact:
    conduit_id: str
    span: PhysicalSpan | None
    mount_way: str | None = None
    # This is a documented approval from the technical compatibility layer,
    # never inferred from the designation or contents of an arbitrary Conduit.
    permitted_cable_classes: frozenset[str] | None = None
    allow_mixed_networks: bool = False


@dataclass(frozen=True, slots=True)
class SegmentFact:
    network_kind: NetworkKind
    segment_id: str
    span: PhysicalSpan | None
    mount_way: str | None
    cable_class: str | None
    conduit_id: str | None

    def key(self) -> tuple[str, str]:
        return self.network_kind, self.segment_id


@dataclass(frozen=True, slots=True)
class AssignmentChange:
    network_kind: NetworkKind
    segment_id: str
    target_conduit_id: str | None

    def key(self) -> tuple[str, str]:
        return self.network_kind, self.segment_id


@dataclass(frozen=True, slots=True)
class AssignmentPlan:
    """Already checked delta; apply atomically under a Project-scoped UnitOfWork."""

    changes: tuple[AssignmentChange, ...]
    affected_conduit_ids: tuple[str, ...]


def _require_id(identifier: str | None, label: str) -> str:
    if not isinstance(identifier, str) or not identifier.strip():
        raise PhysicalAssignmentError(f"{label} is missing")
    if identifier != identifier.strip():
        raise PhysicalAssignmentError(f"{label} is not canonical")
    return identifier


def _require_member(member: SegmentFact) -> None:
    if member.network_kind not in _VALID_NETWORKS:
        raise PhysicalAssignmentError("Unknown physical network kind")
    _require_id(member.segment_id, "segment_id")
    if member.conduit_id is not None:
        _require_id(member.conduit_id, "conduit_id")


def _validate_shared_tube(tube: ConduitFact, members: list[SegmentFact]) -> None:
    """No positive compatibility claim when physical or technical data is absent."""

    reference_span = tube.span
    reference_mount = tube.mount_way
    kinds: set[str] = set()
    classes: set[str] = set()
    for member in members:
        if member.span is None:
            raise PhysicalAssignmentError(
                f"Segment {member.segment_id} has no confirmed physical boundaries"
            )
        if reference_span is None:
            reference_span = member.span
        if member.span.key() != reference_span.key():
            raise PhysicalAssignmentError(f"Conduit {tube.conduit_id}: physical boundaries differ")
        if member.mount_way not in _VALID_MOUNT_WAYS:
            raise PhysicalAssignmentError(f"Segment {member.segment_id}: route method is unknown")
        if member.mount_way == "В кабель-канале":
            raise PhysicalAssignmentError("Cable channel is not a protective Conduit")
        if reference_mount is None:
            reference_mount = member.mount_way
        if member.mount_way != reference_mount:
            raise PhysicalAssignmentError(
                f"Conduit {tube.conduit_id}: physical mount methods differ"
            )
        if not isinstance(member.cable_class, str) or not member.cable_class.strip():
            raise PhysicalAssignmentError(
                f"Segment {member.segment_id}: technical cable class is unknown"
            )
        kinds.add(member.network_kind)
        classes.add(member.cable_class)

    if len(members) > 1:
        allowed = tube.permitted_cable_classes
        if allowed is None or not classes.issubset(allowed):
            raise PhysicalAssignmentError(
                f"Conduit {tube.conduit_id}: shared-cable compatibility not confirmed"
            )
    elif members and tube.permitted_cable_classes is not None:
        if not classes.issubset(tube.permitted_cable_classes):
            raise PhysicalAssignmentError(f"Conduit {tube.conduit_id}: cable class not permitted")
    if len(kinds) > 1 and not tube.allow_mixed_networks:
        raise PhysicalAssignmentError(
            f"Conduit {tube.conduit_id}: ordinary/BUS sharing not approved"
        )


def plan_conduit_assignments(
    *,
    conduits: tuple[ConduitFact, ...],
    segments: tuple[SegmentFact, ...],
    changes: tuple[AssignmentChange, ...],
) -> AssignmentPlan:
    """Validate an entire batch before any write; duplicate/conflicts are errors.

    The caller must read a consistent Project snapshot and apply the returned
    delta in the same transaction under concurrent-revision verification.
    Passing an outdated snapshot or writing only part of a plan is forbidden.
    """

    conduit_by_id: dict[str, ConduitFact] = {}
    for tube in conduits:
        _require_id(tube.conduit_id, "conduit_id")
        if tube.conduit_id in conduit_by_id:
            raise PhysicalAssignmentError(f"Duplicate conduit: {tube.conduit_id}")
        if tube.mount_way is not None and tube.mount_way not in _VALID_MOUNT_WAYS:
            raise PhysicalAssignmentError(f"Conduit {tube.conduit_id}: invalid mount")
        conduit_by_id[tube.conduit_id] = tube

    segment_by_key: dict[tuple[str, str], SegmentFact] = {}
    for member in segments:
        _require_member(member)
        key = member.key()
        if key in segment_by_key:
            raise PhysicalAssignmentError(f"Duplicate physical segment: {key}")
        if member.conduit_id is not None and member.conduit_id not in conduit_by_id:
            raise PhysicalAssignmentError(
                f"Segment {member.segment_id}: current Conduit is missing"
            )
        segment_by_key[key] = member

    seen: set[tuple[str, str]] = set()
    affected: set[str] = set()
    target_by_key: dict[tuple[str, str], str | None] = {}
    for change in changes:
        key = change.key()
        if key in seen:
            raise PhysicalAssignmentError(f"Duplicate assignment change: {key}")
        seen.add(key)
        if key not in segment_by_key:
            raise PhysicalAssignmentError(f"Unknown physical segment: {key}")
        if change.target_conduit_id is not None:
            _require_id(change.target_conduit_id, "target_conduit_id")
            if change.target_conduit_id not in conduit_by_id:
                raise PhysicalAssignmentError(f"Unknown target Conduit: {change.target_conduit_id}")
        original = segment_by_key[key].conduit_id
        if original is not None:
            affected.add(original)
        if change.target_conduit_id is not None:
            affected.add(change.target_conduit_id)
        target_by_key[key] = change.target_conduit_id

    resulting_members: dict[str, list[SegmentFact]] = {conduit_id: [] for conduit_id in affected}
    for member in segments:
        target = target_by_key.get(member.key(), member.conduit_id)
        if target in resulting_members:
            resulting_members[target].append(member)

    for conduit_id in sorted(affected):
        _validate_shared_tube(conduit_by_id[conduit_id], resulting_members[conduit_id])
    return AssignmentPlan(
        changes=tuple(changes),
        affected_conduit_ids=tuple(sorted(affected)),
    )
