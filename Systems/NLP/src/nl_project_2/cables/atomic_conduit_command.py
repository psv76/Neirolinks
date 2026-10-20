"""Atomic, gated Project-owned physical Conduit reassignment (Issue #216).

This is a DOMAIN command, not a GUI action. It cannot run without a trusted
Project/catalog technical-approval provider and a transactional updater for
ordinary cable's DWG-facing mirror. Missing approval is a hard refusal. All
reads, prevalidation, CAS and writes use one UnitOfWork/SQLite transaction.
No schema change, DWG COM, implicit migration or legacy length recalc occurs.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import Engine, delete, select, update

from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    bus,
    bus_segment,
    bus_segment_conduit_assignment,
    cable_line,
    cable_segment,
    conduit,
    conduit_segment_assignment,
    project,
)
from nl_project_2.persistence.uow import UnitOfWork

from .physical_conduit import (
    AssignmentChange,
    ConduitFact,
    PhysicalAssignmentError,
    SegmentFact,
    plan_conduit_assignments,
)
from .physical_identity_repository import load_physical_segment_resolutions


@dataclass(frozen=True, slots=True)
class ApprovedPhysicalFacts:
    """Proof provided ONLY by a trusted Project/catalog validator.

    Caller/GUI cannot infer these from labels, GOFRA_ID or cable descriptions.
    Values are scoped to the current UnitOfWork and project revision.
    """

    conduit_facts: Mapping[str, ConduitFact]
    segment_classes: Mapping[tuple[str, str], str]


class ApprovalProvider(Protocol):
    def __call__(
        self,
        uow: UnitOfWork,
        project_id: str,
        affected_conduit_ids: frozenset[str],
        affected_segment_keys: frozenset[tuple[str, str]],
    ) -> ApprovedPhysicalFacts: ...


class CableMirrorUpdater(Protocol):
    def __call__(
        self,
        uow: UnitOfWork,
        project_id: str,
        segment_id: str,
        conduit_row: Mapping | None,
    ) -> None:
        """Update *all* DWG-facing Project mirror facts in the same UoW."""
        ...


@dataclass(frozen=True, slots=True)
class AtomicAssignmentResult:
    applied: tuple[AssignmentChange, ...]
    affected_conduits: tuple[str, ...]
    project_revision: int


def _assignments(uow, project_id: str) -> dict[tuple[str, str], str]:
    pairs: dict[tuple[str, str], str] = {}
    for kind, table, segment_column in (
        ("CABLE", conduit_segment_assignment, conduit_segment_assignment.c.cable_segment_id),
        ("BUS", bus_segment_conduit_assignment, bus_segment_conduit_assignment.c.bus_segment_id),
    ):
        for row in uow.execute(
            select(table.c.conduit_id, segment_column).where(table.c.project_id == project_id)
        ):
            key = (kind, row[1])
            if key in pairs:
                raise PhysicalAssignmentError(f"Multiple assignments for {key}")
            pairs[key] = row[0]
    return pairs


class AtomicConduitAssignmentService:
    """Strictly gated batch writer; never constructed implicitly by the UI."""

    def __init__(
        self,
        engine: Engine,
        *,
        approval_provider: ApprovalProvider | None = None,
        cable_mirror_updater: CableMirrorUpdater | None = None,
    ) -> None:
        self._engine = engine
        self._approval_provider = approval_provider
        self._cable_mirror_updater = cable_mirror_updater

    def apply(
        self,
        *,
        project_id: str,
        expected_project_revision: int,
        changes: tuple[AssignmentChange, ...],
        expected_current_assignments: Mapping[tuple[str, str], str | None],
        failure_hook: Callable[[], None] | None = None,
    ) -> AtomicAssignmentResult:
        if not changes:
            raise PhysicalAssignmentError("A physical assignment batch must not be empty")
        if not isinstance(expected_project_revision, int) or expected_project_revision < 0:
            raise PhysicalAssignmentError("Expected Project revision must be nonnegative")
        if self._approval_provider is None:
            raise PhysicalAssignmentError("Trusted Project technical approval is unavailable")
        if self._cable_mirror_updater is None and any(
            change.network_kind == "CABLE" for change in changes
        ):
            raise PhysicalAssignmentError(
                "Atomic DWG-facing cable mirror updater is not installed"
            )

        # A write lock *before* physical read prevents another SQLite writer
        # changing membership during our preflight even if it does not bump
        # the Project revision. A failed preflight rolls this CAS back.
        with UnitOfWork(self._engine) as uow:
            now = datetime.now(UTC)
            cas = uow.execute(
                update(project)
                .where(
                    project.c.id == project_id,
                    project.c.lifecycle == "ACTIVE",
                    project.c.project_revision == expected_project_revision,
                )
                .values(
                    project_revision=project.c.project_revision + 1,
                    row_version=project.c.row_version + 1,
                    updated_at_utc=now,
                )
            )
            if cas.rowcount != 1:
                raise PhysicalAssignmentError(
                    "Project was changed: refresh before assigning physical routes"
                )

            conduits = {
                row["id"]: dict(row)
                for row in uow.execute(
                    select(conduit).where(
                        conduit.c.project_id == project_id,
                        conduit.c.lifecycle == "ACTIVE",
                    )
                ).mappings()
            }
            current = _assignments(uow, project_id)
            resolved = {
                (r.network_kind, r.segment_id): r
                for r in load_physical_segment_resolutions(uow.session, project_id)
            }
            if not resolved:
                raise PhysicalAssignmentError("No active physical cable segments in Project")

            # No spurious operations or second assignment to the same segment.
            request_keys: set[tuple[str, str]] = set()
            for change in changes:
                key = change.key()
                if key in request_keys:
                    raise PhysicalAssignmentError(f"Repeated physical segment: {key}")
                request_keys.add(key)
                if key not in resolved:
                    raise PhysicalAssignmentError(f"Unknown active physical segment: {key}")
                if change.target_conduit_id is not None:
                    if change.target_conduit_id not in conduits:
                        raise PhysicalAssignmentError(
                            f"Target Conduit not active in this Project: {change.target_conduit_id}"
                        )

            if set(expected_current_assignments) != request_keys:
                raise PhysicalAssignmentError(
                    "Exact expected assignment identities required for the entire batch"
                )
            for key in request_keys:
                if current.get(key) != expected_current_assignments[key]:
                    raise PhysicalAssignmentError(
                        f"Physical segment {key} was reassigned: refresh before editing"
                    )

            effective = tuple(
                change for change in changes
                if current.get(change.key()) != change.target_conduit_id
            )
            if not effective:
                # No-op is idempotent: rollback the initial revision CAS.
                uow.rollback()
                return AtomicAssignmentResult((), (), expected_project_revision)

            affected: set[str] = set()
            for change in effective:
                old = current.get(change.key())
                if old is not None:
                    affected.add(old)
                if change.target_conduit_id is not None:
                    affected.add(change.target_conduit_id)

            for cid in affected:
                if cid not in conduits:
                    raise PhysicalAssignmentError(f"Current Conduit was deleted: {cid}")

            members: dict[tuple[str, str], dict] = {}
            for row in uow.execute(
                select(cable_segment.c.id, cable_segment.c.mount_way)
                .join(cable_line, cable_line.c.id == cable_segment.c.cable_line_id)
                .where(
                    cable_segment.c.project_id == project_id,
                    cable_line.c.project_id == project_id,
                    cable_line.c.lifecycle == "ACTIVE",
                )
            ).mappings():
                members[("CABLE", row["id"])] = dict(row)
            for row in uow.execute(
                select(bus_segment.c.id, bus_segment.c.mount_way)
                .join(bus, bus.c.id == bus_segment.c.bus_id)
                .where(
                    bus_segment.c.project_id == project_id,
                    bus.c.project_id == project_id,
                    bus.c.lifecycle == "ACTIVE",
                    bus_segment.c.connection_kind == "CABLE",
                )
            ).mappings():
                members[("BUS", row["id"])] = dict(row)

            relevant_keys = frozenset(
                key for key in resolved
                if key in request_keys or current.get(key) in affected
            )
            approval = self._approval_provider(
                uow, project_id, frozenset(affected), relevant_keys
            )
            if not isinstance(approval, ApprovedPhysicalFacts):
                raise PhysicalAssignmentError("Unverified technical approval response")
            for cid in affected:
                fact = approval.conduit_facts.get(cid)
                if fact is None or fact.conduit_id != cid or fact.span is None:
                    raise PhysicalAssignmentError(
                        f"Conduit {cid}: confirmed Project physical bounds are required"
                    )

            physical_facts = []
            for key, resolution in resolved.items():
                row = members.get(key)
                if row is None:
                    raise PhysicalAssignmentError(f"Physical segment row unavailable: {key}")
                cable_class = approval.segment_classes.get(key)
                physical_facts.append(
                    SegmentFact(
                        network_kind=key[0],
                        segment_id=key[1],
                        span=resolution.span,
                        mount_way=row["mount_way"],
                        cable_class=cable_class,
                        conduit_id=current.get(key),
                    )
                )
            approved_conduits = tuple(
                approval.conduit_facts.get(cid, ConduitFact(cid, None))
                for cid in conduits
            )
            plan = plan_conduit_assignments(
                conduits=approved_conduits,
                segments=tuple(physical_facts),
                changes=effective,
            )

            # From here onward ALL statements and mirrored metadata stay inside
            # one UoW. No external callbacks, files, AutoCAD or notifications.
            for change in effective:
                key = change.key()
                if change.network_kind == "CABLE":
                    assignment = conduit_segment_assignment
                    segment_col = assignment.c.cable_segment_id
                else:
                    assignment = bus_segment_conduit_assignment
                    segment_col = assignment.c.bus_segment_id
                uow.execute(
                    delete(assignment).where(
                        assignment.c.project_id == project_id,
                        segment_col == change.segment_id,
                    )
                )
                target = change.target_conduit_id
                if target is not None:
                    fields = {
                        "id": new_id(),
                        "project_id": project_id,
                        "conduit_id": target,
                        "cable_segment_id" if key[0] == "CABLE" else "bus_segment_id":
                            change.segment_id,
                    }
                    uow.execute(assignment.insert().values(**fields))
                chosen = conduits.get(target) if target is not None else None
                if key[0] == "CABLE":
                    # This updater must live in the SAME DB transaction and
                    # must reject ambiguous/shared DWG-facing device mirrors.
                    assert self._cable_mirror_updater is not None
                    self._cable_mirror_updater(
                        uow, project_id, change.segment_id, chosen
                    )
                else:
                    uow.execute(
                        update(bus_segment)
                        .where(
                            bus_segment.c.project_id == project_id,
                            bus_segment.c.id == change.segment_id,
                            bus_segment.c.connection_kind == "CABLE",
                        )
                        .values(
                            gofra_type=chosen["conduit_type"] if chosen else None,
                            gofra_color=chosen["color"] if chosen else None,
                            gofra_id=chosen["designation"] if chosen else None,
                            row_version=bus_segment.c.row_version + 1,
                            updated_at_utc=now,
                        )
                    )
            for cid in plan.affected_conduit_ids:
                tube = conduits[cid]
                path = dict(tube["path_json"] or {})
                if path.get("length_source") == "USER_CONFIRMED":
                    next_length = tube["length_m_decimal"]
                else:
                    next_length = None
                    path["length_source"] = "STALE_AFTER_ASSIGNMENT"
                uow.execute(
                    update(conduit)
                    .where(
                        conduit.c.project_id == project_id,
                        conduit.c.id == cid,
                    )
                    .values(
                        length_m_decimal=next_length,
                        path_json=path,
                        row_version=conduit.c.row_version + 1,
                        updated_at_utc=now,
                    )
                )
            if failure_hook is not None:
                failure_hook()  # test-only injection; must NOT use external effects
            uow.commit()
            return AtomicAssignmentResult(
                effective,
                plan.affected_conduit_ids,
                expected_project_revision + 1,
            )
