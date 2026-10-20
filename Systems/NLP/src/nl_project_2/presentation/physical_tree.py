"""Pure presentation layout for physical cable and BUS segment trees.

The source/target graph determines ancestry; indentation stored by older
read-models is not a physical cable connection. This module never changes
topology, cable lengths or DB facts.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PhysicalEdgeRow:
    index: int
    edge: dict
    prefix: str
    parent_index: int | None
    is_root: bool
    is_branch_point: bool


def _endpoint_key(endpoint: object) -> tuple[str, str] | None:
    """Resolve typed topology identity; display labels are never valid join keys."""

    if not isinstance(endpoint, dict):
        return None
    kind = str(endpoint.get("kind") or endpoint.get("point_kind") or "")
    value = (
        endpoint.get("endpoint_id")
        or endpoint.get("reference")
        or endpoint.get("resource_id")
        or (endpoint.get("board") if kind == "BOARD_OUTPUT" else None)
    )
    return (kind, str(value)) if value is not None and str(value) else None


def physical_edge_layout(edges: list[dict]) -> tuple[PhysicalEdgeRow, ...]:
    """Walk real source→target edges, preserving independent cables at the root.

    References are available in current cable/BUS topology read models. No
    synthetic common segment is inserted for a shared BOARD_OUTPUT. An orphan
    or invalid cyclic remainder is drawn separately, not given a fake parent.
    Ambiguous converging physical endpoints never get an arbitrary parent.
    """

    sources = [_endpoint_key(edge.get("source")) for edge in edges]
    targets = [_endpoint_key(edge.get("target")) for edge in edges]
    target_counts: dict[tuple[str, str], int] = {}
    for target in targets:
        if target is not None:
            target_counts[target] = target_counts.get(target, 0) + 1
    target_keys = set(target_counts)
    adjacency: dict[tuple[str, str], list[int]] = {}
    for index, source in enumerate(sources):
        if source is not None:
            adjacency.setdefault(source, []).append(index)

    order: list[int] = []
    visited: set[int] = set()
    parents: dict[int, int | None] = {}
    children: dict[int | None, list[int]] = {}

    def visit(index: int, parent: int | None) -> None:
        if index in visited:
            return
        visited.add(index)
        parents[index] = parent
        children.setdefault(parent, []).append(index)
        order.append(index)
        target = targets[index]
        if target is not None and target_counts[target] == 1:
            for child in adjacency.get(target, ()):
                visit(child, index)

    for index, source in enumerate(sources):
        if source is None or source not in target_keys or target_counts[source] != 1:
            visit(index, None)
    for index in range(len(edges)):
        visit(index, None)

    result: list[PhysicalEdgeRow] = []
    for index in order:
        parent = parents[index]
        if parent is None:
            # Root siblings are *separate cables*, not branches of a drawn trunk.
            prefix = "↳ "
        else:
            ancestors: list[int] = []
            cursor: int | None = parent
            while cursor is not None:
                ancestors.append(cursor)
                cursor = parents[cursor]
            ancestors.reverse()
            # The root never draws a shared vertical trunk.
            guides = "   "
            for ancestor in ancestors[1:]:
                siblings = children[parents[ancestor]]
                guides += "│  " if ancestor != siblings[-1] else "   "
            siblings = children[parent]
            prefix = guides + ("├─ " if index != siblings[-1] else "└─ ")
        result.append(
            PhysicalEdgeRow(
                index=index,
                edge=edges[index],
                prefix=prefix,
                parent_index=parent,
                is_root=parent is None,
                is_branch_point=len(children.get(index, ())) > 1,
            )
        )
    return tuple(result)


def compact_physical_edge_rows(
    rows: tuple[PhysicalEdgeRow, ...], *, threshold: int = 8
) -> tuple[tuple[PhysicalEdgeRow, ...], int]:
    """Do not hide roots, EL_BOX, forks, diagnostic rows, or their parents."""

    if len(rows) <= threshold:
        return rows, 0
    by_index = {row.index: row for row in rows}
    keep = {row.index for row in rows[:3]}
    for row in rows:
        target = row.edge.get("target") or {}
        if (
            row.is_root
            or row.is_branch_point
            or target.get("point_kind") == "EL_BOX"
            or bool(target.get("room_unresolved"))
            or row.edge.get("calculation_status") != "READY"
        ):
            keep.add(row.index)

    pending = list(keep)
    while pending:
        parent = by_index[pending.pop()].parent_index
        if parent is not None and parent not in keep:
            keep.add(parent)
            pending.append(parent)

    shown = tuple(row for row in rows if row.index in keep)
    return shown, len(rows) - len(shown)
