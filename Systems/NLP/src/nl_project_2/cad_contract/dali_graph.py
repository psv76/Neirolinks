"""Read-only physical DALI source validation; never creates topology or lengths."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Collection, Iterable
from dataclasses import dataclass

from .models import IssueSeverity, ValidatedObservation, ValidationIssue

_POINT = re.compile(r"9[0-9]{2}\.[0-9]{3}")
_BUS = re.compile(r"9[0-9]{2}")
_PHYSICAL = re.compile(r"(?:BOX|TRACK)\.[0-9]{3}")
PASSIVE_DALI_BLOCKS = frozenset({"EL_BOX_OUT_100x100", "TRACK_DALI"})


@dataclass(frozen=True)
class _Node:
    identity: str
    bus: str
    source: str
    kind: str | None
    handle: str


def validate_dali_graph(
    observations: Iterable[ValidatedObservation],
    project_bus_roots: Collection[str] | None,
) -> list[ValidationIssue]:
    """Resolve explicit parents only. Roots must come from a Project snapshot.

    The legacy numeric-only graph retains its root convention when no snapshot
    is supplied. Any physical BOX/TRACK component requires verified roots.
    This is a validator boundary, not a Project snapshot loader or sync plan.
    """
    nodes: dict[str, list[_Node]] = defaultdict(list)
    physical_buses: set[str] = set()
    issues: list[ValidationIssue] = []

    def report(code: str, message: str, node: _Node, field: str = "BUS_SOURCE") -> None:
        issues.append(ValidationIssue(code, message, IssueSeverity.ERROR, True, node.handle, field))

    for item in observations:
        payload = item.read_payload
        if payload is None:
            continue
        attrs = item.normalized_attributes
        name = payload.block_name
        passive = name in PASSIVE_DALI_BLOCKS
        identity = (
            attrs.get("BOX_ID", "")
            if name == "EL_BOX_OUT_100x100"
            else attrs.get("TRACK_ID", "")
            if name in {"TRACK_DALI", "TRACK_230V", "TRACK_48V"}
            else attrs.get("BUS_POINT_ID", "")
        ).strip()
        bus = (payload.bus_id or "").strip()
        source = attrs.get("BUS_SOURCE", "").strip()
        node = _Node(identity, bus, source, payload.bus_type, payload.handle)
        if passive and _BUS.fullmatch(bus):
            physical_buses.add(bus)
            if not _PHYSICAL.fullmatch(identity):
                report("BUS_PHYSICAL_ID_REQUIRED", "DALI node requires BOX.NNN/TRACK.NNN", node)
        if payload.bus_type == "DALI" and _PHYSICAL.fullmatch(source):
            physical_buses.add(bus)
        if _PHYSICAL.fullmatch(identity) or (
            _POINT.fullmatch(identity) and not identity.endswith(".000")
        ):
            nodes[identity].append(node)

    parents: dict[str, str] = {}
    dali_nodes: dict[str, _Node] = {}
    for identity, entries in sorted(nodes.items()):
        entries.sort(key=lambda n: (n.handle, n.bus, n.source))
        dali = [n for n in entries if n.kind == "DALI" and _BUS.fullmatch(n.bus)]
        if len(entries) > 1:
            # Include non-DALI physical inserts in ambiguity detection, but do
            # not implement general TRACK identity management here.
            if dali:
                for node in entries:
                    report("BUS_NODE_DUPLICATE", f"Ambiguous bus endpoint {identity}", node)
                if len({n.source for n in dali}) > 1:
                    for node in dali:
                        report("BUS_SOURCE_DOUBLE_PARENT", f"Multiple parents of {identity}", node)
            continue
        if not dali:
            continue
        node = dali[0]
        dali_nodes[identity] = node
        source = node.source
        if not source:
            report("BUS_SOURCE_REQUIRED", "DALI requires an explicit parent", node)
            continue
        if not (_POINT.fullmatch(source) or _PHYSICAL.fullmatch(source)):
            report("BUS_SOURCE_FORMAT", "Expected one 9YY.ZZZ, BOX.NNN or TRACK.NNN", node)
            continue
        if _POINT.fullmatch(source) and source[:3] != node.bus:
            report("BUS_SOURCE_CROSS_BUS", f"{source} is outside bus {node.bus}", node)
            continue
        if source == f"{node.bus}.000":
            if project_bus_roots is None and node.bus in physical_buses:
                report("BUS_ROOT_UNVERIFIED", f"Project root {source} must be verified", node)
                continue
            if project_bus_roots is not None and source not in project_bus_roots:
                report("BUS_ROOT_NOT_FOUND", f"Project root {source} is absent", node)
                continue
            parents[identity] = source
            continue
        candidates = nodes.get(source, [])
        if not candidates:
            report("BUS_SOURCE_NOT_FOUND", f"BUS_SOURCE {source} is absent", node)
        elif len(candidates) != 1:
            report("BUS_SOURCE_AMBIGUOUS", f"BUS_SOURCE {source} is not unique", node)
        elif candidates[0].bus != node.bus:
            report("BUS_SOURCE_CROSS_BUS", f"{source} is not a member of {node.bus}", node)
        elif candidates[0].kind != "DALI":
            report("BUS_SOURCE_TYPE_CONFLICT", f"{source} is not a DALI endpoint", node)
        else:
            parents[identity] = source

    # Iterative walks avoid recursion limits on large drawings. No numeric
    # order, position or shared BUS_ID is used to invent a parent.
    reachable: set[str] = set()
    failed: set[str] = set()
    for start in sorted(dali_nodes):
        path: list[str] = []
        positions: dict[str, int] = {}
        current = start
        while current in dali_nodes and current not in reachable and current not in failed:
            if current in positions:
                for identity in path[positions[current] :]:
                    report(
                        "BUS_SOURCE_CYCLE", "DALI topology contains a cycle", dali_nodes[identity]
                    )
                break
            positions[current] = len(path)
            path.append(current)
            if current not in parents:
                break
            current = parents[current]
        rooted = current in reachable or (bool(path) and parents.get(path[-1], "").endswith(".000"))
        (reachable if rooted else failed).update(path)
    for identity in sorted(failed):
        report("BUS_SOURCE_UNREACHABLE", "No validated path to the bus root", dali_nodes[identity])
    return issues
