"""D13: explicitly approved, append-only physical-transit staging in Project.

NEVER mutates ordinary electrical CableSegment, cable length facts or canonical
Conduit assignments. Staged spans are excluded from runtime quantity totals.
D12 evidence must be remeasured and SHA-approved before one atomic write.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, is_dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import Connection, Engine, select

from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    cable_line,
    cable_segment,
    cable_transit_route,
    cable_transit_span,
    conduit,
)

from .transit_physical import (
    ApprovedSpanRoute,
    PhysicalTransitRoute,
    TransitCalculationPolicy,
    VerifiedLocation,
    measure_physical_transit,
)


class TransitPersistenceError(RuntimeError):
    """The staged physical route cannot be safely accepted."""


@dataclass(frozen=True, slots=True)
class ApprovedTransitEvidence:
    project_id: str
    cable_line_id: str
    electrical_segment_id: str
    source_endpoint_id: str
    target_endpoint_id: str
    electrical_segment_row_version: int
    route: PhysicalTransitRoute
    locations: Mapping[str, VerifiedLocation]
    decisions: Mapping[str, ApprovedSpanRoute]
    policy: TransitCalculationPolicy
    approval_evidence: str


@dataclass(frozen=True, slots=True)
class StagedTransitReceipt:
    route_id: str
    approved_sha256: str
    new: bool


def _json_ready(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return _json_ready(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TransitPersistenceError("TRANSIT_APPROVAL_PAYLOAD_UNSUPPORTED")


def approved_transit_sha256(evidence: ApprovedTransitEvidence) -> str:
    """Stable exact approval digest including geometry, owners and policy."""
    payload = {
        "contract": "NLP_D13_TRANSIT_STAGE_V1",
        "evidence": _json_ready(evidence),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _same_boundary(first: str, second: str) -> tuple[str, str]:
    return tuple(sorted((first, second)))


def _check_existing_conduit_owners(
    conn: Connection,
    *,
    project_id: str,
    measured,
    decisions: Mapping[str, ApprovedSpanRoute],
) -> None:
    """Fail-closed sharing across staged spans and legacy Conduit.

    Cross-domain ordinary/BUS canonical Conduit boundary reconciliation is
    not implemented: a legacy Conduit record cannot prove the same boundary.
    """
    for part in measured:
        designation = part.conduit_id
        if not designation:
            continue
        existing_conduit = conn.scalar(
            select(conduit.c.id).where(
                conduit.c.project_id == project_id,
                conduit.c.designation == designation,
                conduit.c.lifecycle == "ACTIVE",
            )
        )
        if existing_conduit is not None:
            raise TransitPersistenceError(
                f"TRANSIT_CONDUIT_LEGACY_OWNERSHIP_REQUIRES_REVIEW:{designation}"
            )
        approved = decisions[part.span.physical_key]
        # Accepted staged conduit members must share the same typed physical
        # boundary, route, material/color and geometric evidence.
        matches = conn.execute(
            select(
                cable_transit_span.c.start_boundary,
                cable_transit_span.c.end_boundary,
                cable_transit_span.c.mount_way,
                cable_transit_span.c.gofra_type,
                cable_transit_span.c.gofra_color,
                cable_transit_span.c.geometry_m_decimal,
            ).where(
                cable_transit_span.c.project_id == project_id,
                cable_transit_span.c.proposed_gofra_id == designation,
            )
        ).mappings()
        expected = (
            _same_boundary(part.span.start, part.span.finish),
            approved.mount_way,
            approved.gofra_type or None,
            approved.gofra_color or None,
            str(part.geometry_m),
        )
        for row in matches:
            accepted = (
                _same_boundary(row["start_boundary"], row["end_boundary"]),
                row["mount_way"],
                row["gofra_type"],
                row["gofra_color"],
                row["geometry_m_decimal"],
            )
            if accepted != expected:
                raise TransitPersistenceError(
                    f"TRANSIT_CONDUIT_BOUNDARY_CONFLICT:{designation}"
                )


def persist_approved_transit(
    engine: Engine,
    evidence: ApprovedTransitEvidence,
    *,
    approved_sha256: str,
    confirmed: bool,
) -> StagedTransitReceipt:
    """Save a whole approved physical chain atomically and idempotently.

    Does NOT silently replace an existing approved route or any electrical
    edge. No automatic scan/apply path calls this API in D13.
    """
    if not confirmed or not evidence.approval_evidence.strip():
        raise TransitPersistenceError("TRANSIT_EXPLICIT_APPROVAL_REQUIRED")
    expected = approved_transit_sha256(evidence)
    if approved_sha256 != expected:
        raise TransitPersistenceError("TRANSIT_APPROVAL_DIGEST_MISMATCH")
    route = evidence.route
    if route.status != "CANDIDATE" or route.issue_codes or not route.spans:
        raise TransitPersistenceError("TRANSIT_PATH_REQUIRES_REVIEW")
    if any(part.cable_base != route.cable_base for part in route.spans):
        raise TransitPersistenceError("TRANSIT_SPAN_OWNER_MISMATCH")
    starts = [item.start for item in route.spans]
    finishes = [item.finish for item in route.spans]
    if any(a != b for a, b in zip(finishes[:-1], starts[1:], strict=True)):
        raise TransitPersistenceError("TRANSIT_CHAIN_NOT_CONTIGUOUS")
    if len(set([starts[0], *finishes])) != len(route.spans) + 1:
        raise TransitPersistenceError("TRANSIT_CHAIN_NOT_SIMPLE")
    if tuple(item.physical_key for item in route.spans) != tuple(
        f"{route.cable_base}:{item.start}->{item.finish}" for item in route.spans
    ):
        raise TransitPersistenceError("TRANSIT_PHYSICAL_KEY_INVALID")

    outcome = measure_physical_transit(
        (route,),
        locations=evidence.locations,
        decisions=evidence.decisions,
        policy=evidence.policy,
    )[0]
    if outcome.status != "MEASURED" or outcome.cable_length_m is None:
        codes = ",".join(outcome.issue_codes)
        raise TransitPersistenceError(f"TRANSIT_MEASUREMENT_REQUIRES_REVIEW:{codes}")
    if len(outcome.measured) != len(route.spans):
        raise TransitPersistenceError("TRANSIT_MEASURED_SPAN_COUNT_MISMATCH")

    with engine.begin() as conn:
        line = conn.execute(
            select(cable_line).where(
                cable_line.c.id == evidence.cable_line_id,
                cable_line.c.project_id == evidence.project_id,
                cable_line.c.lifecycle == "ACTIVE",
            )
        ).mappings().one_or_none()
        if line is None or line["designation"] != route.cable_base:
            raise TransitPersistenceError("TRANSIT_CABLE_OWNER_NOT_FOUND")
        segment = conn.execute(
            select(cable_segment).where(
                cable_segment.c.id == evidence.electrical_segment_id,
                cable_segment.c.project_id == evidence.project_id,
                cable_segment.c.cable_line_id == evidence.cable_line_id,
            )
        ).mappings().one_or_none()
        if segment is None:
            raise TransitPersistenceError("TRANSIT_ELECTRICAL_SEGMENT_NOT_FOUND")
        if (
            segment["source_endpoint_id"] != evidence.source_endpoint_id
            or segment["target_endpoint_id"] != evidence.target_endpoint_id
            or segment["row_version"] != evidence.electrical_segment_row_version
        ):
            raise TransitPersistenceError("TRANSIT_STALE_ELECTRICAL_EDGE")

        existing = conn.execute(
            select(cable_transit_route).where(
                cable_transit_route.c.project_id == evidence.project_id,
                cable_transit_route.c.electrical_segment_id == evidence.electrical_segment_id,
            )
        ).mappings().one_or_none()
        if existing is not None:
            if existing["approved_plan_sha256"] == expected:
                return StagedTransitReceipt(existing["id"], expected, False)
            raise TransitPersistenceError("TRANSIT_ACCEPTED_ROUTE_REQUIRES_REVIEW")

        _check_existing_conduit_owners(
            conn,
            project_id=evidence.project_id,
            measured=outcome.measured,
            decisions=evidence.decisions,
        )
        route_id = new_id()
        conn.execute(
            cable_transit_route.insert().values(
                id=route_id,
                project_id=evidence.project_id,
                cable_line_id=evidence.cable_line_id,
                electrical_segment_id=evidence.electrical_segment_id,
                cable_base=route.cable_base,
                approved_plan_sha256=expected,
                source_endpoint_id_at_approval=evidence.source_endpoint_id,
                target_endpoint_id_at_approval=evidence.target_endpoint_id,
                segment_row_version_at_approval=evidence.electrical_segment_row_version,
                preview_cable_length_m_decimal=str(outcome.cable_length_m),
                approval_evidence=evidence.approval_evidence,
                state="STAGED_APPROVED",
            )
        )
        for order, part in enumerate(outcome.measured, start=1):
            decision = evidence.decisions[part.span.physical_key]
            conn.execute(
                cable_transit_span.insert().values(
                    id=new_id(),
                    project_id=evidence.project_id,
                    cable_transit_route_id=route_id,
                    ordinal=order,
                    physical_key=part.span.physical_key,
                    start_boundary=part.span.start,
                    end_boundary=part.span.finish,
                    mount_way=decision.mount_way,
                    gofra_type=decision.gofra_type or None,
                    gofra_color=decision.gofra_color or None,
                    proposed_gofra_id=decision.gofra_id or None,
                    geometry_m_decimal=str(part.geometry_m),
                    corrected_m_decimal=str(part.corrected_m),
                )
            )
        return StagedTransitReceipt(route_id, expected, True)


def read_staged_transit(
    conn: Connection, *, project_id: str
) -> tuple[dict[str, object], ...]:
    """Read-only staged evidence; not an authoritative cable quantity report."""
    return tuple(
        dict(row)
        for row in conn.execute(
            select(cable_transit_route)
            .where(cable_transit_route.c.project_id == project_id)
            .order_by(cable_transit_route.c.cable_base, cable_transit_route.c.id)
        ).mappings()
    )
