"""Pure DIN-rail placement rules."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PlacementInput:
    placement_id: str
    instance_id: str
    start_mm: Decimal
    width_mm: Decimal | None
    mounting_compatible: bool = True


@dataclass(frozen=True, slots=True)
class PanelIssue:
    code: str
    message: str
    placement_ids: tuple[str, ...]
    blocking: bool


@dataclass(frozen=True, slots=True)
class RailEvaluation:
    status: str
    ordered_placement_ids: tuple[str, ...]
    occupied_end_mm: Decimal
    remaining_mm: Decimal | None
    issues: tuple[PanelIssue, ...]


def evaluate_rail(
    usable_width_mm: Decimal | None,
    placements: tuple[PlacementInput, ...],
) -> RailEvaluation:
    """Evaluate current product widths without changing persisted placement facts."""

    ordered = tuple(sorted(placements, key=lambda item: (item.start_mm, item.placement_id)))
    issues: list[PanelIssue] = []
    occupied_end = Decimal("0")
    previous: PlacementInput | None = None
    previous_end: Decimal | None = None

    if usable_width_mm is None:
        issues.append(
            PanelIssue(
                "RAIL_WIDTH_UNKNOWN",
                "Usable rail width is unknown; capacity cannot be verified",
                (),
                False,
            )
        )
    elif usable_width_mm <= 0:
        issues.append(
            PanelIssue("RAIL_WIDTH_INVALID", "Usable rail width must be positive", (), True)
        )

    for item in ordered:
        if item.start_mm < 0:
            issues.append(
                PanelIssue(
                    "START_BEFORE_RAIL",
                    "Placement starts before the rail origin",
                    (item.placement_id,),
                    True,
                )
            )
        if not item.mounting_compatible:
            issues.append(
                PanelIssue(
                    "INCOMPATIBLE_MOUNTING",
                    "Selected product is not compatible with a 35 mm DIN rail",
                    (item.placement_id,),
                    True,
                )
            )
        if item.width_mm is None:
            issues.append(
                PanelIssue(
                    "PRODUCT_WIDTH_UNKNOWN",
                    "Selected product width is unknown; no fallback width was substituted",
                    (item.placement_id,),
                    False,
                )
            )
            previous = None
            previous_end = None
            continue
        if item.width_mm <= 0:
            issues.append(
                PanelIssue(
                    "PRODUCT_WIDTH_INVALID",
                    "Selected product width must be positive for DIN placement",
                    (item.placement_id,),
                    True,
                )
            )
            previous = None
            previous_end = None
            continue
        current_end = item.start_mm + item.width_mm
        occupied_end = max(occupied_end, current_end)
        if previous is not None and previous_end is not None and item.start_mm < previous_end:
            issues.append(
                PanelIssue(
                    "PLACEMENT_OVERLAP",
                    "DIN placements overlap",
                    (previous.placement_id, item.placement_id),
                    True,
                )
            )
        if usable_width_mm is not None and usable_width_mm > 0 and current_end > usable_width_mm:
            issues.append(
                PanelIssue(
                    "RAIL_CAPACITY_EXCEEDED",
                    "Placement exceeds usable rail width",
                    (item.placement_id,),
                    True,
                )
            )
        previous = item
        previous_end = current_end

    status = (
        "ERROR" if any(issue.blocking for issue in issues) else "INCOMPLETE" if issues else "VALID"
    )
    remaining = (
        None if usable_width_mm is None else max(Decimal("0"), usable_width_mm - occupied_end)
    )
    return RailEvaluation(
        status=status,
        ordered_placement_ids=tuple(item.placement_id for item in ordered),
        occupied_end_mm=occupied_end,
        remaining_mm=remaining,
        issues=tuple(issues),
    )
