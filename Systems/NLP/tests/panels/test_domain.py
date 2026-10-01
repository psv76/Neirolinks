from decimal import Decimal

from nl_project_2.panels import PlacementInput, evaluate_rail


def _placement(key: str, start: str, width: str | None, *, compatible: bool = True):
    return PlacementInput(
        key,
        f"instance-{key}",
        Decimal(start),
        None if width is None else Decimal(width),
        compatible,
    )


def test_rail_orders_mixed_widths_and_reports_remaining_space():
    result = evaluate_rail(
        Decimal("108"),
        (_placement("b", "54", "36"), _placement("a", "0", "18")),
    )
    assert result.status == "VALID"
    assert result.ordered_placement_ids == ("a", "b")
    assert result.occupied_end_mm == Decimal("90")
    assert result.remaining_mm == Decimal("18")


def test_rail_reports_overlap_capacity_mounting_and_unknown_without_fallback():
    result = evaluate_rail(
        Decimal("60"),
        (
            _placement("a", "0", "36"),
            _placement("b", "18", "54", compatible=False),
            _placement("c", "90", None),
        ),
    )
    assert result.status == "ERROR"
    codes = {issue.code for issue in result.issues}
    assert codes == {
        "PLACEMENT_OVERLAP",
        "RAIL_CAPACITY_EXCEEDED",
        "INCOMPATIBLE_MOUNTING",
        "PRODUCT_WIDTH_UNKNOWN",
    }
