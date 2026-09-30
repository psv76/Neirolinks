from decimal import Decimal

from nl_project_2.cables import CablePointInput, RouteMethod, calculate_automatic_length


def test_ac_033_exact_floor_ceiling_and_channel_formulas():
    points = (
        CablePointInput.from_values(
            x_mm=0,
            y_mm=0,
            mount_height_mm=300,
            base_mark_mm=-250,
            room_height_m="2.8",
        ),
        CablePointInput.from_values(
            x_mm=1000,
            y_mm=2000,
            mount_height_mm=300,
            base_mark_mm=-150,
            room_height_m="3.0",
        ),
    )
    floor, floor_trace = calculate_automatic_length(points, RouteMethod.FLOOR)
    ceiling, _ = calculate_automatic_length(points, RouteMethod.CEILING)
    channel, _ = calculate_automatic_length(points, RouteMethod.CABLE_CHANNEL)
    assert floor == Decimal("4.1")
    assert ceiling == Decimal("8.4")
    assert channel == Decimal("3")
    assert floor_trace[0]["xy_mm"] == "3000"
    assert floor_trace[0]["level_change_mm"] == "100"


def test_timber_segment_adds_half_meter_only_to_cable_length():
    points = (
        CablePointInput.from_values(
            x_mm=0,
            y_mm=0,
            mount_height_mm=300,
            base_mark_mm=-250,
            room_height_m="2.8",
        ),
        CablePointInput.from_values(
            x_mm=1000,
            y_mm=2000,
            mount_height_mm=600,
            base_mark_mm=-150,
            room_height_m="3.0",
        ),
    )
    total, trace = calculate_automatic_length(points, RouteMethod.TIMBER)
    assert total == Decimal("3.8")
    assert trace[0]["geometry_length_m"] == "3.3"
    assert trace[0]["cable_reserve_m"] == "0.5"
    assert trace[0]["length_m"] == "3.8"

