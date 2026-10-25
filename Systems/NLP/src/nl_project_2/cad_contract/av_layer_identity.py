"""Pure staged AV identities, without runtime validation or product selection."""

from collections.abc import Iterable

from .layer_groups import function_group_for_working_layer


def is_av_working_layer(layer: object) -> bool:
    """Return whether the accepted working-layer resolver classifies AV."""
    return function_group_for_working_layer(layer) == "AV"


def normalize_av_cable_id(cable_id: str) -> str:
    """Trim and uppercase free text; raise TypeError for non-string input."""
    if not isinstance(cable_id, str):
        raise TypeError("cable_id must be a string")
    return cable_id.strip().upper()


def av_line_identity(board: str, cable_id: str) -> tuple[str, str] | None:
    """Return a complete identity, preserving board case; else return None.

    Both fields must be strings, even for incomplete rows; otherwise TypeError
    is raised. Board names are only trimmed, never validated against a format.
    """
    if not isinstance(board, str):
        raise TypeError("board must be a string")
    normalized_id = normalize_av_cable_id(cable_id)
    normalized_board = board.strip()
    if not normalized_board or not normalized_id:
        return None
    return normalized_board, normalized_id


def duplicate_av_identities(items: Iterable[tuple[str, str]]) -> frozenset[tuple[str, str]]:
    """Find repeated normalized identities, excluding incomplete string pairs.

    Non-string fields raise TypeError through av_line_identity. Input rows are
    not modified. Identical cable IDs on different board names are independent.
    """
    seen: set[tuple[str, str]] = set()
    duplicates: set[tuple[str, str]] = set()
    for board, cable_id in items:
        identity = av_line_identity(board, cable_id)
        if identity is None:
            continue
        if identity in seen:
            duplicates.add(identity)
        seen.add(identity)
    return frozenset(duplicates)
