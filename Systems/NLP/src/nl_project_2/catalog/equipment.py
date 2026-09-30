"""Equipment instances, resource materialization, and controlled product replacement."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, delete, or_, select, update

from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    functional_relation,
    instance_resource,
    passport_definition,
    passport_resource_definition,
    product_definition,
    product_selection_history,
    project,
    project_instance,
    resource_reservation,
)
from nl_project_2.persistence.uow import UnitOfWork

SUPPLY_SCOPES = {"NEIROLINKS", "CUSTOMER", "ASSEMBLY_WORKSHOP", "BY_CONTRACT"}


class EquipmentError(RuntimeError):
    pass


class IncompatibleReplacementError(EquipmentError):
    pass


@dataclass(frozen=True)
class InstanceReceipt:
    instance_id: str
    resource_count: int
    product_key: str | None


def _product_count(template: dict[str, Any], product: dict[str, Any] | None) -> int:
    display = template["display_json"] or {}
    if display.get("materialization") != "PRODUCT_DEFINED":
        return 1
    if product is None:
        raise EquipmentError("Product is required to materialize PRODUCT_DEFINED resources")
    grouping = display.get("grouping") or {}
    fields = [grouping.get("bus_count_field"), grouping.get("points_per_bus_field")]
    if not all(fields):
        raise EquipmentError("PRODUCT_DEFINED resource lacks declarative grouping fields")
    values = product["project_parameters_json"]
    try:
        count = int(values[fields[0]]) * int(values[fields[1]])
    except (KeyError, TypeError, ValueError) as exc:
        raise EquipmentError(f"Product lacks capacity fields {fields}") from exc
    if count < 1:
        raise EquipmentError("Materialized resource count must be positive")
    return count


def materialized_group_metadata(
    display: dict[str, Any],
    product_parameters: dict[str, Any],
    ordinal: int,
    resource_key: str,
) -> dict[str, Any]:
    """Derive stable product-defined group/point identity from its declared layout."""

    grouping = dict(display.get("grouping") or {})
    bus_field = grouping.get("bus_count_field")
    points_field = grouping.get("points_per_bus_field")
    if not bus_field or not points_field:
        return {}
    try:
        group_count = int(product_parameters[bus_field])
        points_per_group = int(product_parameters[points_field])
    except (KeyError, TypeError, ValueError) as exc:
        raise EquipmentError(
            "Product-defined grouping requires positive integer group and point counts"
        ) from exc
    if group_count < 1 or points_per_group < 1:
        raise EquipmentError(
            "Product-defined grouping requires positive integer group and point counts"
        )
    group_ordinal, point_ordinal = divmod(int(ordinal), points_per_group)
    if group_ordinal >= group_count:
        raise EquipmentError("Materialized ordinal is outside the declared product grouping")
    return {
        "group_key": f"{resource_key}:GROUP:{group_ordinal + 1}",
        "group_ordinal": group_ordinal,
        "point_ordinal": point_ordinal,
        "group_count": group_count,
        "points_per_group": points_per_group,
    }


def _snapshot(template: dict[str, Any], product: dict[str, Any] | None, ordinal: int) -> dict:
    product_parameters = {} if product is None else product["project_parameters_json"]
    runtime_definition = {}
    if template.get("group_key") is not None:
        runtime_definition["group_key"] = template["group_key"]
    runtime_definition.update(
        materialized_group_metadata(
            dict(template["display_json"] or {}),
            product_parameters,
            ordinal,
            template["resource_key"],
        )
    )
    return {
        "passport_resource": template["display_json"],
        "product_key": None if product is None else product["product_key"],
        "product_parameters": product_parameters,
        "materialized_ordinal": ordinal,
        "resource_definition": runtime_definition,
    }


class EquipmentService:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    @staticmethod
    def _passport(uow: UnitOfWork, project_id: str, key: str) -> dict:
        row = (
            uow.execute(
                select(passport_definition)
                .join(
                    project,
                    project.c.active_catalog_release_id == passport_definition.c.catalog_release_id,
                )
                .where(
                    project.c.id == project_id,
                    passport_definition.c.passport_key == key,
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise EquipmentError(f"Passport {key!r} is not in the project's active release")
        return dict(row)

    @staticmethod
    def _product(uow: UnitOfWork, passport_id: str, key: str | None) -> dict | None:
        if key is None:
            return None
        row = (
            uow.execute(
                select(product_definition).where(
                    product_definition.c.passport_definition_id == passport_id,
                    product_definition.c.product_key == key,
                    product_definition.c.lifecycle == "ACTIVE",
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise EquipmentError(f"Product {key!r} is not compatible with the selected passport")
        return dict(row)

    @staticmethod
    def _templates(uow: UnitOfWork, passport_id: str) -> list[dict]:
        return [
            dict(row)
            for row in uow.execute(
                select(passport_resource_definition)
                .where(passport_resource_definition.c.passport_definition_id == passport_id)
                .order_by(
                    passport_resource_definition.c.resource_key,
                    passport_resource_definition.c.ordinal,
                )
            ).mappings()
        ]

    def create_instance(
        self,
        *,
        project_id: str,
        designation: str,
        passport_key: str,
        product_key: str | None,
        supply_scope: str,
        board_id: str | None = None,
        room_id: str | None = None,
    ) -> InstanceReceipt:
        if supply_scope not in SUPPLY_SCOPES:
            raise EquipmentError(f"Unknown supply scope: {supply_scope}")
        if product_key is None and supply_scope != "CUSTOMER":
            raise EquipmentError("A product may be omitted only for CUSTOMER supply")
        with UnitOfWork(self._engine) as uow:
            passport = self._passport(uow, project_id, passport_key)
            product = self._product(uow, passport["id"], product_key)
            templates = self._templates(uow, passport["id"])
            instance_id = new_id()
            uow.execute(
                project_instance.insert().values(
                    id=instance_id,
                    project_id=project_id,
                    designation=designation,
                    board_id=board_id,
                    room_id=room_id,
                    passport_definition_id=passport["id"],
                    product_definition_id=None if product is None else product["id"],
                    supply_scope=supply_scope,
                    lifecycle="ACTIVE",
                    parameters_json={
                        "passport_key": passport_key,
                        "product_key": product_key,
                    },
                )
            )
            count = 0
            for template in templates:
                materialized = _product_count(template, product)
                # Fixed definitions are already expanded; each row materializes once.
                ordinals = (
                    range(materialized)
                    if template["display_json"].get("materialization") == "PRODUCT_DEFINED"
                    else [template["ordinal"]]
                )
                for ordinal in ordinals:
                    uow.execute(
                        instance_resource.insert().values(
                            id=new_id(),
                            project_id=project_id,
                            project_instance_id=instance_id,
                            resource_key=template["resource_key"],
                            ordinal=ordinal,
                            passport_resource_definition_id=template["id"],
                            resource_kind=template["resource_kind"],
                            direction=template["direction"],
                            medium=template["medium"],
                            snapshot_json=_snapshot(template, product, ordinal),
                            active=True,
                        )
                    )
                    count += 1
            uow.commit()
        return InstanceReceipt(instance_id, count, product_key)

    def replace_product(
        self,
        *,
        project_id: str,
        instance_id: str,
        new_product_key: str,
        actor: str,
        command_id: str | None = None,
    ) -> None:
        command_id = command_id or new_id()
        with UnitOfWork(self._engine) as uow:
            instance = (
                uow.execute(
                    select(project_instance).where(
                        project_instance.c.id == instance_id,
                        project_instance.c.project_id == project_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if instance is None:
                raise EquipmentError("Project instance not found")
            new_product = self._product(uow, instance["passport_definition_id"], new_product_key)
            assert new_product is not None
            templates = self._templates(uow, instance["passport_definition_id"])
            existing = [
                dict(row)
                for row in uow.execute(
                    select(instance_resource).where(
                        instance_resource.c.project_instance_id == instance_id
                    )
                ).mappings()
            ]
            existing_by_key = {(row["resource_key"], row["ordinal"]): row for row in existing}
            desired: dict[tuple[str, int], dict] = {}
            for template in templates:
                count = _product_count(template, new_product)
                ordinals = (
                    range(count)
                    if template["display_json"].get("materialization") == "PRODUCT_DEFINED"
                    else [template["ordinal"]]
                )
                desired.update(
                    {(template["resource_key"], ordinal): template for ordinal in ordinals}
                )
            removed = [row for key, row in existing_by_key.items() if key not in desired]
            removed_ids = [row["id"] for row in removed]
            if removed_ids:
                relation = uow.execute(
                    select(functional_relation.c.id).where(
                        or_(
                            functional_relation.c.source_resource_id.in_(removed_ids),
                            functional_relation.c.target_resource_id.in_(removed_ids),
                        )
                    )
                ).first()
                reservation = uow.execute(
                    select(resource_reservation.c.id).where(
                        resource_reservation.c.resource_id.in_(removed_ids)
                    )
                ).first()
                if relation or reservation:
                    raise IncompatibleReplacementError(
                        "New product has lower resource capacity; remove assignments first"
                    )
                uow.execute(
                    delete(instance_resource).where(instance_resource.c.id.in_(removed_ids))
                )
            for key, template in desired.items():
                current = existing_by_key.get(key)
                if current:
                    uow.execute(
                        update(instance_resource)
                        .where(instance_resource.c.id == current["id"])
                        .values(
                            snapshot_json=_snapshot(template, new_product, key[1]),
                            active=True,
                        )
                    )
                else:
                    uow.execute(
                        instance_resource.insert().values(
                            id=new_id(),
                            project_id=project_id,
                            project_instance_id=instance_id,
                            resource_key=key[0],
                            ordinal=key[1],
                            passport_resource_definition_id=template["id"],
                            resource_kind=template["resource_kind"],
                            direction=template["direction"],
                            medium=template["medium"],
                            snapshot_json=_snapshot(template, new_product, key[1]),
                            active=True,
                        )
                    )
            old_product_id = instance["product_definition_id"]
            uow.execute(
                update(project_instance)
                .where(project_instance.c.id == instance_id)
                .values(
                    product_definition_id=new_product["id"],
                    parameters_json={"product_key": new_product_key},
                    row_version=project_instance.c.row_version + 1,
                )
            )
            uow.execute(
                product_selection_history.insert().values(
                    id=new_id(),
                    project_id=project_id,
                    project_instance_id=instance_id,
                    old_product_definition_id=old_product_id,
                    new_product_definition_id=new_product["id"],
                    command_id=command_id,
                    actor=actor,
                    changed_at_utc=datetime.now(UTC),
                    compatibility_result_json={
                        "result": "SAME_PASSPORT",
                        "assignments_preserved": True,
                    },
                )
            )
            uow.commit()

    def replace_passport(
        self,
        *,
        project_id: str,
        instance_id: str,
        new_passport_key: str,
        new_product_key: str | None = None,
        actor: str = "system",
        command_id: str | None = None,
    ) -> InstanceReceipt:
        command_id = command_id or new_id()
        with UnitOfWork(self._engine) as uow:
            instance = (
                uow.execute(
                    select(project_instance).where(
                        project_instance.c.id == instance_id,
                        project_instance.c.project_id == project_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if instance is None:
                raise EquipmentError("Project instance not found")
            resources = list(
                uow.execute(
                    select(instance_resource.c.id).where(
                        instance_resource.c.project_instance_id == instance_id
                    )
                ).scalars()
            )
            relation = (
                uow.execute(
                    select(functional_relation.c.id).where(
                        or_(
                            functional_relation.c.source_resource_id.in_(resources),
                            functional_relation.c.target_resource_id.in_(resources),
                        )
                    )
                ).first()
                if resources
                else None
            )
            reservation = (
                uow.execute(
                    select(resource_reservation.c.id).where(
                        resource_reservation.c.resource_id.in_(resources)
                    )
                ).first()
                if resources
                else None
            )
            if relation or reservation:
                raise IncompatibleReplacementError(
                    "Passport replacement is blocked until incompatible assignments are removed"
                )
            new_passport = self._passport(uow, project_id, new_passport_key)
            if new_passport["id"] == instance["passport_definition_id"]:
                raise EquipmentError("Use replace_product for the same passport")
            if new_product_key is None and instance["supply_scope"] != "CUSTOMER":
                raise EquipmentError(
                    "Cross-passport replacement requires an explicit compatible product"
                )
            new_product = self._product(uow, new_passport["id"], new_product_key)
            templates = self._templates(uow, new_passport["id"])
            planned: list[tuple[dict, int]] = []
            for template in templates:
                count = _product_count(template, new_product)
                ordinals = (
                    range(count)
                    if template["display_json"].get("materialization") == "PRODUCT_DEFINED"
                    else [template["ordinal"]]
                )
                planned.extend((template, ordinal) for ordinal in ordinals)
            uow.execute(
                delete(instance_resource).where(
                    instance_resource.c.project_instance_id == instance_id
                )
            )
            uow.execute(
                update(project_instance)
                .where(project_instance.c.id == instance_id)
                .values(
                    passport_definition_id=new_passport["id"],
                    product_definition_id=None if new_product is None else new_product["id"],
                    parameters_json={
                        "passport_key": new_passport_key,
                        "product_key": new_product_key,
                    },
                    row_version=project_instance.c.row_version + 1,
                )
            )
            for template, ordinal in planned:
                uow.execute(
                    instance_resource.insert().values(
                        id=new_id(),
                        project_id=project_id,
                        project_instance_id=instance_id,
                        resource_key=template["resource_key"],
                        ordinal=ordinal,
                        passport_resource_definition_id=template["id"],
                        resource_kind=template["resource_kind"],
                        direction=template["direction"],
                        medium=template["medium"],
                        snapshot_json=_snapshot(template, new_product, ordinal),
                        active=True,
                    )
                )
            uow.execute(
                product_selection_history.insert().values(
                    id=new_id(),
                    project_id=project_id,
                    project_instance_id=instance_id,
                    old_product_definition_id=instance["product_definition_id"],
                    new_product_definition_id=None if new_product is None else new_product["id"],
                    command_id=command_id,
                    actor=actor,
                    changed_at_utc=datetime.now(UTC),
                    compatibility_result_json={
                        "result": "CROSS_PASSPORT_AFTER_ASSIGNMENT_REMOVAL",
                        "resources_rematerialized": True,
                    },
                )
            )
            uow.commit()
        return InstanceReceipt(instance_id, len(planned), new_product_key)
