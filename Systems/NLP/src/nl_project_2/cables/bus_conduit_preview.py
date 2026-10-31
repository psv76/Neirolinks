"""Q216 read-only candidate arithmetic for *existing* singleton BUS conduits.

This is evidence for reconciling Conduit-based specification, not a write
command and not approval to publish quantities for procurement.
Requires the read-only canonical-boundary audit from PR #303.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal

from sqlalchemy import select

from nl_project_2.cables.domain import ROUTE_METHOD_BY_MOUNT_WAY, RouteMethod
from nl_project_2.cables.length_policy import LengthPolicy, calculate_conduit_quantity
from nl_project_2.cables.recalculation import cable_length_policy
from nl_project_2.persistence.schema import bus_segment, conduit

from .conduit_audit import ConduitAudit, load_conduit_membership_audit

PreviewStatus = Literal["CANDIDATE", "BLOCKED"]


@dataclass(frozen=True, slots=True)
class BusConduitQuantityPreview:
    conduit_id: str
    designation: str
    status: PreviewStatus
    bus_segment_id: str | None
    geometry_m: Decimal | None
    automatic_m: Decimal | None
    issues: tuple[str, ...]
    # No caller may silently turn this preview into approved purchase length.
    can_publish: bool = False


def _decimal(value: object) -> Decimal | None:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return parsed if parsed.is_finite() and parsed >= 0 else None


def preview_bus_conduit_candidates(
    *,
    audits: tuple[ConduitAudit, ...],
    conduit_rows: tuple[dict, ...],
    bus_segments: tuple[dict, ...],
    policy: LengthPolicy,
) -> tuple[BusConduitQuantityPreview, ...]:
    """Pure fail-closed preview. Does not change source of truth or inventory.

    Eligible: auto-created conduit with no confirmed own length, precisely
    one confirmed physical BUS CABLE member, canonical pair, matching tube
    material/color, known G, recognized protected mount route. Not a
    substitute for separate physical-run and specification acceptance.
    """

    audit_by_id = {row.conduit_id: row for row in audits}
    segments_by_id = {row["id"]: row for row in bus_segments}
    if len(audit_by_id) != len(audits) or len(segments_by_id) != len(bus_segments):
        raise ValueError("Duplicate physical audit or BUS segment identity")

    results: list[BusConduitQuantityPreview] = []
    for tube in sorted(conduit_rows, key=lambda row: (str(row["designation"]), str(row["id"]))):
        path = tube.get("path_json") or {}
        if not isinstance(path, dict) or path.get("origin") != "AUTO_BUS_SEGMENT":
            continue
        if tube.get("length_m_decimal") is not None:
            continue  # Already owns a length: no proposal to overwrite it.
        audit = audit_by_id.get(tube["id"])
        issues: list[str] = []
        bus_id = None
        geometry = None
        automatic = None

        if audit is None:
            issues.append("PHYSICAL_AUDIT_MISSING")
        else:
            if audit.state != "PHYSICAL_MATCH" or audit.physical_span is None:
                issues.append(f"Q03_{audit.state}")
            if audit.ordinary_count or audit.bus_count != 1:
                issues.append("NOT_SINGLE_BUS_ONLY")
            if (
                audit.state == "PHYSICAL_MATCH"
                and audit.bus_count == 1
                and not audit.ordinary_count
            ):
                bus_id = next(mid for kind, mid in audit.member_keys if kind == "BUS")
                segment = segments_by_id.get(bus_id)
                if segment is None:
                    issues.append("BUS_SEGMENT_MISSING")
                else:
                    if segment.get("connection_kind") != "CABLE":
                        issues.append("NOT_PHYSICAL_BUS_CABLE")
                    if segment.get("migration_state") != "CONFIRMED":
                        issues.append("BUS_GEOMETRY_NOT_CONFIRMED")
                    route = ROUTE_METHOD_BY_MOUNT_WAY.get(str(segment.get("mount_way") or ""))
                    if route is None or route == RouteMethod.CABLE_CHANNEL:
                        issues.append("PROTECTED_MOUNT_WAY_NOT_CONFIRMED")
                    if (
                        str(segment.get("gofra_type") or "").strip()
                        != str(tube.get("conduit_type") or "").strip()
                    ):
                        issues.append("CONDUIT_TYPE_MISMATCH")
                    if (
                        str(segment.get("gofra_color") or "").strip().casefold()
                        != str(tube.get("color") or "").strip().casefold()
                    ):
                        issues.append("CONDUIT_COLOR_MISMATCH")
                    geometry = _decimal(segment.get("length_m_decimal"))
                    if geometry is None:
                        issues.append("BUS_GEOMETRY_MISSING")
                    if not issues:
                        automatic = calculate_conduit_quantity(
                            geometry_m=geometry, policy=policy
                        ).automatic_m
        results.append(
            BusConduitQuantityPreview(
                conduit_id=tube["id"],
                designation=tube["designation"],
                status="CANDIDATE" if not issues else "BLOCKED",
                bus_segment_id=bus_id,
                geometry_m=geometry,
                automatic_m=automatic,
                issues=tuple(issues),
            )
        )
    return tuple(results)


def load_bus_conduit_quantity_preview(
    connection, project_id: str
) -> tuple[BusConduitQuantityPreview, ...]:
    """SELECT-only adapter; never writes quantities to Conduit or Specification."""

    audit = load_conduit_membership_audit(connection, project_id)
    conduits = tuple(
        dict(row)
        for row in connection.execute(
            select(conduit).where(
                conduit.c.project_id == project_id,
                conduit.c.lifecycle == "ACTIVE",
            )
        ).mappings()
    )
    segments = tuple(
        dict(row)
        for row in connection.execute(
            select(bus_segment).where(bus_segment.c.project_id == project_id)
        ).mappings()
    )
    settings = cable_length_policy(connection, project_id)
    policy = LengthPolicy(
        nonlinearity_percent=settings.meander_percent,
        bypass_percent=settings.obstacle_percent,
        rounding_step_m=settings.rounding_step_m,
    )
    return preview_bus_conduit_candidates(
        audits=audit, conduit_rows=conduits, bus_segments=segments, policy=policy
    )
