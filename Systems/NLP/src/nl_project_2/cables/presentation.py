"""Presentation-only cable marks proven by the NL Project 1.0 CAD rules."""

from __future__ import annotations

# Adapted from the NL Project 1.0 ``modules/cad_rules.py::CABLE_NAMES`` mapping. Keep stored
# values untouched; this mapping is used only at the user-facing boundary.
LEGACY_CABLE_MARKS = {
    "3Х2,5": "ВВГнг(А)-LS 3х2,5",
    "3X2,5": "ВВГнг(А)-LS 3х2,5",
    "3Х1,5": "ВВГнг(А)-LS 3х1,5",
    "3X1,5": "ВВГнг(А)-LS 3х1,5",
    "3Х4": "ВВГнг(А)-LS 3х4",
    "3X4": "ВВГнг(А)-LS 3х4",
    "3Х6": "ВВГнг(А)-LS 3х6",
    "3X6": "ВВГнг(А)-LS 3х6",
    "5Х1,5": "ВВГнг(А)-LS 5х1,5",
    "5X1,5": "ВВГнг(А)-LS 5х1,5",
    "5Х6": "ВВГнг(А)-LS 5х6",
    "5X6": "ВВГнг(А)-LS 5х6",
    "5Х10": "ВВГнг(А)-LS 5х10",
    "5X10": "ВВГнг(А)-LS 5х10",
    "5Х16": "ВВГнг(А)-LS 5х16",
    "5X16": "ВВГнг(А)-LS 5х16",
    "2Х0,75": "МКШнг-LS 2х0,75",
    "2X0,75": "МКШнг-LS 2х0,75",
    "UTP": "UTP 5e 4х2х0,5",
    "UTP 5E": "UTP 5e 4х2х0,5",
}


def format_cable_mark(value: object) -> str:
    """Return the legacy user-facing mark without changing the canonical value."""

    raw = "" if value is None else str(value).replace("\u00a0", " ").replace("\x00", "").strip()
    return LEGACY_CABLE_MARKS.get(raw.upper(), raw)
