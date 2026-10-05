from decimal import Decimal

from sqlalchemy import select

from nl_project_2.automation import AutomationService
from nl_project_2.buses import BusService
from nl_project_2.buses.recalculation import recalculate_bus_segments
from nl_project_2.panels import PanelService
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    building,
    bus,
    bus_endpoint,
    bus_segment,
    field_device,
    instance_resource,
    room,
)
from nl_project_2.persistence.uow import UnitOfWork


def _insert_room_and_board_geometry(database):
    project_id = database.test_project_id
    building_id = new_id()
    room_id = new_id()
    with database.engine.begin() as connection:
        connection.execute(
            building.insert().values(
                id=building_id,
                project_id=project_id,
                code="B1",
                normalized_code="b1",
                name="Building",
                display_order=1,
            )
        )
        connection.execute(
            room.insert().values(
                id=room_id,
                project_id=project_id,
                building_id=building_id,
                name="Room",
                normalized_name="room",
                base_mark="0",
                height_m_decimal="3",
            )
        )

    panels = PanelService(database.engine)
    board_id = panels.create_board(
        project_id=project_id,
        designation="B.01",
        title="Board",
        room_id=room_id,
    )

    automation = AutomationService(database.engine)
    receipt = automation.constructor.create_instance(
        project_id=project_id,
        designation="MGE.01",
        passport_key="gateway.wirenboard.wb_mge_v3",
        product_key="product.wirenboard.wb_mge_v3",
        supply_scope="NEIROLINKS",
    )
    panels.assign_instance_to_board(
        project_id=project_id,
        instance_id=receipt.instance_id,
        board_id=board_id,
    )
    with database.engine.connect() as connection:
        root_resource_id = connection.scalar(
            select(instance_resource.c.id).where(
                instance_resource.c.project_instance_id == receipt.instance_id,
                instance_resource.c.resource_kind == "RS485_INTERFACE",
                instance_resource.c.ordinal == 0,
            )
        )
    assert root_resource_id is not None

    with database.engine.begin() as connection:
        connection.execute(
            field_device.insert().values(
                id=new_id(),
                project_id=project_id,
                block_kind="BOARD_IN",
                room_id=room_id,
                normalized_fields_json={
                    "DEVICE_TYPE": "BOARD",
                    "BOARD_ID": "B.01",
                    "BUILDING": "B1",
                    "ROOM": "Room",
                    "X": 0,
                    "Y": 0,
                    "MOUNT_HEIGHT": "1800",
                },
                entity_handle="BOARD1",
                lifecycle="ACTIVE",
            )
        )
    return project_id, room_id, root_resource_id


def _insert_field_device(connection, project_id, room_id, *, handle, bus_point, x, y, mount):
    device_id = new_id()
    connection.execute(
        field_device.insert().values(
            id=device_id,
            project_id=project_id,
            block_kind="SENSOR_MSW",
            room_id=room_id,
            normalized_fields_json={
                "DEVICE_TYPE": "SENSOR",
                "BUS_POINT_ID": bus_point,
                "BUILDING": "B1",
                "ROOM": "Room",
                "X": x,
                "Y": y,
                "MOUNT_HEIGHT": str(mount),
            },
            entity_handle=handle,
            lifecycle="ACTIVE",
        )
    )
    return device_id


def test_bus_segment_lengths_use_board_root_and_ordered_field_device_geometry(database):
    project_id, room_id, root_resource_id = _insert_room_and_board_geometry(database)
    bus_id = new_id()
    endpoint_1 = new_id()
    endpoint_2 = new_id()
    segment_1 = new_id()
    segment_2 = new_id()

    with database.engine.begin() as connection:
        device_1 = _insert_field_device(
            connection,
            project_id,
            room_id,
            handle="D1",
            bus_point="904.001",
            x=1000,
            y=0,
            mount=2000,
        )
        device_2 = _insert_field_device(
            connection,
            project_id,
            room_id,
            handle="D2",
            bus_point="904.002",
            x=2000,
            y=1000,
            mount=300,
        )
        connection.execute(
            bus.insert().values(
                id=bus_id,
                project_id=project_id,
                bus_kind="RS485",
                designation="904",
                root_resource_id=root_resource_id,
                topology_policy="LINEAR_SUFFIX_ORDER",
                cable_type="FTP 5e",
                lifecycle="ACTIVE",
            )
        )
        connection.execute(
            bus_endpoint.insert(),
            [
                {
                    "id": endpoint_1,
                    "project_id": project_id,
                    "bus_id": bus_id,
                    "endpoint_kind": "FIELD_DEVICE",
                    "field_device_id": device_1,
                    "endpoint_role": "DEVICE",
                    "address": "904.001",
                    "endpoint_order": 1,
                },
                {
                    "id": endpoint_2,
                    "project_id": project_id,
                    "bus_id": bus_id,
                    "endpoint_kind": "FIELD_DEVICE",
                    "field_device_id": device_2,
                    "endpoint_role": "DEVICE",
                    "address": "904.002",
                    "endpoint_order": 2,
                },
            ],
        )
        connection.execute(
            bus_segment.insert(),
            [
                {
                    "id": segment_1,
                    "project_id": project_id,
                    "bus_id": bus_id,
                    "source_endpoint_id": None,
                    "target_endpoint_id": endpoint_1,
                    "connection_kind": "CABLE",
                    "mount_way": "По полу",
                    "origin_kind": "PROJECT",
                    "migration_state": "CONFIRMED",
                },
                {
                    "id": segment_2,
                    "project_id": project_id,
                    "bus_id": bus_id,
                    "source_endpoint_id": endpoint_1,
                    "target_endpoint_id": endpoint_2,
                    "connection_kind": "CABLE",
                    "mount_way": "По полу",
                    "origin_kind": "PROJECT",
                    "migration_state": "CONFIRMED",
                },
            ],
        )

    with UnitOfWork(database.engine) as uow:
        changed = recalculate_bus_segments(uow, project_id, bus_ids={bus_id})
        uow.commit()

    assert set(changed) == {segment_1, segment_2}
    with database.engine.connect() as connection:
        lengths = dict(
            connection.execute(
                select(bus_segment.c.id, bus_segment.c.length_m_decimal).where(
                    bus_segment.c.bus_id == bus_id
                )
            ).all()
        )
    assert Decimal(lengths[segment_1]) == Decimal("4.8")
    assert Decimal(lengths[segment_2]) == Decimal("4.3")

    card = next(
        item
        for item in BusService(database.engine).journal_cards(project_id)
        if item["designation"] == "904"
    )
    assert Decimal(card["automatic_m"]) == Decimal("13.915")
    assert Decimal(card["effective_m"]) == Decimal("14")
    assert Decimal(card["effective_m"]) > Decimal(card["automatic_m"])
    assert card["incomplete_segments"] == 0


def test_bus_segment_length_stays_unknown_without_root_board_geometry(database):
    project_id = database.test_project_id
    automation = AutomationService(database.engine)
    receipt = automation.constructor.create_instance(
        project_id=project_id,
        designation="MGE.02",
        passport_key="gateway.wirenboard.wb_mge_v3",
        product_key="product.wirenboard.wb_mge_v3",
        supply_scope="NEIROLINKS",
    )
    with database.engine.connect() as connection:
        root_resource_id = connection.scalar(
            select(instance_resource.c.id).where(
                instance_resource.c.project_instance_id == receipt.instance_id,
                instance_resource.c.resource_kind == "RS485_INTERFACE",
                instance_resource.c.ordinal == 0,
            )
        )
    bus_id = new_id()
    endpoint_id = new_id()
    device_id = new_id()
    segment_id = new_id()
    with database.engine.begin() as connection:
        connection.execute(
            field_device.insert().values(
                id=device_id,
                project_id=project_id,
                block_kind="SENSOR_MSW",
                room_id=None,
                normalized_fields_json={
                    "BUS_POINT_ID": "905.001",
                    "X": 1000,
                    "Y": 1000,
                    "MOUNT_HEIGHT": "2000",
                },
                entity_handle="D3",
                lifecycle="ACTIVE",
            )
        )
        connection.execute(
            bus.insert().values(
                id=bus_id,
                project_id=project_id,
                bus_kind="RS485",
                designation="905",
                root_resource_id=root_resource_id,
                topology_policy="LINEAR_SUFFIX_ORDER",
                lifecycle="ACTIVE",
            )
        )
        connection.execute(
            bus_endpoint.insert().values(
                id=endpoint_id,
                project_id=project_id,
                bus_id=bus_id,
                endpoint_kind="FIELD_DEVICE",
                field_device_id=device_id,
                endpoint_role="DEVICE",
                address="905.001",
                endpoint_order=1,
            )
        )
        connection.execute(
            bus_segment.insert().values(
                id=segment_id,
                project_id=project_id,
                bus_id=bus_id,
                source_endpoint_id=None,
                target_endpoint_id=endpoint_id,
                connection_kind="CABLE",
                mount_way="По полу",
                origin_kind="PROJECT",
                migration_state="CONFIRMED",
            )
        )

    with UnitOfWork(database.engine) as uow:
        recalculate_bus_segments(uow, project_id, bus_ids={bus_id})
        uow.commit()

    with database.engine.connect() as connection:
        assert (
            connection.scalar(
                select(bus_segment.c.length_m_decimal).where(bus_segment.c.id == segment_id)
            )
            is None
        )
