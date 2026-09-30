"""Deterministic room identity and presentation rules shared by application services."""

from __future__ import annotations

import colorsys
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

ROOM_COLOR_PALETTE = (
    "#EEF0F2",
    "#D7E3FC",
    "#DDF4E7",
    "#FEEFC3",
    "#FADFC8",
    "#FAD2CF",
    "#F8D7E8",
    "#EADCF8",
    "#CCF3F0",
)
DEFAULT_ROOM_COLOR = "#FFFFFF"

_PREFIX = re.compile(r"^\s*(\d+)\.\s*(.*)$", re.DOTALL)


class RoomLike(Protocol):
    id: str
    name: str


class ColoredRoomLike(RoomLike, Protocol):
    marking_color: str


@dataclass(frozen=True, slots=True)
class RoomResolution:
    room_id: str | None
    method: str | None
    ambiguous: bool = False


@dataclass(frozen=True, slots=True)
class RoomIdentity:
    id: str
    name: str


def normalize_room_name(value: str) -> str:
    return " ".join(str(value).strip().casefold().split())


def leading_room_number(value: str) -> int | None:
    match = _PREFIX.match(str(value))
    return None if match is None else int(match.group(1))


def stripped_room_name(value: str) -> str:
    match = _PREFIX.match(str(value))
    return normalize_room_name(match.group(2) if match else value)


def room_natural_key(room_or_name, room_id: str = "") -> tuple:
    name = room_or_name.name if hasattr(room_or_name, "name") else str(room_or_name)
    identifier = getattr(room_or_name, "id", room_id)
    number = leading_room_number(name)
    return (
        number is None,
        number if number is not None else 10**9,
        normalize_room_name(name),
        str(identifier),
    )


def resolve_room(candidates: Iterable[RoomLike], observed_name: str) -> RoomResolution:
    """Resolve only approved deterministic matches; never guess or create."""

    rooms = tuple(candidates)
    raw = str(observed_name).strip()
    if not raw:
        return RoomResolution(None, None)

    exact = [item for item in rooms if item.name == raw]
    if len(exact) == 1:
        return RoomResolution(exact[0].id, "EXACT_CANONICAL")
    if len(exact) > 1:
        return RoomResolution(None, "EXACT_CANONICAL", True)

    normalized = normalize_room_name(raw)
    normalized_matches = [
        item for item in rooms if normalize_room_name(item.name) == normalized
    ]
    if len(normalized_matches) == 1:
        return RoomResolution(normalized_matches[0].id, "NORMALIZED_EXACT")
    if len(normalized_matches) > 1:
        return RoomResolution(None, "NORMALIZED_EXACT", True)

    number = leading_room_number(raw)
    if number is not None:
        numbered = [item for item in rooms if leading_room_number(item.name) == number]
        if len(numbered) == 1:
            return RoomResolution(numbered[0].id, "UNIQUE_NUMERIC_PREFIX")
        if len(numbered) > 1:
            return RoomResolution(None, "UNIQUE_NUMERIC_PREFIX", True)

    stripped = stripped_room_name(raw)
    stripped_matches = [
        item for item in rooms if stripped_room_name(item.name) == stripped
    ]
    if len(stripped_matches) == 1:
        return RoomResolution(stripped_matches[0].id, "UNIQUE_STRIPPED_PREFIX")
    if len(stripped_matches) > 1:
        return RoomResolution(None, "UNIQUE_STRIPPED_PREFIX", True)
    return RoomResolution(None, None)


def assign_default_room_colors(
    rooms: Iterable[ColoredRoomLike],
) -> dict[str, str]:
    """Return persisted assignments for white rooms without rebalancing existing colors."""

    ordered = sorted(rooms, key=room_natural_key)
    counts = Counter({color: 0 for color in ROOM_COLOR_PALETTE})
    for item in ordered:
        color = _normalized_color(item.marking_color)
        if color in counts and color != DEFAULT_ROOM_COLOR:
            counts[color] += 1

    assignments: dict[str, str] = {}
    previous_color: str | None = None
    for item in ordered:
        current = _normalized_color(item.marking_color)
        if current == DEFAULT_ROOM_COLOR:
            least_used = min(counts.values())
            available = [
                color for color in ROOM_COLOR_PALETTE if counts[color] == least_used
            ]
            if previous_color is None:
                chosen = available[0]
            else:
                chosen = max(
                    available,
                    key=lambda color: (
                        _hue_distance(previous_color, color),
                        -ROOM_COLOR_PALETTE.index(color),
                    ),
                )
            assignments[item.id] = chosen
            counts[chosen] += 1
            current = chosen
        previous_color = current
    return assignments


def contrast_text_color(background: str) -> str:
    red, green, blue = _rgb(_normalized_color(background))

    def linear(channel: int) -> float:
        value = channel / 255
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    luminance = 0.2126 * linear(red) + 0.7152 * linear(green) + 0.0722 * linear(blue)
    white_ratio = 1.05 / (luminance + 0.05)
    black_ratio = (luminance + 0.05) / 0.05
    return "#FFFFFF" if white_ratio > black_ratio else "#202124"


def _normalized_color(value: str) -> str:
    color = str(value or DEFAULT_ROOM_COLOR).strip().upper()
    return color if re.fullmatch(r"#[0-9A-F]{6}", color) else DEFAULT_ROOM_COLOR


def _rgb(color: str) -> tuple[int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def _hue_distance(first: str, second: str) -> float:
    first_hue = colorsys.rgb_to_hsv(*(value / 255 for value in _rgb(first)))[0] * 360
    second_hue = colorsys.rgb_to_hsv(*(value / 255 for value in _rgb(second)))[0] * 360
    distance = abs(first_hue - second_hue)
    return min(distance, 360 - distance)
