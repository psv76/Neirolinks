from __future__ import annotations

from dataclasses import replace

import pytest
from sqlalchemy import func, select, update

from nl_project_2.cables.service import CableService
from nl_project_2.cad_contract import (
    BlockDefinitionMetadata,
    CadObservation,
    CadObservationBatch,
    load_contract,
)
from nl_project_2.cad_sync import (
    ChangeClass,
    DwgSyncError,
    DwgSyncService,
    SyncOwnerKind,
    WriteResult,
)
from nl_project_2.objects.models import ProjectCard
from nl_project_2.objects.service import ObjectService
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    cable_line,
    cable_point,
    cable_point_field_device,
    cable_segment,
    cable_topology_endpoint,
    dwg_baseline,
    dwg_scan,
    dwg_sync_operation,
    field_control_key,
    field_device,
    field_port,
    led_line_profile,
    project,
)
from nl_project_2.persistence.uow import UnitOfWork


def _observation(
    name: str,
    *,
    handle: str,
    cable_id: str | None = None,
    attributes: dict[str, object] | None = None,
    layer: str | None = None,
    x: int = 100,
    y: int = 200,
) -> CadObservation:
    contract = load_contract()
    rule = contract.block(name)
    assert rule is not None
    groups = sorted(group for group in rule.allowed_groups if group != "AV")
    group = groups[0] if groups else None
    if cable_id:
        group = next(
            (
                candidate
                for candidate in groups
                if contract.functional_groups[candidate].cable_prefix == cable_id[0]
            ),
            group,
        )
    chosen_layer = layer or (
        sorted(contract.functional_groups[group].layers)[0] if group else "DALI_GROUPS"
    )
    attrs: dict[str, object] = {tag: "" for tag in rule.required_definition_attributes}
    attrs.update(
        {"DEVICE_NAME": f"Fixture {name}", "BUILDING": "B1", "ROOM": "R1", "MOUNT_HEIGHT": "300"}
    )
    if "CABLE_ID" in attrs:
        assert group is not None
        attrs["CABLE_ID"] = cable_id or f"{contract.functional_groups[group].cable_prefix}01"
    for tag, value in {
        "CABLE_TYPE": "TEST CABLE",
        "BOARD": "B.01",
        "MOUNT_WAY": "По потолку",
        "LOAD_NAME": "Load",
    }.items():
        if tag in attrs:
            attrs[tag] = value
    if "LOAD_TYPE" in attrs and rule.allowed_load_types:
        attrs["LOAD_TYPE"] = sorted(rule.allowed_load_types)[0]
    if "LED_TYPE" in attrs:
        attrs["LED_TYPE"] = "MONO"
    if "BUS_POINT_ID" in attrs:
        attrs["BUS_POINT_ID"] = "901.001"
    if "BUS_SOURCE" in attrs:
        attrs["BUS_SOURCE"] = "901.000"
    if "BUS_CABLE_TYPE" in attrs:
        attrs["BUS_CABLE_TYPE"] = "BUS CABLE"
    if "BUS_MOUNT_WAY" in attrs:
        attrs["BUS_MOUNT_WAY"] = "По потолку"
    if "BOX_ID" in attrs:
        attrs["BOX_ID"] = "BOX.001"
    for index in range(1, rule.key_count + 1):
        attrs[f"KEY_{index}"] = "301"
    for tag in rule.required_definition_attributes:
        attrs.setdefault(tag, "")
    if attributes:
        attrs.update(attributes)
    return CadObservation.from_mapping(
        effective_name=name,
        layer=chosen_layer,
        raw_attributes=attrs,
        x=x,
        y=y,
        handle=handle,
        definition=BlockDefinitionMetadata(tuple(attrs), False),
    )


def _batch(*items: CadObservation) -> CadObservationBatch:
    return CadObservationBatch(
        "C:/fixture/p0003.dwg",
        tuple(items),
        {
            "adapter_version": "test",
            "protocol_version": "1.0",
            "cable_type_conductors": {"TEST CABLE": 8},
        },
    )


def _project(database) -> str:
    return ObjectService(database.engine).create_project(
        ProjectCard(name="P0 003", project_code="P0003")
    )


def _new_paths(proposal) -> set[str]:
    return {
        change.field_path
        for change in proposal.changes
        if change.change_class is ChangeClass.NEW_DWG_INSERTION
    }


def _apply_new(service, proposal) -> str:
    return service.apply_dwg_to_project(
        proposal,
        selected_paths=_new_paths(proposal),
        confirmed=True,
    )


def test_cable_topology_read_model_derives_exact_field_port_root(database):
    project_id = _project(database)
    sync = DwgSyncService(database.engine)
    mrm = _observation(
        "WB_MRM2_MINI",
        handle="M1",
        cable_id="101.01",
        attributes={"BUS_POINT_ID": "", "K1": "", "K2": "", "IN_1": "", "IN_2": ""},
    )
    target = _observation("LIGHT_IN_230V", handle="L1", cable_id="301.01")
    initial = sync.preview(project_id=project_id, batch=_batch(mrm, target))
    _apply_new(sync, initial)
    with UnitOfWork(database.engine) as uow:
        device = (
            uow.execute(select(field_device).where(field_device.c.entity_handle == "M1"))
            .mappings()
            .one()
        )
        fields = dict(device["normalized_fields_json"])
        fields["BUS_POINT_ID"] = "902.003"
        uow.execute(
            update(field_device)
            .where(field_device.c.id == device["id"])
            .values(normalized_fields_json=fields)
        )
        line_id = uow.execute(
            select(cable_line.c.id).where(cable_line.c.designation == "301")
        ).scalar_one()
        port_id = uow.execute(
            select(field_port.c.id).where(
                field_port.c.field_device_id == device["id"],
                field_port.c.port_tag == "K1",
            )
        ).scalar_one()
        source_endpoint_id = new_id()
        uow.execute(
            cable_topology_endpoint.insert().values(
                id=source_endpoint_id,
                project_id=project_id,
                cable_line_id=line_id,
                endpoint_kind="FIELD_PORT",
                field_port_id=port_id,
            )
        )
        uow.execute(
            update(cable_segment)
            .where(cable_segment.c.cable_line_id == line_id)
            .values(source_endpoint_id=source_endpoint_id)
        )
        uow.commit()
    topology = CableService(database.engine).topology(project_id, line_id)
    assert topology["root_endpoint"] == {
        "kind": "FIELD_PORT",
        "reference": "902.003/K1",
        "label": "902.003/K1",
    }
    assert len(topology["edges"]) == 1


def test_scan_is_read_only_deterministic_and_keeps_stable_owner_diagnostics(database):
    project_id = _project(database)
    service = DwgSyncService(database.engine)
    one = _observation("SOCKET_IN", handle="A1", cable_id="101.01")
    two = _observation("SOCKET_IN", handle="A2", cable_id="102.01")
    first = service.preview(project_id=project_id, batch=_batch(one, two))
    shuffled = service.preview(project_id=project_id, batch=_batch(two, one))
    assert [(item.field_path, item.owner_path, item.change_class) for item in first.changes] == [
        (item.field_path, item.owner_path, item.change_class) for item in shuffled.changes
    ]
    invalid = service.preview(
        project_id=project_id,
        batch=_batch(replace(one, layer="0")),
    )
    issue = next(
        item for item in invalid.changes if item.change_class is ChangeClass.INVALID_DWG_DATA
    )
    assert issue.owner_kind is SyncOwnerKind.INSERTION
    assert issue.owner_key == "A1"
    empty = service.preview(project_id=project_id, batch=_batch())
    assert empty.changes == ()
    with database.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(dwg_scan)) == 0
        assert connection.scalar(select(func.count()).select_from(dwg_baseline)) == 0


def test_simple_and_shared_socket_materialize_exactly_one_incoming_segment(database):
    project_id = _project(database)
    service = DwgSyncService(database.engine)
    group = (
        _observation("SOCKET_IN", handle="S2", cable_id="101.01", x=110),
        _observation("SOCKET_IN", handle="S1", cable_id="101.01", x=100),
        _observation("SOCKET_IN", handle="S3", cable_id="101.01", x=120),
    )
    proposal = service.preview(project_id=project_id, batch=_batch(*group))
    _apply_new(service, proposal)
    with database.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(field_device)) == 3
        assert (
            connection.scalar(
                select(func.count())
                .select_from(cable_point)
                .where(cable_point.c.point_kind == "INSTALLATION_GROUP")
            )
            == 1
        )
        assert connection.scalar(select(func.count()).select_from(cable_point_field_device)) == 3
        assert connection.scalar(select(func.count()).select_from(cable_segment)) == 1

    reopened = service.preview(project_id=project_id, batch=_batch(*reversed(group)))
    assert {change.change_class for change in reopened.changes} == {ChangeClass.EQUAL}


def test_grouped_switch_order_and_physical_keys_survive_reopen(database):
    project_id = _project(database)
    service = DwgSyncService(database.engine)
    light = _observation("LIGHT_IN", handle="L1", cable_id="301")
    switch_2 = _observation("SW_IN_2", handle="K2", cable_id="201.02")
    switch_1 = _observation("SW_IN_1", handle="K1", cable_id="201.01", attributes={"KEY_1": "201"})
    proposal = service.preview(project_id=project_id, batch=_batch(switch_2, light, switch_1))
    _apply_new(service, proposal)
    with database.engine.connect() as connection:
        ordered = list(
            connection.execute(
                select(cable_point.c.logical_identity)
                .join(cable_line, cable_line.c.id == cable_point.c.cable_line_id)
                .where(
                    cable_line.c.designation == "201",
                    cable_point.c.point_kind != "INTERNAL_SOURCE",
                )
                .order_by(cable_point.c.ordinal)
            ).scalars()
        )
        keys = list(
            connection.execute(
                select(field_device.c.entity_handle, field_control_key.c.key_tag)
                .join(field_control_key, field_control_key.c.field_device_id == field_device.c.id)
                .order_by(field_device.c.entity_handle, field_control_key.c.key_tag)
            )
        )
        segment_count = connection.scalar(
            select(func.count())
            .select_from(cable_segment)
            .join(cable_line, cable_line.c.id == cable_segment.c.cable_line_id)
            .where(cable_line.c.designation == "201")
        )
    assert ordered == ["201.01", "201.02"]
    assert keys == [("K1", "KEY_1"), ("K2", "KEY_1"), ("K2", "KEY_2")]
    assert segment_count == 2
    reopened = service.preview(
        project_id=project_id,
        batch=_batch(light, switch_1, switch_2),
    )
    assert not any(
        change.change_class is ChangeClass.NEW_DWG_INSERTION for change in reopened.changes
    )
    retargeted_switch = _observation(
        "SW_IN_1", handle="K1", cable_id="201.01", attributes={"KEY_1": "301"}
    )
    retargeted = service.preview(
        project_id=project_id,
        batch=_batch(light, retargeted_switch, switch_2),
    )
    key_change = next(
        change for change in retargeted.changes if change.owner_path == "key:K1:KEY_1"
    )
    service.apply_dwg_to_project(
        retargeted,
        selected_paths={key_change.field_path},
        confirmed=True,
    )
    with database.engine.connect() as connection:
        target_line_id = connection.scalar(
            select(cable_line.c.id).where(cable_line.c.designation == "301")
        )
        key = (
            connection.execute(
                select(field_control_key)
                .join(field_device, field_device.c.id == field_control_key.c.field_device_id)
                .where(
                    field_control_key.c.key_tag == "KEY_1",
                    field_device.c.entity_handle == "K1",
                )
            )
            .mappings()
            .first()
        )
    assert key is not None
    assert key["target_kind"] == "CABLE_LINE"
    assert key["target_cable_line_id"] == target_line_id


def test_elbox_cable_source_chain_materializes_canonical_segments(database):
    project_id = _project(database)
    service = DwgSyncService(database.engine)
    box = _observation(
        "EL_BOX_OUT_100x100",
        handle="E1",
        cable_id="101.01",
        attributes={"BOX_ID": "BOX.010", "BUS_POINT_ID": "", "BUS_SOURCE": ""},
    )
    target = _observation(
        "SOCKET_IN", handle="A1", cable_id="101.02", attributes={"CABLE_SOURCE": "BOX.010"}
    )
    cross = _observation("SOCKET_IN", handle="B1", cable_id="102.01")
    proposal = service.preview(project_id=project_id, batch=_batch(cross, target, box))
    assert proposal.can_apply
    _apply_new(service, proposal)
    with database.engine.connect() as connection:
        counts = dict(
            connection.execute(
                select(cable_line.c.designation, func.count(cable_segment.c.id))
                .join(cable_segment, cable_segment.c.cable_line_id == cable_line.c.id)
                .group_by(cable_line.c.designation)
            ).all()
        )
        elbox = (
            connection.execute(
                select(cable_point).where(cable_point.c.logical_identity == "101.01")
            )
            .mappings()
            .one()
        )
    assert counts == {"101": 2, "102": 1}
    assert elbox["point_kind"] == "EL_BOX"


def test_mrm2_and_m1w2_ports_materialize_without_project_instance(database):
    project_id = _project(database)
    service = DwgSyncService(database.engine)
    mrm = _observation(
        "WB_MRM2_MINI",
        handle="M1",
        cable_id="101.01",
        attributes={"BUS_POINT_ID": "", "K1": "", "K2": "", "IN_1": "", "IN_2": ""},
    )
    sensor = _observation(
        "WB_M1W2",
        handle="W1",
        cable_id="501.01",
        attributes={"BUS_POINT_ID": "", "W1": "", "W2": ""},
    )
    proposal = service.preview(project_id=project_id, batch=_batch(sensor, mrm))
    _apply_new(service, proposal)
    with database.engine.connect() as connection:
        ports = list(
            connection.execute(
                select(field_device.c.entity_handle, field_port.c.port_tag)
                .join(field_port, field_port.c.field_device_id == field_device.c.id)
                .order_by(field_device.c.entity_handle, field_port.c.port_tag)
            )
        )
        values = {
            row["entity_handle"]: row["normalized_fields_json"]
            for row in connection.execute(
                select(field_device.c.entity_handle, field_device.c.normalized_fields_json)
            ).mappings()
        }
    assert ports == [
        ("M1", "COM1"),
        ("M1", "COM2"),
        ("M1", "IN_1"),
        ("M1", "IN_2"),
        ("M1", "K1"),
        ("M1", "K2"),
        ("W1", "W1"),
        ("W1", "W2"),
    ]
    assert values["M1"]["K1"] == ""
    assert values["W1"]["W2"] == ""


class _PlanBridge:
    def __init__(self, *, fail_tag: str | None = None, mismatch_tag: str | None = None):
        self.fail_tag = fail_tag
        self.mismatch_tag = mismatch_tag
        self.calls: list[list[dict[str, str]]] = []

    def write_attributes(self, *, document_identity, changes, deadline_seconds):
        self.calls.append(changes)
        readback = []
        failures = []
        for item in changes:
            if item["tag"] == self.fail_tag:
                failures.append(
                    {"handle": item["handle"], "tag": item["tag"], "reason": "INJECTED"}
                )
                continue
            value = "mismatch" if item["tag"] == self.mismatch_tag else item["new_value"]
            readback.append({"handle": item["handle"], "tag": item["tag"], "value": value})
        return WriteResult(
            document_identity,
            tuple(readback),
            True,
            False,
            "PARTIAL" if failures else "READ_BACK_OK",
            tuple(failures),
        )


def test_owner_aware_write_plan_route_scope_partial_receipt_and_idempotent_retry(database):
    project_id = _project(database)
    service = DwgSyncService(database.engine)
    first = _observation(
        "SOCKET_IN",
        handle="A1",
        cable_id="101.01",
        attributes={
            "MOUNT_WAY": "По полу",
            "GOFRA_TYPE": "ПНД25",
            "GOFRA_COLOR": "Черный",
            "GOFRA_ID": "001.PND25",
        },
    )
    second = _observation(
        "EL_BOX_OUT_100x100",
        handle="E1",
        cable_id="101.02",
        attributes={
            "BOX_ID": "BOX.011",
            "CABLE_SOURCE": "101.01",
            "BUS_POINT_ID": "",
            "BUS_SOURCE": "",
            "MOUNT_WAY": "По потолку",
        },
    )
    initial = service.preview(project_id=project_id, batch=_batch(first, second))
    _apply_new(service, initial)
    with UnitOfWork(database.engine) as uow:
        device = (
            uow.execute(select(field_device).where(field_device.c.entity_handle == "A1"))
            .mappings()
            .one()
        )
        fields = dict(device["normalized_fields_json"])
        fields["MOUNT_WAY"] = "По потолку"
        fields["GOFRA_COLOR"] = "Синий"
        uow.execute(
            update(field_device)
            .where(field_device.c.id == device["id"])
            .values(normalized_fields_json=fields)
        )
        point = uow.execute(
            select(cable_point.c.id).where(cable_point.c.logical_identity == "101.01")
        ).scalar_one()
        target_segment = uow.execute(
            select(cable_segment.c.id)
            .join(
                cable_topology_endpoint,
                cable_topology_endpoint.c.id == cable_segment.c.target_endpoint_id,
            )
            .where(cable_topology_endpoint.c.cable_point_id == point)
        ).scalar_one()
        uow.execute(
            update(cable_segment)
            .where(cable_segment.c.id == target_segment)
            .values(mount_way="По потолку", gofra_color="Синий")
        )
        uow.commit()
    proposal = service.preview(project_id=project_id, batch=_batch(first, second))
    route = [
        change
        for change in proposal.changes
        if change.owner_kind is SyncOwnerKind.SEGMENT
        and change.owner_key == "101/101.01"
        and change.field in {"MOUNT_WAY", "GOFRA_COLOR"}
    ]
    assert {change.change_class for change in route} == {ChangeClass.PROJECT_CHANGED}
    plan = service.plan_project_to_dwg(
        proposal,
        selected_paths={change.field_path for change in route},
    )
    assert {(target.handle, target.tag) for target in plan.targets} == {
        ("A1", "MOUNT_WAY"),
        ("A1", "GOFRA_COLOR"),
    }
    partial_bridge = _PlanBridge(fail_tag="GOFRA_COLOR")
    partial = service.execute_write_plan(plan, confirmed=True, bridge=partial_bridge)
    assert partial.status == "PARTIAL"
    assert partial.completed_targets == (("A1", "MOUNT_WAY"),)
    retry_bridge = _PlanBridge()
    completed = service.execute_write_plan(plan, confirmed=True, bridge=retry_bridge)
    assert completed.status == "READ_BACK_OK"
    assert {(item["handle"], item["tag"]) for item in retry_bridge.calls[0]} == {
        ("A1", "GOFRA_COLOR")
    }
    service.execute_write_plan(plan, confirmed=True, bridge=retry_bridge)
    assert len(retry_bridge.calls) == 1
    with database.engine.connect() as connection:
        results = list(
            connection.execute(
                select(dwg_sync_operation.c.result_json).where(
                    dwg_sync_operation.c.direction == "PROJECT_TO_DWG"
                )
            ).scalars()
        )
    assert [result["status"] for result in results] == ["PARTIAL", "READ_BACK_OK"]


def test_line_write_plan_is_full_set_and_forbidden_fields_never_plan(database):
    project_id = _project(database)
    service = DwgSyncService(database.engine)
    first = _observation("SOCKET_IN", handle="A1", cable_id="101.01")
    second = _observation("SOCKET_IN", handle="A2", cable_id="101.02")
    initial = service.preview(project_id=project_id, batch=_batch(first, second))
    _apply_new(service, initial)
    with UnitOfWork(database.engine) as uow:
        line = uow.execute(select(cable_line)).mappings().one()
        facts = dict(line["cable_facts_json"])
        facts["CABLE_TYPE"] = "PROJECT CABLE"
        uow.execute(
            update(cable_line).where(cable_line.c.id == line["id"]).values(cable_facts_json=facts)
        )
        uow.commit()
    proposal = service.preview(project_id=project_id, batch=_batch(first, second))
    cable_type = next(change for change in proposal.changes if change.field == "CABLE_TYPE")
    plan = service.plan_project_to_dwg(proposal, selected_paths={cable_type.field_path})
    assert {(target.handle, target.tag) for target in plan.targets} == {
        ("A1", "CABLE_TYPE"),
        ("A2", "CABLE_TYPE"),
    }
    forbidden = next(change for change in proposal.changes if change.field == "BLOCK_NAME")
    with pytest.raises(DwgSyncError, match="forbidden"):
        service.plan_project_to_dwg(proposal, selected_paths={forbidden.field_path})


def test_stale_project_revision_rejects_apply_without_partial_state(database):
    project_id = _project(database)
    service = DwgSyncService(database.engine)
    proposal = service.preview(
        project_id=project_id,
        batch=_batch(_observation("SOCKET_IN", handle="A1", cable_id="101.01")),
    )
    with UnitOfWork(database.engine) as uow:
        uow.execute(
            update(project)
            .where(project.c.id == project_id)
            .values(project_revision=project.c.project_revision + 1)
        )
        uow.commit()
    with pytest.raises(DwgSyncError, match="changed after preview"):
        _apply_new(service, proposal)
    with database.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(field_device)) == 0
        assert connection.scalar(select(func.count()).select_from(dwg_baseline)) == 0


def test_three_way_owner_matrix_includes_same_conflict_key_port_source_and_led(database):
    project_id = _project(database)
    service = DwgSyncService(database.engine)
    socket = _observation("SOCKET_IN", handle="A1", cable_id="101.01")
    box = _observation(
        "EL_BOX_OUT_100x100",
        handle="E1",
        cable_id="101.02",
        attributes={
            "CABLE_SOURCE": "101.01",
            "BUS_POINT_ID": "",
            "BUS_SOURCE": "",
        },
    )
    target = _observation("LIGHT_IN_230V", handle="L1", cable_id="301.01")
    switch = _observation(
        "SW_IN_1",
        handle="K1",
        cable_id="201.01",
        attributes={"KEY_1": "301"},
    )
    mrm = _observation(
        "WB_MRM2_MINI",
        handle="M1",
        cable_id="102.01",
        attributes={
            "CABLE_SOURCE": "",
            "K1": "",
            "K2": "",
            "IN_1": "",
            "IN_2": "",
            "BUS_POINT_ID": "",
        },
    )
    led = _observation(
        "LIGHT_LED",
        handle="D1",
        cable_id="401",
        attributes={"LED_TYPE": "MONO"},
    )
    items = (socket, box, target, switch, mrm, led)
    initial = service.preview(project_id=project_id, batch=_batch(*items))
    assert initial.summary.invalid == 0, [
        (change.field_path, change.detail_status, change.display_context)
        for change in initial.changes
        if change.change_class is ChangeClass.INVALID_DWG_DATA
    ]
    assert initial.summary.conflicts == 0, [
        (change.field_path, change.detail_status, change.dwg_value)
        for change in initial.changes
        if change.change_class is ChangeClass.IDENTITY_COLLISION
    ]
    _apply_new(service, initial)
    with UnitOfWork(database.engine) as uow:
        devices = {
            row["entity_handle"]: row for row in uow.execute(select(field_device)).mappings()
        }
        for handle, field, value in (
            ("A1", "DEVICE_NAME", "Project socket"),
            ("E1", "CABLE_SOURCE", "101.01"),
        ):
            fields = dict(devices[handle]["normalized_fields_json"])
            fields[field] = value
            uow.execute(
                update(field_device)
                .where(field_device.c.id == devices[handle]["id"])
                .values(normalized_fields_json=fields)
            )
        line = (
            uow.execute(select(cable_line).where(cable_line.c.designation == "101"))
            .mappings()
            .one()
        )
        facts = dict(line["cable_facts_json"])
        facts["CABLE_TYPE"] = "PROJECT CABLE"
        uow.execute(
            update(cable_line).where(cable_line.c.id == line["id"]).values(cable_facts_json=facts)
        )
        socket_point = uow.execute(
            select(cable_point.c.id).where(cable_point.c.logical_identity == "101.01")
        ).scalar_one()
        socket_segment = uow.execute(
            select(cable_segment.c.id)
            .join(
                cable_topology_endpoint,
                cable_topology_endpoint.c.id == cable_segment.c.target_endpoint_id,
            )
            .where(cable_topology_endpoint.c.cable_point_id == socket_point)
        ).scalar_one()
        uow.execute(
            update(cable_segment)
            .where(cable_segment.c.id == socket_segment)
            .values(mount_way="В кабель-канале")
        )
        key = uow.execute(select(field_control_key)).mappings().one()
        uow.execute(
            update(field_control_key)
            .where(field_control_key.c.id == key["id"])
            .values(functional_target_text="401", target_kind="CABLE_LINE")
        )
        profile = uow.execute(select(led_line_profile)).mappings().one()
        uow.execute(
            update(led_line_profile)
            .where(led_line_profile.c.id == profile["id"])
            .values(led_kind="RGB", channels=3, sync_state="PROJECT_CHANGED")
        )
        uow.commit()

    changed_items = (
        replace(
            socket,
            raw_attributes=tuple(
                replace(attribute, value="Project socket")
                if attribute.tag == "DEVICE_NAME"
                else replace(attribute, value="DWG CABLE")
                if attribute.tag == "CABLE_TYPE"
                else attribute
                for attribute in socket.raw_attributes
            ),
        ),
        replace(
            box,
            raw_attributes=tuple(
                replace(attribute, value="DWG CABLE")
                if attribute.tag == "CABLE_TYPE"
                else attribute
                for attribute in box.raw_attributes
            ),
        ),
        target,
        replace(
            switch,
            raw_attributes=tuple(
                replace(attribute, value="401") if attribute.tag == "KEY_1" else attribute
                for attribute in switch.raw_attributes
            ),
        ),
        mrm,
        replace(
            led,
            raw_attributes=tuple(
                replace(attribute, value="CCT") if attribute.tag == "LED_TYPE" else attribute
                for attribute in led.raw_attributes
            ),
        ),
    )
    proposal = service.preview(project_id=project_id, batch=_batch(*changed_items))
    assert proposal.binding_id is not None
    assert proposal.summary.invalid == 0, [
        (change.field_path, change.reason)
        for change in proposal.changes
        if change.change_class is ChangeClass.INVALID_DWG_DATA
    ]
    by_owner = {change.owner_path: change for change in proposal.changes}
    assert by_owner["insertion:A1:DEVICE_NAME"].detail_status == "BOTH_CHANGED_SAME"
    assert by_owner["base_line:101:CABLE_TYPE"].change_class is ChangeClass.BOTH_CHANGED_CONFLICT
    assert by_owner["segment:101/101.01:MOUNT_WAY"].change_class is ChangeClass.PROJECT_CHANGED
    assert by_owner["key:K1:KEY_1"].detail_status == "BOTH_CHANGED_SAME"
    assert by_owner["port:M1:K1"].change_class is ChangeClass.EQUAL
    assert by_owner["edge:101.02:CABLE_SOURCE"].change_class is ChangeClass.EQUAL
    assert by_owner["base_line:401:LED_TYPE"].change_class is ChangeClass.BOTH_CHANGED_CONFLICT


def test_readback_mismatch_does_not_advance_owner_baseline(database):
    project_id = _project(database)
    service = DwgSyncService(database.engine)
    item = _observation("SOCKET_IN", handle="A1", cable_id="101.01")
    initial = service.preview(project_id=project_id, batch=_batch(item))
    _apply_new(service, initial)
    with UnitOfWork(database.engine) as uow:
        device = uow.execute(select(field_device)).mappings().one()
        fields = dict(device["normalized_fields_json"])
        fields["DEVICE_NAME"] = "Project value"
        uow.execute(
            update(field_device)
            .where(field_device.c.id == device["id"])
            .values(normalized_fields_json=fields)
        )
        uow.commit()
    proposal = service.preview(project_id=project_id, batch=_batch(item))
    change = next(change for change in proposal.changes if change.field == "DEVICE_NAME")
    plan = service.plan_project_to_dwg(proposal, selected_paths={change.field_path})
    receipt = service.execute_write_plan(
        plan,
        confirmed=True,
        bridge=_PlanBridge(mismatch_tag="DEVICE_NAME"),
    )
    assert receipt.status == "PARTIAL"
    with database.engine.connect() as connection:
        baseline = connection.scalar(
            select(dwg_baseline.c.accepted_value_json).where(
                dwg_baseline.c.field_path == "insertion:A1:DEVICE_NAME"
            )
        )
    assert baseline == "Fixture SOCKET_IN"


def test_shared_socket_route_write_plan_targets_group_only(database):
    project_id = _project(database)
    service = DwgSyncService(database.engine)
    group = (
        _observation("SOCKET_IN", handle="S1", cable_id="101.01"),
        _observation("SOCKET_IN", handle="S2", cable_id="101.01"),
    )
    unrelated = _observation("SOCKET_IN", handle="U1", cable_id="102.01")
    initial = service.preview(project_id=project_id, batch=_batch(*group, unrelated))
    _apply_new(service, initial)
    with UnitOfWork(database.engine) as uow:
        point_id = uow.execute(
            select(cable_point.c.id).where(cable_point.c.logical_identity == "101.01")
        ).scalar_one()
        segment_id = uow.execute(
            select(cable_segment.c.id)
            .join(
                cable_topology_endpoint,
                cable_topology_endpoint.c.id == cable_segment.c.target_endpoint_id,
            )
            .where(cable_topology_endpoint.c.cable_point_id == point_id)
        ).scalar_one()
        uow.execute(
            update(cable_segment)
            .where(cable_segment.c.id == segment_id)
            .values(mount_way="В кабель-канале")
        )
        uow.commit()
    proposal = service.preview(project_id=project_id, batch=_batch(unrelated, *group))
    change = next(
        change for change in proposal.changes if change.owner_path == "segment:101/101.01:MOUNT_WAY"
    )
    plan = service.plan_project_to_dwg(proposal, selected_paths={change.field_path})
    assert {(target.handle, target.tag) for target in plan.targets} == {
        ("S1", "MOUNT_WAY"),
        ("S2", "MOUNT_WAY"),
    }


def test_exact_key_source_and_field_port_tags_are_closed_write_targets(database):
    project_id = _project(database)
    service = DwgSyncService(database.engine)
    socket = _observation("SOCKET_IN", handle="A1", cable_id="101.01")
    box = _observation(
        "EL_BOX_OUT_100x100",
        handle="E1",
        cable_id="101.02",
        attributes={
            "CABLE_SOURCE": "101.01",
            "BUS_POINT_ID": "",
            "BUS_SOURCE": "",
        },
    )
    light_301 = _observation("LIGHT_IN_230V", handle="L1", cable_id="301.01")
    led_401 = _observation("LIGHT_LED", handle="D1", cable_id="401")
    switch = _observation(
        "SW_IN_1",
        handle="K1",
        cable_id="201.01",
        attributes={"KEY_1": "301"},
    )
    mrm = _observation(
        "WB_MRM2_MINI",
        handle="M1",
        cable_id="102.01",
        attributes={
            "K1": "",
            "K2": "",
            "IN_1": "",
            "IN_2": "",
            "BUS_POINT_ID": "",
        },
    )
    sensor = _observation(
        "WB_M1W2",
        handle="W1",
        cable_id="501.01",
        attributes={"W1": "", "W2": "", "BUS_POINT_ID": ""},
    )
    items = (socket, box, light_301, led_401, switch, mrm, sensor)
    initial = service.preview(project_id=project_id, batch=_batch(*items))
    _apply_new(service, initial)
    with UnitOfWork(database.engine) as uow:
        devices = {
            row["entity_handle"]: row for row in uow.execute(select(field_device)).mappings()
        }
        for handle, replacements in {
            "M1": {"K1": "301.01", "IN_1": "201.01"},
            "W1": {"W1": "101.01"},
        }.items():
            fields = dict(devices[handle]["normalized_fields_json"])
            fields.update(replacements)
            uow.execute(
                update(field_device)
                .where(field_device.c.id == devices[handle]["id"])
                .values(normalized_fields_json=fields)
            )
        e1_point_id = uow.execute(
            select(cable_point.c.id).where(cable_point.c.logical_identity == "101.02")
        ).scalar_one()
        e1_target_endpoint = uow.execute(
            select(cable_topology_endpoint.c.id).where(
                cable_topology_endpoint.c.cable_point_id == e1_point_id
            )
        ).scalar_one()
        internal_point_id = uow.execute(
            select(cable_point.c.id).where(
                cable_point.c.cable_line_id
                == select(cable_line.c.id)
                .where(cable_line.c.designation == "101")
                .scalar_subquery(),
                cable_point.c.point_kind == "INTERNAL_SOURCE",
            )
        ).scalar_one()
        internal_endpoint = uow.execute(
            select(cable_topology_endpoint.c.id).where(
                cable_topology_endpoint.c.cable_point_id == internal_point_id
            )
        ).scalar_one()
        uow.execute(
            update(cable_segment)
            .where(cable_segment.c.target_endpoint_id == e1_target_endpoint)
            .values(source_endpoint_id=internal_endpoint)
        )
        key = uow.execute(select(field_control_key)).mappings().one()
        led_line_id = uow.execute(
            select(cable_line.c.id).where(cable_line.c.designation == "401")
        ).scalar_one()
        uow.execute(
            update(field_control_key)
            .where(field_control_key.c.id == key["id"])
            .values(
                functional_target_text="401",
                target_cable_line_id=led_line_id,
                target_kind="CABLE_LINE",
            )
        )
        uow.commit()
    proposal = service.preview(project_id=project_id, batch=_batch(*items))
    wanted = {
        "key:K1:KEY_1",
        "edge:101.02:CABLE_SOURCE",
        "port:M1:K1",
        "port:M1:IN_1",
        "port:W1:W1",
    }
    selected = {change.field_path for change in proposal.changes if change.owner_path in wanted}
    assert len(selected) == len(wanted)
    plan = service.plan_project_to_dwg(proposal, selected_paths=selected)
    assert {(target.handle, target.tag) for target in plan.targets} == {
        ("K1", "KEY_1"),
        ("E1", "CABLE_SOURCE"),
        ("M1", "K1"),
        ("M1", "IN_1"),
        ("W1", "W1"),
    }


def test_explicit_conflict_apply_updates_only_selected_owner_and_preserves_project_only(database):
    project_id = _project(database)
    service = DwgSyncService(database.engine)
    original = _observation("SOCKET_IN", handle="A1", cable_id="101.01")
    initial = service.preview(project_id=project_id, batch=_batch(original))
    _apply_new(service, initial)
    with UnitOfWork(database.engine) as uow:
        device = uow.execute(select(field_device)).mappings().one()
        fields = dict(device["normalized_fields_json"])
        fields["DEVICE_NAME"] = "Project name"
        fields["PROJECT_ONLY_NOTE"] = "survives"
        uow.execute(
            update(field_device)
            .where(field_device.c.id == device["id"])
            .values(normalized_fields_json=fields)
        )
        uow.commit()
    changed = replace(
        original,
        raw_attributes=tuple(
            replace(attribute, value="DWG name") if attribute.tag == "DEVICE_NAME" else attribute
            for attribute in original.raw_attributes
        ),
    )
    proposal = service.preview(project_id=project_id, batch=_batch(changed))
    conflict = next(change for change in proposal.changes if change.field == "DEVICE_NAME")
    assert conflict.change_class is ChangeClass.BOTH_CHANGED_CONFLICT
    service.apply_dwg_to_project(
        proposal,
        selected_paths={conflict.field_path},
        confirmed=True,
    )
    with database.engine.connect() as connection:
        fields = connection.scalar(select(field_device.c.normalized_fields_json))
    assert fields["DEVICE_NAME"] == "DWG name"
    assert fields["PROJECT_ONLY_NOTE"] == "survives"
    reopened = service.preview(project_id=project_id, batch=_batch(changed))
    assert (
        next(change for change in reopened.changes if change.field == "DEVICE_NAME").change_class
        is ChangeClass.EQUAL
    )


def test_new_handle_is_candidate_plus_missing_and_never_auto_remapped(database):
    project_id = _project(database)
    service = DwgSyncService(database.engine)
    old = _observation("SOCKET_IN", handle="OLD", cable_id="101.01")
    initial = service.preview(project_id=project_id, batch=_batch(old))
    _apply_new(service, initial)
    replacement = _observation("SOCKET_IN", handle="NEW", cable_id="101.01")

    proposal = service.preview(project_id=project_id, batch=_batch(replacement))

    statuses = {change.change_class for change in proposal.changes}
    assert ChangeClass.NEW_DWG_INSERTION in statuses
    assert ChangeClass.MISSING_DWG_INSERTION in statuses
    remap = next(
        change
        for change in proposal.changes
        if change.detail_status == "STRUCTURAL_IDENTITY_REVIEW" and change.field == "$HANDLE_REMAP"
    )
    assert remap.owner_key == "OLD->NEW"
    with database.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(field_device)) == 1
