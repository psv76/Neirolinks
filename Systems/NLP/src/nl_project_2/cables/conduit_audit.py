"""Read-only physical tube audit, never an assignment/compatibility approval.

It checks only Q03's canonical physical boundary equality for *existing*
ordinary and BUS membership. Cable fill, electrical separation and technical
material compatibility still require independent positive verification.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from .physical_conduit import PhysicalSpan
from .physical_identity import SegmentResolution
from .physical_identity_repository import load_physical_segment_resolutions


AuditState = Literal["EMPTY", "PHYSICAL_MATCH", "UNRESOLVED", "BOUNDARY_CONFLICT"]


@dataclass(frozen=True, slots=True)
class ConduitAudit:
    conduit_id: str
    state: AuditState
    member_keys: tuple[tuple[str, str], ...]
    physical_span: PhysicalSpan | None
    issues: tuple[str, ...]

    @property
    def ordinary_count(self) -> int:
        return sum(network == "CABLE" for network, _ in self.member_keys)

    @property
    def bus_count(self) -> int:
        return sum(network == "BUS" for network, _ in self.member_keys)


def audit_conduit_memberships(
    *,
    conduit_ids: Iterable[str],
    segments: Iterable[SegmentResolution],
    ordinary_memberships: Iterable[tuple[str, str]],
    bus_memberships: Iterable[tuple[str, str]],
) -> tuple[ConduitAudit, ...]:
    """Return a deterministic immutable report. Physical match != tech approval.

    Membership tuples are (conduit_id, segment_id). For a source that has a
    missing/retired owner, the report exposes the unresolved member explicitly.
    """

    known_conduits = tuple(sorted(conduit_ids))
    if len(set(known_conduits)) != len(known_conduits):
        raise ValueError("Conduit IDs must be unique")
    resolved: dict[tuple[str, str], SegmentResolution] = {}
    for segment in segments:
        key = (segment.network_kind, segment.segment_id)
        if key in resolved:
            raise ValueError(f"Duplicate resolved physical segment: {key}")
        resolved[key] = segment

    memberships: dict[str, list[tuple[str, str]]] = {
        conduit_id: [] for conduit_id in known_conduits
    }
    owner_by_member: dict[tuple[str, str], str] = {}
    for kind, items in (
        ("CABLE", ordinary_memberships),
        ("BUS", bus_memberships),
    ):
        for conduit_id, segment_id in items:
            if conduit_id not in memberships:
                raise ValueError(f"Conduit assignment targets missing tube: {conduit_id}")
            key = (kind, segment_id)
            if key in owner_by_member:
                raise ValueError(f"Duplicate conduit assignment: {key}")
            owner_by_member[key] = conduit_id
            memberships[conduit_id].append(key)

    reports: list[ConduitAudit] = []
    for conduit_id in known_conduits:
        members = tuple(sorted(memberships[conduit_id]))
        if not members:
            reports.append(ConduitAudit(conduit_id, "EMPTY", (), None, ()))
            continue
        issues: list[str] = []
        known_spans: dict[tuple, PhysicalSpan] = {}
        unknown_member = False
        for key in members:
            current = resolved.get(key)
            if current is None:
                issues.append(f"{key[0]}/{key[1]}: missing or inactive segment")
                unknown_member = True
            elif current.span is None:
                detail = "; ".join(current.issues) or "physical bounds not confirmed"
                issues.append(f"{key[0]}/{key[1]}: {detail}")
                unknown_member = True
            else:
                known_spans.setdefault(current.span.key(), current.span)
        if len(known_spans) > 1:
            issues.append("Canonical physical boundary pairs differ within this tube")
            state: AuditState = "BOUNDARY_CONFLICT"
        elif unknown_member:
            state = "UNRESOLVED"
        else:
            state = "PHYSICAL_MATCH"
        span = next(iter(known_spans.values())) if state == "PHYSICAL_MATCH" else None
        reports.append(ConduitAudit(conduit_id, state, members, span, tuple(issues)))
    return tuple(reports)


def load_conduit_membership_audit(connection, project_id: str) -> tuple[ConduitAudit, ...]:
    """Only SELECTs; accepts one connection for transaction-consistent reads."""

    from sqlalchemy import select

    from nl_project_2.persistence.schema import (
        bus_segment_conduit_assignment,
        conduit,
        conduit_segment_assignment,
    )

    conduits = tuple(connection.execute(
        select(conduit.c.id).where(
            conduit.c.project_id == project_id,
            conduit.c.lifecycle == "ACTIVE",
        )
    ).scalars())
    ordinary = connection.execute(
        select(
            conduit_segment_assignment.c.conduit_id,
            conduit_segment_assignment.c.cable_segment_id,
        ).where(conduit_segment_assignment.c.project_id == project_id)
    ).all()
    bus_rows = connection.execute(
        select(
            bus_segment_conduit_assignment.c.conduit_id,
            bus_segment_conduit_assignment.c.bus_segment_id,
        ).where(bus_segment_conduit_assignment.c.project_id == project_id)
    ).all()
    return audit_conduit_memberships(
        conduit_ids=conduits,
        segments=load_physical_segment_resolutions(connection, project_id),
        ordinary_memberships=ordinary,
        bus_memberships=bus_rows,
    )
