"""Transactional ordinary CableSegment -> DWG-facing field_device route projection.

Issue #216. Called only inside the Project assignment UnitOfWork AFTER the
entire ordinary+BUS membership batch has been applied (before commit). The
Project's physical assignment remains authoritative. For any physical device
represented by one DWG insertion, one set of GOFRA_* attributes cannot encode
different tubes: detect that ambiguity and roll back, never 'last writer wins'.

No DWG COM/write, migration, fabricated tube ID or implicit geometry change.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import UTC, datetime

from sqlalchemy import select, update

from nl_project_2.persistence.schema import (
    cable_line,
    cable_point,
    cable_point_field_device,
    cable_segment,
    cable_topology_endpoint,
    conduit,
    conduit_segment_assignment,
    field_device,
    field_port,
)

from .physical_conduit import PhysicalAssignmentError

_ROUTE_KEYS = ("GOFRA_TYPE", "GOFRA_COLOR", "GOFRA_ID")
_UNMIRRORED_POINTS = frozenset({"INTERNAL_SOURCE"})


def _route(fact: Mapping | None) -> tuple[str, str, str]:
    if fact is None:
        return "", "", ""
    return (
        str(fact["conduit_type"] or ""),
        str(fact["color"] or ""),
        str(fact["designation"] or ""),
    )


def reconcile_ordinary_route_mirrors(
    uow,
    project_id: str,
    changes: Mapping[str, tuple[str | None, str | None]],
) -> None:
    """Reconcile all changed ordinary segments + affected target DWG insertions.

    changes maps exact changed CableSegment IDs -> (old_tube_id, new_tube_id).
    The assignment tables MUST already reflect new_tube_id. Raises on missing
    or ambiguous physical projection. Caller owns and rolls back the UoW.
    """

    if not changes:
        return

    now = datetime.now(UTC)
    all_segments = {
        row["id"]: dict(row)
        for row in uow.execute(
            select(
                cable_segment.c.id,
                cable_segment.c.target_endpoint_id,
                cable_segment.c.gofra_type,
                cable_segment.c.gofra_color,
            )
            .join(cable_line, cable_line.c.id == cable_segment.c.cable_line_id)
            .where(
                cable_segment.c.project_id == project_id,
                cable_line.c.project_id == project_id,
                cable_line.c.lifecycle == "ACTIVE",
            )
        ).mappings()
    }
    if not set(changes).issubset(all_segments):
        raise PhysicalAssignmentError("Ordinary route mirror: inactive segment in batch")

    endpoints = {
        row["id"]: dict(row)
        for row in uow.execute(
            select(
                cable_topology_endpoint.c.id,
                cable_topology_endpoint.c.endpoint_kind,
                cable_topology_endpoint.c.cable_point_id,
                cable_topology_endpoint.c.field_port_id,
            ).where(cable_topology_endpoint.c.project_id == project_id)
        ).mappings()
    }
    points = {
        row["id"]: row["point_kind"]
        for row in uow.execute(
            select(cable_point.c.id, cable_point.c.point_kind).where(
                cable_point.c.project_id == project_id
            )
        ).mappings()
    }
    active_devices = {
        row["id"]: dict(row)
        for row in uow.execute(
            select(
                field_device.c.id,
                field_device.c.normalized_fields_json,
            ).where(
                field_device.c.project_id == project_id,
                field_device.c.lifecycle == "ACTIVE",
            )
        ).mappings()
    }
    point_devices: dict[str, set[str]] = defaultdict(set)
    for row in uow.execute(
        select(
            cable_point_field_device.c.cable_point_id,
            cable_point_field_device.c.field_device_id,
        ).where(cable_point_field_device.c.project_id == project_id)
    ).mappings():
        # Inactive owners cannot be silently dropped from the projection.
        if row["field_device_id"] not in active_devices:
            raise PhysicalAssignmentError(
                "Ordinary route mirror: physical point references an inactive device"
            )
        point_devices[row["cable_point_id"]].add(row["field_device_id"])

    port_devices = {
        row["id"]: row["field_device_id"]
        for row in uow.execute(
            select(field_port.c.id, field_port.c.field_device_id).where(
                field_port.c.project_id == project_id,
                field_port.c.lifecycle == "ACTIVE",
            )
        ).mappings()
    }
    segment_owners: dict[str, str | None] = {}
    for sid, segment in all_segments.items():
        endpoint = endpoints.get(segment["target_endpoint_id"])
        if endpoint is None:
            raise PhysicalAssignmentError(f"Segment {sid}: no target endpoint")
        kind = endpoint["endpoint_kind"]
        owner = None
        if kind == "TOPOLOGY_POINT":
            point_id = endpoint["cable_point_id"]
            point_kind = points.get(point_id)
            if point_kind is None:
                raise PhysicalAssignmentError(f"Segment {sid}: missing Project point")
            device_ids = point_devices.get(point_id, set())
            if len(device_ids) > 1:
                raise PhysicalAssignmentError(f"Segment {sid}: multiple DWG owners")
            if device_ids:
                owner = next(iter(device_ids))
            elif point_kind not in _UNMIRRORED_POINTS and point_kind != "EL_BOX":
                raise PhysicalAssignmentError(
                    f"Segment {sid}: physical endpoint has no DWG device owner"
                )
        elif kind == "FIELD_PORT":
            owner = port_devices.get(endpoint["field_port_id"])
            if owner is None:
                raise PhysicalAssignmentError(f"Segment {sid}: no active field port owner")
        elif kind == "INSTANCE_RESOURCE":
            # An instance resource can have no corresponding AutoCAD block
            # to carry GOFRA_*. Until an explicit projection is designed,
            # never claim that the DWG-facing mirror is complete.
            if sid in changes:
                raise PhysicalAssignmentError(
                    f"Segment {sid}: INSTANCE_RESOURCE DWG route projection undefined"
                )
        else:
            raise PhysicalAssignmentError(f"Segment {sid}: unsupported target owner")
        if owner is not None and owner not in active_devices:
            raise PhysicalAssignmentError(f"Segment {sid}: inactive DWG device owner")
        segment_owners[sid] = owner

    current_assignments: dict[str, str] = {}
    for row in uow.execute(
        select(
            conduit_segment_assignment.c.cable_segment_id,
            conduit_segment_assignment.c.conduit_id,
        ).where(conduit_segment_assignment.c.project_id == project_id)
    ):
        if row[0] in current_assignments:
            raise PhysicalAssignmentError(f"Segment {row[0]} assigned to multiple tubes")
        current_assignments[row[0]] = row[1]

    tube_ids = set(current_assignments.values()) | {
        item for before_after in changes.values() for item in before_after if item
    }
    tubes = {
        row["id"]: dict(row)
        for row in uow.execute(
            select(
                conduit.c.id,
                conduit.c.conduit_type,
                conduit.c.color,
                conduit.c.designation,
            ).where(
                conduit.c.project_id == project_id,
                conduit.c.lifecycle == "ACTIVE",
                conduit.c.id.in_(tube_ids),
            )
        ).mappings()
    }
    if tube_ids != set(tubes):
        raise PhysicalAssignmentError("Ordinary route mirror: missing/inactive tube")

    for sid, (old_id, new_id) in changes.items():
        if current_assignments.get(sid) != new_id:
            raise PhysicalAssignmentError(
                f"Segment {sid}: route assignment differs from atomic batch"
            )
        row = all_segments[sid]
        new_route = _route(tubes.get(new_id))
        if (row["gofra_type"] or "", row["gofra_color"] or "") != new_route[:2]:
            result = uow.execute(
                update(cable_segment)
                .where(
                    cable_segment.c.project_id == project_id,
                    cable_segment.c.id == sid,
                )
                .values(
                    gofra_type=new_route[0] or None,
                    gofra_color=new_route[1] or None,
                    row_version=cable_segment.c.row_version + 1,
                    updated_at_utc=now,
                )
            )
            if result.rowcount != 1:
                raise PhysicalAssignmentError(
                    f"Segment {sid}: could not update Project route facts"
                )

    members_by_device: dict[str, list[str]] = defaultdict(list)
    for sid, owner in segment_owners.items():
        if owner:
            members_by_device[owner].append(sid)

    affected_devices = {
        segment_owners[sid] for sid in changes if segment_owners[sid] is not None
    }
    for device_id in sorted(affected_devices):
        related = members_by_device[device_id]
        before: set[tuple[str, str, str]] = set()
        after: set[tuple[str, str, str]] = set()
        for sid in related:
            current_tube = current_assignments.get(sid)
            prior_tube = changes[sid][0] if sid in changes else current_tube
            # Pre-existing unassigned route details are unconfirmed legacy
            # data. Their origin cannot be inferred as an empty Conduit.
            if sid not in changes and current_tube is None:
                segment = all_segments[sid]
                if segment["gofra_type"] or segment["gofra_color"]:
                    raise PhysicalAssignmentError(
                        f"DWG device {device_id}: unassigned segment has route facts"
                    )
            before.add(_route(tubes.get(prior_tube)))
            after.add(_route(tubes.get(current_tube)))
        if len(before) != 1 or len(after) != 1:
            raise PhysicalAssignmentError(
                f"DWG device {device_id}: conflicting incoming segment Conduits"
            )
        current_fields = dict(active_devices[device_id]["normalized_fields_json"] or {})
        before_route = next(iter(before))
        after_route = next(iter(after))
        actual_route = tuple(str(current_fields.get(key) or "") for key in _ROUTE_KEYS)
        if actual_route != before_route:
            raise PhysicalAssignmentError(
                f"DWG device {device_id}: route baseline is not reconciled with Project"
            )
        if after_route == before_route:
            continue
        for key, value in zip(_ROUTE_KEYS, after_route, strict=True):
            current_fields[key] = value
        result = uow.execute(
            update(field_device)
            .where(
                field_device.c.id == device_id,
                field_device.c.project_id == project_id,
                field_device.c.lifecycle == "ACTIVE",
            )
            .values(
                normalized_fields_json=current_fields,
                row_version=field_device.c.row_version + 1,
                updated_at_utc=now,
            )
        )
        if result.rowcount != 1:
            raise PhysicalAssignmentError(f"DWG device {device_id}: owner changed")
