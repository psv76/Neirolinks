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
    screed, _ = calculate_automatic_length(points, RouteMethod.SCREED)
    ceiling, _ = calculate_automatic_length(points, RouteMethod.CEILING)
    timber, timber_trace = calculate_automatic_length(points, RouteMethod.TIMBER)
    channel, _ = calculate_automatic_length(points, RouteMethod.CABLE_CHANNEL)
    assert floor == Decimal("4.1")
    assert screed == Decimal("3")
    assert ceiling == Decimal("8.4")
    assert timber == Decimal("3")
    assert channel == Decimal("3")
    assert timber_trace[0]["geometry_m"] == "3"
    assert floor_trace[0]["xy_mm"] == "3000"
    assert floor_trace[0]["level_change_mm"] == "100"


def test_ceiling_ignores_structural_base_but_floor_uses_it():
    # AC-033: finished floor is the zero for both mount and ceiling height.
    # Only the structural base below it changes when base_mark_mm changes.
    original = (
        CablePointInput.from_values(
            x_mm=0, y_mm=0, mount_height_mm=300, base_mark_mm=-250, room_height_m="2.8"
        ),
        CablePointInput.from_values(
            x_mm=1000, y_mm=2000, mount_height_mm=300, base_mark_mm=-150, room_height_m="3.0"
        ),
    )
    changed_base = (
        CablePointInput.from_values(
            x_mm=0, y_mm=0, mount_height_mm=300, base_mark_mm=-600, room_height_m="2.8"
        ),
        CablePointInput.from_values(
            x_mm=1000, y_mm=2000, mount_height_mm=300, base_mark_mm=-50, room_height_m="3.0"
        ),
    )
    before_ceiling, _ = calculate_automatic_length(original, RouteMethod.CEILING)
    after_ceiling, _ = calculate_automatic_length(changed_base, RouteMethod.CEILING)
    assert before_ceiling == after_ceiling == Decimal("8.4")
    before_floor, _ = calculate_automatic_length(original, RouteMethod.FLOOR)
    after_floor, _ = calculate_automatic_length(changed_base, RouteMethod.FLOOR)
    assert before_floor == Decimal("4.1")
    assert after_floor != before_floor
