"""Read-only SQLAlchemy adapter for physical identity checks (Issue #216).

Accepts an existing Connection / UnitOfWork: callers can read the full Project
snapshot within the *same transaction* later used for assignment validation.
No migration, normalization, repair, sync, COM, or write occurs here.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select

from nl_project_2.persistence.schema import (
    board,
    bus,
    bus_endpoint,
    bus_segment,
    cable_line,
    cable_point,
    cable_point_field_device,
    cable_segment,
    cable_topology_endpoint,
    field_device,
    field_port,
    instance_resource,
    project_instance,
)

from .physical_identity import (
    PhysicalOwnerIndex,
    SegmentResolution,
    resolve_bus_segment,
    resolve_cable_segment,
)


def load_physical_segment_resolutions(connection, project_id: str) -> tuple[SegmentResolution, ...]:
    """Resolve known Project owners; incomplete physical boundaries stay unresolved."""

    boards = frozenset(
        connection.execute(
            select(board.c.id).where(
                board.c.project_id == project_id,
                board.c.lifecycle == "ACTIVE",
            )
        ).scalars()
    )
    devices = frozenset(
        connection.execute(
            select(field_device.c.id).where(
                field_device.c.project_id == project_id,
                field_device.c.lifecycle == "ACTIVE",
            )
        ).scalars()
    )
    resources = frozenset(
        connection.execute(
            select(instance_resource.c.id)
            .join(
                project_instance,
                project_instance.c.id == instance_resource.c.project_instance_id,
            )
            .where(
                instance_resource.c.project_id == project_id,
                instance_resource.c.active.is_(True),
                project_instance.c.lifecycle == "ACTIVE",
                project_instance.c.project_id == project_id,
            )
        ).scalars()
    )
    ports = {
        row["id"]: row["field_device_id"]
        for row in connection.execute(
            select(field_port.c.id, field_port.c.field_device_id).where(
                field_port.c.project_id == project_id,
                field_port.c.lifecycle == "ACTIVE",
            )
        ).mappings()
        if row["field_device_id"] in devices
    }
    points = {
        row["id"]: dict(row)
        for row in connection.execute(
            select(cable_point).where(cable_point.c.project_id == project_id)
        ).mappings()
    }
    memberships: dict[str, list[str]] = defaultdict(list)
    for row in connection.execute(
        select(
            cable_point_field_device.c.cable_point_id,
            cable_point_field_device.c.field_device_id,
        ).where(cable_point_field_device.c.project_id == project_id)
    ).mappings():
        if row["field_device_id"] in devices:
            memberships[row["cable_point_id"]].append(row["field_device_id"])
    owners = PhysicalOwnerIndex(
        board_ids=boards,
        resource_ids=resources,
        device_ids=devices,
        port_device_ids=ports,
        cable_points=points,
        point_devices={point_id: tuple(ids) for point_id, ids in memberships.items()},
    )

    ordinary_lines = {
        row["id"]: dict(row)
        for row in connection.execute(
            select(cable_line).where(
                cable_line.c.project_id == project_id,
                cable_line.c.lifecycle == "ACTIVE",
            )
        ).mappings()
    }
    cable_endpoints = {
        row["id"]: dict(row)
        for row in connection.execute(
            select(cable_topology_endpoint).where(
                cable_topology_endpoint.c.project_id == project_id
            )
        ).mappings()
    }

    resolved: list[SegmentResolution] = []
    for segment in connection.execute(
        select(cable_segment)
        .join(cable_line, cable_line.c.id == cable_segment.c.cable_line_id)
        .where(
            cable_segment.c.project_id == project_id,
            cable_line.c.project_id == project_id,
            cable_line.c.lifecycle == "ACTIVE",
        )
    ).mappings():
        line = ordinary_lines.get(segment["cable_line_id"])
        if line is None:
            continue
        resolved.append(
            resolve_cable_segment(
                segment, line=line, endpoints=cable_endpoints, owners=owners
            )
        )

    active_buses = {
        row["id"]: dict(row)
        for row in connection.execute(
            select(bus).where(
                bus.c.project_id == project_id,
                bus.c.lifecycle == "ACTIVE",
            )
        ).mappings()
    }
    bus_endpoints = {
        row["id"]: dict(row)
        for row in connection.execute(
            select(bus_endpoint).where(bus_endpoint.c.project_id == project_id)
        ).mappings()
    }
    for segment in connection.execute(
        select(bus_segment)
        .join(bus, bus.c.id == bus_segment.c.bus_id)
        .where(
            bus_segment.c.project_id == project_id,
            bus.c.project_id == project_id,
            bus.c.lifecycle == "ACTIVE",
            bus_segment.c.connection_kind == "CABLE",
        )
    ).mappings():
        owner_bus = active_buses.get(segment["bus_id"])
        if owner_bus is None:
            continue
        result = resolve_bus_segment(
            segment, bus=owner_bus, endpoints=bus_endpoints, owners=owners
        )
        if result is not None:
            resolved.append(result)

    # A reproducible read view. Nothing is persisted or inferred from raw labels.
    return tuple(sorted(resolved, key=lambda row: (row.network_kind, row.segment_id)))
