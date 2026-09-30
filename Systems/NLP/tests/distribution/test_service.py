import pytest
from sqlalchemy import select

from nl_project_2.constructor import BlockingViolation
from nl_project_2.distribution import DistributionService
from nl_project_2.persistence.database import DatabaseManager
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import cable_line, instance_resource


def _create(service, project_id, designation, passport, product):
    return service.constructor.create_instance(
        project_id=project_id,
        designation=designation,
        passport_key=passport,
        product_key=product,
        supply_scope="NEIROLINKS",
    )


def test_canonical_cross_module_contactor_psu_and_current_icl_state(database):
    project_id = database.test_project_id
    service = DistributionService(database.engine)
    cross_11 = _create(
        service,
        project_id,
        "DIST-A",
        "distribution.cross_module.3l_pen",
        "product.iek.ynd10_4_11_125",
    )
    cross_7 = _create(
        service,
        project_id,
        "DIST-B",
        "distribution.cross_module.3l_pen",
        "product.iek.ynd10_4_07_100",
    )
    contactor = _create(
        service,
        project_id,
        "CONTACTOR-X",
        "switching.modular_contactor.2no.230vac",
        "product.schneider.a9c20732",
    )
    icl = _create(
        service,
        project_id,
        "LIMITER-X",
        "protection.inrush_current_limiter.1ph",
        "product.meanwell.icl_16r",
    )
    psu_24 = _create(
        service,
        project_id,
        "PSU-24-X",
        "power.acdc.24v.din",
        "product.meanwell.hdr_60_24",
    )
    psu_48 = _create(
        service,
        project_id,
        "PSU-48-X",
        "power.acdc.48v.din",
        "product.meanwell.sdr_240_48",
    )
    with database.engine.connect() as connection:
        counts = {
            identifier: len(
                list(
                    connection.scalars(
                        select(instance_resource.c.id).where(
                            instance_resource.c.project_instance_id == identifier
                        )
                    )
                )
            )
            for identifier in (cross_11.instance_id, cross_7.instance_id)
        }
    assert counts == {cross_11.instance_id: 44, cross_7.instance_id: 28}
    resources = service.constructor.list_resources(project_id)
    contactor_keys = {
        row["resource_key"]
        for row in resources
        if row["project_instance_id"] == contactor.instance_id
    }
    assert contactor_keys == {"COIL_CONTROL", "POWER_CONTACT_IN", "POWER_CONTACT_OUT"}
    assert (
        len(
            [
                row
                for row in resources
                if row["project_instance_id"] == contactor.instance_id
                and row["resource_key"] == "POWER_CONTACT_OUT"
            ]
        )
        == 2
    )
    assert (
        service.assess_icl_instances(
            project_id=project_id,
            icl_instance_id=icl.instance_id,
            power_supply_instance_ids=(psu_24.instance_id,),
            has_distribution_node=False,
            project_conditions={
                "ambient_temperature_c": 25,
                "switching_cycles_per_minute": 1,
                "switching_interval_ms": 2000,
            },
        ).status
        == "DATA_INCOMPLETE"
    )
    assert (
        service.assess_icl_instances(
            project_id=project_id,
            icl_instance_id=None,
            power_supply_instance_ids=(),
            has_distribution_node=False,
        ).status
        == "NOT_APPLICABLE"
    )
    assert psu_48.resource_count == 2


def _resource_id(service, project_id, instance_id, resource_key, ordinal=0):
    return next(
        row["id"]
        for row in service.constructor.list_resources(project_id)
        if row["project_instance_id"] == instance_id
        and row["resource_key"] == resource_key
        and row["ordinal"] == ordinal
    )


def test_power_chain_separate_com_cable_assignment_and_reopen(database):
    project_id = database.test_project_id
    service = DistributionService(database.engine)
    breaker = _create(
        service,
        project_id,
        "QF-PSU",
        "protection.circuit_breaker.1p",
        "product.schneider.a9f84116",
    )
    com_breaker = _create(
        service,
        project_id,
        "QF-COM",
        "protection.circuit_breaker.1p",
        "product.schneider.a9f84116",
    )
    icl = _create(
        service,
        project_id,
        "ICL-PSU",
        "protection.inrush_current_limiter.1ph",
        "product.meanwell.icl_16r",
    )
    psu = _create(
        service,
        project_id,
        "PSU-24",
        "power.acdc.24v.din",
        "product.meanwell.hdr_60_24",
    )
    relay = _create(
        service,
        project_id,
        "WB-MR6C",
        "controller.wb_mr6c_v2",
        "product.wirenboard.wb_mr6c_v2",
    )
    contactor = _create(
        service,
        project_id,
        "KM-1",
        "switching.modular_contactor.2no.230vac",
        "product.schneider.a9c20732",
    )
    resources = {
        name: _resource_id(service, project_id, instance.instance_id, key, ordinal)
        for name, instance, key, ordinal in (
            ("breaker_out", breaker, "PROTECTED_OUT", 0),
            ("com_breaker_out", com_breaker, "PROTECTED_OUT", 0),
            ("icl_in", icl, "LINE_IN", 0),
            ("icl_out", icl, "LIMITED_OUT", 0),
            ("psu_in", psu, "AC_INPUT", 0),
            ("psu_out", psu, "DC24_OUTPUT", 0),
            ("relay_power", relay, "ELECTRONICS_POWER", 0),
            ("relay_com", relay, "COM", 0),
            ("contactor_power_out", contactor, "POWER_CONTACT_OUT", 0),
        )
    }
    for source, target in (
        ("breaker_out", "icl_in"),
        ("icl_out", "psu_in"),
    ):
        service.constructor.create_relation(
            project_id=project_id,
            relation_kind="POWER_FLOW",
            source_resource_id=resources[source],
            target_resource_id=resources[target],
        )
    service.constructor.create_relation(
        project_id=project_id,
        relation_kind="POWER_FLOW",
        source_resource_id=resources["psu_out"],
        target_resource_id=resources["relay_power"],
        parameters={"load": {"voltage_range_v": [9, 28], "power_w": 1, "current_a": 0.05}},
    )
    service.constructor.create_relation(
        project_id=project_id,
        relation_kind="FEED_RELAY_COMMON",
        source_resource_id=resources["com_breaker_out"],
        target_resource_id=resources["relay_com"],
    )

    assert service.assess_psu_instance(project_id, psu.instance_id).status == "VERIFIED"
    icl_result = service.assess_linked_icl(
        project_id=project_id,
        icl_instance_id=icl.instance_id,
        project_conditions={
            "ambient_temperature_c": 25,
            "switching_cycles_per_minute": 1,
            "switching_interval_ms": 2000,
        },
    )
    assert icl_result.status == "DATA_INCOMPLETE"
    assert "power_supplies[0].input_apparent_power_va" in icl_result.missing_fields
    relations = service.constructor.list_relations(project_id)
    assert len(relations) == 4
    assert {relation["target_resource_id"] for relation in relations} >= {
        resources["relay_power"],
        resources["relay_com"],
    }

    line_id = new_id()
    with database.engine.begin() as connection:
        connection.execute(
            cable_line.insert().values(
                id=line_id,
                project_id=project_id,
                designation="KM-1 / OUT-1",
                system_kind="POWER",
                cable_facts_json={"source": "CONTACTOR"},
            )
        )
    service.constructor.assign_cable_line(
        project_id=project_id,
        cable_line_id=line_id,
        output_resource_id=resources["contactor_power_out"],
    )
    assert service.constructor.list_cable_assignments(project_id)[0]["cable_line_id"] == line_id

    path = database.path
    database.close()
    reopened = DatabaseManager().open_existing(path)
    try:
        restored = DistributionService(reopened.engine)
        assert len(restored.constructor.list_relations(project_id)) == 4
        assignments = restored.constructor.list_cable_assignments(project_id)
        assert assignments[0]["cable_line_id"] == line_id
        assert restored.assess_psu_instance(project_id, psu.instance_id).status == "VERIFIED"
    finally:
        reopened.close()


def _capacity_actual(assessment):
    return next(
        item["actual"] for item in assessment.trace if item["rule"] == "distribution.psu_capacity"
    )


def test_canonical_24v_psu_direct_fanout_wb_led_delete_and_reopen(database):
    project_id = database.test_project_id
    service = DistributionService(database.engine)
    psu = _create(
        service,
        project_id,
        "PSU-24-FANOUT",
        "power.acdc.24v.din",
        "product.meanwell.hdr_60_24",
    )
    led = _create(
        service,
        project_id,
        "WB-LED-FANOUT",
        "controller.wb_led_v1",
        "product.wirenboard.wb_led_v1",
    )
    output = _resource_id(service, project_id, psu.instance_id, "DC24_OUTPUT")
    load_input = _resource_id(service, project_id, led.instance_id, "LED_LOAD_POWER")
    electronics_input = _resource_id(service, project_id, led.instance_id, "ELECTRONICS_POWER")
    load_relation = service.constructor.create_relation(
        project_id=project_id,
        relation_kind="POWER_FLOW",
        source_resource_id=output,
        target_resource_id=load_input,
        parameters={"load": {"voltage_v": 24, "power_w": 30, "current_a": 1}},
    )
    service.constructor.create_relation(
        project_id=project_id,
        relation_kind="POWER_FLOW",
        source_resource_id=output,
        target_resource_id=electronics_input,
        parameters={
            "load": {
                "voltage_range_v": [9, 28],
                "power_w": 1,
                "current_a": 0.05,
            }
        },
    )
    assessment = service.assess_psu_instance(project_id, psu.instance_id)
    assert assessment.status == "VERIFIED"
    assert _capacity_actual(assessment) == {"power_w": "31", "current_a": "1.05"}
    assert (
        len(
            [
                relation
                for relation in service.constructor.list_relations(project_id)
                if relation["source_resource_id"] == output
            ]
        )
        == 2
    )

    path = database.path
    database.close()
    reopened = DatabaseManager().open_existing(path)
    try:
        restored = DistributionService(reopened.engine)
        assert (
            len(
                [
                    relation
                    for relation in restored.constructor.list_relations(project_id)
                    if relation["source_resource_id"] == output
                ]
            )
            == 2
        )
        assert _capacity_actual(restored.assess_psu_instance(project_id, psu.instance_id)) == {
            "power_w": "31",
            "current_a": "1.05",
        }
        restored.constructor.delete_relation(
            project_id=project_id, relation_id=load_relation.relation_id
        )
        after_delete = restored.assess_psu_instance(project_id, psu.instance_id)
        assert after_delete.status == "VERIFIED"
        assert _capacity_actual(after_delete) == {
            "power_w": "1",
            "current_a": "0.05",
        }
    finally:
        reopened.close()


def test_canonical_48v_psu_fanout_aggregate_limits_and_voltage_diagnostic(database):
    project_id = database.test_project_id
    service = DistributionService(database.engine)
    psu = _create(
        service,
        project_id,
        "PSU-48-FANOUT",
        "power.acdc.48v.din",
        "product.meanwell.sdr_240_48",
    )
    consumers = [
        _create(
            service,
            project_id,
            f"WB-LED-48-{index}",
            "controller.wb_led_v1",
            "product.wirenboard.wb_led_v1",
        )
        for index in range(4)
    ]
    output = _resource_id(service, project_id, psu.instance_id, "DC48_OUTPUT")

    def connect(index, *, voltage, power, current):
        return service.constructor.create_relation(
            project_id=project_id,
            relation_kind="POWER_FLOW",
            source_resource_id=output,
            target_resource_id=_resource_id(
                service,
                project_id,
                consumers[index].instance_id,
                "LED_LOAD_POWER",
            ),
            parameters={
                "load": {
                    "voltage_v": voltage,
                    "power_w": power,
                    "current_a": current,
                }
            },
        )

    connect(0, voltage=48, power=100, current=2)
    connect(1, voltage=48, power=120, current=2.5)
    verified = service.assess_psu_instance(project_id, psu.instance_id)
    assert verified.status == "VERIFIED"
    assert _capacity_actual(verified) == {"power_w": "220", "current_a": "4.5"}

    over_limit = connect(2, voltage=48, power=30, current=0.6)
    exceeded = service.assess_psu_instance(project_id, psu.instance_id)
    assert exceeded.status == "LIMIT_EXCEEDED"
    assert _capacity_actual(exceeded) == {"power_w": "250", "current_a": "5.1"}
    service.constructor.delete_relation(project_id=project_id, relation_id=over_limit.relation_id)

    connect(3, voltage=24, power=1, current=0.1)
    incompatible = service.assess_psu_instance(project_id, psu.instance_id)
    assert incompatible.status == "INCOMPATIBLE"


def test_unrelated_distribution_only_and_exclusive_sources_stay_blocked(database):
    project_id = database.test_project_id
    service = DistributionService(database.engine)
    ups = _create(
        service,
        project_id,
        "UPS-NO-FANOUT",
        "power.wb_ups_v3",
        "product.wirenboard.wb_ups_v3",
    )
    relays = [
        _create(
            service,
            project_id,
            f"RELAY-NO-FANOUT-{index}",
            "controller.wb_mr6c_v2",
            "product.wirenboard.wb_mr6c_v2",
        )
        for index in range(2)
    ]
    ups_output = _resource_id(service, project_id, ups.instance_id, "VOUT")
    service.constructor.create_relation(
        project_id=project_id,
        relation_kind="POWER_FLOW",
        source_resource_id=ups_output,
        target_resource_id=_resource_id(
            service, project_id, relays[0].instance_id, "ELECTRONICS_POWER"
        ),
    )
    with pytest.raises(BlockingViolation, match="распределительный узел"):
        service.constructor.create_relation(
            project_id=project_id,
            relation_kind="POWER_FLOW",
            source_resource_id=ups_output,
            target_resource_id=_resource_id(
                service, project_id, relays[1].instance_id, "ELECTRONICS_POWER"
            ),
        )

    breaker = _create(
        service,
        project_id,
        "QF-EXCLUSIVE",
        "protection.circuit_breaker.1p",
        "product.schneider.a9f84116",
    )
    limiters = [
        _create(
            service,
            project_id,
            f"ICL-EXCLUSIVE-{index}",
            "protection.inrush_current_limiter.1ph",
            "product.meanwell.icl_16r",
        )
        for index in range(2)
    ]
    breaker_output = _resource_id(service, project_id, breaker.instance_id, "PROTECTED_OUT")
    service.constructor.create_relation(
        project_id=project_id,
        relation_kind="POWER_FLOW",
        source_resource_id=breaker_output,
        target_resource_id=_resource_id(service, project_id, limiters[0].instance_id, "LINE_IN"),
    )
    with pytest.raises(BlockingViolation, match="exclusive"):
        service.constructor.create_relation(
            project_id=project_id,
            relation_kind="POWER_FLOW",
            source_resource_id=breaker_output,
            target_resource_id=_resource_id(
                service, project_id, limiters[1].instance_id, "LINE_IN"
            ),
        )
