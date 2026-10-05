"""Pure deterministic cable-length rules from product contract section 22."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum


class CableCalculationError(ValueError):
    pass


class RouteMethod(StrEnum):
    FLOOR = "FLOOR"
    SCREED = "SCREED"
    CEILING = "CEILING"
    WALL = "WALL"
    TIMBER = "TIMBER"
    CABLE_CHANNEL = "CABLE_CHANNEL"


MOUNT_WAY_BY_ROUTE_METHOD = {
    RouteMethod.FLOOR: "По полу",
    RouteMethod.SCREED: "В стяжке",
    RouteMethod.CEILING: "По потолку",
    RouteMethod.WALL: "В стене",
    RouteMethod.TIMBER: "В брусе",
    RouteMethod.CABLE_CHANNEL: "В кабель-канале",
}
ROUTE_METHOD_BY_MOUNT_WAY = {value: key for key, value in MOUNT_WAY_BY_ROUTE_METHOD.items()}
LINE_CONDUIT_ATTRIBUTES = ("MOUNT_WAY", "GOFRA_TYPE", "GOFRA_COLOR", "GOFRA_ID")
CONDUIT_TYPE_CODES = {
    "ПНД": "PND",
    "ПВХ": "PVH",
    "Металлорукав": "MR",
    "ППЛ": "PP",
    "МПТ": "MPT",
}
_CONDUIT_ID = re.compile(r"^(?P<number>[0-9]{3})\.(?P<suffix>[A-Z0-9]+)$")
_NOMINAL_SIZE = re.compile(r"^[0-9]+$")


class ConduitContractError(ValueError):
    pass


def conduit_type_suffix(value: str) -> str:
    """Return the one canonical Latin suffix from a Russian type+nominal value."""

    normalized = " ".join(str(value).strip().split())
    for russian, latin in sorted(CONDUIT_TYPE_CODES.items(), key=lambda item: -len(item[0])):
        if not normalized.startswith(russian):
            continue
        nominal = normalized[len(russian) :].strip()
        if not _NOMINAL_SIZE.fullmatch(nominal):
            break
        return f"{latin}{nominal}"
    raise ConduitContractError(
        "GOFRA_TYPE must contain ПНД, ПВХ, Металлорукав, ППЛ or МПТ and a numeric nominal size"
    )


def parse_conduit_id(value: str, conduit_type: str) -> int:
    match = _CONDUIT_ID.fullmatch(str(value).strip())
    if match is None:
        raise ConduitContractError("GOFRA_ID must match NNN.<LATIN_GOFRA_TYPE>")
    expected = conduit_type_suffix(conduit_type)
    if match.group("suffix") != expected:
        raise ConduitContractError(
            f"GOFRA_ID suffix must be {expected} for GOFRA_TYPE={conduit_type}"
        )
    return int(match.group("number"))


def format_conduit_id(number: int, conduit_type: str) -> str:
    if not 0 <= int(number) <= 999:
        raise ConduitContractError("conduit number cannot be represented by the agreed NNN format")
    return f"{int(number):03d}.{conduit_type_suffix(conduit_type)}"


def conduit_is_present(mount_way: str, conduit_type: str) -> bool:
    if mount_way == "По полу":
        if not conduit_type:
            raise ConduitContractError("GOFRA_TYPE is required for MOUNT_WAY=По полу")
        conduit_type_suffix(conduit_type)
        return True
    if mount_way == "В стяжке":
        if not conduit_type:
            raise ConduitContractError("GOFRA_TYPE is required for MOUNT_WAY=В стяжке")
        conduit_type_suffix(conduit_type)
        return True
    if mount_way == "По потолку":
        if conduit_type:
            conduit_type_suffix(conduit_type)
            return True
        return False
    if mount_way == "В стене":
        if conduit_type:
            conduit_type_suffix(conduit_type)
            return True
        return False
    if mount_way == "В брусе":
        if not conduit_type:
            raise ConduitContractError("GOFRA_TYPE is required for MOUNT_WAY=В брусе")
        if conduit_type not in {"ППЛ20", "ППЛ25"}:
            raise ConduitContractError("GOFRA_TYPE must be ППЛ20 or ППЛ25 for MOUNT_WAY=В брусе")
        return True
    if mount_way == "В кабель-канале":
        if conduit_type:
            raise ConduitContractError("GOFRA_TYPE must be empty for MOUNT_WAY=В кабель-канале")
        return False
    raise ConduitContractError(
        "MOUNT_WAY must be По полу, В стяжке, По потолку, В стене, В брусе or В кабель-канале"
    )


def validate_line_conduit_fields(
    *, mount_way: str, conduit_type: str, conduit_color: str, conduit_id: str
) -> bool:
    present = conduit_is_present(mount_way, conduit_type)
    if not present and (conduit_color or conduit_id):
        raise ConduitContractError("GOFRA_COLOR and GOFRA_ID must be empty when no conduit exists")
    if conduit_id:
        parse_conduit_id(conduit_id, conduit_type)
    return present


@dataclass(frozen=True, slots=True)
class CablePointInput:
    x_mm: Decimal
    y_mm: Decimal
    mount_height_mm: Decimal
    base_mark_mm: Decimal
    room_height_m: Decimal

    @classmethod
    def from_values(
        cls,
        *,
        x_mm,
        y_mm,
        mount_height_mm,
        base_mark_mm,
        room_height_m,
    ) -> CablePointInput:
        return cls(
            _decimal(x_mm, "x_mm"),
            _decimal(y_mm, "y_mm"),
            _decimal(mount_height_mm, "mount_height_mm"),
            _decimal(base_mark_mm, "base_mark_mm"),
            _decimal(room_height_m, "room_height_m", non_negative=True),
        )


@dataclass(frozen=True, slots=True)
class LengthResult:
    automatic_m: Decimal
    additional_m: Decimal
    board_reserve_m: Decimal
    manual_full_m: Decimal | None
    effective_m: Decimal
    trace: tuple[dict[str, str], ...]


def calculate_segment_length(
    first: CablePointInput, second: CablePointInput, route_method: RouteMethod
) -> tuple[Decimal, dict[str, str]]:
    """Calculate one persisted cable segment exactly once."""

    xy = abs(second.x_mm - first.x_mm) + abs(second.y_mm - first.y_mm)
    if route_method is RouteMethod.FLOOR:
        vertical_first = abs(first.mount_height_mm - first.base_mark_mm)
        level_change = abs(second.base_mark_mm - first.base_mark_mm)
        vertical_second = abs(second.mount_height_mm - second.base_mark_mm)
    elif route_method is RouteMethod.CEILING:
        first_ceiling = first.room_height_m * 1000
        second_ceiling = second.room_height_m * 1000
        vertical_first = abs(first_ceiling - first.mount_height_mm)
        level_change = abs(second_ceiling - first_ceiling)
        vertical_second = abs(second_ceiling - second.mount_height_mm)
    elif route_method in {RouteMethod.SCREED, RouteMethod.WALL, RouteMethod.TIMBER}:
        vertical_first = Decimal(0)
        level_change = abs(second.mount_height_mm - first.mount_height_mm)
        vertical_second = Decimal(0)
    elif route_method is RouteMethod.CABLE_CHANNEL:
        vertical_first = Decimal(0)
        level_change = Decimal(0)
        vertical_second = Decimal(0)
    else:  # pragma: no cover - StrEnum protects public callers
        raise CableCalculationError(f"Unsupported route method: {route_method}")
    geometry = (xy + vertical_first + level_change + vertical_second) / 1000
    cable_reserve = Decimal("0.5") if route_method is RouteMethod.TIMBER else Decimal(0)
    length = geometry + cable_reserve
    return length, {
        "route_method": str(route_method),
        "xy_mm": str(xy),
        "vertical_first_mm": str(vertical_first),
        "level_change_mm": str(level_change),
        "vertical_second_mm": str(vertical_second),
        "geometry_m": str(geometry),
        "cable_reserve_m": str(cable_reserve),
        "length_m": str(length),
    }


def conduit_length_from_segment_length(length_m, route_method: RouteMethod) -> Decimal:
    """Return conduit geometry without cable-only reserves."""

    length = _decimal(length_m, "length_m", non_negative=True)
    if route_method is RouteMethod.TIMBER:
        geometry = length - Decimal("0.5")
        if geometry < 0:
            raise CableCalculationError("TIMBER segment length cannot be below its cable reserve")
        return geometry
    return length


def calculate_automatic_length(
    points: tuple[CablePointInput, ...], route_method: RouteMethod
) -> tuple[Decimal, tuple[dict[str, str], ...]]:
    if len(points) < 2:
        raise CableCalculationError("At least two sequential device points are required")
    total = Decimal(0)
    trace: list[dict[str, str]] = []
    for index, (first, second) in enumerate(zip(points, points[1:], strict=False), start=1):
        segment, segment_trace = calculate_segment_length(first, second, route_method)
        total += segment
        trace.append({"segment": str(index), **segment_trace})
    return total, tuple(trace)


def calculate_effective_length(
    *,
    automatic_m,
    additional_m=0,
    board_reserve_m=0,
    manual_full_m=None,
    trace: tuple[dict[str, str], ...] = (),
) -> LengthResult:
    automatic = _decimal(automatic_m, "automatic_m", non_negative=True)
    additional = _decimal(additional_m or 0, "additional_m", non_negative=True)
    reserve = _decimal(board_reserve_m or 0, "board_reserve_m", non_negative=True)
    manual = (
        None
        if manual_full_m in (None, "")
        else _decimal(manual_full_m, "manual_full_m", non_negative=True)
    )
    effective = manual if manual is not None else automatic + additional + reserve
    return LengthResult(automatic, additional, reserve, manual, effective, trace)


def _decimal(value, field: str, *, non_negative: bool = False) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise CableCalculationError(f"{field} must be a decimal") from exc
    if not result.is_finite() or (non_negative and result < 0):
        raise CableCalculationError(f"{field} is outside the allowed range")
    return result
