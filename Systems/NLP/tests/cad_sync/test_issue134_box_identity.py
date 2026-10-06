import uuid
from dataclasses import replace

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from test_p0003_reconciliation import _apply_new, _batch, _observation, _project

from nl_project_2.buses import BusService
from nl_project_2.cables.service import CableService
from nl_project_2.cad_sync import ChangeClass, DwgSyncError, DwgSyncService
from nl_project_2.cad_sync.reconciliation import BusPointPlan, NormalizedCadSnapshot
from nl_project_2.cad_sync.workflow import build_dwg_update_plan
from nl_project_2.catalog.equipment import EquipmentService
from nl_project_2.persistence.database import DatabaseManager
from nl_project_2.persistence.schema import (
    bus,
    bus_endpoint,
    bus_segment,
    cable_line,
    cable_point,
    cable_segment,
    cable_topology_endpoint,
    dwg_baseline,
    dwg_observation,
    dwg_scan,
    dwg_sync_operation,
    field_device,
    instance_resource,
    project,
)
from nl_project_2.persistence.uow import UnitOfWork


def _box(index, *, base="111", source="", **kwargs):
    return _observation(
        "EL_BOX_OUT_100x100",
        handle=f"E{index}",
        cable_id=base,
        attributes={
            "BOX_ID": f"BOX.{20 + index:03d}",
            "CABLE_SOURCE": source,
            "BUS_POINT_ID": "",
            "BUS_SOURCE": "",
        },
        x=100 * index,
        **kwargs,
    )


@pytest.mark.parametrize("count", [2, 4])
def test_distinct_base_only_boxes_form_one_line_chain_and_survive_reopen(database, count):
    pid = _project(database)
    service = DwgSyncService(database.engine)
    boxes = tuple(
        _box(i, source="" if i == 1 else f"BOX.{19 + i:03d}") for i in range(1, count + 1)
    )
    proposal = service.preview(project_id=pid, batch=_batch(*reversed(boxes)))
    assert proposal.summary.invalid == 0
    _apply_new(service, proposal)
    with DatabaseManager().open_existing(database.path) as reopened:
        with reopened.engine.connect() as connection:
            assert list(connection.execute(select(cable_line.c.designation)).scalars()) == ["111"]
            points = dict(
                connection.execute(
                    select(cable_point.c.logical_identity, cable_point.c.id).where(
                        cable_point.c.point_kind == "EL_BOX"
                    )
                ).all()
            )
            assert set(points) == {f"BOX.{20 + i:03d}" for i in range(1, count + 1)}
            endpoints = dict(
                connection.execute(
                    select(
                        cable_topology_endpoint.c.cable_point_id, cable_topology_endpoint.c.id
                    ).where(cable_topology_endpoint.c.cable_point_id.in_(points.values()))
                ).all()
            )
            assert len(set(endpoints.values())) == count
            edges = set(
                connection.execute(
                    select(cable_segment.c.source_endpoint_id, cable_segment.c.target_endpoint_id)
                ).all()
            )
            assert len(edges) == count  # root -> first box, then count-1 physical edges
            assert all(source != target for source, target in edges)
            for i in range(2, count + 1):
                assert (
                    endpoints[points[f"BOX.{19 + i:03d}"]],
                    endpoints[points[f"BOX.{20 + i:03d}"]],
                ) in edges
            assert connection.exec_driver_sql("PRAGMA integrity_check").scalar() == "ok"
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        repeated = DwgSyncService(reopened.engine).preview(project_id=pid, batch=_batch(*boxes))
        # Box-only lines have no LOAD_NAME ATTDEF (existing empty/None line fact).
        assert {
            change.change_class for change in repeated.changes if change.field != "LOAD_NAME"
        } == {ChangeClass.EQUAL}


def test_box_and_ordinary_base_point_are_not_coalesced(database):
    pid = _project(database)
    service = DwgSyncService(database.engine)
    box = _box(1)
    socket = _observation(
        "SOCKET_IN", handle="S1", cable_id="111", attributes={"CABLE_SOURCE": "BOX.021"}
    )
    _apply_new(service, service.preview(project_id=pid, batch=_batch(box, socket)))
    with database.engine.connect() as connection:
        identities = set(
            connection.execute(
                select(cable_point.c.logical_identity).where(
                    cable_point.c.point_kind != "INTERNAL_SOURCE"
                )
            ).scalars()
        )
        assert identities == {"BOX.021", "111"}
        assert connection.scalar(select(func.count()).select_from(cable_segment)) == 2


def test_selective_new_downstream_reuses_unselected_existing_box_endpoint(database):
    pid = _project(database)
    service = DwgSyncService(database.engine)
    source = _box(1)
    _apply_new(service, service.preview(project_id=pid, batch=_batch(source)))
    with database.engine.connect() as connection:
        source_before = dict(
            connection.execute(
                select(cable_point).where(cable_point.c.logical_identity == "BOX.021")
            )
            .mappings()
            .one()
        )
    target = _box(2, source="BOX.021")
    unselected = _observation("SOCKET_IN", handle="U1", cable_id="121.01")
    proposal = service.preview(
        project_id=pid, batch=_batch(replace(source, x=9000), target, unselected)
    )
    service.apply_dwg_to_project(proposal, selected_paths={"E2:$"}, confirmed=True)
    with database.engine.connect() as connection:
        assert set(connection.execute(select(field_device.c.entity_handle)).scalars()) == {
            "E1",
            "E2",
        }
        assert list(connection.execute(select(cable_line.c.designation)).scalars()) == ["111"]
        assert connection.scalar(select(func.count()).select_from(cable_segment)) == 2
        source_after = dict(
            connection.execute(select(cable_point).where(cable_point.c.id == source_before["id"]))
            .mappings()
            .one()
        )
        assert source_after == source_before
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []


def test_selective_missing_source_is_domain_error_and_imports_no_dependency(database):
    pid = _project(database)
    service = DwgSyncService(database.engine)
    target = _observation("SOCKET_IN", handle="S1", cable_id="111.01")
    _apply_new(service, service.preview(project_id=pid, batch=_batch(target)))
    changed = replace(
        target,
        raw_attributes=tuple(
            replace(attribute, value="BOX.021") if attribute.tag == "CABLE_SOURCE" else attribute
            for attribute in target.raw_attributes
        ),
    )
    proposal = service.preview(project_id=pid, batch=_batch(_box(1), changed))
    with database.engine.connect() as connection:
        revision = connection.scalar(select(project.c.project_revision))
        scans = connection.scalar(select(func.count()).select_from(dwg_scan))
    with pytest.raises(DwgSyncError, match="Источник BOX.021 ещё не принят"):
        service.apply_dwg_to_project(
            proposal, selected_paths={"S1:CABLE_SOURCE"}, confirmed=True, allow_structural=True
        )
    with database.engine.connect() as connection:
        assert list(connection.execute(select(field_device.c.entity_handle)).scalars()) == ["S1"]
        assert connection.scalar(select(project.c.project_revision)) == revision
        assert connection.scalar(select(func.count()).select_from(dwg_scan)) == scans


def test_invalid_cross_line_box_source_is_domain_error_not_keyerror(database):
    pid = _project(database)
    service = DwgSyncService(database.engine)
    target = _observation(
        "SOCKET_IN", handle="S1", cable_id="112", attributes={"CABLE_SOURCE": "BOX.021"}
    )
    proposal = service.preview(project_id=pid, batch=_batch(_box(1), target))
    with pytest.raises(DwgSyncError, match="физического порта"):
        service.apply_dwg_to_project(proposal, selected_paths={"S1:$"}, confirmed=True)
    with database.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(cable_line)) == 0
        assert connection.scalar(select(func.count()).select_from(field_device)) == 0


def test_ordinary_selective_direct_line_keeps_board_root_and_excludes_other_line(database):
    pid = _project(database)
    service = DwgSyncService(database.engine)
    target = _observation("SOCKET_IN", handle="S1", cable_id="111")
    other = _observation("SOCKET_IN", handle="U1", cable_id="121")
    proposal = service.preview(project_id=pid, batch=_batch(target, other))
    service.apply_dwg_to_project(proposal, selected_paths={"S1:$"}, confirmed=True)
    with database.engine.connect() as connection:
        assert list(connection.execute(select(cable_line.c.designation)).scalars()) == ["111"]
        assert list(connection.execute(select(field_device.c.entity_handle)).scalars()) == ["S1"]
        segment = connection.execute(select(cable_segment)).mappings().one()
        kind = connection.execute(
            select(cable_point.c.point_kind)
            .join(
                cable_topology_endpoint,
                cable_topology_endpoint.c.cable_point_id == cable_point.c.id,
            )
            .where(cable_topology_endpoint.c.id == segment["source_endpoint_id"])
        ).scalar_one()
        assert kind == "INTERNAL_SOURCE"


def test_selective_unaccepted_physical_port_is_explicit_domain_error(database):
    pid = _project(database)
    service = DwgSyncService(database.engine)
    source = _observation(
        "WB_MRM2_MINI",
        handle="M1",
        cable_id="101",
        attributes={"BUS_POINT_ID": "902.003", "K1": "", "K2": "", "IN_1": "", "IN_2": ""},
    )
    target = _box(1, base="301", source="902.003/K1")
    proposal = service.preview(project_id=pid, batch=_batch(source, target))
    with pytest.raises(DwgSyncError, match="Источник 902.003/K1"):
        service.apply_dwg_to_project(proposal, selected_paths={"E1:$"}, confirmed=True)
    with database.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(field_device)) == 0
        assert connection.scalar(select(func.count()).select_from(cable_line)) == 0


def _rs485_root(database, pid):
    receipt = EquipmentService(database.engine).create_instance(
        project_id=pid,
        designation="WB.01",
        passport_key="module.wirenboard.wb_mcm8",
        product_key="product.wirenboard.wb_mcm8",
        supply_scope="NEIROLINKS",
    )
    with database.engine.connect() as connection:
        root = (
            connection.execute(
                select(instance_resource.c.id).where(
                    instance_resource.c.project_instance_id == receipt.instance_id,
                    instance_resource.c.resource_kind == "RS485_INTERFACE",
                )
            )
            .scalars()
            .first()
        )
    BusService(database.engine).create_rs485_bus(
        project_id=pid,
        designation="902",
        root_resource_id=root,
        points=(),
    )


@pytest.mark.parametrize("selective", [False, True])
def test_physical_output_port_supports_cross_line_full_and_selective_import(database, selective):
    pid = _project(database)
    _rs485_root(database, pid)
    service = DwgSyncService(database.engine)
    source = _observation(
        "WB_MRM2_MINI",
        handle="M1",
        cable_id="101",
        attributes={"BUS_POINT_ID": "902.003", "K1": "", "K2": "", "IN_1": "", "IN_2": ""},
    )
    if selective:
        _apply_new(service, service.preview(project_id=pid, batch=_batch(source)))
    target = _box(1, base="301", source="902.003/K1")
    unselected = _observation("SOCKET_IN", handle="U1", cable_id="121.01")
    proposal = service.preview(project_id=pid, batch=_batch(source, target, unselected))
    service.apply_dwg_to_project(
        proposal, selected_paths={"E1:$"} if selective else {"M1:$", "E1:$"}, confirmed=True
    )
    with database.engine.connect() as connection:
        line_id = connection.execute(
            select(cable_line.c.id).where(cable_line.c.designation == "301")
        ).scalar_one()
        segment = (
            connection.execute(
                select(cable_segment).where(cable_segment.c.cable_line_id == line_id)
            )
            .mappings()
            .one()
        )
        endpoint = (
            connection.execute(
                select(cable_topology_endpoint).where(
                    cable_topology_endpoint.c.id == segment["source_endpoint_id"]
                )
            )
            .mappings()
            .one()
        )
        assert endpoint["endpoint_kind"] == "FIELD_PORT"
        assert endpoint["cable_line_id"] == line_id
        assert endpoint["field_port_id"] is not None
        assert segment["source_endpoint_id"] != segment["target_endpoint_id"]
        assert set(connection.execute(select(field_device.c.entity_handle)).scalars()) == {
            "M1",
            "E1",
        }
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    assert CableService(database.engine).topology(pid, line_id)["root_endpoint"] == {
        "kind": "FIELD_PORT",
        "reference": "902.003/K1",
        "label": "902.003/K1",
    }


def test_materialization_failure_rolls_back_every_write(database, monkeypatch):
    pid = _project(database)
    service = DwgSyncService(database.engine)
    proposal = service.preview(project_id=pid, batch=_batch(_box(1), _box(2, source="BOX.021")))
    original = service._materialize_segment_conduits

    def fail_after_segments(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("injected materialization failure")

    monkeypatch.setattr(service, "_materialize_segment_conduits", fail_after_segments)
    with pytest.raises(RuntimeError, match="injected"):
        _apply_new(service, proposal)
    with database.engine.connect() as connection:
        for table in (
            cable_line,
            cable_point,
            cable_topology_endpoint,
            cable_segment,
            field_device,
            dwg_scan,
            dwg_observation,
            dwg_baseline,
            dwg_sync_operation,
        ):
            assert connection.scalar(select(func.count()).select_from(table)) == 0
        assert connection.scalar(select(project.c.project_revision)) == 0


def test_true_self_edge_is_rejected_by_validation_and_database(database):
    pid = _project(database)
    service = DwgSyncService(database.engine)
    invalid = service.preview(project_id=pid, batch=_batch(_box(1, source="BOX.021")))
    assert "CABLE_SOURCE_CYCLE" in {issue.code for issue in invalid.issues}
    with pytest.raises(DwgSyncError):
        service.apply_dwg_to_project(invalid, selected_paths={"E1:$"}, confirmed=True)
    _apply_new(service, service.preview(project_id=pid, batch=_batch(_box(1))))
    with pytest.raises(IntegrityError, match="ck_cable_segment_no_self_edge"):
        with UnitOfWork(database.engine) as uow:
            segment = uow.execute(select(cable_segment)).mappings().one()
            uow.execute(
                update(cable_segment)
                .where(cable_segment.c.id == segment["id"])
                .values(source_endpoint_id=segment["target_endpoint_id"])
            )
            uow.commit()


def test_legacy_single_box_identity_is_adopted_without_duplicate_or_schema_change(database):
    pid = _project(database)
    service = DwgSyncService(database.engine)
    original = _box(1)
    _apply_new(service, service.preview(project_id=pid, batch=_batch(original)))
    with UnitOfWork(database.engine) as uow:
        point_id = uow.execute(
            select(cable_point.c.id).where(cable_point.c.logical_identity == "BOX.021")
        ).scalar_one()
        uow.execute(
            update(cable_point).where(cable_point.c.id == point_id).values(logical_identity="111")
        )
        for row in uow.execute(select(dwg_baseline)).mappings():
            path = row["field_path"].replace("segment:111/BOX.021:", "segment:111/111:")
            path = path.replace("edge:BOX.021:", "edge:111:")
            if path != row["field_path"]:
                uow.execute(
                    update(dwg_baseline)
                    .where(dwg_baseline.c.id == row["id"])
                    .values(field_path=path)
                )
        uow.commit()
    changed = replace(
        original,
        raw_attributes=tuple(
            replace(attribute, value="В стене") if attribute.tag == "MOUNT_WAY" else attribute
            for attribute in original.raw_attributes
        ),
    )
    proposal = service.preview(project_id=pid, batch=_batch(changed))
    route = next(change for change in proposal.changes if change.field == "MOUNT_WAY")
    assert route.change_class is ChangeClass.DWG_CHANGED
    service.apply_dwg_to_project(proposal, selected_paths={route.field_path}, confirmed=True)
    with database.engine.connect() as connection:
        assert (
            connection.execute(
                select(cable_point.c.id).where(cable_point.c.logical_identity == "BOX.021")
            ).scalar_one()
            == point_id
        )
        assert connection.scalar(select(func.count()).select_from(cable_segment)) == 1
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    repeated = service.preview(project_id=pid, batch=_batch(changed))
    assert {change.change_class for change in repeated.changes if change.field != "LOAD_NAME"} == {
        ChangeClass.EQUAL
    }


def test_unrelated_duplicate_boxes_do_not_block_safe_new_insertion(database):
    pid = _project(database)
    service = DwgSyncService(database.engine)

    box_a = _observation(
        "EL_BOX_OUT_100x100",
        handle="DUP1",
        cable_id="111",
        attributes={
            "BOX_ID": "BOX.035",
            "CABLE_SOURCE": "",
            "BUS_POINT_ID": "",
            "BUS_SOURCE": "",
        },
        x=100,
    )
    box_b = _observation(
        "EL_BOX_OUT_100x100",
        handle="DUP2",
        cable_id="112",
        attributes={
            "BOX_ID": "BOX.035",
            "CABLE_SOURCE": "",
            "BUS_POINT_ID": "",
            "BUS_SOURCE": "",
        },
        x=200,
    )
    safe = _observation("SOCKET_IN", handle="SAFE1", cable_id="121.01", x=300)

    proposal = service.preview(project_id=pid, batch=_batch(box_a, box_b, safe))
    by_handle = {change.handle: change for change in proposal.changes if change.field == "$"}

    assert by_handle["DUP1"].change_class is ChangeClass.INVALID_DWG_DATA
    assert by_handle["DUP2"].change_class is ChangeClass.INVALID_DWG_DATA
    assert by_handle["SAFE1"].change_class is ChangeClass.NEW_DWG_INSERTION

    plan = build_dwg_update_plan(proposal)
    assert "SAFE1:$" in plan.import_paths
    assert "DUP1:$" not in plan.import_paths
    assert "DUP2:$" not in plan.import_paths

    service.apply_dwg_to_project(proposal, selected_paths=plan.import_paths, confirmed=True)

    with database.engine.connect() as connection:
        handles = set(
            connection.execute(
                select(field_device.c.entity_handle).where(field_device.c.lifecycle == "ACTIVE")
            ).scalars()
        )
    assert "SAFE1" in handles
    assert "DUP1" not in handles
    assert "DUP2" not in handles


def test_existing_bus_devices_attach_after_root_is_created_without_reimporting_dwg_changes(
    database,
):
    pid = _project(database)
    _rs485_root(database, pid)
    service = DwgSyncService(database.engine)

    accepted_fields = {
        "BLOCK_NAME": "SENSOR_MSW",
        "BUS_POINT_ID": "902.001",
        "BUS_ID": "902",
        "BUS_TYPE": "RS485",
        "BUS_CABLE_TYPE": "FTP 5e",
        "BUS_LINK": "CABLE",
        "BUS_SOURCE": "",
        "BUS_MOUNT_WAY": "\u041f\u043e \u043f\u043e\u0442\u043e\u043b\u043a\u0443",
        "BUS_GOFRA_TYPE": "",
        "BUS_GOFRA_COLOR": "",
        "BUS_GOFRA_ID": "",
    }
    with UnitOfWork(database.engine) as uow:
        device_id = str(uuid.uuid4())
        uow.execute(
            field_device.insert().values(
                id=device_id,
                project_id=pid,
                block_kind="SENSOR_MSW",
                normalized_fields_json=accepted_fields,
                entity_handle="BUS1",
                lifecycle="ACTIVE",
            )
        )
        uow.commit()

    # Current DWG may contain a different, not-yet-selected route. The repair
    # must attach the already accepted device but must not import that pending
    # route merely because the bus root now exists.
    current_plan = BusPointPlan(
        bus_id="902",
        point_id="902.001",
        source=None,
        bus_kind="RS485",
        handle="BUS1",
        cable_type="FTP 6e",
        connection_kind="CABLE",
        route=(
            ("BUS_MOUNT_WAY", "\u041f\u043e \u043f\u043e\u0442\u043e\u043b\u043a\u0443"),
            ("BUS_GOFRA_TYPE", ""),
            ("BUS_GOFRA_COLOR", ""),
            ("BUS_GOFRA_ID", ""),
        ),
    )
    snapshot = NormalizedCadSnapshot(
        facts=(),
        points=(),
        segments=(),
        ports=(),
        keys=(),
        bus_points=(current_plan,),
        structural_reviews=(),
        point_key_by_handle=(),
    )

    with UnitOfWork(database.engine) as uow:
        affected = service._materialize_bus_snapshot(
            uow,
            project_id=pid,
            snapshot=snapshot,
            device_ids={"BUS1": device_id},
            active_handles=set(),
        )
        uow.commit()

    with database.engine.connect() as connection:
        bus_row = (
            connection.execute(
                select(bus).where(bus.c.project_id == pid, bus.c.designation == "902")
            )
            .mappings()
            .one()
        )
        endpoint = (
            connection.execute(
                select(bus_endpoint).where(
                    bus_endpoint.c.bus_id == bus_row["id"],
                    bus_endpoint.c.address == "902.001",
                )
            )
            .mappings()
            .one()
        )
        segment = (
            connection.execute(select(cable_segment).where(cable_segment.c.project_id == pid))
            .mappings()
            .first()
        )

    assert affected == {bus_row["id"]}
    assert endpoint["field_device_id"] == device_id
    assert segment is None  # ordinary cable table remains untouched

    with database.engine.connect() as connection:
        bus_segment_row = (
            connection.execute(
                select(bus_segment).where(
                    bus_segment.c.bus_id == bus_row["id"],
                    bus_segment.c.target_endpoint_id == endpoint["id"],
                )
            )
            .mappings()
            .one()
        )
    assert bus_segment_row["mount_way"] == "\u041f\u043e \u043f\u043e\u0442\u043e\u043b\u043a\u0443"
    assert bus_segment_row["gofra_type"] is None
    with database.engine.connect() as connection:
        assert (
            connection.execute(
                select(bus.c.cable_type).where(bus.c.id == bus_row["id"])
            ).scalar_one()
            == "FTP 5e"
        )
