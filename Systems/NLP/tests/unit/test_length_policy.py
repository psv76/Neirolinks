"""Accepted NL Project 3.0 route/cable quantity examples (Issue #216 Stage C)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from nl_project_2.cables.length_policy import (
    ActualCableEnd,
    LengthPolicy,
    PhysicalCableSegment,
    calculate_cable_quantity,
    calculate_conduit_quantity,
    round_up_quantity,
    route_length,
)


def segment(identity: str, length: str) -> PhysicalCableSegment:
    return PhysicalCableSegment(identity, Decimal(length))


def end(identity: str, kind: str, override: str | None = None) -> ActualCableEnd:
    return ActualCableEnd(identity, kind, None if override is None else Decimal(override))


def test_one_cable_one_conduit_geometry_percentages_and_outputs():
    policy = LengthPolicy()
    cable = calculate_cable_quantity(
        segments=[segment("S1", "10")],
        ends=[end("S1:BOARD", "BOARD"), end("S1:DEVICE", "ENDPOINT")],
        policy=policy,
    )
    tube = calculate_conduit_quantity(geometry_m="10", policy=policy)
    assert cable.geometry_m == Decimal("10")
    assert cable.routed_m == Decimal("11.5")
    assert cable.board_outputs_m == Decimal("3")
    assert cable.endpoint_outputs_m == Decimal("0.3")
    assert cable.raw_m == Decimal("14.8")
    assert cable.automatic_m == cable.final_m == Decimal("15")
    assert tube.routed_m == Decimal("11.5")
    assert tube.final_m == Decimal("12")


def test_three_physical_board_root_cables_even_one_logical_line():
    cable = calculate_cable_quantity(
        segments=[segment("S1", "2"), segment("S2", "3"), segment("S3", "4")],
        ends=[
            end("S1:BOARD", "BOARD"),
            end("S2:BOARD", "BOARD"),
            end("S3:BOARD", "BOARD"),
        ],
        policy=LengthPolicy(),
    )
    assert cable.board_outputs_m == Decimal("9")
    assert cable.geometry_m == Decimal("9")


def test_real_el_box_ends_not_transit_or_raw_graph_degree():
    cable = calculate_cable_quantity(
        segments=[segment("S1", "10")],
        ends=[
            end("BOX1:S1", "EL_BOX"),
            end("BOX1:S2", "EL_BOX"),
            end("BOX1:S3", "EL_BOX"),
            # A continuous transit has no ActualCableEnd.
        ],
        policy=LengthPolicy(),
    )
    assert cable.box_outputs_m == Decimal("0.6")


def test_two_segments_rounded_only_once_at_line_total():
    cable = calculate_cable_quantity(
        segments=[segment("A", "1.10"), segment("B", "1.10")],
        ends=[],
        policy=LengthPolicy(),
    )
    assert cable.raw_m == Decimal("2.5300")
    assert cable.final_m == Decimal("3")


@pytest.mark.parametrize(
    ("step", "value", "result"),
    [
        ("1", "0", "0"),
        ("1", "15", "15"),
        ("0.5", "14.80", "15.0"),
        ("0.5", "11.50", "11.5"),
        ("0.1", "14.80", "14.8"),
        ("0.1", "14.80000000000000000000000000001", "14.9"),
        ("0.01", "0.0001", "0.01"),
    ],
)
def test_exact_round_up_without_binary_float_or_context_truncation(step, value, result):
    assert round_up_quantity(value, step) == Decimal(result)


def test_duplicates_deduplicated_and_conflicting_geometry_rejected():
    cable = calculate_cable_quantity(
        segments=[segment("S1", "10"), segment("S1", "10.00")],
        ends=[end("E1", "ENDPOINT"), end("E1", "ENDPOINT")],
        policy=LengthPolicy(),
    )
    assert cable.geometry_m == Decimal("10")
    assert cable.endpoint_outputs_m == Decimal("0.3")
    with pytest.raises(ValueError, match="Conflicting geometry"):
        calculate_cable_quantity(
            segments=[segment("S1", "10"), segment("S1", "11")],
            ends=[],
            policy=LengthPolicy(),
        )
    with pytest.raises(ValueError, match="Conflicting termination"):
        calculate_cable_quantity(
            segments=[segment("S1", "10")],
            ends=[end("E1", "ENDPOINT"), end("E1", "EL_BOX")],
            policy=LengthPolicy(),
        )


def test_specific_termination_override_and_additional_are_absolute():
    cable = calculate_cable_quantity(
        segments=[segment("S1", "10")],
        ends=[end("BOARD1", "BOARD", "4.2"), end("BOX1", "EL_BOX", "0")],
        policy=LengthPolicy(),
        additional_m="2",
    )
    assert cable.routed_m == Decimal("11.5")
    assert cable.board_outputs_m == Decimal("4.2")
    assert cable.box_outputs_m == 0
    assert cable.additional_m == 2
    assert cable.raw_m == Decimal("17.7")
    assert cable.final_m == Decimal("18")


def test_manual_full_override_does_not_recompute_or_change_conduit():
    policy = LengthPolicy()
    cable = calculate_cable_quantity(
        segments=[segment("S1", "10")],
        ends=[end("BOARD1", "BOARD")],
        policy=policy,
        manual_full_m="40.3",
    )
    tube = calculate_conduit_quantity(geometry_m="10", policy=policy, manual_override_m="11.2")
    assert cable.automatic_m == Decimal("15")
    assert cable.final_m == Decimal("40.3")
    assert cable.source == "MANUAL"
    assert tube.automatic_m == Decimal("12")
    assert tube.final_m == Decimal("11.2")
    assert tube.source == "MANUAL"
    assert calculate_conduit_quantity(geometry_m="10", policy=policy).final_m == Decimal("12")


def test_manual_conduit_override_with_unknown_geometry_is_explicit():
    assert calculate_conduit_quantity(geometry_m=None, policy=LengthPolicy()).source == "INCOMPLETE"
    override = calculate_conduit_quantity(
        geometry_m=None, policy=LengthPolicy(), manual_override_m="8.4"
    )
    assert override.source == "MANUAL"
    assert override.final_m == Decimal("8.4")
    assert override.automatic_m is None


def test_geometry_only_for_both_percentages_no_special_timber_reserve():
    policy = LengthPolicy()
    assert route_length("10", policy) == Decimal("11.5")
    assert route_length("10", policy) == route_length("10", policy)
    # Method of laying is intentionally absent from the pure length policy.
    assert "timber" not in repr(policy).lower()


@pytest.mark.parametrize(
    ("field", "value"),
    [("rounding_step_m", "0"), ("rounding_step_m", "-1"), ("rounding_step_m", "NaN")],
)
def test_invalid_rounding_step_rejected(field, value):
    with pytest.raises(ValueError):
        policy = LengthPolicy(**{field: Decimal(value)})
        calculate_conduit_quantity(geometry_m="1", policy=policy)


@pytest.mark.parametrize("value", ["-0.1", "Infinity", "NaN", "abc"])
def test_invalid_geometry_rejected(value):
    with pytest.raises(ValueError):
        route_length(value, LengthPolicy())
