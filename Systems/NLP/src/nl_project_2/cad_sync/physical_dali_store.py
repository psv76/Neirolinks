"""Canonical Project-owned DALI physical graph (revision 15).

Physical BOX/TRACK identity is not a protocol short address. This module only
materializes selected, validated facts already accepted in field_device. It
does not infer geometry, cable length, conduit or a missing parent.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Connection, select, update

from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    bus,
    bus_endpoint,
    bus_physical_link,
    bus_physical_node,
    field_device,
)

from .reconciliation import NormalizedCadSnapshot


class PhysicalDaliTopologyError(RuntimeError):
    """A physical graph would adopt/rebind an owner or invent a source."""


@dataclass(frozen=True, slots=True)
class PhysicalDaliSource:
    target_identity: str
    target_handle: str
    bus_designation: str
    source_reference: str
    link_kind: str


def _find_bus(connection: Connection, project_id: str, designation: str):
    row = (
        connection.execute(
            select(bus).where(
                bus.c.project_id == project_id,
                bus.c.designation == designation,
                bus.c.bus_kind == "DALI",
                bus.c.lifecycle == "ACTIVE",
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise PhysicalDaliTopologyError(f"BUS_ROOT_NOT_FOUND:{designation}")
    return row


def _resolve_source(
    connection: Connection,
    *,
    project_id: str,
    bus_row,
    source: str,
) -> dict[str, object]:
    designation = bus_row["designation"]
    if source == f"{designation}.000":
        return {
            "source_kind": "ROOT",
            "source_physical_node_id": None,
            "source_bus_endpoint_id": None,
        }
    if source.startswith(("BOX.", "TRACK.")):
        parent = (
            connection.execute(
                select(bus_physical_node).where(
                    bus_physical_node.c.project_id == project_id,
                    bus_physical_node.c.bus_id == bus_row["id"],
                    bus_physical_node.c.physical_id == source,
                )
            )
            .mappings()
            .one_or_none()
        )
        if parent is None:
            raise PhysicalDaliTopologyError(f"BUS_SOURCE_NOT_FOUND:{source}")
        return {
            "source_kind": "PHYSICAL",
            "source_physical_node_id": parent["id"],
            "source_bus_endpoint_id": None,
        }
    parent = (
        connection.execute(
            select(bus_endpoint).where(
                bus_endpoint.c.project_id == project_id,
                bus_endpoint.c.bus_id == bus_row["id"],
                bus_endpoint.c.address == source,
            )
        )
        .mappings()
        .one_or_none()
    )
    if parent is None:
        raise PhysicalDaliTopologyError(f"BUS_SOURCE_NOT_FOUND:{source}")
    return {
        "source_kind": "ADDRESSED",
        "source_physical_node_id": None,
        "source_bus_endpoint_id": parent["id"],
    }


def persist_selected_physical_graph(
    connection: Connection,
    *,
    project_id: str,
    snapshot: NormalizedCadSnapshot,
    device_ids: dict[str, str],
    active_handles: set[str],
) -> None:
    """Idempotent partial sync, fail-closed and transaction-owned by caller.

    Only active handles may supply new owner evidence or change canonical
    sources. Other accepted Project physical nodes/links remain untouched.
    """
    physical = [
        p
        for p in snapshot.bus_physical_nodes
        if p.handle in active_handles and p.handle in device_ids
    ]
    addressed = [
        p
        for p in snapshot.bus_points
        if p.handle in active_handles
        and p.handle in device_ids
        and p.bus_kind == "DALI"
        and p.source is not None
        and p.source.startswith(("BOX.", "TRACK."))
    ]
    if not physical and not addressed:
        return

    buses = {
        designation: _find_bus(connection, project_id, designation)
        for designation in {p.bus_id for p in physical} | {p.bus_id for p in addressed}
    }

    # First persist *all* selected nodes; later source resolution may refer to
    # another selected node in the same batch, independent of scan order.
    for plan in sorted(physical, key=lambda p: (p.physical_id, p.handle)):
        owner_id = device_ids[plan.handle]
        bus_row = buses[plan.bus_id]
        accepted = (
            connection.execute(
                select(bus_physical_node).where(
                    bus_physical_node.c.project_id == project_id,
                    bus_physical_node.c.physical_id == plan.physical_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        kind = "BOX" if plan.physical_id.startswith("BOX.") else "TRACK"
        if accepted is None:
            connection.execute(
                bus_physical_node.insert().values(
                    id=new_id(),
                    project_id=project_id,
                    bus_id=bus_row["id"],
                    field_device_id=owner_id,
                    physical_id=plan.physical_id,
                    physical_kind=kind,
                )
            )
        elif (
            accepted["field_device_id"] != owner_id
            or accepted["bus_id"] != bus_row["id"]
            or accepted["physical_kind"] != kind
        ):
            raise PhysicalDaliTopologyError(f"BUS_PHYSICAL_ID_OWNER_CONFLICT:{plan.physical_id}")

    targets: list[tuple[str, str, str, str, str]] = []
    for plan in physical:
        # Accepted field_device is the authoritative selected field evidence.
        owner_id = device_ids[plan.handle]
        fields = connection.execute(
            select(field_device.c.normalized_fields_json).where(
                field_device.c.id == owner_id,
                field_device.c.project_id == project_id,
                field_device.c.lifecycle == "ACTIVE",
            )
        ).scalar_one_or_none()
        if not fields or str(fields.get("BUS_ID") or "").strip() != plan.bus_id:
            raise PhysicalDaliTopologyError(f"BUS_PHYSICAL_OWNER_STALE:{plan.physical_id}")
        if str(fields.get("BUS_SOURCE") or "").strip() != plan.source:
            raise PhysicalDaliTopologyError(f"BUS_PHYSICAL_SOURCE_STALE:{plan.physical_id}")
        target = connection.execute(
            select(bus_physical_node.c.id).where(
                bus_physical_node.c.project_id == project_id,
                bus_physical_node.c.bus_id == buses[plan.bus_id]["id"],
                bus_physical_node.c.field_device_id == owner_id,
            )
        ).scalar_one_or_none()
        if target is None:
            raise PhysicalDaliTopologyError(f"BUS_PHYSICAL_ID_NOT_FOUND:{plan.physical_id}")
        targets.append((plan.bus_id, "PHYSICAL", target, plan.source, "CABLE"))
    for plan in addressed:
        owner_id = device_ids[plan.handle]
        fields = connection.execute(
            select(field_device.c.normalized_fields_json).where(
                field_device.c.id == owner_id,
                field_device.c.project_id == project_id,
                field_device.c.lifecycle == "ACTIVE",
            )
        ).scalar_one_or_none()
        if not fields or str(fields.get("BUS_SOURCE") or "").strip() != plan.source:
            raise PhysicalDaliTopologyError(f"BUS_SOURCE_STALE:{plan.point_id}")
        endpoint = connection.execute(
            select(bus_endpoint.c.id).where(
                bus_endpoint.c.project_id == project_id,
                bus_endpoint.c.bus_id == buses[plan.bus_id]["id"],
                bus_endpoint.c.field_device_id == owner_id,
                bus_endpoint.c.address == plan.point_id,
            )
        ).scalar_one_or_none()
        if endpoint is None:
            raise PhysicalDaliTopologyError(f"BUS_POINT_OWNER_NOT_FOUND:{plan.point_id}")
        targets.append((plan.bus_id, "ADDRESSED", endpoint, plan.source, plan.connection_kind))

    for bus_designation, target_kind, target_id, source_ref, link_kind in sorted(targets):
        bus_row = buses[bus_designation]
        source = _resolve_source(
            connection,
            project_id=project_id,
            bus_row=bus_row,
            source=source_ref,
        )
        target_column = (
            bus_physical_link.c.target_physical_node_id
            if target_kind == "PHYSICAL"
            else bus_physical_link.c.target_bus_endpoint_id
        )
        existing = (
            connection.execute(
                select(bus_physical_link).where(
                    bus_physical_link.c.project_id == project_id,
                    bus_physical_link.c.bus_id == bus_row["id"],
                    target_column == target_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        values = {
            **source,
            "source_kind": source["source_kind"],
            "link_kind": link_kind,
        }
        if existing is None:
            connection.execute(
                bus_physical_link.insert().values(
                    id=new_id(),
                    project_id=project_id,
                    bus_id=bus_row["id"],
                    target_kind=target_kind,
                    target_physical_node_id=target_id if target_kind == "PHYSICAL" else None,
                    target_bus_endpoint_id=target_id if target_kind == "ADDRESSED" else None,
                    **values,
                )
            )
        else:
            # The exact physical target owns this edge. Do not remove or
            # overwrite other accepted targets during partial scans.
            connection.execute(
                update(bus_physical_link)
                .where(bus_physical_link.c.id == existing["id"])
                .values(**values)
            )


def read_project_physical_sources(
    connection: Connection, *, project_id: str, binding_id: str | None = None
) -> tuple[PhysicalDaliSource, ...]:
    """Read canonical typed physical source references for Project→DWG preview.

    This is read-only; callers must still run full CAD validation before write.
    """
    rows = list(
        connection.execute(
            select(
                bus.c.designation,
                bus_physical_link,
            )
            .select_from(bus_physical_link.join(bus, bus.c.id == bus_physical_link.c.bus_id))
            .where(bus_physical_link.c.project_id == project_id)
        ).mappings()
    )
    nodes = {
        row["id"]: row
        for row in connection.execute(
            select(bus_physical_node).where(bus_physical_node.c.project_id == project_id)
        ).mappings()
    }
    endpoints = {
        row["id"]: row
        for row in connection.execute(
            select(bus_endpoint).where(bus_endpoint.c.project_id == project_id)
        ).mappings()
    }
    devices = {
        row["id"]: row
        for row in connection.execute(
            select(
                field_device.c.id,
                field_device.c.entity_handle,
                field_device.c.dwg_document_binding_id,
            ).where(
                field_device.c.project_id == project_id,
                field_device.c.lifecycle == "ACTIVE",
            )
        ).mappings()
    }
    result: list[PhysicalDaliSource] = []
    for row in rows:
        if row["source_kind"] == "ROOT":
            source = f"{row['designation']}.000"
        elif row["source_kind"] == "PHYSICAL":
            owner = nodes.get(row["source_physical_node_id"])
            if owner is None:
                raise PhysicalDaliTopologyError("DALI_PHYSICAL_ORPHAN_SOURCE")
            source = owner["physical_id"]
        else:
            owner = endpoints.get(row["source_bus_endpoint_id"])
            if owner is None or not owner["address"]:
                raise PhysicalDaliTopologyError("DALI_PHYSICAL_ORPHAN_ADDRESSED_SOURCE")
            source = owner["address"]
        if row["target_kind"] == "PHYSICAL":
            target = nodes.get(row["target_physical_node_id"])
            if target is None:
                raise PhysicalDaliTopologyError("DALI_PHYSICAL_ORPHAN_TARGET")
            target_identity = target["physical_id"]
            owner_id = target["field_device_id"]
        else:
            target = endpoints.get(row["target_bus_endpoint_id"])
            if target is None or not target["address"]:
                raise PhysicalDaliTopologyError("DALI_PHYSICAL_ORPHAN_ADDRESSED_TARGET")
            target_identity = target["address"]
            owner_id = target["field_device_id"]
        owner = devices.get(owner_id)
        if owner is None or not owner["entity_handle"]:
            raise PhysicalDaliTopologyError(f"DALI_PHYSICAL_TARGET_OWNER_MISSING:{target_identity}")
        if binding_id is not None and owner["dwg_document_binding_id"] != binding_id:
            continue
        result.append(
            PhysicalDaliSource(
                target_identity,
                owner["entity_handle"],
                row["designation"],
                source,
                row["link_kind"],
            )
        )
    return tuple(sorted(result, key=lambda x: (x.bus_designation, x.target_identity)))
