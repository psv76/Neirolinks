"""Transactional application service for instances, relations and reservations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import Engine, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError

from nl_project_2.catalog.equipment import (
    EquipmentService,
    InstanceReceipt,
    materialized_group_metadata,
)
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    cable_line,
    cable_line_assignment,
    cable_topology_endpoint,
    functional_relation,
    instance_resource,
    passport_definition,
    passport_resource_definition,
    passport_rule_definition,
    product_definition,
    product_selection_history,
    project,
    project_instance,
    resource_reservation,
    validation_trace,
)
from nl_project_2.persistence.uow import UnitOfWork
from nl_project_2.resource_labels import (
    resource_display_name,
    resource_technical_identity,
    resource_user_label,
)

from .domain import (
    RelationDefinition,
    RelationPreview,
    ResourceFacts,
    RuleResult,
    default_relation_definitions,
    find_cycle,
    has_path,
    validate_relation,
)
from .trace import (
    FunctionalEdge,
    FunctionalTrace,
    FunctionalTraceStep,
    best_path,
    compile_internal_edges,
    resolve_dependency_statuses,
)


class ConstructorError(RuntimeError):
    pass


class BlockingViolation(ConstructorError):
    def __init__(self, message: str, preview: RelationPreview | None = None) -> None:
        super().__init__(message)
        self.preview = preview


@dataclass(frozen=True, slots=True)
class RelationReceipt:
    relation_id: str
    trace: tuple[RuleResult, ...]


class ConstructorService:
    def __init__(
        self,
        engine: Engine,
        definitions: dict[str, RelationDefinition] | None = None,
    ) -> None:
        self._engine = engine
        self._definitions = dict(definitions or default_relation_definitions())
        self._equipment = EquipmentService(engine)

    @property
    def relation_kinds(self) -> tuple[str, ...]:
        return tuple(sorted(self._definitions))

    def create_instance(self, **kwargs) -> InstanceReceipt:
        designation = str(kwargs.get("designation", "")).strip()
        if not designation:
            raise BlockingViolation("Project instance designation is required")
        kwargs = {**kwargs, "designation": designation}
        try:
            return self._equipment.create_instance(**kwargs)
        except IntegrityError as exc:
            raise BlockingViolation("Project instance designation must be unique") from exc

    def list_instances(self, project_id: str) -> list[dict]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(
                    project_instance,
                    passport_definition.c.passport_key.label("passport_key"),
                    passport_definition.c.name.label("passport_name"),
                    passport_definition.c.version.label("passport_version"),
                    product_definition.c.product_key.label("product_key"),
                    product_definition.c.name.label("product_name"),
                    product_definition.c.version.label("product_version"),
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
                )
                .order_by(project_instance.c.designation)
            ).mappings()
            return [dict(row) for row in rows]

    def list_available_passports(self, project_id: str) -> list[dict]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(
                    passport_definition.c.passport_key,
                    passport_definition.c.name,
                    passport_definition.c.version,
                )
                .join(
                    project,
                    project.c.active_catalog_release_id == passport_definition.c.catalog_release_id,
                )
                .where(
                    project.c.id == project_id,
                    passport_definition.c.lifecycle == "ACTIVE",
                )
                .order_by(passport_definition.c.name)
            ).mappings()
            return [dict(row) for row in rows]

    def list_compatible_products(self, project_id: str, passport_key: str) -> list[dict]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(
                    product_definition.c.product_key,
                    product_definition.c.name,
                    product_definition.c.manufacturer,
                    product_definition.c.model,
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
                    passport_definition.c.passport_key == passport_key,
                    product_definition.c.lifecycle == "ACTIVE",
                )
                .order_by(product_definition.c.name)
            ).mappings()
            return [dict(row) for row in rows]

    def list_resources(self, project_id: str) -> list[dict]:
        with self._engine.connect() as connection:
            rows = list(connection.execute(self._resource_statement(project_id)).mappings())
            reservation_counts = {
                resource_id: count
                for resource_id, count in connection.execute(
                    select(
                        resource_reservation.c.resource_id,
                        func.count(resource_reservation.c.id),
                    )
                    .where(resource_reservation.c.project_id == project_id)
                    .group_by(resource_reservation.c.resource_id)
                )
            }
            assignment_counts: dict[str, int] = {}
            for column in (
                functional_relation.c.source_resource_id,
                functional_relation.c.target_resource_id,
            ):
                for resource_id, count in connection.execute(
                    select(column, func.count(functional_relation.c.id))
                    .where(functional_relation.c.project_id == project_id)
                    .group_by(column)
                ):
                    assignment_counts[resource_id] = assignment_counts.get(resource_id, 0) + count
            for resource_id, count in connection.execute(
                select(
                    cable_topology_endpoint.c.instance_resource_id,
                    func.count(cable_line_assignment.c.id),
                )
                .join(
                    cable_topology_endpoint,
                    cable_topology_endpoint.c.id == cable_line_assignment.c.endpoint_id,
                )
                .where(cable_line_assignment.c.project_id == project_id)
                .where(cable_topology_endpoint.c.instance_resource_id.is_not(None))
                .group_by(cable_topology_endpoint.c.instance_resource_id)
            ):
                assignment_counts[resource_id] = assignment_counts.get(resource_id, 0) + count
        result = []
        for row in rows:
            row_data = dict(row)
            facts = self._facts(row)
            reservations = reservation_counts.get(facts.id, 0)
            assignments = assignment_counts.get(facts.id, 0)
            capacity = _decimal(facts.properties.get("capacity"))
            used = self._used_capacity(project_id, facts.id)
            result.append(
                {
                    **row_data,
                    "properties": facts.properties,
                    "exclusive": facts.exclusive,
                    "branching": facts.branching,
                    "assignable": facts.assignable,
                    "required": facts.required,
                    "group_key": facts.group_key,
                    "occupied": assignments > 0,
                    "assignment_count": assignments,
                    "reservation_count": reservations,
                    "used_capacity": None if used is None else str(used),
                    "remaining_capacity": (
                        None if capacity is None or used is None else str(capacity - used)
                    ),
                    "display_name": resource_display_name(row_data),
                    "user_label": resource_user_label(row_data),
                    "technical_identity": resource_technical_identity(row_data),
                }
            )
        return result

    def list_relations(self, project_id: str) -> list[dict]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(functional_relation)
                .where(functional_relation.c.project_id == project_id)
                .order_by(functional_relation.c.created_at_utc, functional_relation.c.id)
            ).mappings()
            return [dict(row) for row in rows]

    def list_cable_assignments(self, project_id: str) -> list[dict]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(
                    cable_line_assignment,
                    cable_topology_endpoint.c.instance_resource_id.label("output_resource_id"),
                    cable_line.c.designation.label("cable_designation"),
                    project_instance.c.id.label("project_instance_id"),
                    project_instance.c.designation.label("instance_designation"),
                    instance_resource.c.resource_key,
                    instance_resource.c.ordinal,
                    instance_resource.c.snapshot_json,
                    passport_resource_definition.c.display_json,
                )
                .join(cable_line, cable_line.c.id == cable_line_assignment.c.cable_line_id)
                .join(
                    cable_topology_endpoint,
                    cable_topology_endpoint.c.id == cable_line_assignment.c.endpoint_id,
                )
                .join(
                    instance_resource,
                    instance_resource.c.id == cable_topology_endpoint.c.instance_resource_id,
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
                .where(cable_line_assignment.c.project_id == project_id)
                .order_by(cable_line.c.designation)
            ).mappings()
            return [
                {
                    **dict(row),
                    "display_name": resource_display_name(row),
                    "user_label": resource_user_label(row),
                    "technical_identity": resource_technical_identity(row),
                }
                for row in rows
            ]

    def derived_internal_edges(self, project_id: str) -> tuple[FunctionalEdge, ...]:
        """Read-only typed internal apparatus paths derived from installed passport facts."""

        resources = self.list_resources(project_id)
        compatibility = self._compatibility_by_instance(project_id)
        return compile_internal_edges(resources, compatibility)

    def trace_cable_assignment(self, *, project_id: str, assignment_id: str) -> FunctionalTrace:
        """Trace an assigned cable upstream without persisting a second graph."""

        assignments = {row["id"]: row for row in self.list_cable_assignments(project_id)}
        assignment = assignments.get(assignment_id)
        if assignment is None:
            raise ConstructorError("Cable line assignment not found")
        resources = self.list_resources(project_id)
        resource_by_id = {row["id"]: row for row in resources}
        with self._engine.connect() as connection:
            relation_rows = list(
                connection.execute(
                    select(functional_relation).where(
                        functional_relation.c.project_id == project_id
                    )
                ).mappings()
            )
        external = tuple(
            FunctionalEdge(
                row["source_resource_id"],
                row["target_resource_id"],
                "FUNCTIONAL_RELATION",
                row["relation_kind"],
                "constructor.functional_relation",
                message="Сохранённая функциональная связь",
                persisted_id=row["id"],
            )
            for row in relation_rows
        )
        external, internal = resolve_dependency_statuses(
            external,
            self.derived_internal_edges(project_id),
            label_for=lambda resource_id: self._resource_label(resource_by_id.get(resource_id)),
        )
        target_resource_id = assignment["output_resource_id"]
        path = best_path(external + internal, target_resource_id)
        steps = [self._trace_step(edge, resource_by_id) for edge in path]
        cable_target_id = f"cable:{assignment['cable_line_id']}"
        steps.append(
            FunctionalTraceStep(
                target_resource_id,
                cable_target_id,
                self._resource_label(resource_by_id.get(target_resource_id)),
                f"Кабельная линия {assignment['cable_designation']}",
                "CABLE_LINE_ASSIGNMENT",
                assignment["assignment_role"],
                "VERIFIED",
                "Отдельное назначение выходного ресурса кабельной линии",
                assignment["id"],
            )
        )
        complete = bool(path)
        verified = complete and all(step.status == "VERIFIED" for step in steps)
        status = "VERIFIED" if verified else "INCOMPLETE"
        source_id = path[0].source_resource_id if path else None
        return FunctionalTrace(
            status,
            source_id,
            target_resource_id,
            assignment["cable_line_id"],
            tuple(steps),
            (
                "Непрерывная функциональная трасса подтверждена"
                if verified
                else "Трасса неполна: отсутствует upstream-путь или обязательная зависимость"
            ),
        )

    def cable_assignment_targets(
        self,
        *,
        project_id: str,
        cable_line_id: str,
        assignment_role: str = "PRIMARY_OUTPUT",
    ) -> list[dict]:
        assignments = self.list_cable_assignments(project_id)
        line_has_role = any(
            row["cable_line_id"] == cable_line_id and row["assignment_role"] == assignment_role
            for row in assignments
        )
        occupied = {
            row["output_resource_id"]
            for row in assignments
            if row["assignment_role"] == assignment_role
        }
        targets = []
        for resource in self.list_resources(project_id):
            reason = "Доступно"
            available = True
            if line_has_role:
                available, reason = False, "У линии уже есть назначение этой роли"
            elif resource["direction"] not in {"OUT", "BIDIRECTIONAL"}:
                available, reason = False, "Требуется выходной или двунаправленный ресурс"
            elif not resource["assignable"]:
                available, reason = False, "Ресурс не допускает назначение кабельной линии"
            elif resource["id"] in occupied:
                available, reason = False, "Ресурс уже занят линией этой роли"
            targets.append({**resource, "available": available, "reason": reason})
        return targets

    def preview_relation(
        self,
        *,
        project_id: str,
        relation_kind: str,
        source_resource_id: str,
        target_resource_id: str,
    ) -> RelationPreview:
        definition = self._definition(relation_kind)
        with self._engine.connect() as connection:
            return self._preview_with_connection(
                connection,
                project_id,
                definition,
                source_resource_id,
                target_resource_id,
            )

    def compatible_targets(
        self, *, project_id: str, relation_kind: str, source_resource_id: str
    ) -> list[tuple[dict, RelationPreview]]:
        targets = []
        for row in self.list_resources(project_id):
            if row["id"] == source_resource_id:
                continue
            preview = self.preview_relation(
                project_id=project_id,
                relation_kind=relation_kind,
                source_resource_id=source_resource_id,
                target_resource_id=row["id"],
            )
            targets.append((row, preview))
        return targets

    def create_relation(
        self,
        *,
        project_id: str,
        relation_kind: str,
        source_resource_id: str,
        target_resource_id: str,
        parameters: dict[str, Any] | None = None,
        command_id: str | None = None,
        expected_project_revision: int | None = None,
    ) -> RelationReceipt:
        definition = self._definition(relation_kind)
        command_id = command_id or new_id()
        parameters = dict(parameters or {})
        now = datetime.now(UTC)
        with UnitOfWork(self._engine) as uow:
            if expected_project_revision is not None:
                actual_revision = uow.execute(
                    select(project.c.project_revision).where(project.c.id == project_id)
                ).scalar_one_or_none()
                if actual_revision != expected_project_revision:
                    raise BlockingViolation(
                        "STALE_PROJECT_REVISION: preview must be rebuilt before confirmation"
                    )
            preview = self._preview_with_connection(
                uow,
                project_id,
                definition,
                source_resource_id,
                target_resource_id,
            )
            if not preview.allowed:
                raise BlockingViolation(_preview_message(preview), preview)
            cycle_result = self._cycle_result(
                uow,
                project_id,
                definition,
                source_resource_id,
                target_resource_id,
            )
            trace = preview.results + ((cycle_result,) if cycle_result else ())
            if cycle_result and cycle_result.outcome == "ERROR":
                raise BlockingViolation(cycle_result.message, preview)
            relation_id = new_id()
            try:
                uow.execute(
                    functional_relation.insert().values(
                        id=relation_id,
                        project_id=project_id,
                        relation_kind=relation_kind,
                        source_resource_id=source_resource_id,
                        target_resource_id=target_resource_id,
                        parameters_json=parameters,
                        command_id=command_id,
                    )
                )
                for resource in (preview.source, preview.target):
                    if resource.exclusive:
                        uow.execute(
                            resource_reservation.insert().values(
                                id=new_id(),
                                project_id=project_id,
                                resource_id=resource.id,
                                reservation_kind="EXCLUSIVE_RELATION",
                                slot_key="EXCLUSIVE",
                                owner_relation_id=relation_id,
                            )
                        )
                demand = _decimal(preview.target.properties.get("demand"))
                if demand is not None:
                    uow.execute(
                        resource_reservation.insert().values(
                            id=new_id(),
                            project_id=project_id,
                            resource_id=source_resource_id,
                            reservation_kind="CAPACITY",
                            slot_key=relation_id,
                            quantity_decimal=str(demand),
                            owner_relation_id=relation_id,
                        )
                    )
                address = parameters.get("address")
                slot_key = parameters.get("slot_key")
                if address is not None or slot_key is not None:
                    uow.execute(
                        resource_reservation.insert().values(
                            id=new_id(),
                            project_id=project_id,
                            resource_id=source_resource_id,
                            reservation_kind="ADDRESS_OR_SLOT",
                            slot_key=None if slot_key is None else str(slot_key),
                            address=None if address is None else str(address),
                            owner_relation_id=relation_id,
                        )
                    )
                self._save_trace(uow, project_id, command_id, trace, now)
                self._touch_project(uow, project_id, now)
                uow.commit()
            except IntegrityError as exc:
                raise BlockingViolation(
                    "Duplicate relation, address, slot or exclusive reservation"
                ) from exc
        return RelationReceipt(relation_id, trace)

    def delete_relation(self, *, project_id: str, relation_id: str) -> None:
        now = datetime.now(UTC)
        with UnitOfWork(self._engine) as uow:
            found = uow.execute(
                select(functional_relation.c.id).where(
                    functional_relation.c.id == relation_id,
                    functional_relation.c.project_id == project_id,
                )
            ).scalar_one_or_none()
            if found is None:
                raise ConstructorError("Relation not found")
            uow.execute(
                delete(resource_reservation).where(
                    resource_reservation.c.owner_relation_id == relation_id
                )
            )
            uow.execute(delete(functional_relation).where(functional_relation.c.id == relation_id))
            self._touch_project(uow, project_id, now)
            uow.commit()

    def assign_cable_line(
        self,
        *,
        project_id: str,
        cable_line_id: str,
        output_resource_id: str,
        assignment_role: str = "PRIMARY_OUTPUT",
    ) -> str:
        now = datetime.now(UTC)
        assignment_id = new_id()
        reservation_id = new_id()
        with UnitOfWork(self._engine) as uow:
            line_exists = uow.execute(
                select(cable_line.c.id).where(
                    cable_line.c.id == cable_line_id,
                    cable_line.c.project_id == project_id,
                    cable_line.c.lifecycle == "ACTIVE",
                )
            ).scalar_one_or_none()
            resource = self._load_facts(uow, project_id, output_resource_id)
            if line_exists is None:
                raise BlockingViolation("Cable line not found")
            if resource.direction not in {"OUT", "BIDIRECTIONAL"} or not resource.assignable:
                raise BlockingViolation("Cable line requires an assignable output resource")
            endpoint_id = uow.execute(
                select(cable_topology_endpoint.c.id).where(
                    cable_topology_endpoint.c.project_id == project_id,
                    cable_topology_endpoint.c.cable_line_id == cable_line_id,
                    cable_topology_endpoint.c.instance_resource_id == output_resource_id,
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
                        instance_resource_id=output_resource_id,
                    )
                )
            try:
                uow.execute(
                    resource_reservation.insert().values(
                        id=reservation_id,
                        project_id=project_id,
                        resource_id=output_resource_id,
                        reservation_kind="CABLE_LINE_ASSIGNMENT",
                        slot_key=assignment_role,
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
                        assignment_role=assignment_role,
                        reservation_id=reservation_id,
                    )
                )
                self._touch_project(uow, project_id, now)
                uow.commit()
            except IntegrityError as exc:
                raise BlockingViolation(
                    "Cable line or output resource is already assigned for this role"
                ) from exc
        return assignment_id

    def delete_cable_assignment(self, *, project_id: str, assignment_id: str) -> None:
        now = datetime.now(UTC)
        with UnitOfWork(self._engine) as uow:
            row = uow.execute(
                select(
                    cable_line_assignment.c.id,
                    cable_line_assignment.c.reservation_id,
                ).where(
                    cable_line_assignment.c.id == assignment_id,
                    cable_line_assignment.c.project_id == project_id,
                )
            ).one_or_none()
            if row is None:
                raise ConstructorError("Cable assignment not found")
            uow.execute(
                delete(cable_line_assignment).where(cable_line_assignment.c.id == assignment_id)
            )
            if row.reservation_id:
                uow.execute(
                    delete(resource_reservation).where(
                        resource_reservation.c.id == row.reservation_id
                    )
                )
            self._touch_project(uow, project_id, now)
            uow.commit()

    def validate_required_resources(self, project_id: str) -> tuple[RuleResult, ...]:
        results = []
        for resource in self.list_resources(project_id):
            if not resource["required"]:
                continue
            complete = resource["assignment_count"] > 0
            results.append(
                RuleResult(
                    "constructor.required_resource",
                    1,
                    "PASS" if complete else "ERROR",
                    False,
                    (resource["id"],),
                    resource["assignment_count"],
                    "at least one assignment",
                    "Required resource is assigned"
                    if complete
                    else "Required resource has no assignment; draft may be saved",
                )
            )
        return tuple(results)

    def path_status(
        self,
        *,
        project_id: str,
        source_resource_id: str,
        target_resource_id: str,
        relation_kinds: set[str] | None = None,
    ) -> RuleResult:
        with self._engine.connect() as connection:
            query = select(
                functional_relation.c.source_resource_id,
                functional_relation.c.target_resource_id,
            ).where(functional_relation.c.project_id == project_id)
            if relation_kinds:
                query = query.where(functional_relation.c.relation_kind.in_(relation_kinds))
            edges = tuple(connection.execute(query))
        complete = has_path(edges, source_resource_id, target_resource_id)
        return RuleResult(
            "constructor.required_path",
            1,
            "PASS" if complete else "ERROR",
            False,
            (source_resource_id, target_resource_id),
            {"path_exists": complete},
            True,
            "Required path exists" if complete else "Required path is missing; draft may be saved",
        )

    def delete_instance(self, *, project_id: str, instance_id: str, confirmed: bool) -> bool:
        if not confirmed:
            return False
        now = datetime.now(UTC)
        with UnitOfWork(self._engine) as uow:
            exists = uow.execute(
                select(project_instance.c.id).where(
                    project_instance.c.id == instance_id,
                    project_instance.c.project_id == project_id,
                    project_instance.c.lifecycle == "ACTIVE",
                )
            ).scalar_one_or_none()
            if exists is None:
                raise ConstructorError("Project instance not found")
            resource_ids = tuple(
                uow.execute(
                    select(instance_resource.c.id).where(
                        instance_resource.c.project_instance_id == instance_id
                    )
                ).scalars()
            )
            relation_ids = (
                tuple(
                    uow.execute(
                        select(functional_relation.c.id).where(
                            or_(
                                functional_relation.c.source_resource_id.in_(resource_ids),
                                functional_relation.c.target_resource_id.in_(resource_ids),
                            )
                        )
                    ).scalars()
                )
                if resource_ids
                else ()
            )
            assignment_ids = (
                tuple(
                    uow.execute(
                        select(cable_line_assignment.c.id)
                        .join(
                            cable_topology_endpoint,
                            cable_topology_endpoint.c.id == cable_line_assignment.c.endpoint_id,
                        )
                        .where(cable_topology_endpoint.c.instance_resource_id.in_(resource_ids))
                    ).scalars()
                )
                if resource_ids
                else ()
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
            if resource_ids:
                uow.execute(
                    delete(cable_topology_endpoint).where(
                        cable_topology_endpoint.c.instance_resource_id.in_(resource_ids)
                    )
                )
            if relation_ids:
                uow.execute(
                    delete(resource_reservation).where(
                        resource_reservation.c.owner_relation_id.in_(relation_ids)
                    )
                )
                uow.execute(
                    delete(functional_relation).where(functional_relation.c.id.in_(relation_ids))
                )
            if resource_ids:
                uow.execute(
                    delete(resource_reservation).where(
                        resource_reservation.c.resource_id.in_(resource_ids)
                    )
                )
            uow.execute(
                delete(product_selection_history).where(
                    product_selection_history.c.project_instance_id == instance_id
                )
            )
            uow.execute(delete(project_instance).where(project_instance.c.id == instance_id))
            self._touch_project(uow, project_id, now)
            uow.commit()
        return True

    def _definition(self, relation_kind: str) -> RelationDefinition:
        try:
            return self._definitions[relation_kind]
        except KeyError as exc:
            raise ConstructorError(f"Unknown relation kind: {relation_kind}") from exc

    def _compatibility_by_instance(self, project_id: str) -> dict[str, dict[str, Any]]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(
                    project_instance.c.id,
                    passport_rule_definition.c.parameters_json,
                )
                .join(
                    passport_rule_definition,
                    passport_rule_definition.c.passport_definition_id
                    == project_instance.c.passport_definition_id,
                )
                .where(
                    project_instance.c.project_id == project_id,
                    project_instance.c.lifecycle == "ACTIVE",
                    passport_rule_definition.c.rule_key == "compatibility",
                )
            )
            return {
                instance_id: dict((parameters or {}).get("value") or {})
                for instance_id, parameters in rows
            }

    @staticmethod
    def _trace_step(edge, resource_by_id):
        return FunctionalTraceStep(
            edge.source_resource_id,
            edge.target_resource_id,
            ConstructorService._resource_label(resource_by_id.get(edge.source_resource_id)),
            ConstructorService._resource_label(resource_by_id.get(edge.target_resource_id)),
            edge.edge_kind,
            edge.behavior,
            edge.status,
            edge.message,
            edge.persisted_id,
        )

    @staticmethod
    def _resource_label(resource):
        return resource_user_label(resource)

    def _preview_with_connection(
        self,
        connection,
        project_id,
        definition,
        source_resource_id,
        target_resource_id,
    ) -> RelationPreview:
        source = self._load_facts(connection, project_id, source_resource_id)
        target = self._load_facts(connection, project_id, target_resource_id)
        source_count = connection.execute(
            select(func.count())
            .select_from(functional_relation)
            .where(
                functional_relation.c.project_id == project_id,
                functional_relation.c.source_resource_id == source_resource_id,
            )
        ).scalar_one()
        target_count = connection.execute(
            select(func.count())
            .select_from(functional_relation)
            .where(
                functional_relation.c.project_id == project_id,
                functional_relation.c.target_resource_id == target_resource_id,
            )
        ).scalar_one()
        existing_demands = []
        rows = connection.execute(
            select(functional_relation.c.target_resource_id).where(
                functional_relation.c.project_id == project_id,
                functional_relation.c.source_resource_id == source_resource_id,
            )
        )
        for row in rows:
            demand = _decimal(
                self._load_facts(connection, project_id, row[0]).properties.get("demand")
            )
            if demand is not None:
                existing_demands.append(demand)
        return validate_relation(
            definition,
            source,
            target,
            source_relation_count=source_count,
            target_relation_count=target_count,
            existing_target_demands=tuple(existing_demands),
        )

    def _load_facts(self, connection, project_id: str, resource_id: str) -> ResourceFacts:
        row = (
            connection.execute(
                self._resource_statement(project_id).where(instance_resource.c.id == resource_id)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise BlockingViolation(
                "Resource endpoint is missing, inactive or from another project"
            )
        return self._facts(row)

    @staticmethod
    def _resource_statement(project_id: str):
        return (
            select(
                instance_resource,
                project_instance.c.designation.label("instance_designation"),
                passport_resource_definition.c.exclusive,
                passport_resource_definition.c.capacity_decimal,
                passport_resource_definition.c.group_key,
                passport_resource_definition.c.display_json,
                passport_resource_definition.c.passport_definition_id,
                passport_definition.c.passport_key,
                passport_definition.c.name.label("passport_name"),
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
            .join(
                passport_definition,
                passport_definition.c.id == passport_resource_definition.c.passport_definition_id,
            )
            .where(
                instance_resource.c.project_id == project_id,
                instance_resource.c.active.is_(True),
                project_instance.c.lifecycle == "ACTIVE",
            )
            .order_by(
                project_instance.c.designation,
                instance_resource.c.resource_key,
                instance_resource.c.ordinal,
            )
        )

    @staticmethod
    def _facts(row) -> ResourceFacts:
        snapshot = dict(row["snapshot_json"] or {})
        display = dict(row["display_json"] or snapshot.get("passport_resource") or {})
        runtime_definition = dict(snapshot.get("resource_definition") or {})
        constraints = dict(display.get("constraints") or {})
        properties = dict(snapshot.get("product_parameters") or {})
        properties.update(constraints)
        properties.update(snapshot.get("properties") or {})
        properties["ordinal"] = row["ordinal"]
        if row["capacity_decimal"] is not None:
            properties.setdefault("capacity", row["capacity_decimal"])
        properties.setdefault("capacity", properties.get("available_power_w"))
        properties.setdefault("current_kind", _current_kind(row["resource_kind"], constraints))
        if "voltage_range" not in properties and constraints.get("range_v") is not None:
            properties["voltage_range"] = constraints["range_v"]
        if "voltage_range" not in properties and constraints.get("backup_range_v") is not None:
            properties["voltage_range"] = constraints["backup_range_v"]
        for key in ("nominal_voltage_v", "voltage_v", "project_value_v"):
            if constraints.get(key) is not None:
                properties.setdefault("voltage_value", constraints[key])
        if runtime_definition.get("group_key") is None:
            runtime_definition.update(
                materialized_group_metadata(
                    display,
                    dict(snapshot.get("product_parameters") or {}),
                    row["ordinal"],
                    row["resource_key"],
                )
            )
        return ResourceFacts(
            id=row["id"],
            instance_id=row["project_instance_id"],
            key=row["resource_key"],
            kind=row["resource_kind"],
            direction=row["direction"],
            medium=row["medium"],
            properties=properties,
            exclusive=bool(runtime_definition.get("exclusive", row["exclusive"])),
            branching=runtime_definition.get("branching", display.get("branching", "FORBIDDEN")),
            assignable=bool(runtime_definition.get("assignable", display.get("assignable", True))),
            required=bool(runtime_definition.get("required", display.get("required", False))),
            group_key=runtime_definition.get("group_key", row["group_key"]),
        )

    def _cycle_result(self, connection, project_id, definition, source_id, target_id):
        if definition.family != "POWER":
            return None
        power_kinds = [kind for kind, item in self._definitions.items() if item.family == "POWER"]
        edges = tuple(
            connection.execute(
                select(
                    functional_relation.c.source_resource_id,
                    functional_relation.c.target_resource_id,
                ).where(
                    functional_relation.c.project_id == project_id,
                    functional_relation.c.relation_kind.in_(power_kinds),
                )
            )
        ) + ((source_id, target_id),)
        cycle = find_cycle(edges)
        return RuleResult(
            "constructor.power_cycle",
            definition.version,
            "PASS" if cycle is None else "ERROR",
            True,
            tuple(cycle or (source_id, target_id)),
            {"cycle": cycle},
            "acyclic power graph",
            "Power graph remains acyclic"
            if cycle is None
            else f"Power cycle is forbidden: {' -> '.join(cycle)}",
        )

    @staticmethod
    def _save_trace(uow, project_id, command_id, results, now):
        for result in results:
            uow.execute(
                validation_trace.insert().values(
                    id=new_id(),
                    project_id=project_id,
                    rule_kind=result.rule_id,
                    rule_version=result.rule_version,
                    input_entity_ids_json=list(result.entity_ids),
                    normalized_operands_json={
                        "actual": _jsonable(result.actual),
                        "required": _jsonable(result.required),
                        "message": result.message,
                        "blocking": result.blocking,
                    },
                    outcome=result.outcome,
                    command_correlation_id=command_id,
                    created_at_utc=now,
                )
            )

    def _used_capacity(self, project_id: str, resource_id: str) -> Decimal | None:
        with self._engine.connect() as connection:
            values = list(
                connection.scalars(
                    select(resource_reservation.c.quantity_decimal).where(
                        resource_reservation.c.project_id == project_id,
                        resource_reservation.c.resource_id == resource_id,
                        resource_reservation.c.reservation_kind == "CAPACITY",
                    )
                )
            )
        numbers = [_decimal(value) for value in values]
        return None if any(value is None for value in numbers) else sum(numbers, Decimal("0"))

    @staticmethod
    def _touch_project(uow, project_id: str, now: datetime) -> None:
        uow.execute(
            update(project)
            .where(project.c.id == project_id)
            .values(project_revision=project.c.project_revision + 1, updated_at_utc=now)
        )


def _preview_message(preview: RelationPreview) -> str:
    return "; ".join(
        result.message
        for result in preview.results
        if result.blocking and result.outcome == "ERROR"
    )


def _decimal(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _current_kind(resource_kind: str, constraints: dict) -> str | None:
    if constraints.get("current_kind"):
        return str(constraints["current_kind"]).upper()
    kind = resource_kind.upper()
    if kind.startswith("DC_") or "_DC_" in kind or kind in {"VOUT", "VIN"}:
        return "DC"
    if kind.startswith("AC_") or "_AC_" in kind:
        return "AC"
    return None


def _jsonable(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value
