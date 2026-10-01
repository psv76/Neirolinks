"""Pure physical-bus topology validation and derived graph calculations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

_POINT = re.compile(r"^(?P<base>9[0-9]{2})\.(?P<suffix>[0-9]{3})$")


@dataclass(frozen=True, slots=True)
class TopologyPoint:
    point_id: str
    cable_id: str
    x_mm: Decimal
    y_mm: Decimal


@dataclass(frozen=True, slots=True)
class TopologyResult:
    status: str
    nodes: tuple[str, ...]
    edges: tuple[tuple[str, str], ...]
    total_length_mm: Decimal
    errors: tuple[str, ...]


def rs485_topology(
    root_id: str,
    base_cable_id: str,
    points,
    *,
    root_x_mm=0,
    root_y_mm=0,
    branches=(),
) -> TopologyResult:
    errors = list(_point_errors(base_cable_id, points))
    if not root_id:
        errors.append("MISSING_SOURCE")
    if branches:
        errors.append("RS485_BRANCH_FORBIDDEN")
    ordered = sorted(points, key=_suffix_order)
    ids = [root_id, *(point.point_id for point in ordered)]
    edges = tuple(zip(ids, ids[1:], strict=False))
    return _result(ids, edges, points, tuple(errors), root_id, root_x_mm, root_y_mm)


def branched_topology(
    root_id: str,
    base_cable_id: str,
    points,
    branches,
    *,
    root_x_mm=0,
    root_y_mm=0,
) -> TopologyResult:
    errors = list(_point_errors(base_cable_id, points))
    if not root_id:
        errors.append("MISSING_SOURCE")
    point_ids = {point.point_id for point in points}
    seen = set()
    edges = []
    edge_keys = set()
    for index, branch in enumerate(branches):
        if not branch:
            errors.append(f"EMPTY_BRANCH:{index}")
            continue
        if any(identifier not in point_ids for identifier in branch):
            errors.append(f"MISSING_POINT:{index}")
            continue
        if index == 0:
            chain = (root_id, *branch)
        else:
            if branch[0] not in seen:
                errors.append(f"INVALID_BRANCH_START:{branch[0]}")
            chain = branch
        for position, identifier in enumerate(branch):
            if identifier in seen and not (index > 0 and position == 0):
                errors.append(f"DUPLICATE_POINT:{identifier}")
            seen.add(identifier)
        for edge in zip(chain, chain[1:], strict=False):
            edge_key = frozenset(edge)
            if edge_key in edge_keys:
                errors.append(f"DUPLICATE_SEGMENT:{edge[0]}->{edge[1]}")
            edge_keys.add(edge_key)
            edges.append(edge)
    if seen != point_ids:
        errors.extend(f"UNREACHABLE_POINT:{item}" for item in sorted(point_ids - seen))
    return _result(
        (root_id, *sorted(point_ids)),
        tuple(edges),
        points,
        tuple(errors),
        root_id,
        root_x_mm,
        root_y_mm,
    )


def _point_errors(base, points):
    errors = []
    suffixes = set()
    point_ids = set()
    for point in points:
        if point.point_id in point_ids:
            errors.append(f"DUPLICATE_POINT:{point.point_id}")
        point_ids.add(point.point_id)
        match = _POINT.fullmatch(point.cable_id)
        if not match:
            errors.append(f"INVALID_SUFFIX:{point.cable_id}")
        elif match.group("base") != base:
            errors.append(f"WRONG_BUS:{point.cable_id}")
        elif match.group("suffix") == "000":
            errors.append(f"RESERVED_ROOT:{point.cable_id}")
        elif match.group("suffix") in suffixes:
            errors.append(f"DUPLICATE_SUFFIX:{match.group('suffix')}")
        else:
            suffixes.add(match.group("suffix"))
    return tuple(errors)


def _suffix_order(point):
    match = _POINT.fullmatch(point.cable_id)
    return int(match.group("suffix")) if match else 100


def _result(nodes, edges, points, errors, root_id, root_x_mm, root_y_mm):
    coordinates = {
        root_id: (Decimal(str(root_x_mm)), Decimal(str(root_y_mm))),
        **{point.point_id: (point.x_mm, point.y_mm) for point in points},
    }
    total = Decimal("0")
    unique_edges = []
    edge_keys = set()
    for source, target in edges:
        edge_key = frozenset((source, target))
        if edge_key in edge_keys:
            continue
        edge_keys.add(edge_key)
        unique_edges.append((source, target))
        if source not in coordinates:
            continue
        if target not in coordinates:
            errors = (*errors, f"MISSING_COORDINATE:{target}")
            continue
        x1, y1 = coordinates[source]
        x2, y2 = coordinates[target]
        total += abs(x2 - x1) + abs(y2 - y1)
    return TopologyResult(
        "VERIFIED" if not errors else "INCOMPATIBLE",
        tuple(nodes),
        tuple(unique_edges),
        total,
        tuple(dict.fromkeys(errors)),
    )
