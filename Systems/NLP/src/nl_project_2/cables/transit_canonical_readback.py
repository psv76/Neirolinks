"""D17: verify prepared transit quantities against *current* canonical owners.

Read-only qualification for a future revision-aware source switch. This module
MUST NOT publish cable_length_fact, alter legacy CableSegment / Conduit, or
turn an acknowledged preview into a production bill-of-materials quantity.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from sqlalchemy import Connection, select

from nl_project_2.cad_sync.transit_physical_store import approved_transit_sha256
from nl_project_2.persistence.schema import (
    cable_length_fact,
    cable_line,
    cable_segment,
    cable_transit_line_commit,
    cable_transit_route,
)

from .transit_line_preview import (
    TransitLineApproval,
    preview_transit_line,
    transit_line_approval_sha256,
)


@dataclass(frozen=True, slots=True)
class TransitCanonicalReadback:
    cable_line_id: str
    status: str
    issues: tuple[str, ...]
    prepared_automatic_m: Decimal | None = None
    prepared_final_m: Decimal | None = None
    legacy_calculated_m: Decimal | None = None
    legacy_manual_m: Decimal | None = None
    # Never infer these are authoritative or published.
    authoritative_m: None = None
    conduit_quantity_m: None = None


def _number(value: object, *, allow_none: bool = False) -> Decimal | None:
    if value is None and allow_none:
        return None
    try:
        number = Decimal(str(value))
    except (ValueError, InvalidOperation, TypeError):
        return None
    if not number.is_finite() or number < 0:
        return None
    return number


def review_prepared_transit_for_canonical(
    connection: Connection,
    approval: TransitLineApproval,
    *,
    expected_batch_sha256: str,
    confirmed: bool = False,
) -> TransitCanonicalReadback:
    """Compare an immutable D16 receipt with fresh D15/D14 + canonical state.

    No source switch is possible here. In particular, the current geometry of
    accepted DWG endpoints and real termination classification cannot be
    independently proven from a D16 receipt: that still needs Windows/DWG
    review before ordinary specifications are allowed to consume these totals.
    """
    ev = approval.transit
    issues: set[str] = set()
    receipt = (
        connection.execute(
            select(cable_transit_line_commit).where(
                cable_transit_line_commit.c.project_id == ev.project_id,
                cable_transit_line_commit.c.cable_line_id == ev.cable_line_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if receipt is None:
        return TransitCanonicalReadback(
            ev.cable_line_id, "REVIEW", ("TRANSIT_D16_RECEIPT_MISSING",)
        )
    if (
        not confirmed
        or len(expected_batch_sha256) != 64
        or expected_batch_sha256 != receipt["approval_sha256"]
        or not receipt["approval_evidence"]
        or receipt["state"] != "PREPARED_APPROVED"
    ):
        issues.add("TRANSIT_D16_RECEIPT_NOT_CONFIRMED")
    if receipt["transit_approval_sha256"] != transit_line_approval_sha256(approval):
        issues.add("TRANSIT_D15_APPROVAL_STALE")

    line = (
        connection.execute(
            select(cable_line).where(
                cable_line.c.id == ev.cable_line_id,
                cable_line.c.project_id == ev.project_id,
                cable_line.c.lifecycle == "ACTIVE",
            )
        )
        .mappings()
        .one_or_none()
    )
    if line is None or line["row_version"] != receipt["line_row_version_at_approval"]:
        issues.add("TRANSIT_D16_LINE_CHANGED")

    segment = (
        connection.execute(
            select(cable_segment).where(
                cable_segment.c.id == ev.electrical_segment_id,
                cable_segment.c.project_id == ev.project_id,
                cable_segment.c.cable_line_id == ev.cable_line_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if (
        segment is None
        or segment["row_version"] != receipt["segment_row_version_at_approval"]
        or segment["source_endpoint_id"] != ev.source_endpoint_id
        or segment["target_endpoint_id"] != ev.target_endpoint_id
        or receipt["electrical_segment_id"] != ev.electrical_segment_id
    ):
        issues.add("TRANSIT_D16_ELECTRICAL_EDGE_CHANGED")

    transit = (
        connection.execute(
            select(cable_transit_route).where(
                cable_transit_route.c.id == receipt["cable_transit_route_id"],
                cable_transit_route.c.project_id == ev.project_id,
                cable_transit_route.c.cable_line_id == ev.cable_line_id,
                cable_transit_route.c.electrical_segment_id == ev.electrical_segment_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if (
        transit is None
        or transit["approved_plan_sha256"] != approved_transit_sha256(ev)
        or transit["state"] != "STAGED_APPROVED"
    ):
        issues.add("TRANSIT_D13_ROUTE_CHANGED")

    fact = (
        connection.execute(
            select(cable_length_fact).where(
                cable_length_fact.c.project_id == ev.project_id,
                cable_length_fact.c.cable_line_id == ev.cable_line_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if fact is None:
        if (
            receipt["length_fact_id_at_approval"] is not None
            or receipt["length_fact_row_version_at_approval"] is not None
        ):
            issues.add("TRANSIT_D16_LENGTH_FACT_CHANGED")
        actual_manual = None
        actual_additional = Decimal(0)
        original_automatic = None
    else:
        if (
            fact["id"] != receipt["length_fact_id_at_approval"]
            or fact["row_version"] != receipt["length_fact_row_version_at_approval"]
        ):
            issues.add("TRANSIT_D16_LENGTH_FACT_CHANGED")
        actual_manual = _number(fact["manual_full_length_m_decimal"], allow_none=True)
        actual_additional = _number(fact["additional_length_m_decimal"] or "0")
        original_automatic = _number(fact["calculated_length_m_decimal"], allow_none=True)
        if (
            actual_additional is None
            or (fact["manual_full_length_m_decimal"] is not None and actual_manual is None)
            or (fact["calculated_length_m_decimal"] is not None and original_automatic is None)
        ):
            issues.add("TRANSIT_CANONICAL_LENGTH_FACT_INVALID")

    if actual_additional != _number(approval.additional_m) or actual_manual != _number(
        approval.manual_full_m, allow_none=True
    ):
        issues.add("TRANSIT_D16_MANUAL_OR_ADDITIONAL_CHANGED")

    # The exact D15 read-only guard rechecks all D14 ordinary/BUS Conduit
    # collisions, accepted BOX membership, geometry evidence and real ends.
    recalculated = preview_transit_line(
        connection,
        approval,
        approved_sha256=transit_line_approval_sha256(approval),
        confirmed=True,
    )
    if recalculated.status != "APPROVED_PREVIEW_ONLY" or recalculated.quantity is None:
        issues.update(recalculated.issues or ("TRANSIT_D15_CANDIDATE_NO_LONGER_VALID",))

    approved_automatic = _number(receipt["automatic_length_m_decimal"])
    approved_final = _number(receipt["final_length_m_decimal"])
    breakdown = receipt["calculation_snapshot_json"]
    if (
        approved_automatic is None
        or approved_final is None
        or not isinstance(breakdown, dict)
        or receipt["source"] not in {"AUTOMATIC", "MANUAL"}
    ):
        issues.add("TRANSIT_D16_QUANTITY_INVALID")
    elif recalculated.quantity is not None:
        quantity = recalculated.quantity
        if (
            approved_automatic != quantity.automatic_m
            or approved_final != quantity.final_m
            or receipt["source"] != quantity.source
            or any(
                _number(breakdown.get(key)) != getattr(quantity, key)
                for key in (
                    "geometry_m",
                    "routed_m",
                    "board_outputs_m",
                    "box_outputs_m",
                    "endpoint_outputs_m",
                    "additional_m",
                    "raw_m",
                    "automatic_m",
                    "final_m",
                )
            )
            or breakdown.get("source") != quantity.source
        ):
            issues.add("TRANSIT_D16_BREAKDOWN_MISMATCH")

    # No automatic adoption on numerical parity: the legacy algorithm and
    # a real physical-transit algorithm represent distinct route contracts.
    return TransitCanonicalReadback(
        cable_line_id=ev.cable_line_id,
        status="REVIEW" if issues else "VERIFIED_READBACK_ONLY",
        issues=tuple(sorted(issues)),
        prepared_automatic_m=approved_automatic,
        prepared_final_m=approved_final,
        legacy_calculated_m=original_automatic,
        legacy_manual_m=actual_manual,
    )
