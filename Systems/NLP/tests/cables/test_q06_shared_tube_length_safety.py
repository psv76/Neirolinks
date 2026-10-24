"""Q06 length safety: BUS ownership prevents ordinary-only tube inference/deletion."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from test_p0004_segment_recalculation import _graph, _project, _rows

from nl_project_2.automation import AutomationService
from nl_project_2.cables import CableService
from nl_project_2.cables.recalculation import (
    _remove_assignment_and_empty_auto,
    refresh_conduit_length,
)
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    bus,
    bus_endpoint,
    bus_segment,
    bus_segment_conduit_assignment,
    conduit,
)
from nl_project_2.persistence.uow import UnitOfWork


def _bus_resources(database, project_id):
    automation = AutomationService(database.engine)
    result = []
    for index in range(2):
        receipt = automation.constructor.create_instance(
            project_id=project_id,
            designation=f"Q06.MR6C.{index}",
            passport_key="controller.wb_mr6c_v2",
            product_key="product.wirenboard.wb_mr6c_v2",
            supply_scope="NEIROLINKS",
        )
        result.append(
            next(
                row["id"]
                for row in automation.list_resources(project_id)
                if row["project_instance_id"] == receipt.instance_id
                and row["resource_kind"] == "RS485_INTERFACE"
            )
        )
    return result


def test_bus_member_blocks_inferred_ordinary_tube_length_and_auto_deletion(database):
    _objects, project_id, room_a, room_b, _building = _project(database)
    _line, cable_ids, _endpoints = _graph(
        database,
        project_id,
        (room_a, room_b),
        routes=[(0, 1, "По полу", "ПНД25")],
    )
    CableService(database.engine).recalculate(project_id=project_id, segment_ids=cable_ids)
    tube_id = _rows(database)[2][0]["id"]
    assert Decimal(_rows(database)[2][0]["length_m_decimal"]) == Decimal("5")

    root, target = _bus_resources(database, project_id)
    bus_id, endpoint_id, segment_id = (new_id() for _ in range(3))
    with UnitOfWork(database.engine) as uow:
        uow.execute(
            bus.insert().values(
                id=bus_id,
                project_id=project_id,
                designation="901",
                bus_kind="RS485",
                root_resource_id=root,
                topology_policy="LINEAR_SUFFIX_ORDER",
            )
        )
        uow.execute(
            bus_endpoint.insert().values(
                id=endpoint_id,
                project_id=project_id,
                bus_id=bus_id,
                endpoint_kind="INSTANCE_RESOURCE",
                resource_id=target,
                endpoint_role="DEVICE",
            )
        )
        uow.execute(
            bus_segment.insert().values(
                id=segment_id,
                project_id=project_id,
                bus_id=bus_id,
                source_endpoint_id=None,
                target_endpoint_id=endpoint_id,
                connection_kind="CABLE",
                mount_way="По полу",
            )
        )
        uow.execute(
            bus_segment_conduit_assignment.insert().values(
                id=new_id(),
                project_id=project_id,
                bus_segment_id=segment_id,
                conduit_id=tube_id,
            )
        )
        refresh_conduit_length(uow, project_id, tube_id)
        uow.commit()

    with database.engine.connect() as connection:
        tube = connection.execute(select(conduit).where(conduit.c.id == tube_id)).mappings().one()
        assert tube["length_m_decimal"] is None
        assert tube["path_json"]["length_source"] == "INCOMPLETE_SHARED"

    # Removing last ordinary member must not delete tube still carrying BUS.
    with UnitOfWork(database.engine) as uow:
        _remove_assignment_and_empty_auto(uow, project_id, cable_ids[0], tube_id)
        uow.commit()
    with database.engine.connect() as connection:
        assert connection.scalar(select(conduit.c.id).where(conduit.c.id == tube_id)) == tube_id
        assert (
            connection.scalar(
                select(bus_segment_conduit_assignment.c.id).where(
                    bus_segment_conduit_assignment.c.conduit_id == tube_id
                )
            )
            is not None
        )

    CableService(database.engine).update_conduit_length(
        project_id=project_id, conduit_id=tube_id, length_m="12.5"
    )
    with UnitOfWork(database.engine) as uow:
        refresh_conduit_length(uow, project_id, tube_id)
        uow.commit()
    with database.engine.connect() as connection:
        row = connection.execute(select(conduit).where(conduit.c.id == tube_id)).mappings().one()
        assert Decimal(row["length_m_decimal"]) == Decimal("12.5")
        assert row["path_json"]["length_source"] == "USER_CONFIRMED"
