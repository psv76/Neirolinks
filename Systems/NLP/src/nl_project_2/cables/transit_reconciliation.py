"""D14: read-only reconciliation of staged transit with canonical cable quantities.

This is a *shadow*, not an authorization to recalculate cable_length_fact,
replace existing cable_segment edges, merge a Conduit, or write DWG. Rejected or
stale physical evidence never contributes to a candidate quantity.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation

from sqlalchemy import Connection, select

from nl_project_2.persistence.schema import (
    bus_segment,
    cable_line,
    cable_segment,
    cable_transit_route,
    cable_transit_span,
    conduit,
    field_device,
)


def _nonnegative(value: object) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return result if result.is_finite() and result >= 0 else None


def _physical_boundary(start: str, end: str) -> tuple[str, str]:
    return tuple(sorted((start, end)))


def staged_transit_reconciliation(connection: Connection, project_id: str) -> dict:
    """Render one independently auditable, side-effect-free Project snapshot.

    Proposals and actual canonical amounts deliberately occupy separate keys.
    Existing untyped ordinary/BUS Conduit records cannot prove shared physical
    boundaries, even if their designation coincides with staged GOFRA_ID.
    """
    routes = list(
        connection.execute(
            select(cable_transit_route)
            .where(cable_transit_route.c.project_id == project_id)
            .order_by(cable_transit_route.c.cable_base, cable_transit_route.c.id)
        ).mappings()
    )
    segment_ids = {route["electrical_segment_id"] for route in routes}
    lines = {
        row["id"]: row
        for row in connection.execute(
            select(cable_line).where(cable_line.c.project_id == project_id)
        ).mappings()
    }
    segments = {
        row["id"]: row
        for row in connection.execute(
            select(cable_segment).where(cable_segment.c.project_id == project_id)
        ).mappings()
    }
    line_segments: dict[str, int] = defaultdict(int)
    for segment in segments.values():
        line_segments[segment["cable_line_id"]] += 1

    # Do not mistake matching route labels for physical identity.
    box_owners: dict[str, list[dict]] = defaultdict(list)
    for row in connection.execute(
        select(field_device.c.normalized_fields_json)
        .where(
            field_device.c.project_id == project_id,
            field_device.c.block_kind == "EL_BOX_OUT_100x100",
            field_device.c.lifecycle == "ACTIVE",
        )
    ).scalars():
        fields = dict(row or {})
        box_id = str(fields.get("BOX_ID") or "").strip()
        if box_id:
            box_owners[box_id].append(fields)

    canonical_designations = {
        str(row)
        for row in connection.execute(
            select(conduit.c.designation).where(
                conduit.c.project_id == project_id,
                conduit.c.lifecycle == "ACTIVE",
            )
        ).scalars()
    }
    bus_designations = {
        str(value)
        for value in connection.execute(
            select(bus_segment.c.gofra_id).where(
                bus_segment.c.project_id == project_id,
                bus_segment.c.connection_kind == "CABLE",
                bus_segment.c.gofra_id.is_not(None),
            )
        ).scalars()
        if str(value).strip()
    }

    drafts: list[dict] = []
    physical_conduits: dict[str, list[tuple[dict, tuple, Decimal]]] = defaultdict(list)
    for route in routes:
        issues: set[str] = set()
        spans = list(
            connection.execute(
                select(cable_transit_span)
                .where(
                    cable_transit_span.c.project_id == project_id,
                    cable_transit_span.c.cable_transit_route_id == route["id"],
                )
                .order_by(cable_transit_span.c.ordinal, cable_transit_span.c.id)
            ).mappings()
        )
        electrical = segments.get(route["electrical_segment_id"])
        line = lines.get(route["cable_line_id"])
        if (
            line is None
            or line["lifecycle"] != "ACTIVE"
            or line["designation"] != route["cable_base"]
            or electrical is None
            or electrical["cable_line_id"] != route["cable_line_id"]
        ):
            issues.add("TRANSIT_CANONICAL_OWNER_STALE")
        elif (
            electrical["row_version"] != route["segment_row_version_at_approval"]
            or electrical["source_endpoint_id"] != route["source_endpoint_id_at_approval"]
            or electrical["target_endpoint_id"] != route["target_endpoint_id_at_approval"]
        ):
            issues.add("TRANSIT_ELECTRICAL_EDGE_CHANGED")
        if line_segments.get(route["cable_line_id"], 0) != 1:
            # Reserves belong to the entire line; multi-edge shared trunks
            # cannot be combined from per-edge D13 approval lengths.
            issues.add("TRANSIT_LINE_COVERAGE_REQUIRES_REVIEW")
        if route["state"] != "STAGED_APPROVED" or not route["approval_evidence"]:
            issues.add("TRANSIT_APPROVAL_MISSING")
        if len(spans) < 2 or [s["ordinal"] for s in spans] != list(range(1, len(spans) + 1)):
            issues.add("TRANSIT_SPAN_SEQUENCE_INVALID")
        if any(a["end_boundary"] != b["start_boundary"] for a, b in zip(spans, spans[1:], strict=False)):
            issues.add("TRANSIT_SPAN_CHAIN_BROKEN")
        if spans and len({spans[0]["start_boundary"], *(s["end_boundary"] for s in spans)}) != len(spans) + 1:
            issues.add("TRANSIT_SPAN_BOUNDARY_REPEATED")
        if any(
            s["physical_key"] != (
                f"{route['cable_base']}:{s['start_boundary']}->{s['end_boundary']}"
            )
            for s in spans
        ):
            issues.add("TRANSIT_PHYSICAL_KEY_CHANGED")

        # Every internal boundary must still be accepted as a transit box for
        # this exact cable base; a renamed/deleted BOX makes the plan stale.
        if spans:
            for middle in [part["end_boundary"] for part in spans[:-1]]:
                owners = [
                    fields for fields in box_owners.get(middle, [])
                    if any(
                        token.strip().split("-", 1)[0] == route["cable_base"]
                        for token in str(fields.get("CABLE_TRANSIT") or "").split(";")
                    )
                ]
                if len(owners) != 1:
                    issues.add("TRANSIT_BOX_ACCEPTANCE_CHANGED")

        raw_geometry = Decimal(0)
        raw_corrected = Decimal(0)
        for part in spans:
            geom = _nonnegative(part["geometry_m_decimal"])
            corrected = _nonnegative(part["corrected_m_decimal"])
            if geom is None or corrected is None:
                issues.add("TRANSIT_STAGED_LENGTH_INVALID")
                continue
            raw_geometry += geom
            raw_corrected += corrected
            designation = str(part["proposed_gofra_id"] or "").strip()
            if designation:
                spec = (
                    _physical_boundary(part["start_boundary"], part["end_boundary"]),
                    part["mount_way"],
                    part["gofra_type"] or "",
                    part["gofra_color"] or "",
                    geom,
                )
                physical_conduits[designation].append((route, spec, corrected))

        drafts.append(
            {
                "route_id": route["id"],
                "cable_line_id": route["cable_line_id"],
                "cable_base": route["cable_base"],
                "electrical_segment_id": route["electrical_segment_id"],
                "approval_sha256": route["approved_plan_sha256"],
                "staged_span_count": len(spans),
                "staged_geometry_m": str(raw_geometry),
                "staged_corrected_m": str(raw_corrected),
                "original_preview_length_m": route["preview_cable_length_m_decimal"],
                "issues": issues,
            }
        )

    conduit_issues: dict[str, set[str]] = defaultdict(set)
    conduit_results: list[dict] = []
    for designation, members in sorted(physical_conduits.items()):
        signatures = {spec for _route, spec, _corrected in members}
        owners = sorted({route["cable_base"] for route, _spec, _corrected in members})
        if len(signatures) != 1:
            reason = "TRANSIT_CONDUIT_BOUNDARY_CONFLICT"
        elif designation in canonical_designations:
            reason = "TRANSIT_CANONICAL_CONDUIT_BOUNDARY_UNPROVEN"
        elif designation in bus_designations:
            reason = "TRANSIT_BUS_CONDUIT_BOUNDARY_UNPROVEN"
        else:
            reason = ""
        if reason:
            for route, _spec, _corrected in members:
                conduit_issues[route["id"]].add(reason)
        conduit_results.append(
            {
                "designation": designation,
                "cable_bases": tuple(owners),
                "status": "REVIEW" if reason else "CANDIDATE_ONLY",
                "issues": (reason,) if reason else (),
                "physical_boundary": next(iter(signatures))[0] if len(signatures) == 1 else None,
                # Geometry is shown once per distinct proposed pipe, not once
                # per cable sharing it. It is NOT a rounded/specification length.
                "unique_geometry_m": str(next(iter(signatures))[4]) if len(signatures) == 1 else None,
            }
        )

    summaries: list[dict] = []
    for draft in drafts:
        issues = draft.pop("issues") | conduit_issues.get(draft["route_id"], set())
        summaries.append(
            {
                **draft,
                "status": "REVIEW" if issues else "STAGED_READ_ONLY",
                "issues": tuple(sorted(issues)),
                # No final cable/Conduit quantity is authorized at D14:
                # D13 per-edge totals include reserves and cannot be summed.
                "authoritative_cable_m": None,
                "authoritative_conduit_m": None,
            }
        )
    unique_geometry = sum(
        (
            Decimal(x["unique_geometry_m"])
            for x in conduit_results
            if x["status"] == "CANDIDATE_ONLY" and x["unique_geometry_m"] is not None
        ),
        Decimal(0),
    )
    return {
        "routes": tuple(summaries),
        "conduits": tuple(conduit_results),
        "uncommitted_unique_conduit_geometry_m": str(unique_geometry),
        "review_count": sum(row["status"] == "REVIEW" for row in summaries),
        "mode": "READ_ONLY_NO_CANONICAL_QUANTITY_CHANGE",
    }
