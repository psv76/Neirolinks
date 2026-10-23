"""Exact, side-effect-free geometry-to-quantity policy for NL Project 3.0.

The caller MUST resolve actual physical terminations and each conduit geometry.
No graph degree, board-output count, or segment count is an allowable proxy.
This module deliberately does not read/write the database or DWG and is not yet
wired to the legacy recalculation services (Issue #216, Stage C).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, getcontext, localcontext
from typing import Literal

TerminationKind = Literal["BOARD", "EL_BOX", "ENDPOINT"]


def _length(value: object, *, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field} must be a finite nonnegative Decimal") from exc
    if not result.is_finite() or result < 0:
        raise ValueError(f"{field} must be a finite nonnegative Decimal")
    return result


@dataclass(frozen=True, slots=True)
class LengthPolicy:
    nonlinearity_percent: Decimal = Decimal("5")
    bypass_percent: Decimal = Decimal("10")
    rounding_step_m: Decimal = Decimal("1")
    board_end_m: Decimal = Decimal("3")
    box_end_m: Decimal = Decimal("0.2")
    endpoint_end_m: Decimal = Decimal("0.3")

    def route_factor(self) -> Decimal:
        nonlinearity = _length(self.nonlinearity_percent, field="nonlinearity_percent")
        bypass = _length(self.bypass_percent, field="bypass_percent")
        return Decimal("1") + (nonlinearity + bypass) / Decimal("100")

    def rounding_step(self) -> Decimal:
        step = _length(self.rounding_step_m, field="rounding_step_m")
        if step <= 0:
            raise ValueError("rounding_step_m must be positive")
        return step


@dataclass(frozen=True, slots=True)
class PhysicalCableSegment:
    segment_id: str
    geometry_m: Decimal


@dataclass(frozen=True, slots=True)
class ActualCableEnd:
    """One real cable termination, not merely a topology endpoint.

    Override is per physical end. Continuous transit through an EL_BOX must not
    create an ActualCableEnd. Multiple roots from one BOARD_OUTPUT are distinct.
    """

    end_id: str
    kind: TerminationKind
    override_m: Decimal | None = None


@dataclass(frozen=True, slots=True)
class CableQuantity:
    geometry_m: Decimal
    routed_m: Decimal
    board_outputs_m: Decimal
    box_outputs_m: Decimal
    endpoint_outputs_m: Decimal
    additional_m: Decimal
    raw_m: Decimal
    automatic_m: Decimal
    final_m: Decimal
    source: Literal["AUTOMATIC", "MANUAL"]


@dataclass(frozen=True, slots=True)
class ConduitQuantity:
    geometry_m: Decimal | None
    routed_m: Decimal | None
    automatic_m: Decimal | None
    final_m: Decimal | None
    source: Literal["AUTOMATIC", "MANUAL", "INCOMPLETE"]


def round_up_quantity(length_m: object, step_m: object) -> Decimal:
    """Decimal-safe upward rounding, including exact multiples and zero."""

    length = _length(length_m, field="length_m")
    step = _length(step_m, field="step_m")
    if step <= 0:
        raise ValueError("step_m must be positive")
    # Decimal division uses a finite working precision and can round away a
    # very small positive excess above an exact multiple. Work with exact
    # rational numerator/denominator instead, then convert the count to meters.
    length_n, length_d = length.as_integer_ratio()
    step_n, step_d = step.as_integer_ratio()
    numerator = length_n * step_d
    denominator = length_d * step_n
    count = (numerator + denominator - 1) // denominator
    with localcontext() as context:
        context.prec = max(getcontext().prec, len(str(count)) + len(step.as_tuple().digits) + 2)
        return Decimal(count) * step


def route_length(geometry_m: object, policy: LengthPolicy) -> Decimal:
    """Two additive route reserves on geometry only, never on terminations."""

    return _length(geometry_m, field="geometry_m") * policy.route_factor()


def calculate_cable_quantity(
    *,
    segments: Iterable[PhysicalCableSegment],
    ends: Iterable[ActualCableEnd],
    policy: LengthPolicy,
    additional_m: object = Decimal("0"),
    manual_full_m: object | None = None,
) -> CableQuantity:
    """Sum each physical cable segment once; round once per entire CableLine."""

    policy.rounding_step()
    policy.route_factor()
    geometry_by_id: dict[str, Decimal] = {}
    for segment in segments:
        if not segment.segment_id:
            raise ValueError("PhysicalCableSegment must have a segment_id")
        geometry = _length(segment.geometry_m, field="geometry_m")
        prior = geometry_by_id.setdefault(segment.segment_id, geometry)
        if prior != geometry:
            raise ValueError(f"Conflicting geometry for segment {segment.segment_id}")

    by_end_id: dict[str, tuple[str, Decimal]] = {}
    allowances = {"BOARD": Decimal("0"), "EL_BOX": Decimal("0"), "ENDPOINT": Decimal("0")}
    configured = {
        "BOARD": _length(policy.board_end_m, field="board_end_m"),
        "EL_BOX": _length(policy.box_end_m, field="box_end_m"),
        "ENDPOINT": _length(policy.endpoint_end_m, field="endpoint_end_m"),
    }
    for end in ends:
        if not end.end_id:
            raise ValueError("ActualCableEnd must have an end_id")
        if end.kind not in allowances:
            raise ValueError(f"Unsupported physical end kind: {end.kind}")
        allowance = (
            configured[end.kind]
            if end.override_m is None
            else _length(end.override_m, field="end.override_m")
        )
        identity = (end.kind, allowance)
        if end.end_id in by_end_id:
            if by_end_id[end.end_id] != identity:
                raise ValueError(f"Conflicting termination identity: {end.end_id}")
            continue
        by_end_id[end.end_id] = identity
        allowances[end.kind] += allowance

    geometry_m = sum(geometry_by_id.values(), Decimal("0"))
    routed_m = route_length(geometry_m, policy)
    additional = _length(additional_m, field="additional_m")
    raw = routed_m + sum(allowances.values(), Decimal("0")) + additional
    automatic = round_up_quantity(raw, policy.rounding_step())
    manual = None if manual_full_m is None else _length(manual_full_m, field="manual_full_m")
    return CableQuantity(
        geometry_m=geometry_m,
        routed_m=routed_m,
        board_outputs_m=allowances["BOARD"],
        box_outputs_m=allowances["EL_BOX"],
        endpoint_outputs_m=allowances["ENDPOINT"],
        additional_m=additional,
        raw_m=raw,
        automatic_m=automatic,
        final_m=automatic if manual is None else manual,
        source="AUTOMATIC" if manual is None else "MANUAL",
    )


def calculate_conduit_quantity(
    *,
    geometry_m: object | None,
    policy: LengthPolicy,
    manual_override_m: object | None = None,
) -> ConduitQuantity:
    """Compute each physical Conduit once, regardless of assigned cable count."""

    step = policy.rounding_step()
    policy.route_factor()
    geometry = None if geometry_m is None else _length(geometry_m, field="geometry_m")
    routed = None if geometry is None else route_length(geometry, policy)
    automatic = None if routed is None else round_up_quantity(routed, step)
    manual = (
        None if manual_override_m is None else _length(manual_override_m, field="manual_override_m")
    )
    if manual is not None:
        source: Literal["AUTOMATIC", "MANUAL", "INCOMPLETE"] = "MANUAL"
    elif automatic is None:
        source = "INCOMPLETE"
    else:
        source = "AUTOMATIC"
    return ConduitQuantity(
        geometry_m=geometry,
        routed_m=routed,
        automatic_m=automatic,
        final_m=manual if manual is not None else automatic,
        source=source,
    )
