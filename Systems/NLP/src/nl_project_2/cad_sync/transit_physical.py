"""D12: physical transit spans and approval-gated length/conduit preview.

These are NOT electrical cable_segment rows. A CABLE_TRANSIT box is an
unbroken waypoint, never a splice, an ordinary source, or a cable endpoint.
No database or CAD writes occur in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
from typing import Mapping

from nl_project_2.cables.domain import (
    CablePointInput,
    ConduitContractError,
    RouteMethod,
    validate_line_conduit_fields,
)

from .cable_transit import TransitAudit, TransitRoutePreview

_ROOT_SUFFIX = "/$SOURCE"


@dataclass(frozen=True, slots=True)
class PhysicalTransitSpan:
    cable_base: str
    start: str
    finish: str
    physical_key: str


@dataclass(frozen=True, slots=True)
class PhysicalTransitRoute:
    cable_base: str
    status: str
    spans: tuple[PhysicalTransitSpan, ...]
    issue_codes: tuple[str, ...]
    # Physical BOX_INSERT positions are source evidence, not a line route.
    box_positions: tuple[tuple[str, str, str, str], ...]


@dataclass(frozen=True, slots=True)
class VerifiedLocation:
    """Explicit accepted geometry from Project/validated BOX, not a guess."""

    point: CablePointInput
    evidence: str
    confirmed: bool = False


@dataclass(frozen=True, slots=True)
class ApprovedSpanRoute:
    mount_way: str
    gofra_type: str = ""
    gofra_color: str = ""
    gofra_id: str = ""
    confirmed: bool = False


@dataclass(frozen=True, slots=True)
class TransitCalculationPolicy:
    """Caller-supplied approved Project policy, not a silent default."""

    p_nonlinearity: Decimal
    p_bypass: Decimal
    rounding_m: Decimal
    board_reserve_m: Decimal
    terminated_ends_reserve_m: Decimal
    additional_m: Decimal
    manual_full_m: Decimal | None = None


@dataclass(frozen=True, slots=True)
class MeasuredTransitSpan:
    span: PhysicalTransitSpan
    route_method: str
    geometry_m: Decimal
    corrected_m: Decimal
    conduit_id: str | None
    conduit_required: bool


@dataclass(frozen=True, slots=True)
class ConduitPreview:
    designation: str
    boundary: tuple[str, str]
    measured_m: Decimal
    cable_bases: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PhysicalTransitResult:
    cable_base: str
    status: str
    measured: tuple[MeasuredTransitSpan, ...]
    cable_length_m: Decimal | None
    conduits: tuple[ConduitPreview, ...]
    issue_codes: tuple[str, ...]


def build_physical_transit_routes(audit: TransitAudit) -> tuple[PhysicalTransitRoute, ...]:
    """Form only proven single-electrical-edge physical boundary chains."""
    results: list[PhysicalTransitRoute] = []
    for route in audit.routes:
        box_positions = tuple(
            (
                point.box_id,
                str(point.x),
                str(point.y),
                point.mount_height_mm,
            )
            for point in route.waypoints
        )
        problems = set(route.issue_codes)
        if any(issue.cable_base == route.cable_base or issue.cable_base is None for issue in audit.issues):
            problems.add("TRANSIT_UNPARSED_TOKENS_REQUIRE_REVIEW")
        if route.status != "CANDIDATE" or problems:
            results.append(
                PhysicalTransitRoute(
                    route.cable_base,
                    "REVIEW",
                    (),
                    tuple(sorted(problems)),
                    box_positions,
                )
            )
            continue
        start = route.source_point_key or f"{route.cable_base}{_ROOT_SUFFIX}"
        finish = route.target_point_key
        if not finish:
            results.append(
                PhysicalTransitRoute(
                    route.cable_base,
                    "REVIEW",
                    (),
                    ("TRANSIT_TARGET_UNRESOLVED",),
                    box_positions,
                )
            )
            continue
        vertices = (start, *(point.box_id for point in route.waypoints), finish)
        if len(set(vertices)) != len(vertices):
            results.append(
                PhysicalTransitRoute(
                    route.cable_base,
                    "REVIEW",
                    (),
                    ("TRANSIT_SELF_OR_REPEATED_BOUNDARY",),
                    box_positions,
                )
            )
            continue
        spans = tuple(
            PhysicalTransitSpan(
                route.cable_base,
                a,
                b,
                f"{route.cable_base}:{a}->{b}",
            )
            for a, b in zip(vertices, vertices[1:], strict=True)
        )
        results.append(
            PhysicalTransitRoute(route.cable_base, "CANDIDATE", spans, (), box_positions)
        )
    return tuple(results)


def _rounded(value: Decimal, quantum: Decimal) -> Decimal:
    return (value / quantum).to_integral_value(rounding=ROUND_CEILING) * quantum


def _geometry(first: CablePointInput, second: CablePointInput, method: RouteMethod) -> Decimal:
    """Approved §4 geometric metres; TIMBER carries no fictitious +0.5 m."""
    xy = abs(second.x_mm - first.x_mm) + abs(second.y_mm - first.y_mm)
    if method is RouteMethod.FLOOR:
        vertical = (
            abs(first.mount_height_mm - first.base_mark_mm)
            + abs(second.base_mark_mm - first.base_mark_mm)
            + abs(second.mount_height_mm - second.base_mark_mm)
        )
    elif method is RouteMethod.CEILING:
        first_c = first.room_height_m * 1000
        second_c = second.room_height_m * 1000
        vertical = (
            abs(first_c - first.mount_height_mm)
            + abs(second_c - first_c)
            + abs(second_c - second.mount_height_mm)
        )
    elif method in {RouteMethod.SCREED, RouteMethod.WALL, RouteMethod.TIMBER}:
        vertical = abs(second.mount_height_mm - first.mount_height_mm)
    else:
        vertical = Decimal(0)
    return (xy + vertical) / 1000


def measure_physical_transit(
    routes: tuple[PhysicalTransitRoute, ...],
    *,
    locations: Mapping[str, VerifiedLocation],
    decisions: Mapping[str, ApprovedSpanRoute],
    policy: TransitCalculationPolicy,
) -> tuple[PhysicalTransitResult, ...]:
    """Measure only explicitly evidenced/approved spans without saving them.

    Every physical boundary needs verified coordinates, mount height and room
    B/R. Each incoming hop requires its *own* approved mount/conduit decision.
    Missing evidence blocks that route and does not affect unrelated routes.
    Shared GOFRA_ID is not proof: same physical boundaries are also required.
    """
    all_results: list[PhysicalTransitResult] = []
    if (
        policy.rounding_m <= 0
        or policy.p_nonlinearity < 0
        or policy.p_bypass < 0
        or any(
            x < 0
            for x in (
                policy.board_reserve_m,
                policy.terminated_ends_reserve_m,
                policy.additional_m,
            )
        )
        or (policy.manual_full_m is not None and policy.manual_full_m < 0)
        or not all(
            x.is_finite()
            for x in (
                policy.rounding_m,
                policy.p_nonlinearity,
                policy.p_bypass,
                policy.board_reserve_m,
                policy.terminated_ends_reserve_m,
                policy.additional_m,
                *(tuple() if policy.manual_full_m is None else (policy.manual_full_m,)),
            )
        )
    ):
        raise ValueError("TRANSIT_POLICY_UNVERIFIED")
    ratio = Decimal(1) + policy.p_nonlinearity + policy.p_bypass
    # A single designated pipe must have one demonstrably identical unordered
    # physical boundary, method, type and color across *all* line candidates.
    all_conduits: dict[str, tuple[tuple[str, str], str, str, str, Decimal, set[str]]] = {}
    for route in routes:
        problems = set(route.issue_codes)
        measured: list[MeasuredTransitSpan] = []
        pending: list[tuple[str, tuple[str, str], str, str, str, Decimal]] = []
        if route.status != "CANDIDATE":
            problems.add("TRANSIT_PHYSICAL_PATH_REQUIRES_REVIEW")
        else:
            evidence_box = {
                name: (x, y, z) for name, x, y, z in route.box_positions
            }
            for span in route.spans:
                decision = decisions.get(span.physical_key)
                if decision is None or not decision.confirmed:
                    problems.add("TRANSIT_SPAN_ROUTE_NOT_APPROVED")
                    continue
                try:
                    method = RouteMethod(decision.mount_way)
                    present = validate_line_conduit_fields(
                        mount_way=decision.mount_way,
                        conduit_type=decision.gofra_type,
                        conduit_color=decision.gofra_color,
                        conduit_id=decision.gofra_id,
                    )
                except (ValueError, ConduitContractError):
                    problems.add("TRANSIT_SPAN_ROUTE_INVALID")
                    continue
                first = locations.get(span.start)
                last = locations.get(span.finish)
                if (
                    first is None
                    or last is None
                    or not first.confirmed
                    or not last.confirmed
                    or not first.evidence
                    or not last.evidence
                ):
                    problems.add("TRANSIT_GEOMETRY_NOT_VERIFIED")
                    continue
                invalid_box = False
                for identity, loc in ((span.start, first), (span.finish, last)):
                    if identity in evidence_box:
                        x, y, height = evidence_box[identity]
                        try:
                            anchored = (
                                loc.point.x_mm == Decimal(x)
                                and loc.point.y_mm == Decimal(y)
                                and loc.point.mount_height_mm == Decimal(height)
                            )
                        except (ValueError, ArithmeticError):
                            anchored = False
                        if not anchored:
                            invalid_box = True
                if invalid_box:
                    problems.add("TRANSIT_BOX_GEOMETRY_MISMATCH")
                    continue
                geometry = _geometry(first.point, last.point, method)
                corrected = geometry * ratio
                boundary = tuple(sorted((span.start, span.finish)))
                measured.append(
                    MeasuredTransitSpan(
                        span=span,
                        route_method=method.value,
                        geometry_m=geometry,
                        corrected_m=corrected,
                        conduit_id=decision.gofra_id or None,
                        conduit_required=present,
                    )
                )
                if present and not decision.gofra_id:
                    problems.add("TRANSIT_CONDUIT_ASSIGNMENT_REQUIRED")
                if present and decision.gofra_id:
                    pending.append(
                        (
                            decision.gofra_id,
                            boundary,
                            method.value,
                            decision.gofra_type,
                            decision.gofra_color,
                            geometry,
                        )
                    )

        if len(measured) != len(route.spans) or problems:
            all_results.append(
                PhysicalTransitResult(route.cable_base, "REVIEW", tuple(measured), None, (), tuple(sorted(problems)))
            )
            continue
        # Check all sharing including across cable bases before declaring PASS.
        for designation, boundary, method, kind, color, geometry in pending:
            existing = all_conduits.get(designation)
            key = (boundary, method, kind, color, geometry)
            if existing is not None and existing[:5] != key:
                problems.add("TRANSIT_CONDUIT_BOUNDARY_CONFLICT")
            else:
                if existing is None:
                    all_conduits[designation] = (*key, {route.cable_base})
                else:
                    existing[5].add(route.cable_base)
        if problems:
            all_results.append(
                PhysicalTransitResult(route.cable_base, "REVIEW", tuple(measured), None, (), tuple(sorted(problems)))
            )
            continue
        physical_total = sum((part.corrected_m for part in measured), Decimal(0))
        cable_total = (
            policy.manual_full_m
            if policy.manual_full_m is not None
            else _rounded(
                physical_total
                + policy.board_reserve_m
                + policy.terminated_ends_reserve_m
                + policy.additional_m,
                policy.rounding_m,
            )
        )
        all_results.append(
            PhysicalTransitResult(route.cable_base, "MEASURED", tuple(measured), cable_total, (), ())
        )

    # A shared pipe is never accepted based on a designation alone. Any
    # conflict invalidates *all* participating lines, including the first.
    by_designation: dict[str, set[tuple[tuple[str, str], str, str, str, Decimal]]] = {}
    affected: dict[str, set[str]] = {}
    for result in all_results:
        if result.status != "MEASURED":
            continue
        for part in result.measured:
            if part.conduit_id:
                decision = decisions[part.span.physical_key]
                key = (
                    tuple(sorted((part.span.start, part.span.finish))),
                    part.route_method,
                    decision.gofra_type,
                    decision.gofra_color,
                    part.geometry_m,
                )
                by_designation.setdefault(part.conduit_id, set()).add(key)
                affected.setdefault(part.conduit_id, set()).add(result.cable_base)
    bad = {designation for designation, keys in by_designation.items() if len(keys) != 1}
    final: list[PhysicalTransitResult] = []
    for result in all_results:
        bad_this_line = sorted(
            designation for designation in bad if result.cable_base in affected[designation]
        )
        if result.status != "MEASURED" or bad_this_line:
            issues = set(result.issue_codes)
            if bad_this_line:
                issues.add("TRANSIT_CONDUIT_BOUNDARY_CONFLICT")
            final.append(
                PhysicalTransitResult(
                    result.cable_base,
                    "REVIEW",
                    result.measured,
                    None,
                    (),
                    tuple(sorted(issues)),
                )
            )
            continue
        conduit_results = tuple(
            ConduitPreview(
                designation=designation,
                boundary=next(iter(keys))[0],
                measured_m=_rounded(next(iter(keys))[4] * ratio, policy.rounding_m),
                cable_bases=tuple(sorted(affected[designation])),
            )
            for designation, keys in sorted(by_designation.items())
            if result.cable_base in affected[designation]
        )
        final.append(
            PhysicalTransitResult(
                result.cable_base,
                "MEASURED",
                result.measured,
                result.cable_length_m,
                conduit_results,
                (),
            )
        )
    return tuple(final)
