"""Transactional persistence and derived topology for physical buses."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import Engine, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError

from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    board,
    building,
    bus,
    bus_branch,
    bus_branch_point,
    bus_endpoint,
    bus_physical_link,
    bus_physical_node,
    bus_segment,
    bus_segment_conduit_assignment,
    conduit,
    dali_group,
    dali_group_member,
    field_device,
    functional_relation,
    instance_resource,
    passport_definition,
    passport_resource_definition,
    project_instance,
    room,
)
from nl_project_2.persistence.uow import UnitOfWork
from nl_project_2.resource_labels import resource_technical_identity, resource_user_label

from .domain import TopologyPoint, TopologyResult, branched_topology, rs485_topology
from .recalculation import bus_length_breakdown, recalculate_bus_segments

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
            if not self._validate_rs485_module_root(uow, project_id, root_resource_id):
                raise BusError(
                    "RS-485 module must be installed in an available WB8.5 MOD1–MOD4 slot"
                )
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

    def _add_rs485_typed_endpoint(self, *, project_id: str, bus_id: str, point: dict) -> BusReceipt:
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

    def transfer_rs485_source(
        self, *, project_id: str, bus_id: str, new_root_resource_id: str
    ) -> None:
        """Retarget an existing RS485 bus without deleting topology or cable identities.

        Populated buses can only move between ports mounted in the SAME board.
        The source-to-first-point length remains an existing engineering estimate;
        changing boards would require a reviewed topology/length migration.
        """
        with UnitOfWork(self._engine) as uow:
            current = self._rs485_bus_row(uow, project_id, bus_id)
            previous_root = current["root_resource_id"]
            if new_root_resource_id == previous_root:
                uow.rollback()
                return
            self._validate_rs485_resources(uow, project_id, (new_root_resource_id,))
            if not self._validate_rs485_module_root(uow, project_id, new_root_resource_id):
                raise BusError(
                    "Новый интерфейс RS-485 не установлен в действительный MOD-слот WB8.5"
                )
            self._validate_root_available(uow, project_id, new_root_resource_id)
            attached_as_point = uow.execute(
                select(bus_endpoint.c.id)
                .where(
                    bus_endpoint.c.project_id == project_id,
                    bus_endpoint.c.bus_id == bus_id,
                    bus_endpoint.c.resource_id == new_root_resource_id,
                )
                .limit(1)
            ).first()
            if attached_as_point:
                raise BusError("Новый источник RS-485 уже является точкой этой шины")
            # Existing 9YY.ZZZ points and stored cable/segment geometry are
            # unchanged. Only same-board replacement is supported for wired buses.
            has_physical_data = any(
                uow.execute(
                    select(table.c.id)
                    .where(
                        table.c.project_id == project_id,
                        table.c.bus_id == bus_id,
                    )
                    .limit(1)
                ).first()
                for table in (
                    bus_endpoint,
                    bus_segment,
                    bus_branch,
                    bus_physical_node,
                    bus_physical_link,
                )
            )
            if has_physical_data:
                old_board = self._root_board_id(uow, project_id, previous_root)
                new_board = self._root_board_id(uow, project_id, new_root_resource_id)
                if old_board is None or new_board is None or old_board != new_board:
                    raise BusError(
                        "Шина с точками/сегментами может менять RS-485 источник "
                        "только внутри того же щита. Перенос между щитами "
                        "требует отдельного согласования трассы и длин."
                    )
            updated = uow.execute(
                update(bus)
                .where(
                    bus.c.id == bus_id,
                    bus.c.project_id == project_id,
                    bus.c.bus_kind == "RS485",
                    bus.c.lifecycle == "ACTIVE",
                    bus.c.root_resource_id == previous_root,
                )
                .values(root_resource_id=new_root_resource_id)
            )
            if updated.rowcount != 1:
                raise BusError("Исходная шина изменилась; перенос отменён")
            uow.commit()

    @staticmethod
    def _root_board_id(uow, project_id: str, resource_id: str) -> str | None:
        """Resolve either a directly placed RS485 device or its installed MOD host."""
        row = (
            uow.execute(
                select(
                    project_instance.c.board_id,
                    project_instance.c.id.label("instance_id"),
                    passport_definition.c.passport_key,
                )
                .select_from(instance_resource)
                .join(
                    project_instance,
                    project_instance.c.id == instance_resource.c.project_instance_id,
                )
                .join(
                    passport_definition,
                    passport_definition.c.id == project_instance.c.passport_definition_id,
                )
                .where(
                    instance_resource.c.id == resource_id,
                    instance_resource.c.project_id == project_id,
                    instance_resource.c.active.is_(True),
                    project_instance.c.lifecycle == "ACTIVE",
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        if row["board_id"]:
            return str(row["board_id"])
        if row["passport_key"] != "module.wirenboard.wbe2_i_rs485_iso":
            return None
        attached = (
            uow.execute(
                select(instance_resource.c.id).where(
                    instance_resource.c.project_id == project_id,
                    instance_resource.c.project_instance_id == row["instance_id"],
                    instance_resource.c.resource_kind == "INTERNAL_EXPANSION_MODULE_ATTACHMENT",
                    instance_resource.c.active.is_(True),
                )
            )
            .scalars()
            .all()
        )
        if len(attached) != 1:
            return None
        host_boards = (
            uow.execute(
                select(project_instance.c.board_id)
                .select_from(functional_relation)
                .join(
                    instance_resource,
                    instance_resource.c.id == functional_relation.c.source_resource_id,
                )
                .join(
                    project_instance,
                    project_instance.c.id == instance_resource.c.project_instance_id,
                )
                .where(
                    functional_relation.c.project_id == project_id,
                    functional_relation.c.relation_kind == "MODULE_INSTALLATION",
                    functional_relation.c.target_resource_id == attached[0],
                    instance_resource.c.resource_kind == "INTERNAL_EXPANSION_SLOT",
                    project_instance.c.lifecycle == "ACTIVE",
                )
            )
            .scalars()
            .all()
        )
        return str(host_boards[0]) if len(host_boards) == 1 and host_boards[0] else None

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

    def update_dali_bus(
        self,
        *,
        project_id: str,
        bus_id: str,
        designation: str,
        root_resource_id: str,
    ) -> None:
        """Edit a DALI number and DA root without replacing its identity/topology.

        Already wired buses must be rebuilt from their approved DWG physical
        graph, rather than silently changing root or Cable-ID meaning.
        """
        name = designation.strip()
        if not re.fullmatch(r"9[0-9]{2}", name):
            raise BusError("Номер шины DALI должен иметь формат 9YY (например, 941)")
        try:
            with UnitOfWork(self._engine) as uow:
                current = (
                    uow.execute(
                        select(bus).where(
                            bus.c.project_id == project_id,
                            bus.c.id == bus_id,
                            bus.c.bus_kind == "DALI",
                            bus.c.lifecycle == "ACTIVE",
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if current is None:
                    raise BusError("Шина DALI не найдена в выбранном проекте")
                changing_number = name != current["designation"]
                changing_root = root_resource_id != current["root_resource_id"]
                if not changing_number and not changing_root:
                    uow.rollback()
                    return
                attached = any(
                    uow.execute(
                        select(table.c.id)
                        .where(
                            table.c.project_id == project_id,
                            table.c.bus_id == bus_id,
                        )
                        .limit(1)
                    ).first()
                    for table in (
                        bus_endpoint,
                        bus_segment,
                        bus_branch,
                        bus_physical_node,
                        bus_physical_link,
                        dali_group,
                    )
                )
                if attached:
                    raise BusError(
                        "Шина DALI имеет подключённые точки, ветви, физическую трассу "
                        "или группы. Для изменения номера или DA-выхода сначала "
                        "согласуйте изменение этих связей — автоматическая "
                        "перенумерация CABLE_ID запрещена."
                    )
                if changing_root:
                    candidate_ids = {
                        row["id"] for row in self.list_dali_source_candidates(project_id)
                    }
                    if root_resource_id not in candidate_ids:
                        raise BusError(
                            "Выбранный выход DA недоступен, занят или не принадлежит WB-DALI3"
                        )
                duplicate = uow.execute(
                    select(bus.c.id).where(
                        bus.c.project_id == project_id,
                        bus.c.designation == name,
                        bus.c.lifecycle == "ACTIVE",
                        bus.c.id != bus_id,
                    )
                ).first()
                if duplicate:
                    raise BusError(f"Обозначение шины {name} уже занято")
                uow.execute(
                    update(bus)
                    .where(
                        bus.c.project_id == project_id,
                        bus.c.id == bus_id,
                        bus.c.bus_kind == "DALI",
                        bus.c.lifecycle == "ACTIVE",
                    )
                    .values(designation=name, root_resource_id=root_resource_id)
                )
                uow.commit()
        except IntegrityError as exc:
            raise BusError("Номер или выход DALI конфликтует с другой шиной") from exc

    def delete_dali_bus(self, *, project_id: str, bus_id: str) -> None:
        """Delete only the selected physical DALI bus and its owned graph.

        All referenced external objects (devices, resources, conduits, cable
        lines) survive. Cleanup is ordered for SQLite foreign-key integrity.
        """
        with UnitOfWork(self._engine) as uow:
            exists = uow.execute(
                select(bus.c.id).where(
                    bus.c.id == bus_id,
                    bus.c.project_id == project_id,
                    bus.c.bus_kind == "DALI",
                    bus.c.lifecycle == "ACTIVE",
                )
            ).scalar_one_or_none()
            if exists is None:
                raise BusError("Шина DALI не найдена в выбранном проекте")
            group_ids = select(dali_group.c.id).where(
                dali_group.c.project_id == project_id,
                dali_group.c.bus_id == bus_id,
            )
            branch_ids = select(bus_branch.c.id).where(
                bus_branch.c.project_id == project_id,
                bus_branch.c.bus_id == bus_id,
            )
            segment_ids = select(bus_segment.c.id).where(
                bus_segment.c.project_id == project_id,
                bus_segment.c.bus_id == bus_id,
            )
            uow.execute(
                delete(dali_group_member).where(
                    dali_group_member.c.project_id == project_id,
                    dali_group_member.c.dali_group_id.in_(group_ids),
                )
            )
            uow.execute(
                delete(dali_group).where(
                    dali_group.c.project_id == project_id,
                    dali_group.c.bus_id == bus_id,
                )
            )
            uow.execute(
                delete(bus_physical_link).where(
                    bus_physical_link.c.project_id == project_id,
                    bus_physical_link.c.bus_id == bus_id,
                )
            )
            uow.execute(
                delete(bus_physical_node).where(
                    bus_physical_node.c.project_id == project_id,
                    bus_physical_node.c.bus_id == bus_id,
                )
            )
            uow.execute(
                delete(bus_segment_conduit_assignment).where(
                    bus_segment_conduit_assignment.c.project_id == project_id,
                    bus_segment_conduit_assignment.c.bus_segment_id.in_(segment_ids),
                )
            )
            uow.execute(
                delete(bus_segment).where(
                    bus_segment.c.project_id == project_id,
                    bus_segment.c.bus_id == bus_id,
                )
            )
            uow.execute(
                delete(bus_branch_point).where(
                    bus_branch_point.c.project_id == project_id,
                    bus_branch_point.c.bus_branch_id.in_(branch_ids),
                )
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
                delete(bus_branch).where(
                    bus_branch.c.project_id == project_id,
                    bus_branch.c.bus_id == bus_id,
                )
            )
            uow.execute(
                delete(bus_endpoint).where(
                    bus_endpoint.c.project_id == project_id,
                    bus_endpoint.c.bus_id == bus_id,
                )
            )
            result = uow.execute(
                delete(bus).where(
                    bus.c.project_id == project_id,
                    bus.c.id == bus_id,
                    bus.c.bus_kind == "DALI",
                    bus.c.lifecycle == "ACTIVE",
                )
            )
            if result.rowcount != 1:
                raise BusError("Шина DALI не найдена в выбранном проекте")
            uow.commit()

    def recalculate_lengths(
        self, project_id: str, *, bus_ids: set[str] | None = None
    ) -> tuple[str, ...]:
        """Refresh derived physical bus-segment lengths from accepted Project geometry."""

        with UnitOfWork(self._engine) as uow:
            changed = recalculate_bus_segments(uow, project_id, bus_ids=bus_ids)
            uow.commit()
        return changed

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
                    "source_available": (
                        row["id"] not in occupied_sources
                        and self._validate_rs485_module_root(connection, project_id, row["id"])
                    ),
                    "endpoint_available": True,
                }
                for row in rows
            ]

    def list_dali_source_candidates(self, project_id: str) -> list[dict]:
        """Available physical DA1/DA2/DA3 outputs of active WB-DALI3 instances."""
        with self._engine.connect() as connection:
            used_sources = set(
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
                    passport_definition,
                    passport_definition.c.id == project_instance.c.passport_definition_id,
                )
                .join(
                    passport_resource_definition,
                    passport_resource_definition.c.id
                    == instance_resource.c.passport_resource_definition_id,
                )
                .where(
                    instance_resource.c.project_id == project_id,
                    project_instance.c.project_id == project_id,
                    project_instance.c.lifecycle == "ACTIVE",
                    passport_definition.c.passport_key == "gateway.wirenboard.wb_dali3",
                    instance_resource.c.active.is_(True),
                    instance_resource.c.resource_kind == "DALI_BUS_PORT",
                    ~instance_resource.c.id.in_(used_sources) if used_sources else True,
                )
                .order_by(
                    project_instance.c.designation,
                    instance_resource.c.ordinal,
                )
            ).mappings()
            return [
                {
                    "id": row["id"],
                    "label": resource_user_label(row),
                    "technical_identity": resource_technical_identity(row),
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

    def set_bus_display_name(
        self, *, project_id: str, bus_id: str, display_name: str
    ) -> str | None:
        """Save user's title in Project without modifying bus ID/DWG LOAD_NAME."""
        value = str(display_name or "").strip()
        if len(value) > 160:
            raise BusError("Название шины не должно превышать 160 символов")
        if "\n" in value or "\r" in value or "\t" in value:
            raise BusError("Название шины должно быть одной строкой")
        with UnitOfWork(self._engine) as uow:
            result = uow.execute(
                update(bus)
                .where(
                    bus.c.id == bus_id,
                    bus.c.project_id == project_id,
                    bus.c.lifecycle == "ACTIVE",
                )
                .values(
                    display_name=value or None,
                    row_version=bus.c.row_version + 1,
                )
            )
            if result.rowcount != 1:
                raise BusError("Шина не найдена в текущем объекте")
            uow.commit()
        return value or None

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

    def _journal_human_context(self, project_id: str) -> dict[str, dict]:
        """Read-only, project-scoped origin/purpose for buses already in Project.

        LOAD_NAME belongs to the *individual bus participant*, not the bus.
        Always retain all distinct member names and never guess a bus title
        from the first field device or from SENSOR_* resource kinds.
        """
        with self._engine.connect() as conn:
            origin_rows = (
                conn.execute(
                    select(
                        bus.c.id.label("bus_id"),
                        project_instance.c.id.label("owner_instance_id"),
                        board.c.designation.label("board_name"),
                    )
                    .join(instance_resource, instance_resource.c.id == bus.c.root_resource_id)
                    .join(
                        project_instance,
                        project_instance.c.id == instance_resource.c.project_instance_id,
                    )
                    .outerjoin(board, board.c.id == project_instance.c.board_id)
                    .where(
                        bus.c.project_id == project_id,
                        bus.c.lifecycle == "ACTIVE",
                        project_instance.c.project_id == project_id,
                    )
                )
                .mappings()
                .all()
            )
            members = (
                conn.execute(
                    select(
                        bus_endpoint.c.bus_id,
                        bus.c.designation.label("bus_designation"),
                        bus_endpoint.c.endpoint_order,
                        bus_endpoint.c.address,
                        field_device.c.normalized_fields_json,
                        room.c.id.label("room_id"),
                        room.c.name.label("canonical_room"),
                        room.c.display_json.label("room_display"),
                    )
                    .join(bus, bus.c.id == bus_endpoint.c.bus_id)
                    .join(field_device, field_device.c.id == bus_endpoint.c.field_device_id)
                    .outerjoin(room, room.c.id == field_device.c.room_id)
                    .where(
                        bus.c.project_id == project_id,
                        bus.c.lifecycle == "ACTIVE",
                        field_device.c.project_id == project_id,
                        field_device.c.lifecycle == "ACTIVE",
                    )
                    .order_by(
                        bus_endpoint.c.bus_id,
                        bus_endpoint.c.endpoint_order,
                        bus_endpoint.c.address,
                    )
                )
                .mappings()
                .all()
            )
            # WBE2 has no independent board placement: inherit it strictly
            # from the real controller's occupied MOD slot relation.
            module_attachment = instance_resource.alias("module_attachment")
            host_slot = instance_resource.alias("host_slot")
            host_instance = project_instance.alias("host_instance")
            module_boards = dict(
                conn.execute(
                    select(
                        module_attachment.c.project_instance_id,
                        board.c.designation,
                    )
                    .select_from(functional_relation)
                    .join(
                        module_attachment,
                        module_attachment.c.id == functional_relation.c.target_resource_id,
                    )
                    .join(host_slot, host_slot.c.id == functional_relation.c.source_resource_id)
                    .join(
                        host_instance,
                        host_instance.c.id == host_slot.c.project_instance_id,
                    )
                    .join(board, board.c.id == host_instance.c.board_id)
                    .where(
                        functional_relation.c.project_id == project_id,
                        functional_relation.c.relation_kind == "MODULE_INSTALLATION",
                        module_attachment.c.resource_kind == "INTERNAL_EXPANSION_MODULE_ATTACHMENT",
                        host_slot.c.resource_kind == "INTERNAL_EXPANSION_SLOT",
                        host_instance.c.project_id == project_id,
                        host_instance.c.lifecycle == "ACTIVE",
                    )
                ).all()
            )
        result: dict[str, dict] = {}
        for row in origin_rows:
            result[row["bus_id"]] = {
                "source_board": (
                    row["board_name"] or module_boards.get(row["owner_instance_id"]) or ""
                ),
                "purposes": [],
                "purpose_details": [],
                "room_markers": {},
            }
        for row in members:
            item = result.get(row["bus_id"])
            if item is None:
                continue
            values = dict(row["normalized_fields_json"] or {})
            if row["room_id"] and row["canonical_room"]:
                item["room_markers"].setdefault(
                    row["room_id"],
                    {
                        "id": row["room_id"],
                        "name": row["canonical_room"],
                        "color": (row["room_display"] or {}).get("marking_color", "#FFFFFF"),
                    },
                )
            dwg_bus_id = str(values.get("BUS_ID") or "").strip()
            if dwg_bus_id and dwg_bus_id != row["bus_designation"]:
                # Conflicting DWG tag: never ascribe a different bus's load.
                continue
            name = str(values.get("LOAD_NAME") or "").strip()
            # A device without LOAD_NAME is not evidence of an inferred bus purpose.
            if not name:
                continue
            # Only physically linked BusEndpoints are considered.
            if name not in item["purposes"]:
                item["purposes"].append(name)
            item["purpose_details"].append((str(row["address"] or "").strip(), name))
        return result

    @staticmethod
    def _journal_purpose_summary(purposes: list[str]) -> str:
        if not purposes:
            return "Назначение не задано"
        if len(purposes) == 1:
            return purposes[0]
        preview = " · ".join(purposes[:2])
        remainder = len(purposes) - 2
        return preview + (f" · ещё {remainder}" if remainder else "")

    def journal_cards(self, project_id: str) -> list[dict]:
        """Return physical buses in the same read-model shape as the cable journal."""

        result = []
        human_context = self._journal_human_context(project_id)
        root_labels = self.list_bus_resource_labels(project_id)
        for stored in self.list_buses(project_id):
            topology = self.journal_topology(project_id, stored["id"])
            edges = list(topology["edges"])
            rooms: list[str] = []
            buildings: list[str] = []
            unresolved_rooms: list[str] = []
            endpoint_kinds: list[str] = []
            conduit_ids: set[str] = set()
            mount_values: set[str] = set()
            conduit_values: set[str] = set()
            known_m = Decimal(0)
            incomplete = 0
            for edge in edges:
                target = edge["target"]
                for name in str(target.get("room_names") or "").split(","):
                    clean = name.strip()
                    if clean and clean not in rooms:
                        rooms.append(clean)
                for name in str(target.get("building_names") or "").split(","):
                    clean = name.strip()
                    if clean and clean not in buildings:
                        buildings.append(clean)
                if target.get("room_unresolved"):
                    for name in str(target.get("room_names") or "").split(","):
                        clean = name.strip()
                        if clean and clean not in unresolved_rooms:
                            unresolved_rooms.append(clean)
                description = str(target.get("device_kind") or "").strip()
                if description and description not in endpoint_kinds:
                    endpoint_kinds.append(description)
                if edge.get("mount_way"):
                    mount_values.add(str(edge["mount_way"]))
                if edge.get("gofra_id"):
                    conduit_ids.add(str(edge["gofra_id"]))
                    conduit_values.add(str(edge["gofra_id"]))
                length = edge.get("cable_length_m")
                if length is None:
                    incomplete += 1
                else:
                    known_m += Decimal(str(length))

            mount_way = (
                next(iter(mount_values))
                if len(mount_values) == 1
                else ("MIXED" if mount_values else "")
            )
            gofra_id = (
                next(iter(conduit_values))
                if len(conduit_values) == 1
                else ("MIXED" if conduit_values else "")
            )
            automatic = None
            effective = None
            if edges and incomplete == 0:
                try:
                    with UnitOfWork(self._engine) as uow:
                        length_breakdown = bus_length_breakdown(uow, project_id, stored["id"])
                        uow.rollback()
                    automatic = str(length_breakdown.unrounded_m)
                    effective = str(length_breakdown.rounded_m)
                except Exception:
                    automatic = effective = None
            context = human_context.get(stored["id"], {})
            purposes = context.get("purposes", [])
            suggested_name = self._journal_purpose_summary(purposes)
            custom_name = str(stored.get("display_name") or "").strip()
            load_name = custom_name or suggested_name
            board_name = str(context.get("source_board") or "").strip()
            root_label = str(
                root_labels.get(str(stored["root_resource_id"]), {}).get("label")
                or topology["root_endpoint"]["label"]
            )
            source_label = f"{board_name} · {root_label}" if board_name else root_label
            purpose_details = context.get("purpose_details", [])
            purpose_tooltip = (
                "\n".join(f"{address}: {name}" for address, name in purpose_details)
                if purpose_details
                else "LOAD_NAME не указан в подключённых устройствах DWG"
            )
            result.append(
                {
                    **stored,
                    "network_kind": "BUS",
                    "load_name": load_name,
                    "custom_display_name": custom_name,
                    "suggested_display_name": suggested_name,
                    "load_name_tooltip": (
                        (
                            f"Название шины (Project): {custom_name}\n"
                            f"LOAD_NAME точек DWG:\n{purpose_tooltip}"
                        )
                        if custom_name
                        else purpose_tooltip
                    ),
                    "load_name_count": len(purposes),
                    "source_board": board_name,
                    "source_interface": root_label,
                    "source_tooltip": (
                        f"Щит: {board_name or 'не указан'}\nКонтроллер / порт: {root_label}"
                    ),
                    "load_type": "BUS",
                    "board": source_label,
                    "building_names": ", ".join(buildings),
                    "room_names": ", ".join(rooms),
                    "room_markers": tuple(context.get("room_markers", {}).values()),
                    "unresolved_room_names": tuple(unresolved_rooms),
                    "system_kind": stored["bus_kind"],
                    "cable_type": stored.get("cable_type") or "",
                    "mount_way": mount_way,
                    "gofra_id": gofra_id,
                    "conduit_count": len(conduit_ids),
                    "incomplete_segments": incomplete,
                    "known_segment_m": str(known_m),
                    "automatic_m": automatic,
                    "additional_m": "0",
                    "manual_full_m": None,
                    "effective_m": effective,
                    "length_mode": "Автоматическая" if effective is not None else "Не рассчитана",
                    "length_explanation": (
                        "Геометрия + объектовые выводы + проценты только на геометрию, "
                        "округление вверх до шага проекта"
                    ),
                }
            )
        return result

    def journal_topology(self, project_id: str, bus_id: str) -> dict:
        """Return physical bus edges with working labels, rooms and route facts."""

        stored = self.get_bus(project_id, bus_id)
        resource_labels = self.list_bus_resource_labels(project_id)
        endpoint_rows = {row["id"]: dict(row) for row in stored["endpoints"]}
        field_ids = {
            row["field_device_id"]
            for row in endpoint_rows.values()
            if row["endpoint_kind"] == "FIELD_DEVICE" and row.get("field_device_id")
        }
        resource_ids = {
            row["resource_id"]
            for row in endpoint_rows.values()
            if row["endpoint_kind"] == "INSTANCE_RESOURCE" and row.get("resource_id")
        }

        with self._engine.connect() as connection:
            field_meta = {
                row["id"]: dict(row)
                for row in connection.execute(
                    select(
                        field_device.c.id,
                        field_device.c.block_kind,
                        field_device.c.room_id,
                        field_device.c.normalized_fields_json,
                        room.c.name.label("room_name"),
                        building.c.name.label("building_name"),
                    )
                    .outerjoin(room, room.c.id == field_device.c.room_id)
                    .outerjoin(building, building.c.id == room.c.building_id)
                    .where(
                        field_device.c.project_id == project_id,
                        field_device.c.id.in_(tuple(field_ids) or ("",)),
                        field_device.c.lifecycle == "ACTIVE",
                    )
                ).mappings()
            }
            resource_meta = {
                row["resource_id"]: dict(row)
                for row in connection.execute(
                    select(
                        instance_resource.c.id.label("resource_id"),
                        project_instance.c.designation.label("instance_designation"),
                        project_instance.c.room_id,
                        room.c.name.label("room_name"),
                        building.c.name.label("building_name"),
                    )
                    .join(
                        project_instance,
                        project_instance.c.id == instance_resource.c.project_instance_id,
                    )
                    .outerjoin(room, room.c.id == project_instance.c.room_id)
                    .outerjoin(building, building.c.id == room.c.building_id)
                    .where(
                        instance_resource.c.project_id == project_id,
                        instance_resource.c.id.in_(tuple(resource_ids) or ("",)),
                    )
                ).mappings()
            }
            conduit_by_segment = {
                row["segment_id"]: dict(row)
                for row in connection.execute(
                    select(
                        bus_segment_conduit_assignment.c.bus_segment_id.label("segment_id"),
                        conduit.c.designation,
                    )
                    .join(
                        conduit,
                        conduit.c.id == bus_segment_conduit_assignment.c.conduit_id,
                    )
                    .where(
                        bus_segment_conduit_assignment.c.project_id == project_id,
                        bus_segment_conduit_assignment.c.bus_segment_id.in_(
                            tuple(row["id"] for row in stored["segments"]) or ("",)
                        ),
                    )
                ).mappings()
            }

        def endpoint_info(endpoint_id: str) -> dict:
            endpoint = endpoint_rows[endpoint_id]
            address = str(endpoint.get("address") or "")
            if endpoint["endpoint_kind"] == "FIELD_DEVICE":
                meta = field_meta.get(endpoint["field_device_id"], {})
                fields = dict(meta.get("normalized_fields_json") or {})
                raw_room = str(fields.get("ROOM") or "").strip()
                canonical_room = str(meta.get("room_name") or "").strip()
                raw_building = str(fields.get("BUILDING") or "").strip()
                canonical_building = str(meta.get("building_name") or "").strip()
                description = str(
                    fields.get("LOAD_NAME")
                    or fields.get("DEVICE_NAME")
                    or meta.get("block_kind")
                    or "Полевое устройство"
                ).strip()
                return {
                    "kind": "BUS_POINT",
                    "endpoint_id": endpoint_id,
                    "label": address,
                    "description": description,
                    "device_kind": str(meta.get("block_kind") or ""),
                    "room_names": canonical_room or raw_room,
                    "building_names": canonical_building or raw_building,
                    "room_unresolved": bool(raw_room and not meta.get("room_id")),
                }
            meta = resource_meta.get(endpoint["resource_id"], {})
            label = resource_labels.get(str(endpoint["resource_id"]), {}).get(
                "label",
                f"{meta.get('instance_designation') or 'Устройство'} / {address}",
            )
            return {
                "kind": "BUS_POINT",
                "endpoint_id": endpoint_id,
                "label": address,
                "description": label,
                "device_kind": str(meta.get("instance_designation") or ""),
                "room_names": str(meta.get("room_name") or ""),
                "building_names": str(meta.get("building_name") or ""),
                "room_unresolved": False,
            }

        root_label = resource_labels.get(str(stored["root_resource_id"]), {}).get(
            "label", f"{stored['designation']}.000"
        )
        root = {
            "kind": "BUS_ROOT",
            "label": root_label,
            "reference": f"{stored['designation']}.000",
        }
        adjacency: dict[str | None, list[dict]] = {}
        for segment in stored["segments"]:
            adjacency.setdefault(segment.get("source_endpoint_id"), []).append(segment)

        ordered: list[tuple[int, dict]] = []
        visited: set[str] = set()

        def order_key(segment) -> tuple:
            target = endpoint_rows[segment["target_endpoint_id"]]
            return (
                target.get("endpoint_order")
                if target.get("endpoint_order") is not None
                else 999999,
                str(target.get("address") or ""),
            )

        def walk(source_id: str | None, depth: int) -> None:
            for segment in sorted(adjacency.get(source_id, ()), key=order_key):
                if segment["id"] in visited:
                    continue
                visited.add(segment["id"])
                ordered.append((depth, segment))
                walk(segment["target_endpoint_id"], depth + 1)

        walk(None, 0)
        for segment in sorted(stored["segments"], key=order_key):
            if segment["id"] not in visited:
                ordered.append((0, segment))

        edges = []
        for depth, segment in ordered:
            source_id = segment.get("source_endpoint_id")
            assigned = conduit_by_segment.get(segment["id"], {})
            length = segment.get("length_m_decimal")
            edges.append(
                {
                    "segment_id": segment["id"],
                    "depth": depth,
                    "source": root if source_id is None else endpoint_info(source_id),
                    "target": endpoint_info(segment["target_endpoint_id"]),
                    "connection_kind": segment["connection_kind"],
                    "mount_way": segment.get("mount_way") or "",
                    "gofra_type": segment.get("gofra_type") or "",
                    "gofra_color": segment.get("gofra_color") or "",
                    "gofra_id": assigned.get("designation") or segment.get("gofra_id") or "",
                    "cable_length_m": length,
                    "physical_length_m": length,
                    "calculation_status": "READY" if length is not None else "INCOMPLETE",
                    "calculation_reason": "" if length is not None else "Длина не рассчитана",
                }
            )

        length_breakdown = None
        if edges and all(edge["cable_length_m"] is not None for edge in edges):
            try:
                with UnitOfWork(self._engine) as uow:
                    length_breakdown = bus_length_breakdown(uow, project_id, bus_id)
                    uow.rollback()
            except ValueError:
                length_breakdown = None

        return {
            "network_kind": "BUS",
            "bus_kind": stored["bus_kind"],
            "designation": stored["designation"],
            "root_endpoint": root,
            "edges": tuple(edges),
            "board_reserve_m": (
                "0" if length_breakdown is None else str(length_breakdown.board_reserve_m)
            ),
            "distribution_box_reserve_m": "0",
            "endpoint_reserve_m": (
                "0" if length_breakdown is None else str(length_breakdown.endpoint_reserve_m)
            ),
            "meander_reserve_m": (
                "0" if length_breakdown is None else str(length_breakdown.meander_reserve_m)
            ),
            "obstacle_reserve_m": (
                "0" if length_breakdown is None else str(length_breakdown.obstacle_reserve_m)
            ),
            "geometric_m": (
                None if length_breakdown is None else str(length_breakdown.geometric_m)
            ),
            "unrounded_m": (
                None if length_breakdown is None else str(length_breakdown.unrounded_m)
            ),
            "rounded_m": (None if length_breakdown is None else str(length_breakdown.rounded_m)),
            "distribution_box_lines": 0,
            "endpoint_mechanisms": (
                0 if length_breakdown is None else length_breakdown.endpoint_mechanisms
            ),
            "additional_m": "0",
            "manual_full_m": None,
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
    def _validate_rs485_module_root(uow, project_id: str, resource_id: str) -> bool:
        """Module RS485 ports require a persisted, valid WB8.5 MOD installation."""
        module = (
            uow.execute(
                select(instance_resource.c.project_instance_id, passport_definition.c.passport_key)
                .join(
                    project_instance,
                    project_instance.c.id == instance_resource.c.project_instance_id,
                )
                .join(
                    passport_definition,
                    passport_definition.c.id == project_instance.c.passport_definition_id,
                )
                .where(
                    instance_resource.c.id == resource_id,
                    instance_resource.c.project_id == project_id,
                    instance_resource.c.active.is_(True),
                    project_instance.c.lifecycle == "ACTIVE",
                )
            )
            .mappings()
            .one_or_none()
        )
        if module is None:
            return False
        if module["passport_key"] != "module.wirenboard.wbe2_i_rs485_iso":
            return True
        attachments = list(
            uow.execute(
                select(instance_resource.c.id).where(
                    instance_resource.c.project_id == project_id,
                    instance_resource.c.project_instance_id == module["project_instance_id"],
                    instance_resource.c.resource_kind == "INTERNAL_EXPANSION_MODULE_ATTACHMENT",
                    instance_resource.c.active.is_(True),
                )
            ).scalars()
        )
        if len(attachments) != 1:
            return False
        sources = list(
            uow.execute(
                select(functional_relation.c.source_resource_id).where(
                    functional_relation.c.project_id == project_id,
                    functional_relation.c.relation_kind == "MODULE_INSTALLATION",
                    functional_relation.c.target_resource_id == attachments[0],
                )
            ).scalars()
        )
        if len(sources) != 1:
            return False
        slot = (
            uow.execute(
                select(
                    instance_resource.c.resource_kind,
                    instance_resource.c.resource_key,
                    instance_resource.c.ordinal,
                    passport_definition.c.passport_key,
                )
                .join(
                    project_instance,
                    project_instance.c.id == instance_resource.c.project_instance_id,
                )
                .join(
                    passport_definition,
                    passport_definition.c.id == project_instance.c.passport_definition_id,
                )
                .where(
                    instance_resource.c.id == sources[0],
                    instance_resource.c.project_id == project_id,
                    instance_resource.c.active.is_(True),
                    project_instance.c.lifecycle == "ACTIVE",
                )
            )
            .mappings()
            .one_or_none()
        )
        return bool(
            slot
            and slot["passport_key"] == "controller.wiren_board_8_5"
            and slot["resource_kind"] == "INTERNAL_EXPANSION_SLOT"
            and slot["resource_key"] == "INTERNAL_MODULE_SLOT"
            and slot["ordinal"] in (0, 1, 2, 3)
        )

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
