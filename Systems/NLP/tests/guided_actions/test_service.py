from __future__ import annotations

import hashlib
from dataclasses import fields

import pytest
from sqlalchemy import func, select

from nl_project_2.catalog.equipment import EquipmentService
from nl_project_2.constructor import ConstructorService
from nl_project_2.field_model import TopologyPersistenceService
from nl_project_2.guided_actions import (
    CandidateState,
    ConfirmationRequired,
    GuidedAction,
    GuidedActionService,
    StalePreview,
)
from nl_project_2.persistence.database import DatabaseManager
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    cable_line,
    cable_line_assignment,
    field_device,
    functional_relation,
    instance_resource,
    project,
    resource_reservation,
)


def _instance(database, designation, passport, product):
    return EquipmentService(database.engine).create_instance(
        project_id=database.test_project_id,
        designation=designation,
        passport_key=passport,
        product_key=product,
        supply_scope="NEIROLINKS",
    )


def _resources(database, instance_id):
    return [
        row
        for row in ConstructorService(database.engine).list_resources(database.test_project_id)
        if row["project_instance_id"] == instance_id
    ]


def _resource(database, instance_id, key, ordinal=0):
    return next(
        row
        for row in _resources(database, instance_id)
        if row["resource_key"] == key and row["ordinal"] == ordinal
    )


def _line(database, designation, system_kind="LIGHTING_230V", facts=None):
    identifier = new_id()
    with database.engine.begin() as connection:
        connection.execute(
            cable_line.insert().values(
                id=identifier,
                project_id=database.test_project_id,
                designation=designation,
                system_kind=system_kind,
                cable_facts_json=facts or {},
            )
        )
    return identifier


def _device(database, cable_id, handle="FD1"):
    identifier = new_id()
    with database.engine.begin() as connection:
        connection.execute(
            field_device.insert().values(
                id=identifier,
                project_id=database.test_project_id,
                block_kind="WB_MRM2_MINI",
                normalized_fields_json={"CABLE_ID": cable_id},
                entity_handle=handle,
            )
        )
    return identifier


def _key(database, device_id, number, line_id):
    return TopologyPersistenceService(database.engine).create_control_key(
        project_id=database.test_project_id,
        field_device_id=device_id,
        key_tag=f"KEY_{number}",
        target_kind="CABLE_LINE",
        target_id=line_id,
        target_text="Свет в комнате",
    )


def _selectable(query, contains):
    return next(
        item for item in query.candidates if item.selectable and contains in item.target_label
    )


def _revision(database):
    with database.engine.connect() as connection:
        return connection.scalar(
            select(project.c.project_revision).where(project.c.id == database.test_project_id)
        )


def test_candidate_query_is_deterministic_read_only_and_public_dto_is_human_first(database):
    project_id = database.test_project_id
    mcm = _instance(
        database,
        "MCM8.1",
        "module.wirenboard.wb_mcm8",
        "product.wirenboard.wb_mcm8",
    )
    line = _line(database, "201", "SWITCHES", {"LOAD_NAME": "Клавиши спальни"})
    device = _device(database, "201.01")
    key = _key(database, device, 1, line)
    service = GuidedActionService(database.engine)
    before_hash = hashlib.sha256(database.path.read_bytes()).hexdigest()
    before_revision = _revision(database)

    first = service.input_candidates(project_id=project_id, field_control_key_id=key)
    second = service.input_candidates(project_id=project_id, field_control_key_id=key)

    assert first == second
    assert [item.target_label for item in first.candidates][:8] == [
        f"MCM8.1 / Input {number}" for number in range(1, 9)
    ]
    assert hashlib.sha256(database.path.read_bytes()).hexdigest() == before_hash
    assert _revision(database) == before_revision
    assert {item.name for item in fields(first.candidates[0])}.isdisjoint(
        {"resource_id", "field_port_id", "ordinal", "relation_kind", "assignment_role"}
    )
    assert all(not item.candidate_id.startswith(mcm.instance_id) for item in first.candidates)


def test_protection_and_power_candidates_reuse_constructor_rules_and_psu_branches(database):
    project_id = database.test_project_id
    breaker = _instance(
        database,
        "QF.1",
        "protection.circuit_breaker.1p",
        "product.schneider.a9f84116",
    )
    psu24 = _instance(
        database,
        "PSU.24",
        "power.acdc.24v.din",
        "product.meanwell.hdr_60_24",
    )
    _instance(
        database,
        "PSU.48",
        "power.acdc.48v.din",
        "product.meanwell.sdr_240_48",
    )
    mcm1 = _instance(
        database,
        "MCM8.1",
        "module.wirenboard.wb_mcm8",
        "product.wirenboard.wb_mcm8",
    )
    mcm2 = _instance(
        database,
        "MCM8.2",
        "module.wirenboard.wb_mcm8",
        "product.wirenboard.wb_mcm8",
    )
    target1 = _resource(database, mcm1.instance_id, "ELECTRONICS_POWER")
    target2 = _resource(database, mcm2.instance_id, "ELECTRONICS_POWER")
    service = GuidedActionService(database.engine)

    protection = service.protection_candidates(
        project_id=project_id, target_resource_id=target1["id"]
    )
    assert any(
        item.selectable and "PROTECTED_OUT" in (item.technical_identity or "")
        for item in protection.candidates
    )
    assert any(
        item.state == CandidateState.UNAVAILABLE
        and "INCOMPATIBLE_KIND_DIRECTION" in item.reason_codes
        for item in protection.candidates
    )

    power = service.power_candidates(project_id=project_id, target_resource_id=target1["id"])
    compatible = _selectable(power, "PSU.24")
    incompatible = next(item for item in power.candidates if "PSU.48" in item.target_label)
    assert "INCOMPATIBLE_VOLTAGE_SIGNAL_POWER" in incompatible.reason_codes
    preview = service.preview(
        GuidedAction.POWER, project_id, target1["id"], compatible.candidate_id
    )
    with pytest.raises(ConfirmationRequired):
        service.confirm(preview, confirmed=False)
    receipt = service.confirm(preview, confirmed=True)
    assert receipt.canonical_fact_kind == "FUNCTIONAL_RELATION"
    assert receipt.updated_state == "ASSIGNED"

    second_power = service.power_candidates(project_id=project_id, target_resource_id=target2["id"])
    assert _selectable(second_power, "PSU.24")
    second_preview = service.preview(
        GuidedAction.POWER,
        project_id,
        target2["id"],
        _selectable(second_power, "PSU.24").candidate_id,
    )
    service.confirm(second_preview, confirmed=True)
    with database.engine.connect() as connection:
        output = _resource(database, psu24.instance_id, "DC24_OUTPUT")
        assert (
            connection.scalar(
                select(func.count())
                .select_from(functional_relation)
                .where(functional_relation.c.source_resource_id == output["id"])
            )
            == 2
        )

    protected_out = _resource(database, breaker.instance_id, "PROTECTED_OUT")
    ConstructorService(database.engine).create_relation(
        project_id=project_id,
        relation_kind="POWER_FLOW",
        source_resource_id=protected_out["id"],
        target_resource_id=_resource(database, psu24.instance_id, "AC_INPUT")["id"],
    )
    occupied = service.power_candidates(project_id=project_id, target_resource_id=target2["id"])
    protected_candidate = next(item for item in occupied.candidates if "QF.1" in item.target_label)
    assert "OCCUPIED" in protected_candidate.reason_codes


def test_power_user_reserve_and_missing_voltage_are_distinct_from_occupancy(database):
    project_id = database.test_project_id
    psu = _instance(
        database,
        "PSU.1",
        "power.acdc.24v.din",
        "product.meanwell.hdr_60_24",
    )
    target_module = _instance(
        database,
        "PWM.1",
        "controller.wb_led_v1",
        "product.wirenboard.wb_led_v1",
    )
    unknown_voltage_target = _resource(database, target_module.instance_id, "LED_LOAD_POWER")
    output = _resource(database, psu.instance_id, "DC24_OUTPUT")
    incomplete = GuidedActionService(database.engine).power_candidates(
        project_id=project_id, target_resource_id=unknown_voltage_target["id"]
    )
    incomplete_candidate = next(
        item for item in incomplete.candidates if "PSU.1" in item.target_label
    )
    assert incomplete_candidate.state == CandidateState.INCOMPLETE
    assert incomplete_candidate.reason_codes == ("MISSING_OFFICIAL_OR_PROJECT_FACTS",)
    TopologyPersistenceService(database.engine).set_user_reserve(
        project_id=project_id,
        target_kind="INSTANCE_RESOURCE",
        target_id=output["id"],
        actor="test",
    )
    query = GuidedActionService(database.engine).power_candidates(
        project_id=project_id, target_resource_id=unknown_voltage_target["id"]
    )
    candidate = next(item for item in query.candidates if "PSU.1" in item.target_label)
    assert "USER_RESERVE" in candidate.reason_codes
    assert "OCCUPIED" not in candidate.reason_codes
    assert "MISSING_OFFICIAL_OR_PROJECT_FACTS" in candidate.reason_codes
    assert candidate.state == CandidateState.UNAVAILABLE


def test_ordinary_and_field_output_preview_confirm_canonical_facts_and_reopen(database):
    project_id = database.test_project_id
    _instance(
        database,
        "MR6C.1",
        "controller.wb_mr6c_v2",
        "product.wirenboard.wb_mr6c_v2",
    )
    ordinary_line = _line(database, "301", facts={"LOAD_NAME": "Свет кухни"})
    service = GuidedActionService(database.engine)
    query = service.output_candidates(project_id=project_id, cable_line_id=ordinary_line)
    compatible = _selectable(query, "MR6C.1 / K1")
    assert any("INCOMPATIBLE_KIND_DIRECTION" in item.reason_codes for item in query.candidates)
    before_revision = _revision(database)
    preview = service.preview(
        GuidedAction.OUTPUT, project_id, ordinary_line, compatible.candidate_id
    )
    assert _revision(database) == before_revision
    assert "Линия 301 — Свет кухни" in preview.owner_label
    receipt = service.confirm(preview, confirmed=True)
    assert receipt.canonical_fact_kind == "CABLE_LINE_ASSIGNMENT"
    assert receipt.project_revision_after == before_revision + 1

    field_line = _line(database, "302")
    device = _device(database, "901.01", "MRM1")
    field = TopologyPersistenceService(database.engine)
    field.create_field_port(project_id=project_id, field_device_id=device, port_tag="K1")
    field_query = service.output_candidates(project_id=project_id, cable_line_id=field_line)
    field_candidate = _selectable(field_query, "WB_MRM2_MINI / K1")
    field_preview = service.preview(
        GuidedAction.OUTPUT, project_id, field_line, field_candidate.candidate_id
    )
    field_receipt = service.confirm(field_preview, confirmed=True)
    assert field_receipt.project_revision_after == field_receipt.project_revision_before + 1
    with database.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(cable_line_assignment)) == 2
        assert connection.scalar(select(func.count()).select_from(resource_reservation)) == 1

    path = database.path
    database.close()
    reopened = DatabaseManager().open_existing(path)
    try:
        restored = GuidedActionService(reopened.engine).output_candidates(
            project_id=project_id, cable_line_id=field_line
        )
        assert restored.status == "NO_SELECTABLE_CANDIDATES"
        assert all(not item.selectable for item in restored.candidates)
    finally:
        reopened.close()


@pytest.mark.parametrize(
    ("kind", "product", "channel_count"),
    (
        ("MONO", "product.arlight.048822", 1),
        ("CCT", "product.arlight.045179", 2),
        ("RGB", "product.arlight.046937", 3),
        ("RGBW", "product.arlight.046937", 4),
    ),
)
def test_led_bundle_candidate_and_commit_for_every_canonical_layout(
    database, kind, product, channel_count
):
    project_id = database.test_project_id
    pwm = _instance(
        database,
        "PWM.1",
        "controller.wb_led_v1",
        "product.wirenboard.wb_led_v1",
    )
    line = _line(database, f"LED-{kind}", "LED")
    automation = GuidedActionService(database.engine).automation
    automation.create_led_profile(
        project_id=project_id,
        cable_line_id=line,
        led_kind=kind,
        tape_product_key=product,
        supply_scope="NEIROLINKS",
        segments=({"design_length_mm": 1000},),
    )
    service = GuidedActionService(database.engine)
    query = service.output_candidates(project_id=project_id, cable_line_id=line)
    candidate = next(item for item in query.candidates if item.selectable)
    assert candidate.target_label.count("Channel") == channel_count
    assert candidate.instance_label == "PWM.1"
    preview = service.preview(GuidedAction.OUTPUT, project_id, line, candidate.candidate_id)
    receipt = service.confirm(preview, confirmed=True)
    assert receipt.canonical_fact_count == channel_count
    with database.engine.connect() as connection:
        assert (
            connection.scalar(
                select(func.count())
                .select_from(cable_line_assignment)
                .where(cable_line_assignment.c.cable_line_id == line)
            )
            == channel_count
        )
    assert pwm.instance_id not in candidate.target_label


def test_led_occupied_and_reserved_channels_only_disable_affected_bundles(database):
    project_id = database.test_project_id
    pwm = _instance(
        database,
        "PWM.1",
        "controller.wb_led_v1",
        "product.wirenboard.wb_led_v1",
    )
    service = GuidedActionService(database.engine)
    mono_line = _line(database, "LED-MONO", "LED")
    mono_profile = service.automation.create_led_profile(
        project_id=project_id,
        cable_line_id=mono_line,
        led_kind="MONO",
        tape_product_key="product.arlight.048822",
        supply_scope="NEIROLINKS",
        segments=({"design_length_mm": 1000},),
    )
    service.automation.assign_led_channels(
        project_id=project_id,
        profile_id=mono_profile,
        module_instance_id=pwm.instance_id,
        channel_ordinals=(0,),
    )
    channel1 = _resource(database, pwm.instance_id, "PWM_OUTPUT", 1)
    service.field_model.set_user_reserve(
        project_id=project_id,
        target_kind="INSTANCE_RESOURCE",
        target_id=channel1["id"],
        actor="test",
    )
    cct_line = _line(database, "LED-CCT", "LED")
    service.automation.create_led_profile(
        project_id=project_id,
        cable_line_id=cct_line,
        led_kind="CCT",
        tape_product_key="product.arlight.045179",
        supply_scope="NEIROLINKS",
        segments=({"design_length_mm": 1000},),
    )
    query = service.output_candidates(project_id=project_id, cable_line_id=cct_line)
    assert any("OCCUPIED" in item.reason_codes for item in query.candidates)
    assert any("USER_RESERVE" in item.reason_codes for item in query.candidates)
    free = [item for item in query.candidates if item.selectable]
    assert free
    assert all(
        "Channel1" not in item.target_label and "Channel2" not in item.target_label for item in free
    )


def test_key_inputs_are_exact_distinct_explained_and_field_port_assignable(database):
    project_id = database.test_project_id
    mcm = _instance(
        database,
        "MCM8.1",
        "module.wirenboard.wb_mcm8",
        "product.wirenboard.wb_mcm8",
    )
    line = _line(database, "201", "SWITCHES")
    device = _device(database, "201.01", "KEYS1")
    field = TopologyPersistenceService(database.engine)
    keys = [_key(database, device, number, line) for number in range(1, 5)]
    port1 = field.create_field_port(project_id=project_id, field_device_id=device, port_tag="IN_1")
    field.create_field_port(project_id=project_id, field_device_id=device, port_tag="IN_2")
    service = GuidedActionService(database.engine)

    first = service.input_candidates(project_id=project_id, field_control_key_id=keys[0])
    input1 = _selectable(first, "MCM8.1 / Input 1")
    service.confirm(
        service.preview(GuidedAction.INPUT, project_id, keys[0], input1.candidate_id),
        confirmed=True,
    )
    second = service.input_candidates(project_id=project_id, field_control_key_id=keys[1])
    assert (
        "OCCUPIED"
        in next(
            item for item in second.candidates if item.target_label == "MCM8.1 / Input 1"
        ).reason_codes
    )
    input2 = _selectable(second, "MCM8.1 / Input 2")
    service.confirm(
        service.preview(GuidedAction.INPUT, project_id, keys[1], input2.candidate_id),
        confirmed=True,
    )
    input3_resource = _resource(database, mcm.instance_id, "INPUT", 2)
    field.set_user_reserve(
        project_id=project_id,
        target_kind="INSTANCE_RESOURCE",
        target_id=input3_resource["id"],
        actor="test",
    )
    third = service.input_candidates(project_id=project_id, field_control_key_id=keys[2])
    reserved = next(item for item in third.candidates if item.target_label == "MCM8.1 / Input 3")
    assert "USER_RESERVE" in reserved.reason_codes and "OCCUPIED" not in reserved.reason_codes
    field_candidate = _selectable(third, "WB_MRM2_MINI / IN_1")
    service.confirm(
        service.preview(GuidedAction.INPUT, project_id, keys[2], field_candidate.candidate_id),
        confirmed=True,
    )
    fourth = service.input_candidates(project_id=project_id, field_control_key_id=keys[3])
    assert (
        "OCCUPIED"
        in next(
            item for item in fourth.candidates if item.technical_identity == "KEYS1:IN_1"
        ).reason_codes
    )
    model = field.control_key_read_model(project_id)
    assert len({row["input_id"] for row in model if row["status"] == "ASSIGNED"}) == 3
    assert any(row["input_id"] == port1 for row in model)


def test_stale_preview_rolls_back_and_preview_contains_no_write(database):
    project_id = database.test_project_id
    relay = _instance(
        database,
        "MR6C.1",
        "controller.wb_mr6c_v2",
        "product.wirenboard.wb_mr6c_v2",
    )
    line = _line(database, "STALE")
    service = GuidedActionService(database.engine)
    query = service.output_candidates(project_id=project_id, cable_line_id=line)
    candidate = _selectable(query, "MR6C.1 / K1")
    before_assignments = len(service.automation.list_assignments(project_id))
    preview = service.preview(GuidedAction.OUTPUT, project_id, line, candidate.candidate_id)
    assert len(service.automation.list_assignments(project_id)) == before_assignments
    unrelated = _resource(database, relay.instance_id, "RELAY_OUTPUT", 5)
    service.field_model.set_user_reserve(
        project_id=project_id,
        target_kind="INSTANCE_RESOURCE",
        target_id=unrelated["id"],
        actor="test",
    )
    with pytest.raises(StalePreview):
        service.confirm(preview, confirmed=True)
    assert len(service.automation.list_assignments(project_id)) == before_assignments
    with database.engine.connect() as connection:
        assert (
            connection.scalar(
                select(func.count())
                .select_from(cable_line_assignment)
                .where(cable_line_assignment.c.cable_line_id == line)
            )
            == 0
        )
        assert (
            connection.scalar(
                select(func.count())
                .select_from(instance_resource)
                .where(instance_resource.c.project_id == project_id)
            )
            == 17
        )
