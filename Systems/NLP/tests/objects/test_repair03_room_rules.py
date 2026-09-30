from __future__ import annotations

from dataclasses import dataclass

from nl_project_2.objects.room_rules import (
    DEFAULT_ROOM_COLOR,
    ROOM_COLOR_PALETTE,
    assign_default_room_colors,
    contrast_text_color,
    resolve_room,
)


@dataclass(frozen=True)
class Candidate:
    id: str
    name: str
    marking_color: str = DEFAULT_ROOM_COLOR


def test_room_resolver_uses_only_approved_deterministic_matches():
    rooms = (
        Candidate("1", "1. Прихожая"),
        Candidate("2", "2. Гардероб"),
        Candidate("3", "10. Гост. мастер спальня"),
    )
    assert resolve_room(rooms, "1. Прихожая").room_id == "1"
    assert resolve_room(rooms, " 1.  ПРИХОЖАЯ ").room_id == "1"
    assert resolve_room(rooms, "1. Старое название").room_id == "1"
    assert resolve_room(rooms, "Прихожая").room_id == "1"
    assert resolve_room(rooms, "Спальня").room_id is None

    ambiguous = rooms + (Candidate("4", "4. Прихожая"),)
    result = resolve_room(ambiguous, "Прихожая")
    assert result.room_id is None
    assert result.ambiguous


def test_room_colors_are_deterministic_persist_only_defaults_and_do_not_rebalance():
    rooms = (
        Candidate("manual", "1. Прихожая", "#123456"),
        Candidate("a", "2. Гардероб"),
        Candidate("b", "3. Гостиная"),
    )
    first = assign_default_room_colors(rooms)
    second = assign_default_room_colors(rooms)
    assert first == second
    assert "manual" not in first
    assert set(first.values()).issubset(ROOM_COLOR_PALETTE)
    assert len(set(first.values())) == 2

    persisted = tuple(
        Candidate(item.id, item.name, first.get(item.id, item.marking_color))
        for item in rooms
    )
    assert assign_default_room_colors(persisted) == {}
    assert contrast_text_color(first["a"]) in {"#202124", "#FFFFFF"}
