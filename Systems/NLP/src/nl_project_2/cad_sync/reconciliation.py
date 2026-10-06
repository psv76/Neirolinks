"""Deterministic owner-aware normalization for validated CAD snapshots.

This module is transport and persistence neutral.  It turns the P0_002
``NormalizedCadReadPayload`` into stable owner facts and an explicit topology
plan.  It never reads or writes SQLite or CAD.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from nl_project_2.cad_contract import CableSuffixKind, ValidatedObservation

from .models import SyncOwnerKind

LINE_FIELDS = frozenset({"CABLE_TYPE", "BOARD", "FUNCTION_GROUP", "LED_TYPE", "LOAD_NAME"})
ROUTE_FIELDS = ("MOUNT_WAY", "GOFRA_TYPE", "GOFRA_COLOR", "GOFRA_ID")
KEY_FIELDS = frozenset({"KEY_1", "KEY_2", "KEY_3", "KEY_4"})
OUTPUT_FIELDS = frozenset()
PORT_FIELDS = frozenset({"COM1", "COM2", "W1", "W2", "K1", "K2", "IN_1", "IN_2"})
SPECIAL_FIELDS = KEY_FIELDS | OUTPUT_FIELDS | PORT_FIELDS


@dataclass(frozen=True, slots=True)
class OwnerFact:
    owner_kind: SyncOwnerKind
    owner_key: str
    owner_path: str
    field: str
    value: Any
    primary_handle: str
    affected_handles: tuple[str, ...]
    structural: bool = False


@dataclass(frozen=True, slots=True)
class PointPlan:
    key: str
    base: str
    logical_identity: str
    point_kind: str
    ordinal: int
    handles: tuple[str, ...]
    x: Any
    y: Any


@dataclass(frozen=True, slots=True)
class SegmentPlan:
    key: str
    base: str
    source_point_key: str | None
    source_reference: str | None
    target_point_key: str
    target_handles: tuple[str, ...]
    route: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class PortPlan:
    handle: str
    block_name: str
    tag: str
    value: str


@dataclass(frozen=True, slots=True)
class KeyPlan:
    handle: str
    tag: str
    value: str


@dataclass(frozen=True, slots=True)
class BusPointPlan:
    bus_id: str
    point_id: str
    source: str | None
    bus_kind: str
    handle: str
    cable_type: str
    connection_kind: str
    route: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class NormalizedCadSnapshot:
    facts: tuple[OwnerFact, ...]
    points: tuple[PointPlan, ...]
    segments: tuple[SegmentPlan, ...]
    ports: tuple[PortPlan, ...]
    keys: tuple[KeyPlan, ...]
    bus_points: tuple[BusPointPlan, ...]
    structural_reviews: tuple[str, ...]
    point_key_by_handle: tuple[tuple[str, str], ...]

    def fact_map(self) -> dict[str, OwnerFact]:
        return {fact.owner_path: fact for fact in self.facts}


@dataclass(frozen=True, slots=True)
class DualProjectionResult:
    canonical_target: str | None
    downstream_value: str | None
    port_value: str | None
    status: str


def reconcile_edge_projections(
    baseline_target: str | None,
    downstream_target: str | None,
    port_target: str | None,
) -> DualProjectionResult:
    """Three-way resolution for two DWG projections of one physical edge."""

    baseline = baseline_target or None
    downstream = downstream_target or None
    port = port_target or None
    if downstream == port:
        return DualProjectionResult(downstream, downstream, port, "AGREE")
    downstream_changed = downstream != baseline
    port_changed = port != baseline
    if downstream_changed and not port_changed:
        return DualProjectionResult(downstream, downstream, downstream, "DOWNSTREAM_CHANGED")
    if port_changed and not downstream_changed:
        return DualProjectionResult(port, port, port, "PORT_CHANGED")
    return DualProjectionResult(None, downstream, port, "REQUIRES_ATTENTION")


def normalize_validated_snapshot(
    observations: tuple[ValidatedObservation, ...] | list[ValidatedObservation],
) -> NormalizedCadSnapshot:
    """Return a scan-order independent snapshot from P0_002 payloads."""

    rows = sorted(
        (
            item
            for item in observations
            if not item.ignored_project_data and item.read_payload is not None
        ),
        key=lambda item: item.observation.handle,
    )
    facts: list[OwnerFact] = []
    points: list[PointPlan] = []
    ports: list[PortPlan] = []
    keys: list[KeyPlan] = []
    reviews: list[str] = []
    bus_points: list[BusPointPlan] = []

    by_base: dict[str, list[ValidatedObservation]] = {}
    point_rows: dict[tuple[str, str], list[ValidatedObservation]] = {}
    for item in rows:
        payload = item.read_payload
        assert payload is not None
        identity = payload.cable_identity
        if identity is not None:
            by_base.setdefault(identity.base, []).append(item)
            point_rows.setdefault((identity.base, _point_identity(item)), []).append(item)

    # Insertion and exact tagged owners.
    for item in rows:
        payload = item.read_payload
        assert payload is not None
        handle = item.observation.handle
        identity = payload.cable_identity
        point_identity = _point_identity(item) if identity is not None else None
        point_key = None if identity is None else _point_key(identity.base, point_identity)
        excluded = LINE_FIELDS | set(ROUTE_FIELDS) | SPECIAL_FIELDS | {"CABLE_ID", "CABLE_SOURCE"}
        insertion_values: dict[str, Any] = {
            "BLOCK_NAME": item.observation.effective_name,
            "LAYER": item.observation.layer,
            "X": item.observation.x,
            "Y": item.observation.y,
            "DWG_HANDLE": handle,
            "DEVICE_TYPE": item.device_type,
        }
        insertion_values.update(
            (field, value)
            for field, value in item.normalized_attributes.items()
            if field not in excluded and field != "DEVICE_TYPE"
        )
        for field, value in sorted(insertion_values.items()):
            owner_path = f"insertion:{handle}:{field}"
            facts.append(
                OwnerFact(
                    SyncOwnerKind.INSERTION,
                    handle,
                    owner_path,
                    field,
                    value,
                    handle,
                    (handle,),
                )
            )

        if identity is not None:
            owner_kind = (
                SyncOwnerKind.BASE_LINE
                if identity.suffix_kind is CableSuffixKind.BASE
                else SyncOwnerKind.TOPOLOGY_POINT
            )
            owner_key = identity.base if owner_kind is SyncOwnerKind.BASE_LINE else point_key
            owner_path = f"{owner_kind.value.lower()}:{owner_key}:CABLE_ID"
            group_handles = tuple(
                sorted(
                    row.observation.handle
                    for row in (
                        by_base[identity.base]
                        if owner_kind is SyncOwnerKind.BASE_LINE
                        else point_rows[(identity.base, point_identity)]
                    )
                    if row.read_payload.cable_identity.raw == identity.raw
                )
            )
            if not any(fact.owner_path == owner_path for fact in facts):
                facts.append(
                    OwnerFact(
                        owner_kind,
                        str(owner_key),
                        owner_path,
                        "CABLE_ID",
                        identity.raw,
                        group_handles[0],
                        group_handles,
                        structural=True,
                    )
                )

            facts.append(
                OwnerFact(
                    SyncOwnerKind.SEGMENT,
                    point_key or identity.raw,
                    f"edge:{point_identity}:CABLE_SOURCE",
                    "CABLE_SOURCE",
                    payload.cable_source or "",
                    handle,
                    (handle,),
                    structural=True,
                )
            )

        for tagged in payload.keys:
            path = f"key:{handle}:{tagged.tag}"
            facts.append(
                OwnerFact(
                    SyncOwnerKind.CONTROL_KEY,
                    f"{handle}:{tagged.tag}",
                    path,
                    tagged.tag,
                    tagged.value,
                    handle,
                    (handle,),
                )
            )
            keys.append(KeyPlan(handle, tagged.tag, tagged.value))
        for tagged in payload.topology_outputs:
            path = f"out:{handle}:{tagged.tag}"
            facts.append(
                OwnerFact(
                    SyncOwnerKind.TOPOLOGY_OUTPUT,
                    f"{handle}:{tagged.tag}",
                    path,
                    tagged.tag,
                    tagged.value,
                    handle,
                    (handle,),
                    structural=True,
                )
            )
        for tagged in payload.field_ports:
            path = f"port:{handle}:{tagged.tag}"
            facts.append(
                OwnerFact(
                    SyncOwnerKind.FIELD_PORT,
                    f"{handle}:{tagged.tag}",
                    path,
                    tagged.tag,
                    tagged.value,
                    handle,
                    (handle,),
                )
            )
            ports.append(PortPlan(handle, payload.block_name, tagged.tag, tagged.value))
        if payload.bus_point_id and payload.bus_id and payload.bus_type:
            bus_points.append(
                BusPointPlan(
                    payload.bus_id,
                    payload.bus_point_id,
                    payload.bus_source,
                    payload.bus_type,
                    handle,
                    item.normalized_attributes.get("BUS_CABLE_TYPE", ""),
                    payload.bus_link_kind or "CABLE",
                    tuple((fact.tag, fact.value) for fact in payload.bus_route_fields),
                )
            )

    # One owner fact per base line and per incoming point/segment.
    for base, items in sorted(by_base.items()):
        handles = tuple(sorted(item.observation.handle for item in items))
        sample = items[0]
        load_names = sorted(
            {
                str(item.normalized_attributes.get("LOAD_NAME", "")).strip()
                for item in items
                if str(item.normalized_attributes.get("LOAD_NAME", "")).strip()
            }
        )
        line_values = {
            "CABLE_TYPE": sample.normalized_attributes.get("CABLE_TYPE", ""),
            "BOARD": sample.normalized_attributes.get("BOARD", ""),
            "FUNCTION_GROUP": sample.function_group,
            "LOAD_NAME": load_names[0] if load_names else "",
        }
        led_values = {
            item.read_payload.led_type
            for item in items
            if item.read_payload is not None and item.read_payload.led_type is not None
        }
        if led_values:
            line_values["LED_TYPE"] = sorted(led_values)[0]
        for field, value in sorted(line_values.items()):
            facts.append(
                OwnerFact(
                    SyncOwnerKind.BASE_LINE,
                    base,
                    f"base_line:{base}:{field}",
                    field,
                    value,
                    handles[0],
                    handles,
                )
            )

    point_key_by_handle: list[tuple[str, str]] = []
    for ordinal, ((base, logical_identity), items) in enumerate(sorted(point_rows.items())):
        handles = tuple(sorted(item.observation.handle for item in items))
        sample = items[0]
        payload = sample.read_payload
        assert payload is not None and payload.cable_identity is not None
        key = _point_key(base, logical_identity)
        if payload.box_id:
            point_kind = "EL_BOX"
        elif len(handles) > 1:
            point_kind = "INSTALLATION_GROUP"
        elif sample.function_group == "BUS":
            point_kind = "BUS_POINT"
        else:
            point_kind = "DEVICE_POINT"
        points.append(
            PointPlan(
                key,
                base,
                logical_identity,
                point_kind,
                ordinal,
                handles,
                sample.observation.x,
                sample.observation.y,
            )
        )
        point_key_by_handle.extend((handle, key) for handle in handles)
        route_values = {fact.tag: fact.value for fact in payload.route_fields}
        for field in ROUTE_FIELDS:
            facts.append(
                OwnerFact(
                    SyncOwnerKind.SEGMENT,
                    key,
                    f"segment:{key}:{field}",
                    field,
                    route_values.get(field, ""),
                    handles[0],
                    handles,
                )
            )

    segments: list[SegmentPlan] = []
    points_by_base: dict[str, list[PointPlan]] = {}
    for point in points:
        points_by_base.setdefault(point.base, []).append(point)
    rows_by_handle = {item.observation.handle: item for item in rows}
    points_by_key = {point.key: point for point in points}
    points_by_identity = {point.logical_identity: point for point in points}
    box_points = {
        item.read_payload.box_id: points_by_key[
            _point_key(item.read_payload.cable_identity.base, _point_identity(item))
        ]
        for item in rows
        if item.read_payload is not None
        and item.read_payload.box_id
        and item.read_payload.cable_identity is not None
    }
    for base, line_points in sorted(points_by_base.items()):
        line_items = by_base[base]
        switch_line = bool(line_items) and all(
            item.device_type in {"SWITCH", "BUTTON"} for item in line_items
        )
        if switch_line:
            ordered = sorted(
                line_points,
                key=lambda point: (
                    rows_by_handle[point.handles[0]].read_payload.cable_identity.suffix_order or 0,
                    point.key,
                ),
            )
            previous: str | None = None
            for point in ordered:
                segments.append(_segment(previous, None, point, rows_by_handle))
                previous = point.key
            continue
        for point in sorted(line_points, key=lambda item: item.key):
            item = rows_by_handle[point.handles[0]]
            assert item.read_payload is not None
            reference = item.read_payload.cable_source
            source_key = None
            if reference in points_by_identity:
                source_key = points_by_identity[reference].key
            elif reference in box_points:
                source_key = box_points[reference].key
            segments.append(_segment(source_key, reference, point, rows_by_handle))

    bus_point_by_handle = {point.handle: point.point_id for point in bus_points}
    segment_index = {
        points_by_key[segment.target_point_key].logical_identity: index
        for index, segment in enumerate(segments)
    }
    for port in ports:
        if port.tag not in {"K1", "K2"} or not port.value:
            continue
        bus_point_id = bus_point_by_handle.get(port.handle)
        segment_position = segment_index.get(port.value)
        if not bus_point_id or segment_position is None:
            continue
        port_reference = f"{bus_point_id}/{port.tag}"
        segment = segments[segment_position]
        if segment.source_reference is None:
            segments[segment_position] = replace(
                segment,
                source_point_key=None,
                source_reference=port_reference,
            )

    return NormalizedCadSnapshot(
        facts=tuple(sorted(facts, key=lambda fact: fact.owner_path)),
        points=tuple(sorted(points, key=lambda point: point.key)),
        segments=tuple(sorted(segments, key=lambda segment: segment.key)),
        ports=tuple(sorted(set(ports), key=lambda port: (port.handle, port.tag))),
        keys=tuple(sorted(set(keys), key=lambda key: (key.handle, key.tag))),
        bus_points=tuple(sorted(set(bus_points), key=lambda point: point.point_id)),
        structural_reviews=tuple(sorted(set(reviews))),
        point_key_by_handle=tuple(sorted(point_key_by_handle)),
    )


def reconcile_snapshot_edge_projections(
    snapshot: NormalizedCadSnapshot,
    baselines: dict[str, object],
) -> NormalizedCadSnapshot:
    """Resolve reciprocal K-port/CABLE_SOURCE projections against accepted baselines."""

    points_by_key = {point.key: point for point in snapshot.points}
    bus_point_by_handle = {point.handle: point.point_id for point in snapshot.bus_points}
    current_ports: dict[str, set[str]] = {}
    baseline_ports: dict[str, set[str]] = {}
    for port in snapshot.ports:
        if port.tag not in {"K1", "K2"}:
            continue
        bus_point_id = bus_point_by_handle.get(port.handle)
        if not bus_point_id:
            continue
        reference = f"{bus_point_id}/{port.tag}"
        if port.value:
            current_ports.setdefault(port.value, set()).add(reference)
        baseline_value = baselines.get(f"port:{port.handle}:{port.tag}")
        if baseline_value:
            baseline_ports.setdefault(str(baseline_value), set()).add(reference)

    resolved_segments: list[SegmentPlan] = []
    reviews = [
        review
        for review in snapshot.structural_reviews
        if ":DUAL_PROJECTION_CONFLICT:" not in review
    ]
    for segment in snapshot.segments:
        target = points_by_key[segment.target_point_key].logical_identity
        current_source = segment.source_reference
        baseline_source = baselines.get(f"edge:{target}:CABLE_SOURCE") or None
        current_set = current_ports.get(target, set())
        baseline_set = baseline_ports.get(target, set())
        port_involved = bool(current_set or baseline_set)
        source_involved = bool(
            (current_source and "/" in current_source)
            or (baseline_source and "/" in str(baseline_source))
        )
        if not (port_involved or source_involved):
            resolved_segments.append(segment)
            continue

        source_changed = current_source != baseline_source
        port_changed = current_set != baseline_set
        canonical_source: str | None
        conflict = False
        if current_source and current_source in current_set:
            canonical_source = current_source
        elif source_changed and not port_changed:
            canonical_source = current_source
        elif port_changed and not source_changed:
            if len(current_set) <= 1:
                canonical_source = next(iter(current_set), None)
            else:
                canonical_source = None
                conflict = True
        elif source_changed and port_changed:
            canonical_source = None
            conflict = True
        else:
            canonical_source = current_source
            conflict = True

        if conflict:
            reviews.append(f"{segment.base}:DUAL_PROJECTION_CONFLICT:{target}")
            resolved_segments.append(segment)
        elif canonical_source and "/" in canonical_source:
            resolved_segments.append(
                replace(
                    segment,
                    source_point_key=None,
                    source_reference=canonical_source,
                )
            )
        elif canonical_source is None:
            resolved_segments.append(replace(segment, source_point_key=None, source_reference=None))
        else:
            resolved_segments.append(segment)

    return replace(
        snapshot,
        segments=tuple(sorted(resolved_segments, key=lambda segment: segment.key)),
        structural_reviews=tuple(sorted(set(reviews))),
    )


def _point_key(base: str, logical_identity: str) -> str:
    return f"{base}/{logical_identity}"


def _point_identity(item: ValidatedObservation) -> str:
    payload = item.read_payload
    assert payload is not None and payload.cable_identity is not None
    # A base-only CABLE_ID names the line, not a physical box on that line.
    # Keep existing suffixed point identities and their accepted owner baselines.
    if payload.box_id and payload.cable_identity.suffix_kind is CableSuffixKind.BASE:
        return payload.box_id
    return payload.cable_identity.raw


def _segment(
    source_key: str | None,
    source_reference: str | None,
    target: PointPlan,
    rows_by_handle: dict[str, ValidatedObservation],
) -> SegmentPlan:
    item = rows_by_handle[target.handles[0]]
    assert item.read_payload is not None
    route = tuple((fact.tag, fact.value) for fact in item.read_payload.route_fields)
    source = source_key or f"{target.base}/$SOURCE"
    return SegmentPlan(
        f"{target.base}:{source}->{target.key}",
        target.base,
        source_key,
        source_reference,
        target.key,
        target.handles,
        route,
    )
