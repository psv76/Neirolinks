"""Transactional automation assignments and derived LED read models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import Engine, delete, or_, select, update

from nl_project_2.constructor import ConstructorService
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    cable_line,
    cable_line_assignment,
    cable_topology_endpoint,
    instance_resource,
    led_line_profile,
    led_segment,
    passport_definition,
    product_definition,
    project,
    project_instance,
    resource_reservation,
    user_reserve,
)
from nl_project_2.persistence.uow import UnitOfWork

from .domain import (
    LedLoad,
    ReelPacking,
    SegmentCut,
    assess_pwm_capacity,
    calculate_led_load,
    cut_segment,
    led_layout,
    normalize_led_kind,
    pack_reels,
)


class AutomationError(RuntimeError):
    pass


_PASSPORT_BY_KIND = {
    "MONO": "led_tape.constant_voltage.mono.24v",
    "CCT": "led_tape.constant_voltage.cct.24v",
    # The canonical RGBW passport is a four-channel superset; RGB uses its
    # verified R/G/B channels without inventing a synthetic catalog entity.
    "RGB": "led_tape.constant_voltage.rgbw.24v",
    "RGBW": "led_tape.constant_voltage.rgbw.24v",
}
_AUTOMATION_CLASSES = {
    "WB_MR6C_V2",
    "WB_LED_V1",
    "WB_UPS_V3",
    "WIREN_BOARD_8_5",
}


@dataclass(frozen=True, slots=True)
class LedProfileResult:
    profile_id: str
    product_key: str
    supply_scope: str
    cuts: tuple[SegmentCut, ...]
    packing: ReelPacking
    load: LedLoad | None


@dataclass(frozen=True, slots=True)
class ChannelAssignmentResult:
    status: str
    assignment_ids: tuple[str, ...]
    trace: tuple[dict[str, Any], ...]


class AutomationService:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self.constructor = ConstructorService(engine)

    def list_instances(self, project_id: str) -> list[dict]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(
                    project_instance,
                    passport_definition.c.passport_key,
                    passport_definition.c.name.label("passport_name"),
                    passport_definition.c.equipment_class,
                    product_definition.c.product_key,
                    product_definition.c.name.label("product_name"),
                )
                .join(
                    passport_definition,
                    passport_definition.c.id == project_instance.c.passport_definition_id,
                )
                .outerjoin(
                    product_definition,
                    product_definition.c.id == project_instance.c.product_definition_id,
                )
                .where(
                    project_instance.c.project_id == project_id,
                    project_instance.c.lifecycle == "ACTIVE",
                    passport_definition.c.equipment_class.in_(_AUTOMATION_CLASSES),
                )
                .order_by(project_instance.c.designation)
            ).mappings()
            return [dict(row) for row in rows]

    def list_resources(self, project_id: str) -> list[dict]:
        instance_ids = {row["id"] for row in self.list_instances(project_id)}
        return [
            row
            for row in self.constructor.list_resources(project_id)
            if row["project_instance_id"] in instance_ids
        ]

    def list_assignments(self, project_id: str) -> list[dict]:
        return self.constructor.list_cable_assignments(project_id)

    def list_cable_lines(self, project_id: str) -> list[dict]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(cable_line)
                .where(
                    cable_line.c.project_id == project_id,
                    cable_line.c.lifecycle == "ACTIVE",
                )
                .order_by(cable_line.c.designation)
            ).mappings()
            return [dict(row) for row in rows]

    def list_led_products(self, project_id: str) -> list[dict]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(
                    product_definition.c.product_key,
                    product_definition.c.name,
                    passport_definition.c.passport_key,
                    product_definition.c.project_parameters_json,
                )
                .join(
                    passport_definition,
                    passport_definition.c.id == product_definition.c.passport_definition_id,
                )
                .join(
                    project,
                    project.c.active_catalog_release_id == passport_definition.c.catalog_release_id,
                )
                .where(
                    project.c.id == project_id,
                    product_definition.c.lifecycle == "ACTIVE",
                    passport_definition.c.equipment_class == "LED_TAPE_CONSTANT_VOLTAGE",
                )
                .order_by(product_definition.c.name)
            ).mappings()
            return [dict(row) for row in rows]

    def create_led_profile(
        self,
        *,
        project_id: str,
        cable_line_id: str,
        led_kind: str,
        tape_product_key: str,
        supply_scope: str,
        segments: tuple[dict[str, Any], ...],
    ) -> str:
        normalized = normalize_led_kind(led_kind)
        channels, _conductors = led_layout(normalized)
        with UnitOfWork(self._engine) as uow:
            line = uow.execute(
                select(cable_line.c.id).where(
                    cable_line.c.id == cable_line_id,
                    cable_line.c.project_id == project_id,
                    cable_line.c.lifecycle == "ACTIVE",
                )
            ).scalar_one_or_none()
            if line is None:
                raise AutomationError("Cable line not found")
            product = self._product(uow, project_id, tape_product_key)
            expected_passport = _PASSPORT_BY_KIND.get(normalized)
            if expected_passport is None:
                raise AutomationError(
                    "No approved tape product passport is available for this LED type"
                )
            if product["passport_key"] != expected_passport:
                raise AutomationError("LED kind is incompatible with the selected tape product")
            parameters = product["project_parameters_json"] or {}
            voltage = _required_decimal(parameters.get("supply_voltage_v_dc"), "voltage")
            power = _required_decimal(parameters.get("total_power_w_per_m_max"), "power per metre")
            profile_id = new_id()
            uow.execute(
                led_line_profile.insert().values(
                    id=profile_id,
                    project_id=project_id,
                    cable_line_id=cable_line_id,
                    led_kind=normalized,
                    voltage_decimal=str(voltage),
                    channels=channels,
                    power_per_m_decimal=str(power),
                    tape_product_definition_id=product["id"],
                    supply_scope=supply_scope,
                )
            )
            self._insert_segments(uow, project_id, profile_id, segments)
            self._touch_project(uow, project_id)
            uow.commit()
        return profile_id

    def replace_segments(
        self,
        *,
        project_id: str,
        profile_id: str,
        segments: tuple[dict[str, Any], ...],
    ) -> None:
        with UnitOfWork(self._engine) as uow:
            exists = uow.execute(
                select(led_line_profile.c.id).where(
                    led_line_profile.c.id == profile_id,
                    led_line_profile.c.project_id == project_id,
                )
            ).scalar_one_or_none()
            if exists is None:
                raise AutomationError("LED profile not found")
            uow.execute(
                delete(led_segment).where(
                    led_segment.c.led_line_profile_id == profile_id,
                    led_segment.c.project_id == project_id,
                )
            )
            self._insert_segments(uow, project_id, profile_id, segments)
            self._touch_project(uow, project_id)
            uow.commit()

    def replace_led_product(
        self,
        *,
        project_id: str,
        profile_id: str,
        tape_product_key: str,
    ) -> None:
        with UnitOfWork(self._engine) as uow:
            profile = (
                uow.execute(
                    select(led_line_profile).where(
                        led_line_profile.c.id == profile_id,
                        led_line_profile.c.project_id == project_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if profile is None:
                raise AutomationError("LED profile not found")
            product = self._product(uow, project_id, tape_product_key)
            expected_passport = _PASSPORT_BY_KIND.get(profile["led_kind"])
            if expected_passport is None or product["passport_key"] != expected_passport:
                raise AutomationError("LED kind is incompatible with the replacement product")
            parameters = product["project_parameters_json"] or {}
            voltage = _required_decimal(parameters.get("supply_voltage_v_dc"), "voltage")
            power = _required_decimal(parameters.get("total_power_w_per_m_max"), "power per metre")
            uow.execute(
                update(led_line_profile)
                .where(led_line_profile.c.id == profile_id)
                .values(
                    tape_product_definition_id=product["id"],
                    voltage_decimal=str(voltage),
                    power_per_m_decimal=str(power),
                    row_version=led_line_profile.c.row_version + 1,
                )
            )
            self._touch_project(uow, project_id)
            uow.commit()

    def set_profile_supply_scope(
        self,
        *,
        project_id: str,
        profile_id: str,
        supply_scope: str,
    ) -> None:
        with UnitOfWork(self._engine) as uow:
            result = uow.execute(
                update(led_line_profile)
                .where(
                    led_line_profile.c.id == profile_id,
                    led_line_profile.c.project_id == project_id,
                )
                .values(
                    supply_scope=supply_scope,
                    row_version=led_line_profile.c.row_version + 1,
                )
            )
            if result.rowcount != 1:
                raise AutomationError("LED profile not found")
            self._touch_project(uow, project_id)
            uow.commit()

    def list_led_profiles(self, project_id: str) -> list[dict]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(
                    led_line_profile,
                    cable_line.c.designation.label("cable_designation"),
                    product_definition.c.product_key,
                    product_definition.c.name.label("product_name"),
                )
                .join(cable_line, cable_line.c.id == led_line_profile.c.cable_line_id)
                .join(
                    product_definition,
                    product_definition.c.id == led_line_profile.c.tape_product_definition_id,
                )
                .where(led_line_profile.c.project_id == project_id)
                .order_by(cable_line.c.designation)
            ).mappings()
            return [dict(row) for row in rows]

    def calculate_profile(self, project_id: str, profile_id: str) -> LedProfileResult:
        with self._engine.connect() as connection:
            profile = self._profile(connection, project_id, profile_id)
            segment_rows = list(
                connection.execute(
                    select(led_segment)
                    .where(
                        led_segment.c.project_id == project_id,
                        led_segment.c.led_line_profile_id == profile_id,
                    )
                    .order_by(led_segment.c.segment_order)
                ).mappings()
            )
        parameters = profile["project_parameters_json"] or {}
        cut_increment = parameters.get("cut_increment_mm")
        reel_length = parameters.get("reel_length_mm")
        cuts = tuple(
            cut_segment(
                row["id"],
                Decimal(row["requested_length_m_decimal"]) * Decimal("1000"),
                cut_increment,
                reel_length,
            )
            for row in segment_rows
        )
        packing = pack_reels(
            cuts,
            reel_length_mm=reel_length,
            cut_increment_mm=cut_increment,
            sale_mode=parameters.get("sale_mode"),
            minimum_purchase_increment_mm=parameters.get("minimum_purchase_increment_mm"),
        )
        load = None
        if packing.status == "VERIFIED":
            load = calculate_led_load(
                led_kind=profile["led_kind"],
                cut_lengths_mm=tuple(cut.cut_length_mm for cut in cuts),
                voltage_v=profile["voltage_decimal"],
                total_power_w_per_m=profile["power_per_m_decimal"],
                channel_power_w_per_m=parameters.get("channel_power_w_per_m_max"),
            )
        return LedProfileResult(
            profile_id,
            profile["product_key"],
            profile["supply_scope"],
            cuts,
            packing,
            load,
        )

    def calculate_project_packing(self, project_id: str) -> list[dict]:
        groups: dict[tuple[str, str], dict[str, Any]] = {}
        for profile in self.list_led_profiles(project_id):
            result = self.calculate_profile(project_id, profile["id"])
            key = (result.product_key, result.supply_scope)
            group = groups.setdefault(
                key,
                {
                    "product_key": result.product_key,
                    "supply_scope": result.supply_scope,
                    "cuts": [],
                    "parameters": profile["project_parameters_json"]
                    if "project_parameters_json" in profile
                    else None,
                },
            )
            group["cuts"].extend(result.cuts)
        output = []
        for (product_key, supply_scope), group in sorted(groups.items()):
            with self._engine.connect() as connection:
                product = self._product(connection, project_id, product_key)
            parameters = product["project_parameters_json"] or {}
            packing = pack_reels(
                tuple(group["cuts"]),
                reel_length_mm=parameters.get("reel_length_mm"),
                cut_increment_mm=parameters.get("cut_increment_mm"),
                sale_mode=parameters.get("sale_mode"),
                minimum_purchase_increment_mm=parameters.get("minimum_purchase_increment_mm"),
            )
            output.append(
                {
                    "project_id": project_id,
                    "product_key": product_key,
                    "supply_scope": supply_scope,
                    "packing": packing,
                }
            )
        return output

    def assign_led_channels(
        self,
        *,
        project_id: str,
        profile_id: str,
        module_instance_id: str,
        channel_ordinals: tuple[int, ...],
        expected_project_revision: int | None = None,
    ) -> ChannelAssignmentResult:
        calculation = self.calculate_profile(project_id, profile_id)
        if calculation.load is None:
            raise AutomationError("LED channel assignment is blocked until every segment is valid")
        with self._engine.connect() as connection:
            profile = self._profile(connection, project_id, profile_id)
            module = (
                connection.execute(
                    select(
                        project_instance.c.id,
                        product_definition.c.project_parameters_json,
                    )
                    .join(
                        passport_definition,
                        passport_definition.c.id == project_instance.c.passport_definition_id,
                    )
                    .join(
                        product_definition,
                        product_definition.c.id == project_instance.c.product_definition_id,
                    )
                    .where(
                        project_instance.c.id == module_instance_id,
                        project_instance.c.project_id == project_id,
                        project_instance.c.lifecycle == "ACTIVE",
                        passport_definition.c.equipment_class == "WB_LED_V1",
                    )
                )
                .mappings()
                .one_or_none()
            )
        if module is None:
            raise AutomationError("Selected instance is not a canonical PWM module")
        parameters = module["project_parameters_json"] or {}
        status, capacity_trace = assess_pwm_capacity(
            calculation.load,
            selected_channel_count=len(channel_ordinals),
            maximum_current_a_per_channel=parameters.get("maximum_current_a_per_channel"),
            maximum_combined_current_a=parameters.get("maximum_combined_current_a"),
        )
        voltage_limit = _decimal(parameters.get("maximum_load_voltage_v_dc"))
        line_voltage = _decimal(profile["voltage_decimal"])
        voltage_ok = (
            voltage_limit is not None and line_voltage is not None and line_voltage <= voltage_limit
        )
        voltage_trace = {
            "rule": "automation.pwm_voltage",
            "result": "PASS" if voltage_ok else "INCOMPATIBLE",
            "actual": None if line_voltage is None else str(line_voltage),
            "required_max": None if voltage_limit is None else str(voltage_limit),
        }
        trace = calculation.load.trace + capacity_trace + (voltage_trace,)
        if status != "VERIFIED" or not voltage_ok:
            raise AutomationError(f"PWM assignment blocked: {trace}")
        resources = [
            row
            for row in self.constructor.list_resources(project_id)
            if row["project_instance_id"] == module_instance_id
            and row["resource_key"] == "PWM_OUTPUT"
            and row["ordinal"] in channel_ordinals
        ]
        by_ordinal = {row["ordinal"]: row for row in resources}
        if len(by_ordinal) != len(channel_ordinals) or len(set(channel_ordinals)) != len(
            channel_ordinals
        ):
            raise AutomationError("Selected PWM channels must be unique existing resources")
        resource_ids = tuple(by_ordinal[ordinal]["id"] for ordinal in channel_ordinals)
        assignment_ids = self._assign_resources(
            project_id=project_id,
            cable_line_id=profile["cable_line_id"],
            resource_ids=resource_ids,
            role_prefix="PWM_CHANNEL",
            required_directions={"OUT", "BIDIRECTIONAL"},
            expected_project_revision=expected_project_revision,
        )
        return ChannelAssignmentResult("VERIFIED", assignment_ids, trace)

    def assign_input_line(
        self,
        *,
        project_id: str,
        cable_line_id: str,
        input_resource_id: str,
        expected_project_revision: int | None = None,
    ) -> str:
        with self._engine.connect() as connection:
            system_kind = connection.scalar(
                select(cable_line.c.system_kind).where(
                    cable_line.c.id == cable_line_id,
                    cable_line.c.project_id == project_id,
                )
            )
        if system_kind == "SWITCHES":
            raise AutomationError(
                "SWITCHES inputs must be assigned per physical key, not per CableLine"
            )
        assignments = self._assign_resources(
            project_id=project_id,
            cable_line_id=cable_line_id,
            resource_ids=(input_resource_id,),
            role_prefix="FIELD_INPUT",
            required_directions={"IN", "BIDIRECTIONAL"},
            expected_project_revision=expected_project_revision,
        )
        return assignments[0]

    def assign_output_line(
        self,
        *,
        project_id: str,
        cable_line_id: str,
        output_resource_id: str,
        expected_project_revision: int | None = None,
    ) -> str:
        assignments = self._assign_resources(
            project_id=project_id,
            cable_line_id=cable_line_id,
            resource_ids=(output_resource_id,),
            role_prefix="CONTROLLED_LOAD",
            required_directions={"OUT", "BIDIRECTIONAL"},
            expected_project_revision=expected_project_revision,
        )
        return assignments[0]

    def unassign_line(self, *, project_id: str, cable_line_id: str) -> None:
        with UnitOfWork(self._engine) as uow:
            assignment_ids = tuple(
                uow.execute(
                    select(cable_line_assignment.c.id).where(
                        cable_line_assignment.c.project_id == project_id,
                        cable_line_assignment.c.cable_line_id == cable_line_id,
                    )
                ).scalars()
            )
            if assignment_ids:
                uow.execute(
                    delete(cable_line_assignment).where(
                        cable_line_assignment.c.id.in_(assignment_ids)
                    )
                )
                uow.execute(
                    delete(resource_reservation).where(
                        resource_reservation.c.owner_assignment_id.in_(assignment_ids)
                    )
                )
                self._touch_project(uow, project_id)
            uow.commit()

    def _assign_resources(
        self,
        *,
        project_id: str,
        cable_line_id: str,
        resource_ids: tuple[str, ...],
        role_prefix: str,
        required_directions: set[str],
        expected_project_revision: int | None = None,
    ) -> tuple[str, ...]:
        if not resource_ids or len(resource_ids) != len(set(resource_ids)):
            raise AutomationError("Assignment resources must be non-empty and unique")
        with UnitOfWork(self._engine) as uow:
            if expected_project_revision is not None:
                actual_revision = uow.execute(
                    select(project.c.project_revision).where(project.c.id == project_id)
                ).scalar_one_or_none()
                if actual_revision != expected_project_revision:
                    raise AutomationError(
                        "STALE_PROJECT_REVISION: preview must be rebuilt before confirmation"
                    )
            line = uow.execute(
                select(cable_line.c.id).where(
                    cable_line.c.id == cable_line_id,
                    cable_line.c.project_id == project_id,
                    cable_line.c.lifecycle == "ACTIVE",
                )
            ).scalar_one_or_none()
            rows = list(
                uow.execute(
                    select(instance_resource).where(
                        instance_resource.c.project_id == project_id,
                        instance_resource.c.id.in_(resource_ids),
                        instance_resource.c.active.is_(True),
                    )
                ).mappings()
            )
            if line is None or len(rows) != len(resource_ids):
                raise AutomationError("Cable line or assignment resource not found")
            if any(row["direction"] not in required_directions for row in rows):
                raise AutomationError("Resource direction is incompatible with the field line")
            if any(
                (row["snapshot_json"] or {}).get("passport_resource", {}).get("assignable", True)
                is False
                for row in rows
            ):
                raise AutomationError("Internal resource cannot receive a field-line assignment")
            if role_prefix == "PWM_CHANNEL" and any(
                row["resource_kind"] != "OPEN_COLLECTOR_PWM_OUTPUT" for row in rows
            ):
                raise AutomationError("PWM_CHANNEL_INCOMPATIBLE_RESOURCE_KIND")
            reserved = uow.execute(
                select(user_reserve.c.id).where(
                    user_reserve.c.project_id == project_id,
                    user_reserve.c.target_kind == "INSTANCE_RESOURCE",
                    user_reserve.c.instance_resource_id.in_(resource_ids),
                    user_reserve.c.lifecycle == "ACTIVE",
                )
            ).first()
            if reserved:
                raise AutomationError(
                    "PWM_CHANNEL_RESERVED" if role_prefix == "PWM_CHANNEL" else "RESOURCE_RESERVED"
                )
            conflict = uow.execute(
                select(cable_line_assignment.c.id)
                .join(
                    cable_topology_endpoint,
                    cable_topology_endpoint.c.id == cable_line_assignment.c.endpoint_id,
                )
                .where(
                    cable_line_assignment.c.project_id == project_id,
                    or_(
                        cable_line_assignment.c.cable_line_id == cable_line_id,
                        cable_topology_endpoint.c.instance_resource_id.in_(resource_ids),
                    ),
                )
            ).first()
            if conflict:
                raise AutomationError(
                    "PWM_CHANNEL_OCCUPIED: already assigned"
                    if role_prefix == "PWM_CHANNEL"
                    else "Cable line or exclusive resource is already assigned"
                )
            assignment_ids = []
            for index, resource_id in enumerate(resource_ids, start=1):
                assignment_id = new_id()
                reservation_id = new_id()
                role = f"{role_prefix}_{index}"
                endpoint_id = uow.execute(
                    select(cable_topology_endpoint.c.id).where(
                        cable_topology_endpoint.c.project_id == project_id,
                        cable_topology_endpoint.c.cable_line_id == cable_line_id,
                        cable_topology_endpoint.c.instance_resource_id == resource_id,
                    )
                ).scalar_one_or_none()
                if endpoint_id is None:
                    endpoint_id = new_id()
                    uow.execute(
                        cable_topology_endpoint.insert().values(
                            id=endpoint_id,
                            project_id=project_id,
                            cable_line_id=cable_line_id,
                            endpoint_kind="INSTANCE_RESOURCE",
                            instance_resource_id=resource_id,
                        )
                    )
                uow.execute(
                    resource_reservation.insert().values(
                        id=reservation_id,
                        project_id=project_id,
                        resource_id=resource_id,
                        reservation_kind="CABLE_LINE_ASSIGNMENT",
                        slot_key="EXCLUSIVE",
                        owner_assignment_kind="CABLE_LINE_ASSIGNMENT",
                        owner_assignment_id=assignment_id,
                    )
                )
                uow.execute(
                    cable_line_assignment.insert().values(
                        id=assignment_id,
                        project_id=project_id,
                        cable_line_id=cable_line_id,
                        endpoint_id=endpoint_id,
                        assignment_role=role,
                        reservation_id=reservation_id,
                    )
                )
                assignment_ids.append(assignment_id)
            self._touch_project(uow, project_id)
            uow.commit()
        return tuple(assignment_ids)

    @staticmethod
    def _insert_segments(uow, project_id, profile_id, segments) -> None:
        if not segments:
            raise AutomationError("LED profile requires at least one physical segment")
        for order, segment in enumerate(segments):
            length_mm = _required_decimal(segment.get("design_length_mm"), "design length")
            uow.execute(
                led_segment.insert().values(
                    id=segment.get("segment_id") or new_id(),
                    project_id=project_id,
                    led_line_profile_id=profile_id,
                    requested_length_m_decimal=str(length_mm / Decimal("1000")),
                    segment_order=order,
                    zone=segment.get("zone"),
                    explicit_split_json=segment.get("explicit_split") or {},
                )
            )

    @staticmethod
    def _product(connection, project_id, product_key):
        row = (
            connection.execute(
                select(
                    product_definition,
                    passport_definition.c.passport_key,
                )
                .join(
                    passport_definition,
                    passport_definition.c.id == product_definition.c.passport_definition_id,
                )
                .join(
                    project,
                    project.c.active_catalog_release_id == passport_definition.c.catalog_release_id,
                )
                .where(
                    project.c.id == project_id,
                    product_definition.c.product_key == product_key,
                    product_definition.c.lifecycle == "ACTIVE",
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise AutomationError("Product is not in the project's active canonical catalog")
        return dict(row)

    @staticmethod
    def _profile(connection, project_id, profile_id):
        row = (
            connection.execute(
                select(
                    led_line_profile,
                    product_definition.c.product_key,
                    product_definition.c.project_parameters_json,
                )
                .join(
                    product_definition,
                    product_definition.c.id == led_line_profile.c.tape_product_definition_id,
                )
                .where(
                    led_line_profile.c.id == profile_id,
                    led_line_profile.c.project_id == project_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise AutomationError("LED profile not found")
        return dict(row)

    @staticmethod
    def _touch_project(uow, project_id: str) -> None:
        uow.execute(
            update(project)
            .where(project.c.id == project_id)
            .values(
                project_revision=project.c.project_revision + 1,
                updated_at_utc=datetime.now(UTC),
            )
        )


def _decimal(value) -> Decimal | None:
    if value is None:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def _required_decimal(value, name) -> Decimal:
    result = _decimal(value)
    if result is None or result <= 0:
        raise AutomationError(f"Positive {name} is required")
    return result
