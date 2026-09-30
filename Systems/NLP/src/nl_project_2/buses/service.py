"""Transactional persistence and derived topology for physical buses."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import Engine, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError

from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    bus,
    bus_branch,
    bus_branch_point,
    bus_endpoint,
    bus_segment,
    dali_group,
    dali_group_member,
    field_device,
    functional_relation,
    instance_resource,
    passport_resource_definition,
    project_instance,
)
from nl_project_2.persistence.uow import UnitOfWork
from nl_project_2.resource_labels import resource_technical_identity, resource_user_label

from .domain import TopologyPoint, TopologyResult, branched_topology, rs485_topology

_DALI_GROUP = re.compile(r"^D\.[0-9]{3}$")


class BusError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class BusReceipt:
    bus_id: str
    endpoint_count: int


@dataclass(frozen=True, slots=True)
class DaliGroupReceipt:
    group_id: str
    member_count: int


class BusService:
    """Physical bus topology and Project-owned DALI group use cases."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create_rs485_bus(
        self,
        *,
        project_id: str,
        designation: str,
        root_resource_id: str,
        points: tuple[dict, ...],
    ) -> BusReceipt:
        topology = rs485_topology(
            root_resource_id,
            designation,
            tuple(
                TopologyPoint(
                    self._point_owner_id(item),
                    str(item["cable_id"]),
                    Decimal(str(item["x_mm"])),
                    Decimal(str(item["y_mm"])),
                )
                for item in points
            ),
            branches=tuple(item.get("branch") for item in points if item.get("branch")),
        )
        if topology.errors:
            raise BusError("; ".join(topology.errors))
        owner_ids = (root_resource_id, *(self._point_owner_id(item) for item in points))
        if len(set(owner_ids)) != len(owner_ids):
            raise BusError(
                "Bus source and endpoints must be distinct resources/physical identities"
            )
        bus_id = new_id()
        with UnitOfWork(self._engine) as uow:
            self._validate_rs485_resources(uow, project_id, (root_resource_id,))
            self._validate_rs485_points(uow, project_id, points)
            self._validate_root_available(uow, project_id, root_resource_id)
            uow.execute(
                bus.insert().values(
                    id=bus_id,
                    project_id=project_id,
                    bus_kind="RS485",
                    designation=designation,
                    root_resource_id=root_resource_id,
                    topology_policy="LINEAR_SUFFIX_ORDER",
                    lifecycle="ACTIVE",
                )
            )
            ordered = sorted(
                points,
                key=lambda item: int(str(item["cable_id"]).rsplit(".", 1)[1]),
            )
            previous_endpoint_id = None
            for order, point in enumerate(ordered, start=1):
                endpoint_id = new_id()
                uow.execute(
                    bus_endpoint.insert().values(
                        id=endpoint_id,
                        project_id=project_id,
                        bus_id=bus_id,
                        endpoint_kind=(
                            "FIELD_DEVICE" if point.get("field_device_id") else "INSTANCE_RESOURCE"
                        ),
                        resource_id=point.get("resource_id"),
                        field_device_id=point.get("field_device_id"),
                        endpoint_role="DEVICE",
                        address=point["cable_id"],
                        endpoint_order=order,
                    )
                )
                uow.execute(
                    bus_segment.insert().values(
                        id=new_id(),
                        project_id=project_id,
                        bus_id=bus_id,
                        source_endpoint_id=previous_endpoint_id,
                        target_endpoint_id=endpoint_id,
                        connection_kind="CABLE",
                        origin_kind="PROJECT",
                        migration_state="CONFIRMED",
                    )
                )
                previous_endpoint_id = endpoint_id
            uow.commit()
        return BusReceipt(bus_id, len(points))

    def add_rs485_endpoint(
        self,
        *,
        project_id: str,
        bus_id: str,
        resource_id: str,
        cable_id: str,
    ) -> BusReceipt:
        """Add one instance-resource endpoint and restore numeric suffix ordering."""

        return self._add_rs485_typed_endpoint(
            project_id=project_id,
            bus_id=bus_id,
            point={"resource_id": resource_id, "cable_id": cable_id},
        )

    def add_rs485_field_endpoint(
        self,
        *,
        project_id: str,
        bus_id: str,
        field_device_id: str,
        cable_id: str,
    ) -> BusReceipt:
        """Add an approved field device without creating a fake ProjectInstance."""

        return self._add_rs485_typed_endpoint(
            project_id=project_id,
            bus_id=bus_id,
            point={"field_device_id": field_device_id, "cable_id": cable_id},
        )

    def _add_rs485_typed_endpoint(
        self, *, project_id: str, bus_id: str, point: dict
    ) -> BusReceipt:
        owner_id = self._point_owner_id(point)
        cable_id = str(point["cable_id"])

        try:
            with UnitOfWork(self._engine) as uow:
                bus_row = self._rs485_bus_row(uow, project_id, bus_id)
                existing = list(
                    uow.execute(
                        select(bus_endpoint).where(
                            bus_endpoint.c.project_id == project_id,
                            bus_endpoint.c.bus_id == bus_id,
                        )
                    ).mappings()
                )
                owner_ids = (
                    bus_row["root_resource_id"],
                    *(self._endpoint_owner_id(row) for row in existing),
                    owner_id,
                )
                if len(set(owner_ids)) != len(owner_ids):
                    raise BusError(
                        "Bus source and endpoints must be distinct resources/physical identities"
                    )
                self._validate_rs485_resources(uow, project_id, (bus_row["root_resource_id"],))
                self._validate_rs485_points(uow, project_id, (point,))
                points = tuple(
                    TopologyPoint(
                        self._endpoint_owner_id(row),
                        row["address"],
                        Decimal("0"),
                        Decimal("0"),
                    )
                    for row in existing
                ) + (TopologyPoint(owner_id, cable_id, Decimal("0"), Decimal("0")),)
                topology = rs485_topology(
                    bus_row["root_resource_id"],
                    bus_row["designation"],
                    points,
                )
                if topology.errors:
                    raise BusError("; ".join(topology.errors))
                uow.execute(
                    bus_endpoint.insert().values(
                        id=new_id(),
                        project_id=project_id,
                        bus_id=bus_id,
                        endpoint_kind=(
                            "FIELD_DEVICE" if point.get("field_device_id") else "INSTANCE_RESOURCE"
                        ),
                        resource_id=point.get("resource_id"),
                        field_device_id=point.get("field_device_id"),
                        endpoint_role="DEVICE",
                        address=cable_id,
                        endpoint_order=None,
                    )
                )
                endpoint_count = self._reorder_rs485_endpoints(uow, project_id, bus_id)
                self._replace_linear_segments(uow, project_id, bus_id)
                uow.commit()
        except IntegrityError as exc:
            raise BusError("RS-485 endpoint conflicts with existing bus data") from exc
        return BusReceipt(bus_id, endpoint_count)

    def remove_rs485_endpoint(
        self,
        *,
        project_id: str,
        bus_id: str,
        endpoint_id: str,
    ) -> BusReceipt:
        """Remove exactly one endpoint without renaming remaining addresses."""

        with UnitOfWork(self._engine) as uow:
            self._rs485_bus_row(uow, project_id, bus_id)
            endpoint = uow.execute(
                select(bus_endpoint.c.id).where(
                    bus_endpoint.c.id == endpoint_id,
                    bus_endpoint.c.project_id == project_id,
                    bus_endpoint.c.bus_id == bus_id,
                )
            ).scalar_one_or_none()
            if endpoint is None:
                raise BusError("RS-485 endpoint not found in the selected bus")
            uow.execute(
                delete(bus_segment).where(
                    bus_segment.c.project_id == project_id,
                    bus_segment.c.bus_id == bus_id,
                )
            )
            uow.execute(
                delete(bus_endpoint).where(
                    bus_endpoint.c.id == endpoint_id,
                    bus_endpoint.c.project_id == project_id,
                    bus_endpoint.c.bus_id == bus_id,
                )
            )
            endpoint_count = self._reorder_rs485_endpoints(uow, project_id, bus_id)
            self._replace_linear_segments(uow, project_id, bus_id)
            uow.commit()
        return BusReceipt(bus_id, endpoint_count)

    def delete_rs485_bus(self, *, project_id: str, bus_id: str) -> None:
        """Delete an RS-485 bus and its endpoints, preserving resources and relations."""

        with UnitOfWork(self._engine) as uow:
            self._rs485_bus_row(uow, project_id, bus_id)
            uow.execute(delete(bus_segment).where(bus_segment.c.bus_id == bus_id))
            uow.execute(
                delete(bus_endpoint).where(
                    bus_endpoint.c.project_id == project_id,
                    bus_endpoint.c.bus_id == bus_id,
                )
            )
            result = uow.execute(
                delete(bus).where(
                    bus.c.id == bus_id,
                    bus.c.project_id == project_id,
                    bus.c.bus_kind == "RS485",
                    bus.c.lifecycle == "ACTIVE",
                )
            )
            if result.rowcount != 1:
                raise BusError("RS-485 bus not found")
            uow.commit()

    def list_rs485_resource_candidates(self, project_id: str) -> list[dict]:
        """Return active Project RS-485 resources for future source/endpoint selectors."""

        with self._engine.connect() as connection:
            occupied_sources = set(
                connection.execute(
                    select(bus.c.root_resource_id).where(
                        bus.c.project_id == project_id,
                        bus.c.lifecycle == "ACTIVE",
                    )
                ).scalars()
            )
            rows = connection.execute(
                select(
                    instance_resource.c.id,
                    instance_resource.c.project_instance_id,
                    project_instance.c.designation.label("instance_designation"),
                    instance_resource.c.resource_key,
                    instance_resource.c.ordinal,
                    instance_resource.c.snapshot_json,
                    passport_resource_definition.c.display_json,
                )
                .join(
                    project_instance,
                    project_instance.c.id == instance_resource.c.project_instance_id,
                )
                .join(
                    passport_resource_definition,
                    passport_resource_definition.c.id
                    == instance_resource.c.passport_resource_definition_id,
                )
                .where(
                    instance_resource.c.project_id == project_id,
                    project_instance.c.project_id == project_id,
                    instance_resource.c.resource_kind == "RS485_INTERFACE",
                    instance_resource.c.active.is_(True),
                    project_instance.c.lifecycle == "ACTIVE",
                )
                .order_by(
                    project_instance.c.designation,
                    instance_resource.c.resource_key,
                    instance_resource.c.ordinal,
                )
            ).mappings()
            return [
                {
                    **dict(row),
                    "resource_designation": row["resource_key"],
                    "label": resource_user_label(row),
                    "technical_identity": resource_technical_identity(row),
                    "source_available": row["id"] not in occupied_sources,
                    "endpoint_available": True,
                }
                for row in rows
            ]

    def list_bus_resource_labels(self, project_id: str) -> dict[str, dict[str, str]]:
        """Return consistent user/technical labels for all physical-bus resources."""

        with self._engine.connect() as connection:
            rows = connection.execute(
                select(
                    instance_resource.c.id,
                    project_instance.c.designation.label("instance_designation"),
                    instance_resource.c.resource_key,
                    instance_resource.c.ordinal,
                    instance_resource.c.snapshot_json,
                    passport_resource_definition.c.display_json,
                )
                .join(
                    project_instance,
                    project_instance.c.id == instance_resource.c.project_instance_id,
                )
                .join(
                    passport_resource_definition,
                    passport_resource_definition.c.id
                    == instance_resource.c.passport_resource_definition_id,
                )
                .where(
                    instance_resource.c.project_id == project_id,
                    instance_resource.c.active.is_(True),
                    project_instance.c.lifecycle == "ACTIVE",
                    instance_resource.c.resource_kind.in_(
                        ("RS485_INTERFACE", "DALI_BUS_PORT", "KNX_BUS_PORT")
                    ),
                )
            ).mappings()
            return {
                str(row["id"]): {
                    "label": resource_user_label(row),
                    "technical_identity": resource_technical_identity(row),
                }
                for row in rows
            }

    def create_branched_bus(
        self,
        *,
        project_id: str,
        bus_kind: str,
        designation: str,
        root_resource_id: str,
        points: tuple[dict, ...],
        branches: tuple[tuple[str, ...], ...],
    ) -> BusReceipt:
        kind = bus_kind.upper()
        if kind not in {"DALI", "KNX"}:
            raise BusError("Branched bus kind must be DALI or KNX")
        topology_points = self._topology_points(points)
        topology = branched_topology(
            root_resource_id,
            designation,
            topology_points,
            branches,
        )
        if topology.errors:
            raise BusError("; ".join(topology.errors))
        if kind == "DALI" and len(points) > 63:
            raise BusError("DALI_DEVICE_LIMIT_EXCEEDED")
        resource_ids = (root_resource_id, *(item["resource_id"] for item in points))
        if len(set(resource_ids)) != len(resource_ids):
            raise BusError("Bus source and endpoints must be distinct resources")
        bus_id = new_id()
        try:
            with UnitOfWork(self._engine) as uow:
                self._validate_branched_resources(uow, project_id, kind, resource_ids)
                self._validate_root_available(uow, project_id, root_resource_id)
                uow.execute(
                    bus.insert().values(
                        id=bus_id,
                        project_id=project_id,
                        bus_kind=kind,
                        designation=designation,
                        root_resource_id=root_resource_id,
                        topology_policy="ORDERED_BRANCHES",
                        lifecycle="ACTIVE",
                    )
                )
                self._insert_branched_rows(
                    uow,
                    project_id=project_id,
                    bus_id=bus_id,
                    points=points,
                    branches=branches,
                )
                uow.commit()
        except IntegrityError as exc:
            raise BusError("Branched bus conflicts with existing Project data") from exc
        return BusReceipt(bus_id, len(points))

    def replace_branched_topology(
        self,
        *,
        project_id: str,
        bus_id: str,
        points: tuple[dict, ...],
        branches: tuple[tuple[str, ...], ...],
    ) -> BusReceipt:
        stored = self.get_bus(project_id, bus_id)
        kind = stored["bus_kind"]
        if kind not in {"DALI", "KNX"}:
            raise BusError("Only DALI/KNX topology has ordered branches")
        topology = branched_topology(
            stored["root_resource_id"],
            stored["designation"],
            self._topology_points(points),
            branches,
        )
        if topology.errors:
            raise BusError("; ".join(topology.errors))
        if kind == "DALI" and len(points) > 63:
            raise BusError("DALI_DEVICE_LIMIT_EXCEEDED")
        resource_ids = tuple(item["resource_id"] for item in points)
        try:
            with UnitOfWork(self._engine) as uow:
                self._validate_branched_resources(
                    uow,
                    project_id,
                    kind,
                    (stored["root_resource_id"], *resource_ids),
                )
                grouped = set(
                    uow.execute(
                        select(dali_group_member.c.resource_id)
                        .join(dali_group, dali_group.c.id == dali_group_member.c.dali_group_id)
                        .where(
                            dali_group.c.project_id == project_id,
                            dali_group.c.bus_id == bus_id,
                            dali_group.c.lifecycle == "ACTIVE",
                        )
                    ).scalars()
                )
                if not grouped.issubset(resource_ids):
                    raise BusError("Topology replacement would orphan DALI group members")
                branch_ids = select(bus_branch.c.id).where(
                    bus_branch.c.project_id == project_id,
                    bus_branch.c.bus_id == bus_id,
                )
                uow.execute(
                    update(bus_endpoint)
                    .where(
                        bus_endpoint.c.project_id == project_id,
                        bus_endpoint.c.bus_id == bus_id,
                    )
                    .values(bus_branch_id=None)
                )
                uow.execute(
                    delete(bus_branch_point).where(
                        bus_branch_point.c.project_id == project_id,
                        bus_branch_point.c.bus_branch_id.in_(branch_ids),
                    )
                )
                uow.execute(
                    delete(bus_branch).where(
                        bus_branch.c.project_id == project_id,
                        bus_branch.c.bus_id == bus_id,
                    )
                )
                uow.execute(
                    delete(bus_segment).where(
                        bus_segment.c.project_id == project_id,
                        bus_segment.c.bus_id == bus_id,
                    )
                )
                uow.execute(
                    delete(bus_endpoint).where(
                        bus_endpoint.c.project_id == project_id,
                        bus_endpoint.c.bus_id == bus_id,
                    )
                )
                self._insert_branched_rows(
                    uow,
                    project_id=project_id,
                    bus_id=bus_id,
                    points=points,
                    branches=branches,
                )
                uow.commit()
        except IntegrityError as exc:
            raise BusError("Topology replacement conflicts with Project data") from exc
        return BusReceipt(bus_id, len(points))

    def list_buses(self, project_id: str) -> list[dict]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(bus)
                .where(bus.c.project_id == project_id, bus.c.lifecycle == "ACTIVE")
                .order_by(bus.c.designation)
            ).mappings()
            return [dict(row) for row in rows]

    def get_bus(self, project_id: str, bus_id: str) -> dict:
        with self._engine.connect() as connection:
            bus_row = (
                connection.execute(
                    select(bus).where(
                        bus.c.id == bus_id,
                        bus.c.project_id == project_id,
                        bus.c.lifecycle == "ACTIVE",
                    )
                )
                .mappings()
                .one_or_none()
            )
            if bus_row is None:
                raise BusError("Bus not found")
            endpoints = connection.execute(
                select(bus_endpoint)
                .where(
                    bus_endpoint.c.bus_id == bus_id,
                    bus_endpoint.c.project_id == project_id,
                )
                .order_by(bus_endpoint.c.endpoint_order, bus_endpoint.c.address)
            ).mappings()
            branch_rows = list(
                connection.execute(
                    select(bus_branch)
                    .where(
                        bus_branch.c.bus_id == bus_id,
                        bus_branch.c.project_id == project_id,
                    )
                    .order_by(bus_branch.c.branch_order)
                ).mappings()
            )
            branches = []
            for branch_row in branch_rows:
                resource_ids = tuple(
                    connection.execute(
                        select(bus_branch_point.c.resource_id)
                        .where(
                            bus_branch_point.c.project_id == project_id,
                            bus_branch_point.c.bus_branch_id == branch_row["id"],
                        )
                        .order_by(bus_branch_point.c.point_order)
                    ).scalars()
                )
                branches.append({**dict(branch_row), "resource_ids": resource_ids})
            return {
                **dict(bus_row),
                "BUS_ID": bus_row["designation"],
                "ROOT_POINT_ID": f"{bus_row['designation']}.000",
                "endpoints": tuple(dict(row) for row in endpoints),
                "branches": tuple(branches),
                "segments": tuple(
                    dict(row)
                    for row in connection.execute(
                        select(bus_segment)
                        .where(
                            bus_segment.c.project_id == project_id,
                            bus_segment.c.bus_id == bus_id,
                        )
                        .order_by(bus_segment.c.target_endpoint_id)
                    ).mappings()
                ),
            }

    def topology(
        self,
        *,
        project_id: str,
        bus_id: str,
        coordinates: dict[str, tuple[Decimal | str | int, Decimal | str | int]],
    ) -> TopologyResult:
        stored = self.get_bus(project_id, bus_id)
        root = stored["root_resource_id"]
        root_coordinates = coordinates.get(root)
        missing = []
        if root_coordinates is None:
            missing.append(root)
            root_coordinates = (0, 0)
        points = []
        for endpoint in stored["endpoints"]:
            owner_id = self._endpoint_owner_id(endpoint)
            coordinate = coordinates.get(owner_id)
            if coordinate is None:
                missing.append(owner_id)
                coordinate = (0, 0)
            points.append(
                TopologyPoint(
                    owner_id,
                    endpoint["address"],
                    Decimal(str(coordinate[0])),
                    Decimal(str(coordinate[1])),
                )
            )
        if stored["bus_kind"] == "RS485":
            result = rs485_topology(
                root,
                stored["designation"],
                tuple(points),
                root_x_mm=Decimal(str(root_coordinates[0])),
                root_y_mm=Decimal(str(root_coordinates[1])),
            )
        else:
            result = branched_topology(
                root,
                stored["designation"],
                tuple(points),
                tuple(branch["resource_ids"] for branch in stored["branches"]),
                root_x_mm=Decimal(str(root_coordinates[0])),
                root_y_mm=Decimal(str(root_coordinates[1])),
            )
        if not missing:
            return result
        return TopologyResult(
            "INCOMPATIBLE",
            result.nodes,
            result.edges,
            result.total_length_mm,
            (*result.errors, *(f"MISSING_COORDINATE:{item}" for item in missing)),
        )

    def create_dali_group(
        self,
        *,
        project_id: str,
        bus_id: str,
        group_key: str,
        member_resource_ids: tuple[str, ...],
    ) -> DaliGroupReceipt:
        if not _DALI_GROUP.fullmatch(group_key):
            raise BusError("DALI group identifier must match D.YYY")
        if not member_resource_ids or len(set(member_resource_ids)) != len(member_resource_ids):
            raise BusError("DALI group requires unique non-empty membership")
        stored = self.get_bus(project_id, bus_id)
        if stored["bus_kind"] != "DALI":
            raise BusError("DALI group must belong to a physical DALI bus")
        endpoint_ids = {row["resource_id"] for row in stored["endpoints"]}
        if not set(member_resource_ids).issubset(endpoint_ids):
            raise BusError("DALI group members must be endpoints of the same physical bus")
        group_id = new_id()
        try:
            with UnitOfWork(self._engine) as uow:
                uow.execute(
                    dali_group.insert().values(
                        id=group_id,
                        project_id=project_id,
                        bus_id=bus_id,
                        group_key=group_key,
                        lifecycle="ACTIVE",
                    )
                )
                for resource_id in member_resource_ids:
                    uow.execute(
                        dali_group_member.insert().values(
                            id=new_id(),
                            project_id=project_id,
                            dali_group_id=group_id,
                            resource_id=resource_id,
                        )
                    )
                uow.commit()
        except IntegrityError as exc:
            raise BusError("DALI group identifier or member conflicts with Project data") from exc
        return DaliGroupReceipt(group_id, len(member_resource_ids))

    def list_dali_groups(self, project_id: str, bus_id: str | None = None) -> list[dict]:
        with self._engine.connect() as connection:
            statement = select(dali_group).where(
                dali_group.c.project_id == project_id,
                dali_group.c.lifecycle == "ACTIVE",
            )
            if bus_id is not None:
                statement = statement.where(dali_group.c.bus_id == bus_id)
            rows = list(connection.execute(statement.order_by(dali_group.c.group_key)).mappings())
            result = []
            for row in rows:
                members = tuple(
                    connection.execute(
                        select(dali_group_member.c.resource_id)
                        .where(
                            dali_group_member.c.project_id == project_id,
                            dali_group_member.c.dali_group_id == row["id"],
                        )
                        .order_by(dali_group_member.c.resource_id)
                    ).scalars()
                )
                result.append({**dict(row), "member_resource_ids": members})
            return result

    def connection_states(self, project_id: str, bus_id: str) -> list[dict]:
        stored = self.get_bus(project_id, bus_id)
        resource_endpoints = tuple(
            row["resource_id"]
            for row in stored["endpoints"]
            if row["endpoint_kind"] == "INSTANCE_RESOURCE"
        )
        bus_resources = (
            stored["root_resource_id"],
            *resource_endpoints,
        )
        with self._engine.connect() as connection:
            instance_by_resource = dict(
                connection.execute(
                    select(
                        instance_resource.c.id,
                        instance_resource.c.project_instance_id,
                    ).where(
                        instance_resource.c.project_id == project_id,
                        instance_resource.c.id.in_(bus_resources),
                    )
                ).all()
            )
            instance_ids = set(instance_by_resource.values())
            power_inputs: dict[str, list[str]] = {identifier: [] for identifier in instance_ids}
            for resource_id, instance_id in connection.execute(
                select(
                    instance_resource.c.id,
                    instance_resource.c.project_instance_id,
                ).where(
                    instance_resource.c.project_id == project_id,
                    instance_resource.c.project_instance_id.in_(instance_ids),
                    or_(
                        instance_resource.c.resource_kind.contains("POWER_INPUT"),
                        instance_resource.c.resource_kind == "INTERNAL_EXPANSION_MODULE_ATTACHMENT",
                    ),
                    instance_resource.c.active.is_(True),
                )
            ):
                power_inputs[instance_id].append(resource_id)
            powered_targets = set(
                connection.execute(
                    select(functional_relation.c.target_resource_id).where(
                        functional_relation.c.project_id == project_id,
                        functional_relation.c.target_resource_id.in_(
                            tuple(item for values in power_inputs.values() for item in values)
                        ),
                    )
                ).scalars()
            )
        states = []
        for resource_id in bus_resources:
            inputs = power_inputs.get(instance_by_resource[resource_id], [])
            powered_count = sum(item in powered_targets for item in inputs)
            if not inputs:
                power_state = "NOT_APPLICABLE"
            elif powered_count == len(inputs):
                power_state = "VERIFIED"
            elif powered_count:
                power_state = "INCOMPLETE"
            else:
                power_state = "MISSING"
            states.append(
                {
                    "resource_id": resource_id,
                    "communication_state": "VERIFIED",
                    "power_state": power_state,
                }
            )
        states.extend(
            {
                "endpoint_kind": "FIELD_DEVICE",
                "field_device_id": row["field_device_id"],
                "communication_state": "VERIFIED",
                "power_state": "NOT_APPLICABLE",
            }
            for row in stored["endpoints"]
            if row["endpoint_kind"] == "FIELD_DEVICE"
        )
        return states

    @staticmethod
    def _validate_rs485_resources(uow, project_id: str, resource_ids) -> None:
        rows = list(
            uow.execute(
                select(instance_resource.c.id, instance_resource.c.resource_kind).where(
                    instance_resource.c.project_id == project_id,
                    instance_resource.c.id.in_(resource_ids),
                    instance_resource.c.active.is_(True),
                )
            )
        )
        if len(rows) != len(resource_ids):
            raise BusError("All bus resources must be active resources of the Project")
        if any(row.resource_kind != "RS485_INTERFACE" for row in rows):
            raise BusError("RS-485 bus requires only RS485_INTERFACE resources")

    @staticmethod
    def _validate_rs485_points(uow, project_id: str, points: tuple[dict, ...]) -> None:
        resource_ids = tuple(
            item["resource_id"] for item in points if item.get("resource_id") is not None
        )
        if resource_ids:
            BusService._validate_rs485_resources(uow, project_id, resource_ids)
        field_points = [item for item in points if item.get("field_device_id") is not None]
        if len(resource_ids) + len(field_points) != len(points):
            raise BusError("Each RS-485 endpoint must have exactly one typed owner")
        for point in field_points:
            row = (
                uow.execute(
                    select(field_device.c.block_kind, field_device.c.normalized_fields_json).where(
                        field_device.c.id == point["field_device_id"],
                        field_device.c.project_id == project_id,
                        field_device.c.lifecycle == "ACTIVE",
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise BusError("Field bus endpoint must be an active device of the Project")
            if row["block_kind"] != "WB_MRM2_MINI":
                raise BusError("Field bus endpoint is not an approved RS-485 relay device")
            declared = str((row["normalized_fields_json"] or {}).get("CABLE_ID", "")).strip()
            if declared != str(point["cable_id"]).strip():
                raise BusError("Field bus endpoint CABLE_ID does not match its persisted identity")

    @staticmethod
    def _point_owner_id(point: dict) -> str:
        resource_id = point.get("resource_id")
        field_device_id = point.get("field_device_id")
        if bool(resource_id) == bool(field_device_id):
            raise BusError("Each bus endpoint requires exactly one typed owner")
        return str(resource_id or field_device_id)

    @staticmethod
    def _endpoint_owner_id(endpoint) -> str:
        return str(endpoint["resource_id"] or endpoint["field_device_id"])

    @staticmethod
    def _rs485_bus_row(uow, project_id: str, bus_id: str):
        row = (
            uow.execute(
                select(bus).where(
                    bus.c.id == bus_id,
                    bus.c.project_id == project_id,
                    bus.c.lifecycle == "ACTIVE",
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise BusError("Bus not found")
        if row["bus_kind"] != "RS485":
            raise BusError("Operation requires an RS-485 bus")
        return row

    @staticmethod
    def _reorder_rs485_endpoints(uow, project_id: str, bus_id: str) -> int:
        rows = list(
            uow.execute(
                select(bus_endpoint.c.id, bus_endpoint.c.address).where(
                    bus_endpoint.c.project_id == project_id,
                    bus_endpoint.c.bus_id == bus_id,
                )
            )
        )
        ordered = sorted(
            rows,
            key=lambda row: int(str(row.address).rsplit(".", 1)[1]),
        )
        for endpoint_order, row in enumerate(ordered, start=1):
            uow.execute(
                update(bus_endpoint)
                .where(bus_endpoint.c.id == row.id)
                .values(endpoint_order=endpoint_order)
            )
        return len(ordered)

    @staticmethod
    def _replace_linear_segments(uow, project_id: str, bus_id: str) -> None:
        uow.execute(
            delete(bus_segment).where(
                bus_segment.c.project_id == project_id,
                bus_segment.c.bus_id == bus_id,
            )
        )
        endpoint_ids = list(
            uow.execute(
                select(bus_endpoint.c.id)
                .where(
                    bus_endpoint.c.project_id == project_id,
                    bus_endpoint.c.bus_id == bus_id,
                )
                .order_by(bus_endpoint.c.endpoint_order, bus_endpoint.c.address)
            ).scalars()
        )
        previous = None
        for endpoint_id in endpoint_ids:
            uow.execute(
                bus_segment.insert().values(
                    id=new_id(),
                    project_id=project_id,
                    bus_id=bus_id,
                    source_endpoint_id=previous,
                    target_endpoint_id=endpoint_id,
                    connection_kind="CABLE",
                    origin_kind="PROJECT",
                    migration_state="CONFIRMED",
                )
            )
            previous = endpoint_id

    @staticmethod
    def _topology_points(points: tuple[dict, ...]) -> tuple[TopologyPoint, ...]:
        return tuple(
            TopologyPoint(
                str(item["resource_id"]),
                str(item["cable_id"]),
                Decimal(str(item["x_mm"])),
                Decimal(str(item["y_mm"])),
            )
            for item in points
        )

    @staticmethod
    def _validate_branched_resources(uow, project_id: str, kind: str, resource_ids) -> None:
        rows = list(
            uow.execute(
                select(instance_resource.c.id, instance_resource.c.resource_kind).where(
                    instance_resource.c.project_id == project_id,
                    instance_resource.c.id.in_(resource_ids),
                    instance_resource.c.active.is_(True),
                )
            )
        )
        if len(rows) != len(resource_ids):
            raise BusError("All bus resources must be active resources of the Project")
        expected = "DALI_BUS_PORT" if kind == "DALI" else "KNX_BUS_PORT"
        root_kind = next(row.resource_kind for row in rows if row.id == resource_ids[0])
        if root_kind != expected:
            raise BusError(f"{kind} bus source must be a {expected} resource")

    @staticmethod
    def _validate_root_available(uow, project_id: str, root_resource_id: str) -> None:
        occupied = uow.execute(
            select(func.count())
            .select_from(bus)
            .where(
                bus.c.project_id == project_id,
                bus.c.root_resource_id == root_resource_id,
                bus.c.lifecycle == "ACTIVE",
            )
        ).scalar_one()
        if occupied:
            raise BusError("Source port already belongs to an active physical bus")

    @staticmethod
    def _insert_branched_rows(
        uow,
        *,
        project_id: str,
        bus_id: str,
        points: tuple[dict, ...],
        branches: tuple[tuple[str, ...], ...],
    ) -> None:
        first_branch: dict[str, str] = {}
        branch_rows = []
        for branch_order, resource_ids in enumerate(branches):
            branch_id = new_id()
            branch_rows.append((branch_id, resource_ids))
            uow.execute(
                bus_branch.insert().values(
                    id=branch_id,
                    project_id=project_id,
                    bus_id=bus_id,
                    branch_key=f"BRANCH-{branch_order + 1:03d}",
                    branch_order=branch_order,
                )
            )
            for resource_id in resource_ids:
                first_branch.setdefault(resource_id, branch_id)
        point_by_resource = {item["resource_id"]: item for item in points}
        endpoint_by_resource: dict[str, str] = {}
        for resource_id, point in point_by_resource.items():
            endpoint_id = new_id()
            endpoint_by_resource[resource_id] = endpoint_id
            uow.execute(
                bus_endpoint.insert().values(
                    id=endpoint_id,
                    project_id=project_id,
                    bus_id=bus_id,
                    resource_id=resource_id,
                    endpoint_role="DEVICE",
                    address=point["cable_id"],
                    endpoint_order=None,
                    bus_branch_id=first_branch[resource_id],
                )
            )
        inserted_edges: set[tuple[str | None, str]] = set()
        for branch_index, (_branch_id, resource_ids) in enumerate(branch_rows):
            previous = endpoint_by_resource[resource_ids[0]] if branch_index else None
            selected_resources = resource_ids[1:] if branch_index else resource_ids
            for resource_id in selected_resources:
                target = endpoint_by_resource[resource_id]
                edge = (previous, target)
                if edge not in inserted_edges:
                    uow.execute(
                        bus_segment.insert().values(
                            id=new_id(),
                            project_id=project_id,
                            bus_id=bus_id,
                            source_endpoint_id=previous,
                            target_endpoint_id=target,
                            connection_kind="CABLE",
                            origin_kind="PROJECT",
                            migration_state="CONFIRMED",
                        )
                    )
                    inserted_edges.add(edge)
                previous = target
        for branch_id, resource_ids in branch_rows:
            for point_order, resource_id in enumerate(resource_ids):
                uow.execute(
                    bus_branch_point.insert().values(
                        id=new_id(),
                        project_id=project_id,
                        bus_branch_id=branch_id,
                        resource_id=resource_id,
                        point_order=point_order,
                    )
                )
