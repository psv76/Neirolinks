from __future__ import annotations

import pytest
from sqlalchemy import func, select

from nl_project_2.constructor import (
    BlockingViolation,
    ConstructorService,
    RelationDefinition,
)
from nl_project_2.distribution import DistributionService
from nl_project_2.persistence.database import DatabaseManager
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    cable_line,
    cable_line_assignment,
    functional_relation,
    instance_resource,
    passport_definition,
    passport_resource_definition,
    project,
    project_instance,
    resource_reservation,
    validation_trace,
)


def _resource(
    database,
    designation,
    direction,
    family,
    *,
    kind="SYNTHETIC_RESOURCE",
    properties=None,
    exclusive=False,
    branching="ALLOWED",
    required=False,
    group_key=None,
):
    project_id = database.test_project_id
    instance_id = new_id()
    resource_id = new_id()
    with database.engine.begin() as connection:
        passport = connection.execute(
            select(passport_definition.c.id).where(
                passport_definition.c.passport_key == "protection.circuit_breaker.1p"
            )
        ).scalar_one()
        template = connection.execute(
            select(passport_resource_definition.c.id).where(
                passport_resource_definition.c.passport_definition_id == passport,
                passport_resource_definition.c.resource_key == "LINE_IN",
            )
        ).scalar_one()
        connection.execute(
            project_instance.insert().values(
                id=instance_id,
                project_id=project_id,
                designation=designation,
                passport_definition_id=passport,
                product_definition_id=None,
                supply_scope="CUSTOMER",
                lifecycle="ACTIVE",
                parameters_json={"synthetic_test_fixture": True},
            )
        )
        connection.execute(
            instance_resource.insert().values(
                id=resource_id,
                project_id=project_id,
                project_instance_id=instance_id,
                resource_key="RESOURCE",
                ordinal=0,
                passport_resource_definition_id=template,
                resource_kind=kind,
                direction=direction,
                medium=family,
                snapshot_json={
                    "properties": {"family": family, **(properties or {})},
                    "resource_definition": {
                        "exclusive": exclusive,
                        "branching": branching,
                        "required": required,
                        "group_key": group_key,
                    },
                },
                active=True,
            )
        )
    return instance_id, resource_id


def _power(database, designation, direction, voltage=24, **kwargs):
    return _resource(
        database,
        designation,
        direction,
        "POWER",
        kind="GENERIC_POWER_RESOURCE",
        properties={
            "current_kind": "DC",
            "voltage_value": voltage,
            **kwargs.pop("properties", {}),
        },
        **kwargs,
    )


def test_relation_commit_trace_reopen_required_path_and_line_assignment(database):
    project_id = database.test_project_id
    service = ConstructorService(database.engine)
    _source_instance, source = _power(
        database,
        "GEN.SOURCE",
        "OUT",
        properties={"capacity": 100},
    )
    _target_instance, target = _power(
        database,
        "GEN.LOAD",
        "IN",
        properties={"demand": 25},
        required=True,
    )
    receipt = service.create_relation(
        project_id=project_id,
        relation_kind="POWER_FLOW",
        source_resource_id=source,
        target_resource_id=target,
    )
    assert receipt.relation_id
    assert (
        service.path_status(
            project_id=project_id,
            source_resource_id=source,
            target_resource_id=target,
        ).outcome
        == "PASS"
    )
    assert (
        service.path_status(
            project_id=project_id,
            source_resource_id=target,
            target_resource_id=source,
        ).outcome
        == "ERROR"
    )
    assert service.validate_required_resources(project_id)[0].outcome == "PASS"

    line_id = new_id()
    with database.engine.begin() as connection:
        connection.execute(
            cable_line.insert().values(
                id=line_id,
                project_id=project_id,
                designation="GENERIC-LINE",
                system_kind="SYNTHETIC",
                cable_facts_json={},
            )
        )
    assignment = service.assign_cable_line(
        project_id=project_id,
        cable_line_id=line_id,
        output_resource_id=source,
    )
    with database.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(functional_relation)) == 1
        assert connection.scalar(select(func.count()).select_from(validation_trace)) >= 8
        assert connection.scalar(select(func.count()).select_from(cable_line_assignment)) == 1
        assert connection.scalar(
            select(cable_line_assignment.c.id).where(cable_line_assignment.c.id == assignment)
        )

    path = database.path
    database.close()
    reopened = DatabaseManager().open_existing(path)
    try:
        restored = ConstructorService(reopened.engine)
        assert restored.list_relations(project_id)[0]["id"] == receipt.relation_id
        state = {row["id"]: row for row in restored.list_resources(project_id)}
        assert state[source]["used_capacity"] == "25"
        assert state[source]["remaining_capacity"] == "75"
    finally:
        reopened.close()


def test_forbidden_matrix_rolls_back_and_power_cycle_is_rejected(database):
    project_id = database.test_project_id
    service = ConstructorService(database.engine)
    _, source = _power(database, "P.A", "BIDIRECTIONAL")
    _, middle = _power(database, "P.B", "BIDIRECTIONAL")
    _, target = _power(database, "P.C", "BIDIRECTIONAL")
    service.create_relation(
        project_id=project_id,
        relation_kind="POWER_FLOW",
        source_resource_id=source,
        target_resource_id=middle,
    )
    service.create_relation(
        project_id=project_id,
        relation_kind="POWER_FLOW",
        source_resource_id=middle,
        target_resource_id=target,
    )
    with pytest.raises(BlockingViolation, match="cycle|Cycle"):
        service.create_relation(
            project_id=project_id,
            relation_kind="POWER_FLOW",
            source_resource_id=target,
            target_resource_id=source,
        )
    _, wrong_voltage = _power(database, "P.48", "IN", voltage=48)
    with pytest.raises(BlockingViolation, match="voltage"):
        service.create_relation(
            project_id=project_id,
            relation_kind="POWER_FLOW",
            source_resource_id=source,
            target_resource_id=wrong_voltage,
        )
    _, another_input = _power(database, "P.IN", "IN")
    with pytest.raises(BlockingViolation, match="output source"):
        service.create_relation(
            project_id=project_id,
            relation_kind="POWER_FLOW",
            source_resource_id=another_input,
            target_resource_id=wrong_voltage,
        )
    _, another_output = _power(database, "P.OUT", "OUT")
    with pytest.raises(BlockingViolation, match="input target"):
        service.create_relation(
            project_id=project_id,
            relation_kind="POWER_FLOW",
            source_resource_id=source,
            target_resource_id=another_output,
        )
    with pytest.raises(BlockingViolation, match="missing"):
        service.create_relation(
            project_id=project_id,
            relation_kind="POWER_FLOW",
            source_resource_id=source,
            target_resource_id=new_id(),
        )
    with database.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(functional_relation)) == 2


def test_synthetic_ac_chain_and_duplicate_instance_designation(database):
    project_id = database.test_project_id
    service = ConstructorService(database.engine)
    with pytest.raises(BlockingViolation, match="required"):
        service.create_instance(
            project_id=project_id,
            designation="  ",
            passport_key="protection.circuit_breaker.1p",
            product_key="product.schneider.a9f84116",
            supply_scope="NEIROLINKS",
        )
    _, source = _resource(
        database,
        "AC.SOURCE",
        "OUT",
        "POWER",
        kind="GENERIC_POWER_SOURCE",
        properties={"current_kind": "AC", "voltage_value": 230},
        branching="ALLOWED",
    )
    _, target = _resource(
        database,
        "AC.LOAD",
        "IN",
        "POWER",
        kind="GENERIC_POWER_LOAD",
        properties={"current_kind": "AC", "voltage_range": [220, 240]},
    )
    assert service.create_relation(
        project_id=project_id,
        relation_kind="POWER_FLOW",
        source_resource_id=source,
        target_resource_id=target,
    ).relation_id

    service.create_instance(
        project_id=project_id,
        designation="DUPLICATE",
        passport_key="protection.circuit_breaker.1p",
        product_key="product.schneider.a9f84116",
        supply_scope="NEIROLINKS",
    )
    with pytest.raises(BlockingViolation, match="unique"):
        service.create_instance(
            project_id=project_id,
            designation="DUPLICATE",
            passport_key="protection.circuit_breaker.1p",
            product_key="product.schneider.a9f84116",
            supply_scope="NEIROLINKS",
        )


def test_constructor_queries_and_preview_do_not_write(database):
    project_id = database.test_project_id
    service = ConstructorService(database.engine)
    _, source = _power(database, "READ.SOURCE", "OUT")
    _, target = _power(database, "READ.TARGET", "IN")
    with database.engine.connect() as connection:
        before = connection.scalar(
            select(project.c.project_revision).where(project.c.id == project_id)
        )
    assert service.list_instances(project_id)
    assert service.list_resources(project_id)
    assert service.list_relations(project_id) == []
    assert service.preview_relation(
        project_id=project_id,
        relation_kind="POWER_FLOW",
        source_resource_id=source,
        target_resource_id=target,
    ).allowed
    with database.engine.connect() as connection:
        after = connection.scalar(
            select(project.c.project_revision).where(project.c.id == project_id)
        )
        assert connection.scalar(select(func.count()).select_from(validation_trace)) == 0
    assert after == before


def test_exclusive_branch_capacity_address_and_draft_incomplete(database):
    project_id = database.test_project_id
    definitions = {
        "GENERIC": RelationDefinition(
            "GENERIC",
            "SIGNAL",
            check_current_kind=False,
            check_voltage=False,
            check_signal=False,
        )
    }
    service = ConstructorService(database.engine, definitions)
    _, source = _resource(
        database,
        "SIG.SOURCE",
        "OUT",
        "SIGNAL",
        properties={"capacity": 2},
        branching="ALLOWED",
        group_key="SHARED-COM",
    )
    _, first = _resource(
        database,
        "SIG.TARGET.1",
        "IN",
        "SIGNAL",
        properties={"demand": 1},
        exclusive=True,
    )
    _, second = _resource(
        database,
        "SIG.TARGET.2",
        "IN",
        "SIGNAL",
        properties={"demand": 1},
        required=True,
    )
    service.create_relation(
        project_id=project_id,
        relation_kind="GENERIC",
        source_resource_id=source,
        target_resource_id=first,
        parameters={"address": "7"},
    )
    with pytest.raises(BlockingViolation, match="exclusive"):
        service.create_relation(
            project_id=project_id,
            relation_kind="GENERIC",
            source_resource_id=source,
            target_resource_id=first,
        )
    with pytest.raises(BlockingViolation, match="Duplicate"):
        service.create_relation(
            project_id=project_id,
            relation_kind="GENERIC",
            source_resource_id=source,
            target_resource_id=second,
            parameters={"address": "7"},
        )
    receipt = service.create_relation(
        project_id=project_id,
        relation_kind="GENERIC",
        source_resource_id=source,
        target_resource_id=second,
        parameters={"address": "8", "slot_key": "PORT-2"},
    )
    _, too_much = _resource(
        database,
        "SIG.TARGET.3",
        "IN",
        "SIGNAL",
        properties={"demand": 1},
    )
    with pytest.raises(BlockingViolation, match="capacity"):
        service.create_relation(
            project_id=project_id,
            relation_kind="GENERIC",
            source_resource_id=source,
            target_resource_id=too_much,
        )
    service.delete_relation(project_id=project_id, relation_id=receipt.relation_id)
    required = service.validate_required_resources(project_id)
    assert any(item.outcome == "ERROR" and not item.blocking for item in required)


def test_control_analog_bus_definitions_and_confirmed_delete(database):
    project_id = database.test_project_id
    analog_definition = RelationDefinition(
        "VOLTAGE_ANALOG",
        "ANALOG",
        check_current_kind=False,
        check_voltage=False,
        check_capacity=False,
    )
    definitions = {
        "CONTROL": RelationDefinition("CONTROL", "CONTROL"),
        "VOLTAGE_ANALOG": analog_definition,
        "BUS_LINK": RelationDefinition(
            "BUS_LINK", "BUS", check_current_kind=False, check_voltage=False
        ),
        "INTERFACE": RelationDefinition(
            "INTERFACE", "INTERFACE", check_current_kind=False, check_voltage=False
        ),
    }
    service = ConstructorService(database.engine, definitions)
    cases = (
        (
            "CONTROL",
            "CONTROL",
            {"current_kind": "AC", "voltage_value": 230, "signal_type": "DISCRETE"},
        ),
        (
            "VOLTAGE_ANALOG",
            "ANALOG",
            {
                "signal_type": "VOLTAGE",
                "signal_range": {"min": 0, "max": 10, "unit": "V"},
            },
        ),
        (
            "VOLTAGE_ANALOG",
            "ANALOG",
            {
                "signal_type": "CURRENT",
                "signal_range": {"min": 4, "max": 20, "unit": "mA"},
            },
        ),
        ("BUS_LINK", "BUS", {"signal_type": "RS485"}),
        ("INTERFACE", "INTERFACE", {"signal_type": "ONE_TO_ONE"}),
    )
    created = []
    deleted_instance = None
    for index, (kind, family, properties) in enumerate(cases):
        source_instance, source = _resource(
            database,
            f"GEN.S{index}",
            "OUT" if family != "BUS" else "BIDIRECTIONAL",
            family,
            properties=properties,
            branching="ALLOWED",
        )
        target_instance, target = _resource(
            database,
            f"GEN.T{index}",
            "IN" if family != "BUS" else "BIDIRECTIONAL",
            family,
            properties=properties,
        )
        created.append(
            service.create_relation(
                project_id=project_id,
                relation_kind=kind,
                source_resource_id=source,
                target_resource_id=target,
            ).relation_id
        )
        if index == 1:
            deleted_instance = target_instance
    assert len(created) == 5
    assert not service.delete_instance(
        project_id=project_id, instance_id=deleted_instance, confirmed=False
    )
    assert len(service.list_relations(project_id)) == 5
    assert service.delete_instance(
        project_id=project_id, instance_id=deleted_instance, confirmed=True
    )
    assert len(service.list_relations(project_id)) == 4
    with database.engine.connect() as connection:
        assert (
            connection.scalar(
                select(func.count())
                .select_from(resource_reservation)
                .where(resource_reservation.c.owner_relation_id == created[1])
            )
            == 0
        )
        assert (
            connection.scalar(
                select(func.count())
                .select_from(instance_resource)
                .where(instance_resource.c.project_instance_id == deleted_instance)
            )
            == 0
        )
        assert (
            connection.scalar(
                select(func.count())
                .select_from(project_instance)
                .where(project_instance.c.id == deleted_instance)
            )
            == 0
        )


def _canonical_instance(service, project_id, designation, passport, product):
    return service.create_instance(
        project_id=project_id,
        designation=designation,
        passport_key=passport,
        product_key=product,
        supply_scope="NEIROLINKS",
    )


def _canonical_resource(service, project_id, instance_id, key, ordinal=0):
    return next(
        row
        for row in service.list_resources(project_id)
        if row["project_instance_id"] == instance_id
        and row["resource_key"] == key
        and row["ordinal"] == ordinal
    )


def test_product_defined_groups_are_materialized_and_readable_without_snapshot_cache(database):
    project_id = database.test_project_id
    service = ConstructorService(database.engine)
    xt = _canonical_instance(
        service,
        project_id,
        "GEN.XT",
        "distribution.cross_module.3l_pen",
        "product.iek.ynd10_4_11_125",
    )
    resources = [
        row
        for row in service.list_resources(project_id)
        if row["project_instance_id"] == xt.instance_id
    ]
    groups = {}
    for row in resources:
        groups.setdefault(row["group_key"], []).append(row)
        runtime = row["snapshot_json"]["resource_definition"]
        assert runtime["group_key"] == row["group_key"]
        assert runtime["point_ordinal"] == row["ordinal"] % 11
    assert {key: len(value) for key, value in groups.items()} == {
        "BUS_CONNECTION_POINT:GROUP:1": 11,
        "BUS_CONNECTION_POINT:GROUP:2": 11,
        "BUS_CONNECTION_POINT:GROUP:3": 11,
        "BUS_CONNECTION_POINT:GROUP:4": 11,
    }

    # Existing project rows from the previous runtime remain readable after upgrade.
    with database.engine.begin() as connection:
        for row in resources:
            snapshot = dict(row["snapshot_json"])
            snapshot.pop("resource_definition", None)
            connection.execute(
                instance_resource.update()
                .where(instance_resource.c.id == row["id"])
                .values(snapshot_json=snapshot)
            )
    restored_groups = {
        row["group_key"]
        for row in service.list_resources(project_id)
        if row["project_instance_id"] == xt.instance_id
    }
    assert restored_groups == set(groups)


@pytest.mark.parametrize(
    ("relay_designation", "contactor_designation"),
    (
        ("GEN.RELAY", "GEN.KM"),
        ("UNRELATED.MODULE", "UNRELATED.CONTACTOR"),
    ),
)
def test_full_trace_keeps_external_internal_and_cable_edges_distinct(
    database, relay_designation, contactor_designation
):
    project_id = database.test_project_id
    service = DistributionService(database.engine).constructor
    qf = _canonical_instance(
        service,
        project_id,
        "GEN.QF",
        "protection.circuit_breaker.1p",
        "product.schneider.a9f84116",
    )
    qf_control = _canonical_instance(
        service,
        project_id,
        "GEN.QF.CONTROL",
        "protection.circuit_breaker.1p",
        "product.schneider.a9f84106",
    )
    xt = _canonical_instance(
        service,
        project_id,
        "GEN.XT",
        "distribution.cross_module.3l_pen",
        "product.iek.ynd10_4_11_125",
    )
    qfd = _canonical_instance(
        service,
        project_id,
        "GEN.QFD",
        "protection.rcbo.1pn",
        "product.schneider.a9d11816",
    )
    km = _canonical_instance(
        service,
        project_id,
        contactor_designation,
        "switching.modular_contactor.2no.230vac",
        "product.schneider.a9c20732",
    )
    relay = _canonical_instance(
        service,
        project_id,
        relay_designation,
        "controller.wb_mr6c_v2",
        "product.wirenboard.wb_mr6c_v2",
    )
    psu = _canonical_instance(
        service,
        project_id,
        "GEN.PSU",
        "power.acdc.24v.din",
        "product.meanwell.hdr_60_24",
    )

    def resource(instance, key, ordinal=0):
        return _canonical_resource(service, project_id, instance.instance_id, key, ordinal)["id"]

    service.create_relation(
        project_id=project_id,
        relation_kind="POWER_FLOW",
        source_resource_id=resource(qf, "PROTECTED_OUT"),
        target_resource_id=resource(xt, "BUS_CONNECTION_POINT", 0),
    )
    service.create_relation(
        project_id=project_id,
        relation_kind="POWER_FLOW",
        source_resource_id=resource(xt, "BUS_CONNECTION_POINT", 1),
        target_resource_id=resource(qfd, "LINE_IN"),
    )
    service.create_relation(
        project_id=project_id,
        relation_kind="POWER_FLOW",
        source_resource_id=resource(qfd, "PROTECTED_LINE_OUT"),
        target_resource_id=resource(km, "POWER_CONTACT_IN", 0),
    )
    service.create_relation(
        project_id=project_id,
        relation_kind="FEED_RELAY_COMMON",
        source_resource_id=resource(qf_control, "PROTECTED_OUT"),
        target_resource_id=resource(relay, "COM", 0),
    )
    service.create_relation(
        project_id=project_id,
        relation_kind="CONTROL",
        source_resource_id=resource(relay, "RELAY_OUTPUT", 0),
        target_resource_id=resource(km, "COIL_CONTROL"),
    )
    line_id = new_id()
    with database.engine.begin() as connection:
        connection.execute(
            cable_line.insert().values(
                id=line_id,
                project_id=project_id,
                designation="GEN.AC.LOAD",
                system_kind="POWER",
                cable_facts_json={},
            )
        )
    assignment_id = service.assign_cable_line(
        project_id=project_id,
        cable_line_id=line_id,
        output_resource_id=resource(km, "POWER_CONTACT_OUT", 0),
    )

    incomplete = service.trace_cable_assignment(project_id=project_id, assignment_id=assignment_id)
    assert incomplete.status == "INCOMPLETE"
    assert any(
        step.behavior == "CONTROLLED"
        and step.status == "INCOMPLETE"
        and "ELECTRONICS_POWER" in step.message
        for step in incomplete.steps
    )
    with database.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(functional_relation)) == 5
        assert connection.scalar(select(func.count()).select_from(cable_line_assignment)) == 1

    service.create_relation(
        project_id=project_id,
        relation_kind="POWER_FLOW",
        source_resource_id=resource(psu, "DC24_OUTPUT"),
        target_resource_id=resource(relay, "ELECTRONICS_POWER"),
    )
    trace = service.trace_cable_assignment(project_id=project_id, assignment_id=assignment_id)
    assert trace.status == "VERIFIED"
    assert trace.source_resource_id == resource(qf, "LINE_IN")
    assert [step.edge_kind for step in trace.steps].count("FUNCTIONAL_RELATION") == 3
    assert trace.steps[-1].edge_kind == "CABLE_LINE_ASSIGNMENT"
    assert {step.behavior for step in trace.steps if step.edge_kind == "INTERNAL"} >= {
        "PASS_THROUGH",
        "DISTRIBUTION",
        "CONTROLLED",
    }
    assert any(step.behavior == "CONTROLLED" and step.status == "VERIFIED" for step in trace.steps)
    with database.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(functional_relation)) == 6
        assert connection.scalar(select(func.count()).select_from(cable_line_assignment)) == 1

    path = database.path
    database.close()
    reopened = DatabaseManager().open_existing(path)
    try:
        restored = DistributionService(reopened.engine).constructor.trace_cable_assignment(
            project_id=project_id, assignment_id=assignment_id
        )
        assert restored == trace
    finally:
        reopened.close()


def test_definition_only_0_10v_relation_validates_traces_and_reopens(database):
    project_id = database.test_project_id
    kind = "SYNTHETIC_VOLTAGE_RANGE"
    definitions = {
        kind: RelationDefinition(
            kind,
            "ANALOG",
            check_current_kind=False,
            check_voltage=False,
            check_capacity=False,
        )
    }
    service = ConstructorService(database.engine, definitions)
    _, source = _resource(
        database,
        "SYN.AO",
        "OUT",
        "ANALOG",
        kind="SYNTHETIC_ANALOG_OUTPUT",
        properties={
            "signal_type": "VOLTAGE",
            "signal_range": {"min": 0, "max": 10, "unit": "V"},
        },
    )
    _, compatible = _resource(
        database,
        "SYN.AI.10",
        "IN",
        "ANALOG",
        kind="SYNTHETIC_ANALOG_INPUT",
        properties={
            "signal_type": "VOLTAGE",
            "signal_range": {"min": 0, "max": 10, "unit": "V"},
        },
    )
    _, incompatible = _resource(
        database,
        "SYN.AI.5",
        "IN",
        "ANALOG",
        kind="SYNTHETIC_ANALOG_INPUT",
        properties={
            "signal_type": "VOLTAGE",
            "signal_range": {"min": 0, "max": 5, "unit": "V"},
        },
    )
    preview = service.preview_relation(
        project_id=project_id,
        relation_kind=kind,
        source_resource_id=source,
        target_resource_id=compatible,
    )
    assert preview.allowed
    assert any(item.rule_id == "constructor.signal_range" for item in preview.results)
    with pytest.raises(BlockingViolation, match="signal"):
        service.create_relation(
            project_id=project_id,
            relation_kind=kind,
            source_resource_id=source,
            target_resource_id=incompatible,
        )
    receipt = service.create_relation(
        project_id=project_id,
        relation_kind=kind,
        source_resource_id=source,
        target_resource_id=compatible,
    )
    assert all(result.rule_version == 1 for result in receipt.trace)

    path = database.path
    database.close()
    reopened = DatabaseManager().open_existing(path)
    try:
        restored = ConstructorService(reopened.engine, definitions)
        assert restored.list_relations(project_id)[0]["relation_kind"] == kind
        assert "synthetic_voltage" not in {column.name for column in functional_relation.columns}
    finally:
        reopened.close()
