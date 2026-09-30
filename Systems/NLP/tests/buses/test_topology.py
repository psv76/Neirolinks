from decimal import Decimal

from nl_project_2.buses import TopologyPoint, branched_topology, rs485_topology


def _point(identifier, suffix, x, y, base="901"):
    rendered = f"{int(suffix):03d}" if str(suffix).isdigit() else str(suffix)
    return TopologyPoint(identifier, f"{base}.{rendered}", Decimal(x), Decimal(y))


def test_rs485_orders_four_points_detects_break_and_forbids_branch_semantics():
    points = (
        _point("device-3", "03", "3000", "1000"),
        _point("device-1", "01", "1000", "0"),
        _point("device-4", "04", "4000", "1000"),
        _point("device-2", "02", "2000", "0"),
    )
    result = rs485_topology("source", "901", points)
    assert result.status == "VERIFIED"
    assert result.edges == (
        ("source", "device-1"),
        ("device-1", "device-2"),
        ("device-2", "device-3"),
        ("device-3", "device-4"),
    )
    assert result.total_length_mm == 5000

    invalid = rs485_topology(
        "source",
        "901",
        (*points, _point("wrong", "05", "0", "0", base="902")),
    )
    assert "WRONG_BUS:902.005" in invalid.errors
    assert (
        "RS485_BRANCH_FORBIDDEN"
        in rs485_topology("source", "901", points, branches=(("device-1", "device-2"),)).errors
    )
    malformed = rs485_topology(
        "source", "901", (*points, _point("bad", "not-two-digits", "0", "0"))
    )
    assert any(error.startswith("INVALID_SUFFIX") for error in malformed.errors)


def test_generic_branching_two_branches_unique_segments_and_invalid_start():
    points = (
        _point("p1", "01", "1000", "0"),
        _point("p2", "02", "2000", "0"),
        _point("p3", "03", "2000", "1000"),
        _point("p4", "04", "3000", "1000"),
    )
    valid = branched_topology(
        "source",
        "901",
        points,
        (("p1", "p2"), ("p2", "p3", "p4")),
    )
    assert valid.status == "VERIFIED"
    assert valid.edges == (
        ("source", "p1"),
        ("p1", "p2"),
        ("p2", "p3"),
        ("p3", "p4"),
    )
    assert valid.total_length_mm == 4000

    invalid = branched_topology(
        "source",
        "901",
        points,
        (("p1", "p2"), ("p3", "p2"), ("p1", "p2")),
    )
    assert any(error.startswith("INVALID_BRANCH_START") for error in invalid.errors)
    assert any(error.startswith("DUPLICATE_POINT") for error in invalid.errors)
    assert any(error.startswith("DUPLICATE_SEGMENT") for error in invalid.errors)

    reverse_duplicate = branched_topology(
        "source",
        "901",
        points,
        (("p1", "p2", "p3"), ("p3", "p2", "p4")),
    )
    assert "DUPLICATE_SEGMENT:p3->p2" in reverse_duplicate.errors
    assert reverse_duplicate.total_length_mm == 5000
