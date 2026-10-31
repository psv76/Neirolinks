"""Q216 SELECT-derived, non-publishable one-source-per-Conduit quantity plan.

This is a shadow Specification proposal. It does not change Specification
build(), procurement, Conduit lengths, BUS segment lengths, or any overrides.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal

from nl_project_2.cables.bus_conduit_preview import BusConduitQuantityPreview
from nl_project_2.cables.conduit_audit import ConduitAudit

DecisionStatus = Literal[
    "KNOWN_SINGLE",
    "CANDIDATE_BUS",
    "BLOCKED_EMPTY",
    "BLOCKED_SHARED",
    "BLOCKED_UNRESOLVED",
    "BLOCKED_UNKNOWN_LENGTH",
    "BLOCKED_BUS",
]


@dataclass(frozen=True, slots=True)
class ConduitSpecificationDecision:
    conduit_id: str
    designation: str
    status: DecisionStatus
    quantity_m: Decimal | None
    stored_m: Decimal | None
    ordinary_count: int
    bus_count: int
    issues: tuple[str, ...]
    can_publish: bool = False


def _known_m(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        number = Decimal(str(value))
    except (TypeError, InvalidOperation, ValueError):
        return None
    return number if number.is_finite() and number >= 0 else None


def plan_conduit_specification(
    *,
    conduits: tuple[dict, ...],
    audits: tuple[ConduitAudit, ...],
    bus_previews: tuple[BusConduitQuantityPreview, ...],
) -> tuple[ConduitSpecificationDecision, ...]:
    """All active Conduit IDs exactly once; unsafe quantities stay None.

    A BUS candidate has a calculated Q08 quantity but not a published quantity.
    Known single ordinary tubes use already stored Conduit quantities; they
    are not recalculated here. Empty, shared and unresolved physical tubes are
    explicitly blocked rather than silently retaining, duplicating or zeroing.
    """

    audit_map = {row.conduit_id: row for row in audits}
    preview_map = {row.conduit_id: row for row in bus_previews}
    conduit_ids = [row["id"] for row in conduits]
    if len(set(conduit_ids)) != len(conduits):
        raise ValueError("Duplicate active Conduit id")
    if len(audit_map) != len(audits) or len(preview_map) != len(bus_previews):
        raise ValueError("Duplicate Q03 audit or BUS preview")
    if set(audit_map) != set(conduit_ids):
        raise ValueError("Q03 audit must cover exactly the active Conduit IDs")
    if not set(preview_map).issubset(conduit_ids):
        raise ValueError("BUS preview has unknown Conduit")

    results: list[ConduitSpecificationDecision] = []
    for tube in sorted(conduits, key=lambda row: (str(row["designation"]), str(row["id"]))):
        identifier = tube["id"]
        audit = audit_map[identifier]
        preview = preview_map.get(identifier)
        stored = _known_m(tube.get("length_m_decimal"))
        path = tube.get("path_json") or {}
        origin = path.get("origin") if isinstance(path, dict) else None
        issues: list[str] = []
        value = None

        if audit.state == "EMPTY":
            status: DecisionStatus = "BLOCKED_EMPTY"
            issues.append(
                "EMPTY_WITH_SAVED_LENGTH" if stored is not None else "EMPTY_WITHOUT_MEMBER"
            )
        elif audit.state != "PHYSICAL_MATCH" or audit.physical_span is None:
            status = "BLOCKED_UNRESOLVED"
            issues.append(f"Q03_{audit.state}")
        elif audit.ordinary_count + audit.bus_count != 1:
            status = "BLOCKED_SHARED"
            issues.append("MULTIPLE_MEMBERS_REQUIRE_Q03_Q06_COMPATIBILITY")
        elif audit.bus_count:
            if origin != "AUTO_BUS_SEGMENT" or preview is None or preview.status != "CANDIDATE":
                status = "BLOCKED_BUS"
                issues.append("BUS_CONDUIT_CONFIRMATION_MISSING")
                if preview is not None:
                    issues.extend(preview.issues)
            elif stored is not None:
                status = "BLOCKED_BUS"
                issues.append("EXISTING_BUS_CONDUIT_LENGTH_REQUIRES_RECONCILIATION")
            else:
                status = "CANDIDATE_BUS"
                value = preview.automatic_m
                if value is None:
                    raise ValueError("BUS candidate has no calculated quantity")
        elif origin == "AUTO_BUS_SEGMENT":
            status = "BLOCKED_BUS"
            issues.append("BUS_ORIGIN_CONDUIT_HAS_ORDINARY_MEMBER")
        elif stored is None:
            status = "BLOCKED_UNKNOWN_LENGTH"
            issues.append("SINGLE_ORDINARY_CONDUIT_LENGTH_UNKNOWN")
        else:
            status = "KNOWN_SINGLE"
            value = stored

        results.append(
            ConduitSpecificationDecision(
                conduit_id=identifier,
                designation=tube["designation"],
                status=status,
                quantity_m=value,
                stored_m=stored,
                ordinary_count=audit.ordinary_count,
                bus_count=audit.bus_count,
                issues=tuple(issues),
            )
        )
    return tuple(results)
