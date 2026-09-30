from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import func, select, update

from nl_project_2.automation import AutomationService
from nl_project_2.buses import BusError, BusService
from nl_project_2.cad_sync import DwgSyncService
from nl_project_2.persistence.database import DatabaseManager
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    bus_segment,
    bus_segment_conduit_assignment,
    conduit,
    functional_relation,
)
from nl_project_2.persistence.uow import UnitOfWork

from .test_service import _rs485_resources


def _instance(automation, project_id, designation, passport, product):
    return automation.constructor.create_instance(
        project_id=project_id,
        designation=designation,
        passport_key=passport,
        product_key=product,
        supply_scope="NEIROLINKS",
    )


def _resource(automation, project_id, instance_id, key, ordinal=0):
    return next(
        row["id"]
        for row in automation.constructor.list_resources(project_id)
        if row["project_instance_id"] == instance_id
        and row["resource_key"] == key
        and row["ordinal"] == ordinal
    )


def _points(resources, base="903"):
    facts = (("01", 1000, 0), ("02", 2000, 0), ("03", 2000, 1000), ("04", 3000, 1000))
    return tuple(
        {
            "resource_id": resource_id,
            "cable_id": f"{base}.{int(suffix):03d}",
            "x_mm": x,
            "y_mm": y,
        }
        for resource_id, (suffix, x, y) in zip(resources, facts, strict=True)
    )


def _sources(database):
    project_id = database.test_project_id
    automation = AutomationService(database.engine)
    dali = _instance(
        automation,
        project_id,
        "DALI-SOURCE",
        "gateway.wirenboard.wb_dali3",
        "product.wirenboard.wb_dali3",
    )
    knx = _instance(
        automation,
        project_id,
        "KNX-SOURCE",
        "module.wirenboard.wbe2_i_knx",
        "product.wirenboard.wbe2_i_knx",
    )
    return (
        automation,
        _resource(automation, project_id, dali.instance_id, "DALI_PORT", 0),
        _resource(automation, project_id, knx.instance_id, "KNX_PORT", 0),
        dali.instance_id,
    )


def test_physical_bus_segments_share_conduit_once_and_track_has_none(database):
    project_id = database.test_project_id
    _automation, dali_root, _knx_root, _instance_id = _sources(database)
    endpoints = _rs485_resources(database, count=4)
    bus_receipt = BusService(database.engine).create_branched_bus(
        project_id=project_id,
        bus_kind="DALI",
        designation="905",
        root_resource_id=dali_root,
        points=_points(endpoints, base="905")[:2],
        branches=((endpoints[0], endpoints[1]),),
    )
    route = {
        "BUS_MOUNT_WAY": "По потолку",
        "BUS_GOFRA_TYPE": "ПНД25",
        "BUS_GOFRA_COLOR": "Черный",
        "BUS_GOFRA_ID": "007.PND25",
    }
    sync = DwgSyncService(database.engine)
    with UnitOfWork(database.engine) as uow:
        segment_ids = list(
            uow.execute(
                select(bus_segment.c.id)
                .where(bus_segment.c.bus_id == bus_receipt.bus_id)
                .order_by(bus_segment.c.id)
            ).scalars()
        )
        for segment_id in segment_ids:
            uow.execute(
                update(bus_segment)
                .where(bus_segment.c.id == segment_id)
                .values(
                    mount_way=route["BUS_MOUNT_WAY"],
                    gofra_type=route["BUS_GOFRA_TYPE"],
                    gofra_color=route["BUS_GOFRA_COLOR"],
                    gofra_id=route["BUS_GOFRA_ID"],
                )
            )
            sync._materialize_bus_segment_conduit(
                uow,
                project_id=project_id,
                segment_id=segment_id,
                connection_kind="CABLE",
                route=route,
            )
        sync._materialize_bus_segment_conduit(
            uow,
            project_id=project_id,
            segment_id=segment_ids[-1],
            connection_kind="TRACK",
            route={},
        )
        uow.commit()
    with database.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(conduit)) == 1
        assert connection.scalar(
            select(func.count()).select_from(bus_segment_conduit_assignment)
        ) == 1
        assert connection.scalar(
            select(func.count()).select_from(bus_segment)
        ) == 2
def test_dali_branches_group_recalculation_and_reopen(database):
    project_id = database.test_project_id
    automation, dali_root, _knx_root, _dali_instance = _sources(database)
    endpoints = _rs485_resources(database, count=4)
    service = BusService(database.engine)
    points = _points(endpoints)
    branches = ((endpoints[0], endpoints[1]), (endpoints[1], endpoints[2], endpoints[3]))
    receipt = service.create_branched_bus(
        project_id=project_id,
        bus_kind="DALI",
        designation="903",
        root_resource_id=dali_root,
        points=points,
        branches=branches,
    )
    stored = service.get_bus(project_id, receipt.bus_id)
    assert stored["bus_kind"] == "DALI"
    assert tuple(row["resource_ids"] for row in stored["branches"]) == branches
    coordinates = {dali_root: (0, 0)} | {
        point["resource_id"]: (point["x_mm"], point["y_mm"]) for point in points
    }
    before = service.topology(
        project_id=project_id,
        bus_id=receipt.bus_id,
        coordinates=coordinates,
    )
    assert before.status == "VERIFIED"
    assert before.total_length_mm == Decimal("4000")

    group = service.create_dali_group(
        project_id=project_id,
        bus_id=receipt.bus_id,
        group_key="D.001",
        member_resource_ids=(endpoints[0], endpoints[2]),
    )
    assert group.member_count == 2
    assert service.list_dali_groups(project_id, receipt.bus_id)[0]["member_resource_ids"] == tuple(
        sorted((endpoints[0], endpoints[2]))
    )
    with pytest.raises(BusError, match="orphan"):
        service.replace_branched_topology(
            project_id=project_id,
            bus_id=receipt.bus_id,
            points=(points[0], points[1], points[3]),
            branches=((endpoints[0], endpoints[1], endpoints[3]),),
        )

    changed_branches = (
        (endpoints[0], endpoints[1], endpoints[2]),
        (endpoints[1], endpoints[3]),
    )
    service.replace_branched_topology(
        project_id=project_id,
        bus_id=receipt.bus_id,
        points=points,
        branches=changed_branches,
    )
    after = service.topology(
        project_id=project_id,
        bus_id=receipt.bus_id,
        coordinates=coordinates,
    )
    assert after.edges != before.edges
    assert after.total_length_mm == Decimal("5000")
    assert service.list_dali_groups(project_id, receipt.bus_id)[0]["id"] == group.group_id

    path = database.path
    database.close()
    reopened = DatabaseManager().open_existing(path)
    try:
        reopened_service = BusService(reopened.engine)
        assert len(reopened_service.get_bus(project_id, receipt.bus_id)["branches"]) == 2
        assert (
            reopened_service.list_dali_groups(project_id, receipt.bus_id)[0]["group_key"] == "D.001"
        )
    finally:
        reopened.close()


def test_knx_source_invalid_branch_and_dali_group_scope_are_enforced(database):
    project_id = database.test_project_id
    _automation, dali_root, knx_root, _dali_instance = _sources(database)
    all_endpoints = _rs485_resources(database, count=8)
    dali_endpoints = all_endpoints[:4]
    knx_endpoints = all_endpoints[4:]
    service = BusService(database.engine)
    invalid_branches = ((knx_endpoints[0], knx_endpoints[1]), (knx_endpoints[2],))
    with pytest.raises(BusError, match="INVALID_BRANCH_START"):
        service.create_branched_bus(
            project_id=project_id,
            bus_kind="KNX",
            designation="904",
            root_resource_id=knx_root,
            points=_points(knx_endpoints, "904"),
            branches=invalid_branches,
        )
    knx = service.create_branched_bus(
        project_id=project_id,
        bus_kind="KNX",
        designation="904",
        root_resource_id=knx_root,
        points=_points(knx_endpoints, "904"),
        branches=(
            (knx_endpoints[0], knx_endpoints[1]),
            (knx_endpoints[1], knx_endpoints[2], knx_endpoints[3]),
        ),
    )
    assert service.get_bus(project_id, knx.bus_id)["topology_policy"] == "ORDERED_BRANCHES"
    knx_states = {
        row["resource_id"]: row for row in service.connection_states(project_id, knx.bus_id)
    }
    assert knx_states[knx_root]["communication_state"] == "VERIFIED"
    assert knx_states[knx_root]["power_state"] == "MISSING"
    with pytest.raises(BusError, match="physical DALI bus"):
        service.create_dali_group(
            project_id=project_id,
            bus_id=knx.bus_id,
            group_key="D.002",
            member_resource_ids=(knx_endpoints[0],),
        )

    dali = service.create_branched_bus(
        project_id=project_id,
        bus_kind="DALI",
        designation="903",
        root_resource_id=dali_root,
        points=_points(dali_endpoints),
        branches=(
            (dali_endpoints[0], dali_endpoints[1]),
            (dali_endpoints[1], dali_endpoints[2], dali_endpoints[3]),
        ),
    )
    with pytest.raises(BusError, match="same physical bus"):
        service.create_dali_group(
            project_id=project_id,
            bus_id=dali.bus_id,
            group_key="D.003",
            member_resource_ids=(knx_endpoints[0],),
        )


def test_power_and_bus_link_states_are_independent(database):
    project_id = database.test_project_id
    automation, dali_root, _knx_root, dali_instance = _sources(database)
    endpoints = _rs485_resources(database, count=4)
    service = BusService(database.engine)
    receipt = service.create_branched_bus(
        project_id=project_id,
        bus_kind="DALI",
        designation="903",
        root_resource_id=dali_root,
        points=_points(endpoints),
        branches=((endpoints[0], endpoints[1]), (endpoints[1], endpoints[2], endpoints[3])),
    )
    states = {
        row["resource_id"]: row for row in service.connection_states(project_id, receipt.bus_id)
    }
    assert states[dali_root] == {
        "resource_id": dali_root,
        "communication_state": "VERIFIED",
        "power_state": "MISSING",
    }
    power_inputs = [
        row["id"]
        for row in automation.constructor.list_resources(project_id)
        if row["project_instance_id"] == dali_instance and "POWER_INPUT" in row["resource_kind"]
    ]
    with database.engine.begin() as connection:
        connection.execute(
            functional_relation.insert().values(
                id=new_id(),
                project_id=project_id,
                relation_kind="TEST_POWER",
                source_resource_id=endpoints[0],
                target_resource_id=power_inputs[0],
                parameters_json={},
                command_id=new_id(),
            )
        )
    assert {
        row["resource_id"]: row for row in service.connection_states(project_id, receipt.bus_id)
    }[dali_root]["power_state"] == "INCOMPLETE"
    with database.engine.begin() as connection:
        connection.execute(
            functional_relation.insert().values(
                id=new_id(),
                project_id=project_id,
                relation_kind="TEST_POWER",
                source_resource_id=endpoints[1],
                target_resource_id=power_inputs[1],
                parameters_json={},
                command_id=new_id(),
            )
        )
    assert {
        row["resource_id"]: row for row in service.connection_states(project_id, receipt.bus_id)
    }[dali_root]["power_state"] == "VERIFIED"
