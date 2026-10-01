"""Read models and application orchestration for power distribution."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Engine, select

from nl_project_2.constructor import (
    ConstructorService,
    RelationDefinition,
    default_relation_definitions,
)
from nl_project_2.persistence.schema import (
    functional_relation,
    passport_definition,
    product_definition,
    project_instance,
)

from .domain import Assessment, assess_distribution_node, assess_icl, assess_psu_load


def distribution_relation_definitions():
    definitions = default_relation_definitions()
    definitions.update(
        {
            "FEED_RELAY_COMMON": RelationDefinition(
                "FEED_RELAY_COMMON",
                "POWER",
                source_families=frozenset({"POWER"}),
                target_families=frozenset({"CONTROL"}),
                check_signal=False,
            ),
            "CONTROLLED_OUTPUT": RelationDefinition("CONTROLLED_OUTPUT", "CONTROL"),
        }
    )
    return definitions


class DistributionService:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self.constructor = ConstructorService(engine, distribution_relation_definitions())

    def list_instances(self, project_id: str) -> list[dict]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(
                    project_instance,
                    passport_definition.c.passport_key,
                    passport_definition.c.name.label("passport_name"),
                    passport_definition.c.equipment_class,
                    passport_definition.c.functional_role,
                    product_definition.c.product_key,
                    product_definition.c.name.label("product_name"),
                    product_definition.c.project_parameters_json,
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

    def distribution_resources(self, project_id: str) -> list[dict]:
        power_tokens = (
            "POWER",
            "LINE",
            "NEUTRAL",
            "BUSBAR",
            "RELAY",
            "VOUT",
            "VIN",
        )
        return [
            row
            for row in self.constructor.list_resources(project_id)
            if any(token in row["resource_kind"].upper() for token in power_tokens)
        ]

    def assess_psu_instance(self, project_id: str, instance_id: str) -> Assessment:
        instance = self._instance(instance_id, project_id)
        params = instance["project_parameters_json"] or {}
        output_resources = [
            row
            for row in self.constructor.list_resources(project_id)
            if row["project_instance_id"] == instance_id
            and row["direction"] in {"OUT", "BIDIRECTIONAL"}
            and "POWER" in row["resource_kind"]
        ]
        output_ids = {row["id"] for row in output_resources}
        consumers = []
        with self._engine.connect() as connection:
            relations = connection.execute(
                select(functional_relation.c.parameters_json).where(
                    functional_relation.c.project_id == project_id,
                    functional_relation.c.source_resource_id.in_(output_ids),
                )
            ).scalars()
            for relation_parameters in relations:
                values = dict(relation_parameters or {})
                load = dict(values.get("load") or values)
                consumers.append(load)
        return assess_psu_load(
            output_voltage_v=params.get("output_voltage_v_dc"),
            rated_power_w=params.get("rated_output_power_w"),
            rated_current_a=params.get("rated_output_current_a"),
            consumers=tuple(consumers),
        )

    def assess_cross_module_instance(self, project_id: str, instance_id: str) -> Assessment:
        instance = self._instance(instance_id, project_id)
        params = instance["project_parameters_json"] or {}
        resources = [
            row
            for row in self.constructor.list_resources(project_id)
            if row["project_instance_id"] == instance_id
        ]
        roles = []
        currents = []
        sections = []
        resource_ids = {row["id"] for row in resources}
        with self._engine.connect() as connection:
            for relation in connection.execute(
                select(functional_relation).where(
                    functional_relation.c.project_id == project_id,
                    (
                        functional_relation.c.source_resource_id.in_(resource_ids)
                        | functional_relation.c.target_resource_id.in_(resource_ids)
                    ),
                )
            ).mappings():
                relation_params = relation["parameters_json"] or {}
                roles.append(relation_params.get("distribution_role"))
                if relation_params.get("current_a") is not None:
                    currents.append(relation_params["current_a"])
                if relation_params.get("conductor_section_mm2") is not None:
                    sections.append(relation_params["conductor_section_mm2"])
        section_data = params.get("conductor_section_mm2") or {}
        return assess_distribution_node(
            available_points=len(resources),
            used_points=sum(row["assignment_count"] > 0 for row in resources),
            rated_current_a=params.get("rated_current_a"),
            total_current_a=(
                sum((Decimal(str(value)) for value in currents), Decimal("0")) if currents else None
            ),
            allowed_section_range_mm2=section_data.get("general_connected_range"),
            conductor_sections_mm2=tuple(sections),
            required_bus_configuration=params.get("bus_configuration", ""),
            actual_bus_configuration=params.get("bus_configuration", ""),
            source_count=roles.count("SOURCE"),
        )

    def assess_icl_instances(
        self,
        *,
        project_id: str,
        icl_instance_id: str | None,
        power_supply_instance_ids: tuple[str, ...],
        has_distribution_node: bool,
        project_conditions: dict | None = None,
    ) -> Assessment:
        if icl_instance_id is None:
            return assess_icl(
                icl=None,
                power_supplies=(),
                has_distribution_node=has_distribution_node,
            )
        icl = self._instance(icl_instance_id, project_id)["project_parameters_json"] or {}
        power_supplies = tuple(
            {
                "current_kind": "AC",
                **(self._instance(identifier, project_id)["project_parameters_json"] or {}),
            }
            for identifier in power_supply_instance_ids
        )
        conditions = dict(project_conditions or {})
        return assess_icl(
            icl=icl,
            power_supplies=power_supplies,
            has_distribution_node=has_distribution_node,
            **conditions,
        )

    def assess_linked_icl(
        self,
        *,
        project_id: str,
        icl_instance_id: str,
        project_conditions: dict | None = None,
    ) -> Assessment:
        resources = self.constructor.list_resources(project_id)
        resource_instance = {row["id"]: row["project_instance_id"] for row in resources}
        by_instance: dict[str, set[str]] = {}
        for row in resources:
            by_instance.setdefault(row["project_instance_id"], set()).add(row["id"])
        instances = {row["id"]: row for row in self.list_instances(project_id)}
        relations = self.constructor.list_relations(project_id)
        first_targets = {
            relation["target_resource_id"]
            for relation in relations
            if relation["source_resource_id"] in by_instance.get(icl_instance_id, set())
        }
        psu_ids = set()
        distribution_ids = set()
        for resource_id in first_targets:
            instance_id = resource_instance.get(resource_id)
            equipment_class = (instances.get(instance_id) or {}).get("equipment_class", "")
            if equipment_class.startswith("AC_DC_POWER_SUPPLY"):
                psu_ids.add(instance_id)
            elif equipment_class == "DISTRIBUTION_BLOCK":
                distribution_ids.add(instance_id)
        if distribution_ids:
            distribution_resources = set().union(
                *(by_instance.get(identifier, set()) for identifier in distribution_ids)
            )
            for relation in relations:
                if relation["source_resource_id"] not in distribution_resources:
                    continue
                instance_id = resource_instance.get(relation["target_resource_id"])
                equipment_class = (instances.get(instance_id) or {}).get("equipment_class", "")
                if equipment_class.startswith("AC_DC_POWER_SUPPLY"):
                    psu_ids.add(instance_id)
        return self.assess_icl_instances(
            project_id=project_id,
            icl_instance_id=icl_instance_id,
            power_supply_instance_ids=tuple(sorted(psu_ids)),
            has_distribution_node=bool(distribution_ids),
            project_conditions=project_conditions,
        )

    def _instance(self, instance_id: str, project_id: str) -> dict:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    select(
                        project_instance,
                        passport_definition.c.passport_key,
                        product_definition.c.product_key,
                        product_definition.c.project_parameters_json,
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
                        project_instance.c.id == instance_id,
                        project_instance.c.project_id == project_id,
                        project_instance.c.lifecycle == "ACTIVE",
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise ValueError("Distribution instance not found")
        return dict(row)
