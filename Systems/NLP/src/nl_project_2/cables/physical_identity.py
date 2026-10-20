"""Resolve physical cable/BUS boundaries from canonical Project-owned entities.

A topology endpoint id belongs to one line/bus; its *physical owner* can be
shared across multiple lines. In particular, migration 000000000014 allows
multiple cable_topology_endpoint rows to reference one physical cable_point.
Neither a visible label (BOX.010), DWG coordinates, nor GOFRA_ID is an ID.

Functions in this module are pure and intentionally fail closed. The caller
must supply project-filtered database rows; see physical_identity_repository.
Continuous transit at an EL_BOX is NOT modeled as electrical commutation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .physical_conduit import PhysicalBoundary, PhysicalSpan


@dataclass(frozen=True, slots=True)
class PhysicalOwnerIndex:
    """Only validated, same-project and active physical owners."""

    board_ids: frozenset[str]
    resource_ids: frozenset[str]
    device_ids: frozenset[str]
    port_device_ids: Mapping[str, str]
    cable_points: Mapping[str, Mapping]
    point_devices: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class BoundaryResolution:
    boundary: PhysicalBoundary | None
    issue: str | None = None


@dataclass(frozen=True, slots=True)
class SegmentResolution:
    network_kind: str
    segment_id: str
    span: PhysicalSpan | None
    source: BoundaryResolution
    target: BoundaryResolution

    @property
    def complete(self) -> bool:
        return self.span is not None

    @property
    def issues(self) -> tuple[str, ...]:
        return tuple(issue for issue in (self.source.issue, self.target.issue) if issue is not None)


def _missing(reason: str) -> BoundaryResolution:
    return BoundaryResolution(None, reason)


def _owner(kind: str, identifier: str | None, allowed: frozenset[str]) -> BoundaryResolution:
    if identifier is None or identifier not in allowed:
        return _missing(f"{kind}: confirmed active physical owner is missing")
    return BoundaryResolution(PhysicalBoundary(kind, identifier))


def resolve_cable_endpoint(
    endpoint: Mapping | None,
    *,
    line: Mapping,
    owners: PhysicalOwnerIndex,
) -> BoundaryResolution:
    """Resolve one typed CableLine endpoint to its Project-wide physical owner."""

    if endpoint is None or endpoint.get("cable_line_id") != line.get("id"):
        return _missing("CABLE_ENDPOINT: missing or belongs to another line")

    kind = endpoint.get("endpoint_kind")
    if kind == "INSTANCE_RESOURCE":
        return _owner(
            "INSTANCE_RESOURCE", endpoint.get("instance_resource_id"), owners.resource_ids
        )
    if kind == "FIELD_PORT":
        port_id = endpoint.get("field_port_id")
        device_id = owners.port_device_ids.get(port_id)
        return _owner("FIELD_DEVICE", device_id, owners.device_ids)
    if kind != "TOPOLOGY_POINT":
        return _missing("CABLE_ENDPOINT: unknown endpoint kind")

    point_id = endpoint.get("cable_point_id")
    point = owners.cable_points.get(point_id)
    if point is None:
        return _missing("CABLE_POINT: physical point is missing")
    point_kind = point.get("point_kind")
    if point_kind == "INTERNAL_SOURCE":
        return _owner("BOARD", line.get("board_id"), owners.board_ids)
    if point_kind == "EL_BOX":
        # This is the persisted, possibly shared physical point UUID, *not*
        # point.logical_identity (BOX.010 is display/cable-source notation).
        return BoundaryResolution(PhysicalBoundary("EL_BOX", point_id))
    if point_kind in {"DEVICE_POINT", "BUS_POINT", "INSTALLATION_GROUP"}:
        physical_owners = tuple(dict.fromkeys(owners.point_devices.get(point_id, ())))
        if len(physical_owners) != 1:
            return _missing("CABLE_POINT: device boundary must have one confirmed physical owner")
        return _owner("FIELD_DEVICE", physical_owners[0], owners.device_ids)
    return _missing("CABLE_POINT: unsupported physical point kind")


def resolve_bus_endpoint(
    endpoint: Mapping | None,
    *,
    bus: Mapping,
    owners: PhysicalOwnerIndex,
    is_root: bool = False,
) -> BoundaryResolution:
    """Bus root is an instance_resource; bus device is its typed physical owner."""

    if is_root:
        return _owner("INSTANCE_RESOURCE", bus.get("root_resource_id"), owners.resource_ids)
    if endpoint is None or endpoint.get("bus_id") != bus.get("id"):
        return _missing("BUS_ENDPOINT: missing or belongs to another bus")
    kind = endpoint.get("endpoint_kind")
    if kind == "FIELD_DEVICE":
        return _owner("FIELD_DEVICE", endpoint.get("field_device_id"), owners.device_ids)
    if kind == "INSTANCE_RESOURCE":
        return _owner("INSTANCE_RESOURCE", endpoint.get("resource_id"), owners.resource_ids)
    return _missing("BUS_ENDPOINT: unknown physical owner kind")


def _segment_resolution(
    kind: str,
    segment_id: str,
    source: BoundaryResolution,
    target: BoundaryResolution,
) -> SegmentResolution:
    if source.boundary is None or target.boundary is None:
        return SegmentResolution(kind, segment_id, None, source, target)
    if source.boundary == target.boundary:
        issue = _missing("SEGMENT: the same physical owner is on both boundaries")
        return SegmentResolution(kind, segment_id, None, source, issue)
    return SegmentResolution(
        kind,
        segment_id,
        PhysicalSpan(source.boundary, target.boundary),
        source,
        target,
    )


def resolve_cable_segment(
    segment: Mapping,
    *,
    line: Mapping,
    endpoints: Mapping[str, Mapping],
    owners: PhysicalOwnerIndex,
) -> SegmentResolution:
    if segment.get("cable_line_id") != line.get("id"):
        raise ValueError("CableSegment has a mismatched owning CableLine")
    return _segment_resolution(
        "CABLE",
        str(segment["id"]),
        resolve_cable_endpoint(
            endpoints.get(segment.get("source_endpoint_id")), line=line, owners=owners
        ),
        resolve_cable_endpoint(
            endpoints.get(segment.get("target_endpoint_id")), line=line, owners=owners
        ),
    )


def resolve_bus_segment(
    segment: Mapping,
    *,
    bus: Mapping,
    endpoints: Mapping[str, Mapping],
    owners: PhysicalOwnerIndex,
) -> SegmentResolution | None:
    if segment.get("bus_id") != bus.get("id"):
        raise ValueError("BusSegment has a mismatched owning Bus")
    if segment.get("connection_kind") != "CABLE":
        return None  # TRACK is functional connectivity, not physical cable.
    source_id = segment.get("source_endpoint_id")
    return _segment_resolution(
        "BUS",
        str(segment["id"]),
        resolve_bus_endpoint(
            endpoints.get(source_id),
            bus=bus,
            owners=owners,
            is_root=source_id is None,
        ),
        resolve_bus_endpoint(
            endpoints.get(segment.get("target_endpoint_id")),
            bus=bus,
            owners=owners,
        ),
    )
