"""D15: explicitly approved single-edge line preview, never canonical apply.

Reuse #218/#231 quantity arithmetic. D13 edge totals and corrected spans are
not inputs: only remeasured pure geometry and explicitly evidenced real ends.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import Connection, select

from nl_project_2.cables.length_policy import (
    ActualCableEnd,
    CableQuantity,
    LengthPolicy,
    PhysicalCableSegment,
    calculate_cable_quantity,
)
from nl_project_2.cables.transit_reconciliation import staged_transit_reconciliation
from nl_project_2.cad_sync.transit_physical import measure_physical_transit
from nl_project_2.cad_sync.transit_physical_store import (
    ApprovedTransitEvidence,
    _json_ready,
    approved_transit_sha256,
)
from nl_project_2.persistence.schema import cable_transit_span


@dataclass(frozen=True, slots=True)
class VerifiedLineEnd:
    endpoint_id: str
    end: ActualCableEnd
    evidence: str


@dataclass(frozen=True, slots=True)
class TransitLineApproval:
    transit: ApprovedTransitEvidence
    ends: tuple[VerifiedLineEnd, ...]
    policy: LengthPolicy
    additional_m: Decimal
    manual_full_m: Decimal | None
    approval_evidence: str


@dataclass(frozen=True, slots=True)
class TransitLinePreview:
    status: str
    issues: tuple[str, ...]
    quantity: CableQuantity | None = None
    authoritative_cable_m: None = None
    authoritative_conduit_m: None = None


def transit_line_approval_sha256(approval: TransitLineApproval) -> str:
    payload = {"contract": "NLP_D15_LINE_PREVIEW_V1", "approval": _json_ready(approval)}
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def preview_transit_line(
    connection: Connection,
    approval: TransitLineApproval,
    *,
    approved_sha256: str,
    confirmed: bool = False,
) -> TransitLinePreview:
    """Read-only gate, deliberately restricted to D14 complete single-edge lines.

    End classification/overrides must be independently reviewed by the caller;
    graph degree is never used as a physical termination proxy. Approval is a
    preview authorization only, not permission to persist or release quantities.
    """
    issues: set[str] = set()
    ev = approval.transit
    if (
        not confirmed
        or not approval.approval_evidence.strip()
        or approved_sha256 != transit_line_approval_sha256(approval)
    ):
        return TransitLinePreview("REVIEW", ("LINE_APPROVAL_REQUIRED",))
    snapshot = staged_transit_reconciliation(connection, ev.project_id)
    rows = [r for r in snapshot["routes"] if r["cable_line_id"] == ev.cable_line_id]
    if len(rows) != 1:
        return TransitLinePreview("REVIEW", ("LINE_STAGED_COVERAGE_UNPROVEN",))
    row = rows[0]
    issues.update(row["issues"])
    if (
        row["approval_sha256"] != approved_transit_sha256(ev)
        or row["electrical_segment_id"] != ev.electrical_segment_id
    ):
        issues.add("LINE_TRANSIT_APPROVAL_CHANGED")
    # Exactly two real ends, on the existing electrical endpoints. Intermediate
    # physical BOX boundaries cannot become terminations or earn splice reserve.
    if (
        len(approval.ends) != 2
        or {e.endpoint_id for e in approval.ends} != {ev.source_endpoint_id, ev.target_endpoint_id}
        or len({e.end.end_id for e in approval.ends}) != 2
        or any(not e.evidence.strip() for e in approval.ends)
    ):
        issues.add("LINE_REAL_ENDS_UNPROVEN")
    if issues:
        return TransitLinePreview("REVIEW", tuple(sorted(issues)))
    try:
        measured = measure_physical_transit(
            (ev.route,), locations=ev.locations, decisions=ev.decisions, policy=ev.policy
        )[0]
        if measured.status != "MEASURED":
            return TransitLinePreview("REVIEW", measured.issue_codes)
        stored = list(
            connection.execute(
                select(cable_transit_span)
                .where(
                    cable_transit_span.c.project_id == ev.project_id,
                    cable_transit_span.c.cable_transit_route_id == row["route_id"],
                )
                .order_by(cable_transit_span.c.ordinal)
            ).mappings()
        )
        expected = [
            (
                p.span.physical_key,
                p.span.start,
                p.span.finish,
                p.geometry_m,
                ev.decisions[p.span.physical_key].mount_way,
                ev.decisions[p.span.physical_key].gofra_type,
                ev.decisions[p.span.physical_key].gofra_color,
                ev.decisions[p.span.physical_key].gofra_id,
            )
            for p in measured.measured
        ]
        actual = [
            (
                p["physical_key"],
                p["start_boundary"],
                p["end_boundary"],
                Decimal(p["geometry_m_decimal"]),
                p["mount_way"],
                p["gofra_type"] or "",
                p["gofra_color"] or "",
                p["proposed_gofra_id"] or "",
            )
            for p in stored
        ]
        if actual != expected or len({p[0] for p in expected}) != len(expected):
            return TransitLinePreview("REVIEW", ("LINE_STORED_SPANS_CHANGED",))
        quantity = calculate_cable_quantity(
            segments=[
                PhysicalCableSegment(p.span.physical_key, p.geometry_m) for p in measured.measured
            ],
            ends=[e.end for e in approval.ends],
            policy=approval.policy,
            additional_m=approval.additional_m,
            manual_full_m=approval.manual_full_m,
        )
    except (ValueError, ArithmeticError):
        return TransitLinePreview("REVIEW", ("LINE_NUMERIC_EVIDENCE_INVALID",))
    return TransitLinePreview("APPROVED_PREVIEW_ONLY", (), quantity)
