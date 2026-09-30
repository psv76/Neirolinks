"""Transactional persistence API for physical topology and field identities."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, delete, func, select, update
from sqlalchemy.exc import IntegrityError

from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    cable_line,
    cable_line_assignment,
    cable_point,
    cable_point_field_device,
    cable_segment,
    cable_topology_endpoint,
    catalog_release,
    conduit,
    conduit_segment_assignment,
    control_key_input_assignment,
    dali_group,
    field_control_key,
    field_device,
    field_device_product_selection,
    field_port,
    instance_resource,
    led_line_profile,
    passport_resource_definition,
    product_definition,
    project,
    project_instance,
    resource_reservation,
    user_reserve,
)
from nl_project_2.persistence.uow import UnitOfWork
from nl_project_2.resource_labels import resource_user_label

from .domain import FieldModelRuleError, RouteFacts, canonical_port, normalize_led_type


class FieldModelError(RuntimeError):
    """A topology persistence command cannot be committed."""


FIELD_CONFIGURATION_FAMILIES = frozenset(
    {
        "temperature_humidity",
        "illumination_ir",
        "sound",
        "motion",
        "co2",
        "air_quality_voc",
        "verification",
        "body_color",
        "case_top_type",
    }
)

SUPPLY_SCOPES = frozenset({"NEIROLINKS", "CUSTOMER", "ASSEMBLY_WORKSHOP", "BY_CONTRACT"})


class TopologyPersistenceService:
    """One-command/one-UoW API over the successor persistence boundary."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create_topology_point(
        self,
        *,
        project_id: str,
        cable_line_id: str,
        point_kind: str,
        logical_identity: str | None,
        location: dict[str, Any] | None = None,
    ) -> str:
        kind = str(point_kind).strip().upper()
        approved = {
            "INTERNAL_SOURCE",
            "DEVICE_POINT",
            "INSTALLATION_GROUP",
            "EL_BOX",
            "BUS_POINT",
        }
        if kind not in approved:
            raise FieldModelError(f"Unsupported topology point kind: {point_kind}")
        identity = None if logical_identity in (None, "") else str(logical_identity).strip()
        identifier = new_id()
        with UnitOfWork(self._engine) as uow:
            self._require_line(uow, project_id, cable_line_id)
            ordinal = uow.execute(
                select(func.max(cable_point.c.ordinal)).where(
                    cable_point.c.project_id == project_id,
                    cable_point.c.cable_line_id == cable_line_id,
                )
            ).scalar_one()
            try:
                uow.execute(
                    cable_point.insert().values(
                        id=identifier,
                        project_id=project_id,
                        cable_line_id=cable_line_id,
                        field_device_id=None,
                        point_kind=kind,
                        ordinal=(ordinal if ordinal is not None else -1) + 1,
                        logical_identity=identity,
                        origin_kind="PROJECT",
                        migration_state="CONFIRMED",
                        location_json=location,
                    )
                )
                self._touch(uow, project_id)
                uow.commit()
            except IntegrityError as exc:
                raise FieldModelError("Topology point identity already exists") from exc
        return identifier

    def add_field_device_to_point(
        self, *, project_id: str, cable_point_id: str, field_device_id: str
    ) -> str:
        identifier = new_id()
        with UnitOfWork(self._engine) as uow:
            point = uow.execute(
                select(cable_point.c.id).where(
                    cable_point.c.id == cable_point_id,
                    cable_point.c.project_id == project_id,
                )
            ).scalar_one_or_none()
            device = uow.execute(
                select(field_device.c.id).where(
                    field_device.c.id == field_device_id,
                    field_device.c.project_id == project_id,
                    field_device.c.lifecycle == "ACTIVE",
                )
            ).scalar_one_or_none()
            if point is None or device is None:
                raise FieldModelError("Topology point or field device not found")
            try:
                uow.execute(
                    cable_point_field_device.insert().values(
                        id=identifier,
                        project_id=project_id,
                        cable_point_id=cable_point_id,
                        field_device_id=field_device_id,
                    )
                )
                self._touch(uow, project_id)
                uow.commit()
            except IntegrityError as exc:
                raise FieldModelError("Field device already belongs to a topology point") from exc
        return identifier

    def create_field_port(self, *, project_id: str, field_device_id: str, port_tag: str) -> str:
        identifier = new_id()
        with UnitOfWork(self._engine) as uow:
            block_kind = uow.execute(
                select(field_device.c.block_kind).where(
                    field_device.c.id == field_device_id,
                    field_device.c.project_id == project_id,
                    field_device.c.lifecycle == "ACTIVE",
                )
            ).scalar_one_or_none()
            if block_kind is None:
                raise FieldModelError("Field device not found")
            try:
                port_kind, direction = canonical_port(block_kind, port_tag)
            except FieldModelRuleError as exc:
                raise FieldModelError(str(exc)) from exc
            try:
                uow.execute(
                    field_port.insert().values(
                        id=identifier,
                        project_id=project_id,
                        field_device_id=field_device_id,
                        port_tag=str(port_tag).strip().upper(),
                        port_kind=port_kind,
                        direction=direction,
                        contract_version=1,
                    )
                )
                self._touch(uow, project_id)
                uow.commit()
            except IntegrityError as exc:
                raise FieldModelError("Field port already exists") from exc
        return identifier

    def endpoint_for_point(
        self, *, project_id: str, cable_line_id: str, cable_point_id: str
    ) -> str:
        return self._create_endpoint(
            project_id=project_id,
            cable_line_id=cable_line_id,
            endpoint_kind="TOPOLOGY_POINT",
            owner_id=cable_point_id,
        )

    def endpoint_for_instance_resource(
        self, *, project_id: str, cable_line_id: str, instance_resource_id: str
    ) -> str:
        return self._create_endpoint(
            project_id=project_id,
            cable_line_id=cable_line_id,
            endpoint_kind="INSTANCE_RESOURCE",
            owner_id=instance_resource_id,
        )

    def endpoint_for_field_port(
        self, *, project_id: str, cable_line_id: str, field_port_id: str
    ) -> str:
        return self._create_endpoint(
            project_id=project_id,
            cable_line_id=cable_line_id,
            endpoint_kind="FIELD_PORT",
            owner_id=field_port_id,
        )

    def create_segment(
        self,
        *,
        project_id: str,
        cable_line_id: str,
        source_endpoint_id: str,
        target_endpoint_id: str,
        route: RouteFacts | None = None,
    ) -> str:
        route = route or RouteFacts()
        try:
            route = route.normalized()
        except FieldModelRuleError as exc:
            raise FieldModelError(str(exc)) from exc
        identifier = new_id()
        with UnitOfWork(self._engine) as uow:
            endpoint_ids = set(
                uow.execute(
                    select(cable_topology_endpoint.c.id).where(
                        cable_topology_endpoint.c.project_id == project_id,
                        cable_topology_endpoint.c.cable_line_id == cable_line_id,
                        cable_topology_endpoint.c.id.in_((source_endpoint_id, target_endpoint_id)),
                    )
                ).scalars()
            )
            if endpoint_ids != {source_endpoint_id, target_endpoint_id}:
                raise FieldModelError("Segment endpoints must belong to the same cable line")
            try:
                uow.execute(
                    cable_segment.insert().values(
                        id=identifier,
                        project_id=project_id,
                        cable_line_id=cable_line_id,
                        source_endpoint_id=source_endpoint_id,
                        target_endpoint_id=target_endpoint_id,
                        mount_way=route.mount_way,
                        gofra_type=route.gofra_type,
                        gofra_color=route.gofra_color,
                        origin_kind="PROJECT",
                        migration_state="CONFIRMED",
                    )
                )
                self._touch(uow, project_id)
                uow.commit()
            except IntegrityError as exc:
                raise FieldModelError(
                    "Duplicate physical edge or a second incoming parent is forbidden"
                ) from exc
        return identifier

    def assign_segment_conduit(
        self, *, project_id: str, cable_segment_id: str, conduit_id: str
    ) -> str:
        identifier = new_id()
        with UnitOfWork(self._engine) as uow:
            segment = uow.execute(
                select(cable_segment.c.id).where(
                    cable_segment.c.id == cable_segment_id,
                    cable_segment.c.project_id == project_id,
                )
            ).scalar_one_or_none()
            target_conduit = uow.execute(
                select(conduit.c.id).where(
                    conduit.c.id == conduit_id,
                    conduit.c.project_id == project_id,
                    conduit.c.lifecycle == "ACTIVE",
                )
            ).scalar_one_or_none()
            if segment is None or target_conduit is None:
                raise FieldModelError("Cable segment or conduit not found")
            try:
                uow.execute(
                    conduit_segment_assignment.insert().values(
                        id=identifier,
                        project_id=project_id,
                        cable_segment_id=cable_segment_id,
                        conduit_id=conduit_id,
                    )
                )
                self._touch(uow, project_id)
                uow.commit()
            except IntegrityError as exc:
                raise FieldModelError("Cable segment is already assigned to a conduit") from exc
        return identifier

    def create_control_key(
        self,
        *,
        project_id: str,
        field_device_id: str,
        key_tag: str,
        target_kind: str,
        target_id: str,
        target_text: str,
    ) -> str:
        key = str(key_tag).strip().upper()
        kind = str(target_kind).strip().upper()
        if key not in {"KEY_1", "KEY_2", "KEY_3", "KEY_4"}:
            raise FieldModelError("Physical key tag must be KEY_1..KEY_4")
        if kind not in {"CABLE_LINE", "DALI_GROUP"}:
            raise FieldModelError("Control target must be CABLE_LINE or DALI_GROUP")
        identifier = new_id()
        with UnitOfWork(self._engine) as uow:
            device = uow.execute(
                select(field_device.c.id).where(
                    field_device.c.id == field_device_id,
                    field_device.c.project_id == project_id,
                )
            ).scalar_one_or_none()
            target_table = cable_line if kind == "CABLE_LINE" else dali_group
            target = uow.execute(
                select(target_table.c.id).where(
                    target_table.c.id == target_id,
                    target_table.c.project_id == project_id,
                )
            ).scalar_one_or_none()
            if device is None or target is None:
                raise FieldModelError("Field device or control target not found")
            values = {
                "target_cable_line_id": target_id if kind == "CABLE_LINE" else None,
                "target_dali_group_id": target_id if kind == "DALI_GROUP" else None,
            }
            try:
                uow.execute(
                    field_control_key.insert().values(
                        id=identifier,
                        project_id=project_id,
                        field_device_id=field_device_id,
                        key_tag=key,
                        functional_target_text=str(target_text).strip(),
                        target_kind=kind,
                        origin_json={"kind": "PROJECT"},
                        **values,
                    )
                )
                self._touch(uow, project_id)
                uow.commit()
            except IntegrityError as exc:
                raise FieldModelError("Physical key identity already exists") from exc
        return identifier

    def assign_control_key_input(
        self,
        *,
        project_id: str,
        field_control_key_id: str,
        input_resource_id: str,
        expected_project_revision: int | None = None,
    ) -> str:
        assignment_id = new_id()
        reservation_id = new_id()
        with UnitOfWork(self._engine) as uow:
            self._require_revision(uow, project_id, expected_project_revision)
            key = uow.execute(
                select(field_control_key.c.id).where(
                    field_control_key.c.id == field_control_key_id,
                    field_control_key.c.project_id == project_id,
                    field_control_key.c.lifecycle == "ACTIVE",
                )
            ).scalar_one_or_none()
            resource = uow.execute(
                select(
                    instance_resource.c.direction,
                    instance_resource.c.resource_kind,
                    instance_resource.c.active,
                ).where(
                    instance_resource.c.id == input_resource_id,
                    instance_resource.c.project_id == project_id,
                )
            ).one_or_none()
            reserved = uow.execute(
                select(user_reserve.c.id).where(
                    user_reserve.c.project_id == project_id,
                    user_reserve.c.target_kind == "INSTANCE_RESOURCE",
                    user_reserve.c.instance_resource_id == input_resource_id,
                    user_reserve.c.lifecycle == "ACTIVE",
                )
            ).scalar_one_or_none()
            if key is None or resource is None or not resource.active:
                raise FieldModelError("Physical key or input resource not found")
            if resource.resource_kind not in {
                "DRY_CONTACT_INPUT",
                "DIGITAL_INPUT",
            } or resource.direction not in {"IN", "BIDIRECTIONAL"}:
                raise FieldModelError(
                    "Physical key requires a passport-compatible DRY_CONTACT_INPUT resource"
                )
            if reserved is not None:
                raise FieldModelError("Input resource is marked as user reserve")
            try:
                uow.execute(
                    resource_reservation.insert().values(
                        id=reservation_id,
                        project_id=project_id,
                        resource_id=input_resource_id,
                        reservation_kind="CONTROL_KEY_INPUT",
                        slot_key="EXCLUSIVE",
                        owner_assignment_kind="CONTROL_KEY_INPUT",
                        owner_assignment_id=assignment_id,
                    )
                )
                uow.execute(
                    control_key_input_assignment.insert().values(
                        id=assignment_id,
                        project_id=project_id,
                        field_control_key_id=field_control_key_id,
                        input_kind="INSTANCE_RESOURCE",
                        input_resource_id=input_resource_id,
                        field_port_id=None,
                        reservation_id=reservation_id,
                    )
                )
                self._touch(uow, project_id)
                uow.commit()
            except IntegrityError as exc:
                raise FieldModelError("Physical key or input is already assigned") from exc
        return assignment_id

    def assign_control_key_field_port(
        self,
        *,
        project_id: str,
        field_control_key_id: str,
        field_port_id: str,
        expected_project_revision: int | None = None,
    ) -> str:
        """Link one physical key to one canonical field-device input port."""

        assignment_id = new_id()
        with UnitOfWork(self._engine) as uow:
            self._require_revision(uow, project_id, expected_project_revision)
            key = uow.execute(
                select(field_control_key.c.id).where(
                    field_control_key.c.id == field_control_key_id,
                    field_control_key.c.project_id == project_id,
                    field_control_key.c.lifecycle == "ACTIVE",
                )
            ).scalar_one_or_none()
            port = uow.execute(
                select(field_port.c.port_kind, field_port.c.direction).where(
                    field_port.c.id == field_port_id,
                    field_port.c.project_id == project_id,
                    field_port.c.lifecycle == "ACTIVE",
                )
            ).one_or_none()
            if key is None or port is None:
                raise FieldModelError("Physical key or field input port not found")
            if port.port_kind != "DIGITAL_INPUT" or port.direction != "IN":
                raise FieldModelError("Physical key requires a canonical DIGITAL_INPUT field port")
            try:
                uow.execute(
                    control_key_input_assignment.insert().values(
                        id=assignment_id,
                        project_id=project_id,
                        field_control_key_id=field_control_key_id,
                        input_kind="FIELD_PORT",
                        input_resource_id=None,
                        field_port_id=field_port_id,
                        reservation_id=None,
                    )
                )
                self._touch(uow, project_id)
                uow.commit()
            except IntegrityError as exc:
                raise FieldModelError(
                    "Physical key or field input port is already assigned"
                ) from exc
        return assignment_id

    def unassign_control_key_input(self, *, project_id: str, field_control_key_id: str) -> None:
        """Remove the exact key-level assignment and its resource reservation atomically."""

        with UnitOfWork(self._engine) as uow:
            row = (
                uow.execute(
                    select(control_key_input_assignment).where(
                        control_key_input_assignment.c.project_id == project_id,
                        control_key_input_assignment.c.field_control_key_id == field_control_key_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is not None:
                uow.execute(
                    delete(control_key_input_assignment).where(
                        control_key_input_assignment.c.id == row["id"]
                    )
                )
                if row["reservation_id"] is not None:
                    uow.execute(
                        delete(resource_reservation).where(
                            resource_reservation.c.id == row["reservation_id"]
                        )
                    )
                self._touch(uow, project_id)
            uow.commit()

    def list_control_input_candidates(
        self, project_id: str, *, include_unavailable: bool = False
    ) -> list[dict[str, Any]]:
        """Return free compatible key inputs; user reserve is free but not selectable."""

        with self._engine.connect() as connection:
            occupied = set(
                connection.execute(
                    select(control_key_input_assignment.c.input_resource_id).where(
                        control_key_input_assignment.c.project_id == project_id,
                        control_key_input_assignment.c.input_kind == "INSTANCE_RESOURCE",
                    )
                ).scalars()
            )
            reserved = set(
                connection.execute(
                    select(user_reserve.c.instance_resource_id).where(
                        user_reserve.c.project_id == project_id,
                        user_reserve.c.target_kind == "INSTANCE_RESOURCE",
                        user_reserve.c.lifecycle == "ACTIVE",
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
                    instance_resource.c.resource_kind,
                    instance_resource.c.direction,
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
                    instance_resource.c.resource_kind == "DRY_CONTACT_INPUT",
                    instance_resource.c.direction.in_(("IN", "BIDIRECTIONAL")),
                    instance_resource.c.active.is_(True),
                    project_instance.c.lifecycle == "ACTIVE",
                )
                .order_by(
                    project_instance.c.designation,
                    instance_resource.c.resource_key,
                    instance_resource.c.ordinal,
                )
            ).mappings()
            result = []
            for row in rows:
                item = dict(row)
                item["label"] = resource_user_label(row)
                item["occupied"] = row["id"] in occupied
                item["user_reserved"] = row["id"] in reserved
                item["selectable"] = not item["occupied"] and not item["user_reserved"]
                result.append(item)
            return result if include_unavailable else [row for row in result if row["selectable"]]

    def control_key_read_model(self, project_id: str) -> list[dict[str, Any]]:
        """Expose physical identity, functional target and exact typed input owner."""

        candidates = {
            row["id"]: row
            for row in self.list_control_input_candidates(project_id, include_unavailable=True)
        }
        with self._engine.connect() as connection:
            keys = list(
                connection.execute(
                    select(field_control_key, field_device.c.entity_handle)
                    .join(
                        field_device,
                        field_device.c.id == field_control_key.c.field_device_id,
                    )
                    .where(
                        field_control_key.c.project_id == project_id,
                        field_control_key.c.lifecycle == "ACTIVE",
                    )
                ).mappings()
            )
            assignments = {
                row["field_control_key_id"]: dict(row)
                for row in connection.execute(
                    select(control_key_input_assignment).where(
                        control_key_input_assignment.c.project_id == project_id
                    )
                ).mappings()
            }
            ports = {
                row["id"]: dict(row)
                for row in connection.execute(
                    select(field_port).where(field_port.c.project_id == project_id)
                ).mappings()
            }
        result = []
        for key in keys:
            assignment = assignments.get(key["id"])
            label = None
            if assignment and assignment["input_kind"] == "INSTANCE_RESOURCE":
                label = (candidates.get(assignment["input_resource_id"]) or {}).get("label")
            elif assignment:
                port = ports.get(assignment["field_port_id"])
                label = None if port is None else port["port_tag"]
            result.append(
                {
                    **dict(key),
                    "physical_identity": (
                        f"{key['entity_handle'] or key['field_device_id']}:{key['key_tag']}"
                    ),
                    "input_kind": None if assignment is None else assignment["input_kind"],
                    "input_id": (
                        None
                        if assignment is None
                        else assignment["input_resource_id"] or assignment["field_port_id"]
                    ),
                    "input_label": label,
                    "status": "UNASSIGNED" if assignment is None else "ASSIGNED",
                }
            )
        return result

    def grouped_switch_capacity(
        self,
        *,
        project_id: str,
        cable_line_id: str,
        available_input_count: int | None = None,
    ) -> dict[str, Any]:
        """Assess a grouped 2YY line without scan-order or free-text cable guesses."""

        with self._engine.connect() as connection:
            line = (
                connection.execute(
                    select(cable_line).where(
                        cable_line.c.id == cable_line_id,
                        cable_line.c.project_id == project_id,
                        cable_line.c.lifecycle == "ACTIVE",
                    )
                )
                .mappings()
                .one_or_none()
            )
            if line is None or line["system_kind"] != "SWITCHES":
                raise FieldModelError("Grouped capacity requires an active SWITCHES cable line")
            devices = list(
                connection.execute(
                    select(field_device.c.id, field_device.c.normalized_fields_json)
                    .join(
                        cable_point_field_device,
                        cable_point_field_device.c.field_device_id == field_device.c.id,
                    )
                    .join(
                        cable_point,
                        cable_point.c.id == cable_point_field_device.c.cable_point_id,
                    )
                    .where(
                        cable_point.c.project_id == project_id,
                        cable_point.c.cable_line_id == cable_line_id,
                        field_device.c.lifecycle == "ACTIVE",
                    )
                ).mappings()
            )
            device_ids = tuple(row["id"] for row in devices)
            key_rows = (
                list(
                    connection.execute(
                        select(
                            field_control_key.c.field_device_id,
                            field_control_key.c.key_tag,
                        ).where(
                            field_control_key.c.project_id == project_id,
                            field_control_key.c.field_device_id.in_(device_ids),
                            field_control_key.c.lifecycle == "ACTIVE",
                        )
                    )
                )
                if device_ids
                else []
            )
        ordered = sorted(
            devices,
            key=lambda row: _numeric_suffix(
                str((row["normalized_fields_json"] or {}).get("CABLE_ID", ""))
            ),
        )
        key_count = len(key_rows)
        required = key_count + 1
        facts = dict(line["cable_facts_json"] or {})
        capacity = _machine_conductor_capacity(facts)
        if available_input_count is None:
            available_input_count = sum(
                row["selectable"] for row in self.list_control_input_candidates(project_id)
            )
        reasons = []
        status = "VERIFIED"
        if capacity is None:
            status = "INCOMPLETE"
            reasons.append("CONDUCTOR_CAPACITY_UNKNOWN")
        elif required > capacity:
            status = "BLOCKED"
            reasons.append("CONDUCTOR_SHORTAGE")
        if key_count > available_input_count:
            status = "BLOCKED"
            reasons.append("INPUT_SHORTAGE")
        return {
            "cable_line_id": cable_line_id,
            "device_order": tuple(
                (row["normalized_fields_json"] or {}).get("CABLE_ID") for row in ordered
            ),
            "physical_key_count": key_count,
            "required_conductors": required,
            "available_conductors": capacity,
            "available_inputs": available_input_count,
            "status": status,
            "reasons": tuple(reasons),
        }

    def field_port_read_model(self, project_id: str) -> list[dict[str, Any]]:
        """Expose exact canonical ports and their independent key/cable links."""

        with self._engine.connect() as connection:
            ports = list(
                connection.execute(
                    select(
                        field_port,
                        field_device.c.block_kind,
                        field_device.c.entity_handle,
                    )
                    .join(field_device, field_device.c.id == field_port.c.field_device_id)
                    .where(
                        field_port.c.project_id == project_id,
                        field_port.c.lifecycle == "ACTIVE",
                    )
                    .order_by(field_device.c.id, field_port.c.port_tag)
                ).mappings()
            )
            key_links = {
                row["field_port_id"]: row["field_control_key_id"]
                for row in connection.execute(
                    select(
                        control_key_input_assignment.c.field_port_id,
                        control_key_input_assignment.c.field_control_key_id,
                    ).where(
                        control_key_input_assignment.c.project_id == project_id,
                        control_key_input_assignment.c.input_kind == "FIELD_PORT",
                    )
                ).mappings()
            }
            cable_links: dict[str, list[str]] = {}
            for port_id, line_id in connection.execute(
                select(
                    cable_topology_endpoint.c.field_port_id,
                    cable_line_assignment.c.cable_line_id,
                )
                .join(
                    cable_line_assignment,
                    cable_line_assignment.c.endpoint_id == cable_topology_endpoint.c.id,
                )
                .where(
                    cable_topology_endpoint.c.project_id == project_id,
                    cable_topology_endpoint.c.endpoint_kind == "FIELD_PORT",
                )
            ):
                cable_links.setdefault(port_id, []).append(line_id)
        return [
            {
                **dict(row),
                "physical_identity": (
                    f"{row['entity_handle'] or row['field_device_id']}:{row['port_tag']}"
                ),
                "linked_key_id": key_links.get(row["id"]),
                "linked_cable_line_ids": tuple(cable_links.get(row["id"], ())),
                "status": (
                    "LINKED" if row["id"] in key_links or row["id"] in cable_links else "UNUSED"
                ),
            }
            for row in ports
        ]

    def assign_line_to_field_port(
        self,
        *,
        project_id: str,
        cable_line_id: str,
        field_port_id: str,
        assignment_role: str,
        expected_project_revision: int | None = None,
    ) -> str:
        """Assign one line to one field port in a single stale-safe Unit of Work."""

        identifier = new_id()
        with UnitOfWork(self._engine) as uow:
            self._require_revision(uow, project_id, expected_project_revision)
            self._require_line(uow, project_id, cable_line_id)
            port = uow.execute(
                select(field_port.c.id, field_port.c.direction).where(
                    field_port.c.id == field_port_id,
                    field_port.c.project_id == project_id,
                    field_port.c.lifecycle == "ACTIVE",
                )
            ).one_or_none()
            if port is None or port.direction not in {"OUT", "BIDIRECTIONAL"}:
                raise FieldModelError("Cable line requires a canonical output field port")
            endpoint_id = uow.execute(
                select(cable_topology_endpoint.c.id).where(
                    cable_topology_endpoint.c.project_id == project_id,
                    cable_topology_endpoint.c.cable_line_id == cable_line_id,
                    cable_topology_endpoint.c.field_port_id == field_port_id,
                )
            ).scalar_one_or_none()
            if endpoint_id is None:
                endpoint_id = new_id()
                uow.execute(
                    cable_topology_endpoint.insert().values(
                        id=endpoint_id,
                        project_id=project_id,
                        cable_line_id=cable_line_id,
                        endpoint_kind="FIELD_PORT",
                        field_port_id=field_port_id,
                    )
                )
            occupied = uow.execute(
                select(cable_line_assignment.c.id)
                .join(
                    cable_topology_endpoint,
                    cable_topology_endpoint.c.id == cable_line_assignment.c.endpoint_id,
                )
                .where(
                    cable_line_assignment.c.project_id == project_id,
                    cable_topology_endpoint.c.field_port_id == field_port_id,
                )
            ).first()
            if occupied is not None:
                raise FieldModelError("Exclusive field port is already linked")
            try:
                uow.execute(
                    cable_line_assignment.insert().values(
                        id=identifier,
                        project_id=project_id,
                        cable_line_id=cable_line_id,
                        endpoint_id=endpoint_id,
                        assignment_role=str(assignment_role).strip().upper(),
                        reservation_id=None,
                    )
                )
                self._touch(uow, project_id)
                uow.commit()
            except IntegrityError as exc:
                raise FieldModelError("Cable-line endpoint or role is already assigned") from exc
        return identifier

    def set_user_reserve(
        self,
        *,
        project_id: str,
        target_kind: str,
        target_id: str,
        actor: str,
        note: str = "",
    ) -> str:
        kind = str(target_kind).strip().upper()
        if kind not in {"PROJECT_INSTANCE", "INSTANCE_RESOURCE"}:
            raise FieldModelError("User reserve target must be instance or resource")
        target_table = project_instance if kind == "PROJECT_INSTANCE" else instance_resource
        identifier = new_id()
        with UnitOfWork(self._engine) as uow:
            target = uow.execute(
                select(target_table.c.id).where(
                    target_table.c.id == target_id,
                    target_table.c.project_id == project_id,
                )
            ).scalar_one_or_none()
            if target is None:
                raise FieldModelError("User reserve target not found")
            values = {
                "project_instance_id": target_id if kind == "PROJECT_INSTANCE" else None,
                "instance_resource_id": target_id if kind == "INSTANCE_RESOURCE" else None,
            }
            try:
                uow.execute(
                    user_reserve.insert().values(
                        id=identifier,
                        project_id=project_id,
                        target_kind=kind,
                        actor=str(actor).strip(),
                        note=str(note).strip() or None,
                        **values,
                    )
                )
                self._touch(uow, project_id)
                uow.commit()
            except IntegrityError as exc:
                raise FieldModelError(
                    "An active user reserve already exists for this target"
                ) from exc
        return identifier

    def set_led_sync_fact(
        self,
        *,
        project_id: str,
        cable_line_id: str,
        led_type: str,
        origin: str,
        baseline: dict[str, Any] | None,
        sync_state: str,
    ) -> str:
        try:
            normalized, channels, _conductors = normalize_led_type(led_type)
        except FieldModelRuleError as exc:
            raise FieldModelError(str(exc)) from exc
        clean_origin = str(origin).strip().upper()
        clean_state = str(sync_state).strip().upper()
        if clean_origin not in {"DWG", "PROJECT", "MIGRATION"}:
            raise FieldModelError("Unsupported LED fact origin")
        approved_states = {
            "UNCONFIRMED",
            "IN_SYNC",
            "DWG_CHANGED",
            "PROJECT_CHANGED",
            "BOTH_CHANGED_CONFLICT",
        }
        if clean_state not in approved_states:
            raise FieldModelError("Unsupported LED sync state")
        identifier = new_id()
        with UnitOfWork(self._engine) as uow:
            self._require_line(uow, project_id, cable_line_id)
            existing = uow.execute(
                select(led_line_profile.c.id).where(
                    led_line_profile.c.project_id == project_id,
                    led_line_profile.c.cable_line_id == cable_line_id,
                )
            ).scalar_one_or_none()
            values = {
                "led_kind": normalized,
                "channels": channels,
                "led_type_origin": clean_origin,
                "sync_baseline_json": baseline,
                "sync_state": clean_state,
            }
            if existing is None:
                uow.execute(
                    led_line_profile.insert().values(
                        id=identifier,
                        project_id=project_id,
                        cable_line_id=cable_line_id,
                        voltage_decimal=None,
                        power_per_m_decimal=None,
                        tape_product_definition_id=None,
                        supply_scope=None,
                        **values,
                    )
                )
            else:
                identifier = existing
                uow.execute(
                    update(led_line_profile)
                    .where(led_line_profile.c.id == existing)
                    .values(**values, row_version=led_line_profile.c.row_version + 1)
                )
            self._touch(uow, project_id)
            uow.commit()
        return identifier

    def field_device_configuration_capability(
        self, *, project_id: str, field_device_id: str
    ) -> dict[str, Any]:
        """Return only versioned catalog schemas compatible with the physical block identity."""

        with self._engine.connect() as connection:
            device = (
                connection.execute(
                    select(field_device).where(
                        field_device.c.id == field_device_id,
                        field_device.c.project_id == project_id,
                        field_device.c.lifecycle == "ACTIVE",
                    )
                )
                .mappings()
                .one_or_none()
            )
            if device is None:
                raise FieldModelError("Field device not found")
            products = list(
                connection.execute(
                    select(product_definition)
                    .join(
                        catalog_release,
                        catalog_release.c.id == product_definition.c.catalog_release_id,
                    )
                    .where(
                        product_definition.c.lifecycle == "ACTIVE",
                        catalog_release.c.status == "ACTIVE",
                    )
                    .order_by(product_definition.c.product_key, product_definition.c.version)
                ).mappings()
            )
            selection = (
                connection.execute(
                    select(field_device_product_selection).where(
                        field_device_product_selection.c.project_id == project_id,
                        field_device_product_selection.c.field_device_id == field_device_id,
                        field_device_product_selection.c.lifecycle == "ACTIVE",
                    )
                )
                .mappings()
                .one_or_none()
            )
        candidates = []
        for product in products:
            schema = _field_configuration_schema(product["project_parameters_json"])
            if schema is None or device["block_kind"] not in schema["field_block_kinds"]:
                continue
            candidates.append(
                {
                    "product_definition_id": product["id"],
                    "product_key": product["product_key"],
                    "product_version": product["version"],
                    "name": product["name"],
                    "article": product["article"],
                    "schema": schema,
                }
            )
        return {
            "field_device_id": field_device_id,
            "block_kind": device["block_kind"],
            "status": "AVAILABLE" if candidates else "CATALOG/PASSPORT_GAP",
            "user_status": "Требуется действие" if candidates else "Нужны данные",
            "products": tuple(candidates),
            "selection": None if selection is None else dict(selection),
        }

    def select_catalog_field_device_configuration(
        self,
        *,
        project_id: str,
        field_device_id: str,
        product_definition_id: str,
        configuration: dict[str, Any],
        supply_scope: str,
    ) -> str:
        """Persist a normalized configuration only when every value comes from catalog facts."""

        capability = self.field_device_configuration_capability(
            project_id=project_id, field_device_id=field_device_id
        )
        product = next(
            (
                item
                for item in capability["products"]
                if item["product_definition_id"] == product_definition_id
            ),
            None,
        )
        if product is None:
            raise FieldModelError(
                "CATALOG/PASSPORT_GAP: no compatible versioned configuration schema"
            )
        normalized = _normalize_field_configuration(product["schema"], configuration)
        clean_scope = str(supply_scope).strip().upper()
        if clean_scope not in SUPPLY_SCOPES:
            raise FieldModelError("Unsupported supply scope")
        return self.select_field_device_product(
            project_id=project_id,
            field_device_id=field_device_id,
            product_definition_id=product_definition_id,
            configuration_schema_version=product["schema"]["schema_version"],
            configuration=normalized,
            supply_scope=clean_scope,
            knowledge_status="KNOWN",
        )

    def select_field_device_product(
        self,
        *,
        project_id: str,
        field_device_id: str,
        product_definition_id: str,
        configuration_schema_version: int,
        configuration: dict[str, Any],
        supply_scope: str,
        knowledge_status: str = "KNOWN",
    ) -> str:
        if configuration_schema_version < 1 or not isinstance(configuration, dict):
            raise FieldModelError("Configuration must be a versioned normalized object")
        identifier = new_id()
        with UnitOfWork(self._engine) as uow:
            device = uow.execute(
                select(field_device.c.id).where(
                    field_device.c.id == field_device_id,
                    field_device.c.project_id == project_id,
                )
            ).scalar_one_or_none()
            product_row = uow.execute(
                select(product_definition.c.id).where(
                    product_definition.c.id == product_definition_id,
                    product_definition.c.lifecycle == "ACTIVE",
                )
            ).scalar_one_or_none()
            if device is None or product_row is None:
                raise FieldModelError("Field device or versioned product not found")
            existing = uow.execute(
                select(field_device_product_selection.c.id).where(
                    field_device_product_selection.c.field_device_id == field_device_id
                )
            ).scalar_one_or_none()
            values = {
                "product_definition_id": product_definition_id,
                "configuration_schema_version": configuration_schema_version,
                "configuration_json": configuration,
                "supply_scope": str(supply_scope).strip().upper(),
                "knowledge_status": str(knowledge_status).strip().upper(),
            }
            if existing is None:
                uow.execute(
                    field_device_product_selection.insert().values(
                        id=identifier,
                        project_id=project_id,
                        field_device_id=field_device_id,
                        **values,
                    )
                )
            else:
                identifier = existing
                uow.execute(
                    update(field_device_product_selection)
                    .where(field_device_product_selection.c.id == existing)
                    .values(
                        **values,
                        row_version=field_device_product_selection.c.row_version + 1,
                    )
                )
            self._touch(uow, project_id)
            uow.commit()
        return identifier

    def topology_snapshot(self, project_id: str) -> dict[str, list[dict]]:
        tables = {
            "points": cable_point,
            "memberships": cable_point_field_device,
            "endpoints": cable_topology_endpoint,
            "segments": cable_segment,
            "segment_conduits": conduit_segment_assignment,
            "ports": field_port,
            "keys": field_control_key,
            "key_inputs": control_key_input_assignment,
            "user_reserves": user_reserve,
            "field_product_selections": field_device_product_selection,
            "led_profiles": led_line_profile,
        }
        with self._engine.connect() as connection:
            return {
                name: [
                    dict(row)
                    for row in connection.execute(
                        select(table).where(table.c.project_id == project_id)
                    ).mappings()
                ]
                for name, table in tables.items()
            }

    def _create_endpoint(
        self,
        *,
        project_id: str,
        cable_line_id: str,
        endpoint_kind: str,
        owner_id: str,
    ) -> str:
        column_by_kind = {
            "TOPOLOGY_POINT": cable_topology_endpoint.c.cable_point_id,
            "INSTANCE_RESOURCE": cable_topology_endpoint.c.instance_resource_id,
            "FIELD_PORT": cable_topology_endpoint.c.field_port_id,
        }
        column = column_by_kind[endpoint_kind]
        with UnitOfWork(self._engine) as uow:
            self._require_line(uow, project_id, cable_line_id)
            owner_tables = {
                "TOPOLOGY_POINT": cable_point,
                "INSTANCE_RESOURCE": instance_resource,
                "FIELD_PORT": field_port,
            }
            owner = owner_tables[endpoint_kind]
            owner_row = uow.execute(
                select(owner.c.id).where(owner.c.id == owner_id, owner.c.project_id == project_id)
            ).scalar_one_or_none()
            if owner_row is None:
                raise FieldModelError("Topology endpoint owner not found")
            existing = uow.execute(
                select(cable_topology_endpoint.c.id).where(
                    cable_topology_endpoint.c.project_id == project_id,
                    cable_topology_endpoint.c.cable_line_id == cable_line_id,
                    column == owner_id,
                )
            ).scalar_one_or_none()
            if existing is not None:
                uow.commit()
                return existing
            identifier = new_id()
            values = {
                "cable_point_id": owner_id if endpoint_kind == "TOPOLOGY_POINT" else None,
                "instance_resource_id": owner_id if endpoint_kind == "INSTANCE_RESOURCE" else None,
                "field_port_id": owner_id if endpoint_kind == "FIELD_PORT" else None,
            }
            uow.execute(
                cable_topology_endpoint.insert().values(
                    id=identifier,
                    project_id=project_id,
                    cable_line_id=cable_line_id,
                    endpoint_kind=endpoint_kind,
                    **values,
                )
            )
            self._touch(uow, project_id)
            uow.commit()
            return identifier

    def _assign_line_endpoint(
        self,
        *,
        project_id: str,
        cable_line_id: str,
        endpoint_id: str,
        assignment_role: str,
    ) -> str:
        identifier = new_id()
        with UnitOfWork(self._engine) as uow:
            endpoint = uow.execute(
                select(
                    cable_topology_endpoint.c.id,
                    cable_topology_endpoint.c.endpoint_kind,
                ).where(
                    cable_topology_endpoint.c.id == endpoint_id,
                    cable_topology_endpoint.c.project_id == project_id,
                    cable_topology_endpoint.c.cable_line_id == cable_line_id,
                )
            ).one_or_none()
            if endpoint is None:
                raise FieldModelError("Cable-line endpoint not found")
            if endpoint.endpoint_kind == "FIELD_PORT":
                occupied = uow.execute(
                    select(cable_line_assignment.c.id).where(
                        cable_line_assignment.c.project_id == project_id,
                        cable_line_assignment.c.endpoint_id == endpoint_id,
                    )
                ).scalar_one_or_none()
                if occupied is not None:
                    raise FieldModelError("Exclusive field port is already linked")
            try:
                uow.execute(
                    cable_line_assignment.insert().values(
                        id=identifier,
                        project_id=project_id,
                        cable_line_id=cable_line_id,
                        endpoint_id=endpoint_id,
                        assignment_role=str(assignment_role).strip().upper(),
                        reservation_id=None,
                    )
                )
                self._touch(uow, project_id)
                uow.commit()
            except IntegrityError as exc:
                raise FieldModelError("Cable-line endpoint or role is already assigned") from exc
        return identifier

    @staticmethod
    def _require_revision(
        uow: UnitOfWork, project_id: str, expected_project_revision: int | None
    ) -> None:
        if expected_project_revision is None:
            return
        actual_revision = uow.execute(
            select(project.c.project_revision).where(project.c.id == project_id)
        ).scalar_one_or_none()
        if actual_revision != expected_project_revision:
            raise FieldModelError(
                "STALE_PROJECT_REVISION: preview must be rebuilt before confirmation"
            )

    @staticmethod
    def _require_line(uow: UnitOfWork, project_id: str, line_id: str) -> None:
        found = uow.execute(
            select(cable_line.c.id).where(
                cable_line.c.id == line_id,
                cable_line.c.project_id == project_id,
                cable_line.c.lifecycle == "ACTIVE",
            )
        ).scalar_one_or_none()
        if found is None:
            raise FieldModelError("Cable line not found")

    @staticmethod
    def _touch(uow: UnitOfWork, project_id: str) -> None:
        now = datetime.now(UTC)
        result = uow.execute(
            update(project)
            .where(project.c.id == project_id)
            .values(
                project_revision=project.c.project_revision + 1,
                row_version=project.c.row_version + 1,
                updated_at_utc=now,
            )
        )
        if result.rowcount != 1:
            raise FieldModelError("Project not found")


def _numeric_suffix(cable_id: str) -> int:
    try:
        base, suffix = cable_id.rsplit(".", 1)
        if not base or not suffix.isdigit():
            raise ValueError
        return int(suffix)
    except ValueError as exc:
        raise FieldModelError(
            f"Physical device CABLE_ID has no numeric .ZZ suffix: {cable_id}"
        ) from exc


def _machine_conductor_capacity(facts: dict[str, Any]) -> int | None:
    """Use only explicit approved machine facts; never parse CABLE_TYPE/display text."""

    value = facts.get("CONDUCTOR_CAPACITY", facts.get("CABLE_CONDUCTOR_CAPACITY"))
    model = facts.get("CABLE_MODEL")
    if value is None and isinstance(model, dict):
        value = model.get("conductors")
    if value is None and str(facts.get("CABLE_STANDARD", "")).strip().upper() == "UTP_8":
        value = 8
    try:
        capacity = int(value)
    except (TypeError, ValueError):
        return None
    return capacity if capacity > 0 else None


def _field_configuration_schema(parameters: Any) -> dict[str, Any] | None:
    if not isinstance(parameters, dict):
        return None
    raw = parameters.get("field_configuration_schema")
    if not isinstance(raw, dict):
        return None
    try:
        version = int(raw["schema_version"])
    except (KeyError, TypeError, ValueError):
        return None
    block_kinds = raw.get("field_block_kinds")
    options = raw.get("options")
    if version < 1 or not isinstance(block_kinds, list) or not isinstance(options, list):
        return None
    normalized_options = []
    seen = set()
    for option in options:
        if not isinstance(option, dict):
            return None
        key = str(option.get("key", "")).strip()
        values = option.get("values")
        if key not in FIELD_CONFIGURATION_FAMILIES or key in seen or not isinstance(values, list):
            return None
        normalized_values = []
        value_ids = set()
        for value in values:
            if not isinstance(value, dict):
                return None
            identifier = str(value.get("id", "")).strip()
            label = str(value.get("label", "")).strip()
            if not identifier or not label or identifier in value_ids:
                return None
            value_ids.add(identifier)
            normalized_values.append({"id": identifier, "label": label})
        if not normalized_values:
            return None
        seen.add(key)
        normalized_options.append(
            {
                "key": key,
                "label": str(option.get("label") or key),
                "required": bool(option.get("required", True)),
                "values": tuple(normalized_values),
            }
        )
    clean_blocks = tuple(
        sorted({str(value).strip() for value in block_kinds if str(value).strip()})
    )
    if not clean_blocks:
        return None
    return {
        "schema_version": version,
        "field_block_kinds": clean_blocks,
        "options": tuple(normalized_options),
    }


def _normalize_field_configuration(
    schema: dict[str, Any], configuration: dict[str, Any]
) -> dict[str, str]:
    if not isinstance(configuration, dict):
        raise FieldModelError("Configuration must be an object")
    options = {option["key"]: option for option in schema["options"]}
    unknown = set(configuration) - set(options)
    if unknown:
        raise FieldModelError(f"Configuration contains unknown options: {sorted(unknown)}")
    normalized = {}
    for key, option in options.items():
        raw = configuration.get(key)
        if raw in (None, ""):
            if option["required"]:
                raise FieldModelError(f"Configuration option is required: {key}")
            continue
        value = str(raw).strip()
        allowed = {item["id"] for item in option["values"]}
        if value not in allowed:
            raise FieldModelError(f"Configuration value is not in catalog schema: {key}={value}")
        normalized[key] = value
    return {key: normalized[key] for key in sorted(normalized)}
