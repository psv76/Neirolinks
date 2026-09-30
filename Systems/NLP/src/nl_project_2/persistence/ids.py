"""Stable technical identifiers independent from natural/project identifiers."""

from __future__ import annotations

import uuid


def new_id() -> str:
    return str(uuid.uuid4())


def is_canonical_id(value: str) -> bool:
    try:
        parsed = uuid.UUID(value, version=4)
    except (AttributeError, ValueError):
        return False
    return value == str(parsed)
