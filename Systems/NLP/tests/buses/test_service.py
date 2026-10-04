from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import func, select

from nl_project_2.automation import AutomationService
from nl_project_2.buses import BusError, BusService
from nl_project_2.persistence.database import DatabaseManager
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    bus,
    bus_endpoint,
    functional_relation,
    instance_resource,
    project,
)
from nl_project_2.persistence.uow import UnitOfWork


def _rs485_resources(database, count=5):
    automation = AutomationService(database.engine)
    resources = []
    for index in range(count):
        receipt = automation.constructor.create_instance(
            project_id=database.test_project_id,
            designation=f"WB-{index}",
            passport_key="controller.wb_mr6c_v2",
            product_key="product.wirenboard.wb_mr6c_v2",
            supply_scope="NEIROLINKS",
        )
        resources.append(
            next(
                row["id"]
                for row in automation.list_resources(database.test_project_id)
                if row["project_instance_id"] == receipt.instance_id
                and row["resource_kind"] == "RS485_INTERFACE"
            )
        )
    return resources


def _points(resources):
    coordinates = (("03", 3000, 1000), ("01", 1000, 0), ("04", 4000, 1000), ("02", 2000, 0))
    return tuple(
        {
            "resource_id": resource_id,
            "cable_id": f"901.{int(suffix):03d}",
            "x_mm": x,
            "y_mm": y,
        }
        for resource_id, (suffix, x, y) in zip(resources, coordinates, strict=True)
    )


def _empty_rs485_bus(service, project_id, root_resource_id, designation="901"):
    return service.create_rs485_bus(
        project_id=project_id,
        designation=designation,
        root_resource_id=root_resource_id,
        points=(),
    )


def _second_project(database):
    with database.engine.begin() as connection:
        release_id = connection.scalar(
            select(project.c.active_catalog_release_id).where(
                project.c.id == database.test_project_id
            )
        )
        project_id = new_id()
        connection.execute(
            project.insert().values(
                id=project_id,
                project_code=f"BUS-{project_id[:8]}",
                name="Other bus test",
                card_fields_json={},
                active_catalog_release_id=release_id,
                lifecycle="ACTIVE",
            )
        )
    return project_id


def _create_rs485_resource(database, project_id, designation):
    automation = AutomationService(database.engine)
    receipt = automation.constructor.create_instance(
        project_id=project_id,
        designation=designation,
        passport_key="controller.wb_mr6c_v2",
        product_key="product.wirenboard.wb_mr6c_v2",
        supply_scope="NEIROLINKS",
    )
    resources = automation.constructor.list_resources(project_id)
    return next(
        row
        for row in resources
        if row["project_instance_id"] == receipt.instance_id
        and row["resource_kind"] == "RS485_INTERFACE"
    )


def test_rs485_persists_order_reopens_and_derives_graph(database):
    project_id = database.test_project_id
    root, *endpoints = _rs485_resources(database)
    service = BusService(database.engine)
    receipt = service.create_rs485_bus(
        project_id=project_id,
        designation="901",
        root_resource_id=root,
        points=_points(endpoints),
    )
    stored = service.get_bus(project_id, receipt.bus_id)
    assert [row["address"] for row in stored["endpoints"]] == [
        "901.001",
        "901.002",
        "901.003",
        "901.004",
    ]
    coordinates = {root: (0, 0)}
    coordinates.update(
        {point["resource_id"]: (point["x_mm"], point["y_mm"]) for point in _points(endpoints)}
    )
    topology = service.topology(
        project_id=project_id,
        bus_id=receipt.bus_id,
        coordinates=coordinates,
    )
    assert topology.status == "VERIFIED"
    assert topology.total_length_mm == Decimal("5000")
    with database.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(functional_relation)) == 0

    path = database.path
    database.close()
    reopened = DatabaseManager().open_existing(path)
    try:
        reopened_bus = BusService(reopened.engine).get_bus(project_id, receipt.bus_id)
        assert reopened_bus["designation"] == "901"
        assert len(reopened_bus["endpoints"]) == 4
    finally:
        reopened.close()


def test_invalid_rs485_is_atomic_and_missing_coordinates_are_explainable(database):
    project_id = database.test_project_id
    root, *endpoints = _rs485_resources(database)
    service = BusService(database.engine)
    invalid = [*_points(endpoints)]
    invalid[-1] = {**invalid[-1], "branch": "branch-a"}
    with pytest.raises(BusError, match="RS485_BRANCH_FORBIDDEN"):
        service.create_rs485_bus(
            project_id=project_id,
            designation="901",
            root_resource_id=root,
            points=tuple(invalid),
        )
    with database.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(bus)) == 0
        assert connection.scalar(select(func.count()).select_from(bus_endpoint)) == 0

    receipt = service.create_rs485_bus(
        project_id=project_id,
        designation="901",
        root_resource_id=root,
        points=_points(endpoints),
    )
    topology = service.topology(
        project_id=project_id,
        bus_id=receipt.bus_id,
        coordinates={root: (0, 0)},
    )
    assert topology.status == "INCOMPATIBLE"
    assert len([error for error in topology.errors if error.startswith("MISSING_COORDINATE")]) == 4


def test_add_and_remove_rs485_endpoints_reorder_topology_without_relations(database):
    project_id = database.test_project_id
    root, endpoint_03, endpoint_01, endpoint_02 = _rs485_resources(database, count=4)
    service = BusService(database.engine)
    receipt = _empty_rs485_bus(service, project_id, root)

    for resource_id, cable_id in (
        (endpoint_03, "901.003"),
        (endpoint_01, "901.001"),
        (endpoint_02, "901.002"),
    ):
        service.add_rs485_endpoint(
            project_id=project_id,
            bus_id=receipt.bus_id,
            resource_id=resource_id,
            cable_id=cable_id,
        )

    stored = service.get_bus(project_id, receipt.bus_id)
    assert [(row["address"], row["endpoint_order"]) for row in stored["endpoints"]] == [
        ("901.001", 1),
        ("901.002", 2),
        ("901.003", 3),
    ]
    topology = service.topology(
        project_id=project_id,
        bus_id=receipt.bus_id,
        coordinates={
            root: (0, 0),
            endpoint_01: (1, 0),
            endpoint_02: (2, 0),
            endpoint_03: (3, 0),
        },
    )
    assert topology.edges == (
        (root, endpoint_01),
        (endpoint_01, endpoint_02),
        (endpoint_02, endpoint_03),
    )

    middle_id = next(row["id"] for row in stored["endpoints"] if row["address"] == "901.002")
    result = service.remove_rs485_endpoint(
        project_id=project_id,
        bus_id=receipt.bus_id,
        endpoint_id=middle_id,
    )
    assert result.endpoint_count == 2
    remaining = service.get_bus(project_id, receipt.bus_id)["endpoints"]
    assert [(row["address"], row["endpoint_order"]) for row in remaining] == [
        ("901.001", 1),
        ("901.003", 2),
    ]
    topology = service.topology(
        project_id=project_id,
        bus_id=receipt.bus_id,
        coordinates={root: (0, 0), endpoint_01: (1, 0), endpoint_03: (3, 0)},
    )
    assert topology.edges == ((root, endpoint_01), (endpoint_01, endpoint_03))
    with database.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(functional_relation)) == 0


def test_add_rs485_endpoint_rejects_wrong_project_type_duplicates_and_prefix(database):
    project_id = database.test_project_id
    root, endpoint, duplicate_address, wrong_prefix = _rs485_resources(database, count=4)
    service = BusService(database.engine)
    receipt = _empty_rs485_bus(service, project_id, root)
    foreign_project_id = _second_project(database)
    foreign_resource = _create_rs485_resource(database, foreign_project_id, "FOREIGN.01")
    non_rs485 = next(
        row
        for row in AutomationService(database.engine).constructor.list_resources(project_id)
        if row["resource_kind"] != "RS485_INTERFACE"
    )
    non_rs485_bus_id = new_id()
    with database.engine.begin() as connection:
        connection.execute(
            bus.insert().values(
                id=non_rs485_bus_id,
                project_id=project_id,
                bus_kind="DALI",
                designation="903",
                root_resource_id=wrong_prefix,
                topology_policy="BRANCHED",
                lifecycle="ACTIVE",
            )
        )

    with pytest.raises(BusError, match="Bus not found"):
        service.add_rs485_endpoint(
            project_id=foreign_project_id,
            bus_id=receipt.bus_id,
            resource_id=foreign_resource["id"],
            cable_id="901.001",
        )
    with pytest.raises(BusError, match="requires an RS-485 bus"):
        service.add_rs485_endpoint(
            project_id=project_id,
            bus_id=non_rs485_bus_id,
            resource_id=duplicate_address,
            cable_id="903.001",
        )

    for resource_id, cable_id, error in (
        (foreign_resource["id"], "901.001", "active resources of the Project"),
        (non_rs485["id"], "901.001", "requires only RS485_INTERFACE"),
        (root, "901.001", "distinct resources"),
        (wrong_prefix, "902.001", "WRONG_BUS"),
    ):
        with pytest.raises(BusError, match=error):
            service.add_rs485_endpoint(
                project_id=project_id,
                bus_id=receipt.bus_id,
                resource_id=resource_id,
                cable_id=cable_id,
            )

    service.add_rs485_endpoint(
        project_id=project_id,
        bus_id=receipt.bus_id,
        resource_id=endpoint,
        cable_id="901.001",
    )
    with pytest.raises(BusError, match="DUPLICATE_SUFFIX"):
        service.add_rs485_endpoint(
            project_id=project_id,
            bus_id=receipt.bus_id,
            resource_id=duplicate_address,
            cable_id="901.001",
        )
    with pytest.raises(BusError, match="distinct resources"):
        service.add_rs485_endpoint(
            project_id=project_id,
            bus_id=receipt.bus_id,
            resource_id=endpoint,
            cable_id="901.002",
        )
    assert [row["address"] for row in service.get_bus(project_id, receipt.bus_id)["endpoints"]] == [
        "901.001"
    ]
    with database.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(functional_relation)) == 0


def test_remove_rs485_endpoint_rejects_endpoint_from_another_bus(database):
    project_id = database.test_project_id
    root_1, root_2, endpoint = _rs485_resources(database, count=3)
    service = BusService(database.engine)
    first = _empty_rs485_bus(service, project_id, root_1, "901")
    second = _empty_rs485_bus(service, project_id, root_2, "902")
    service.add_rs485_endpoint(
        project_id=project_id,
        bus_id=second.bus_id,
        resource_id=endpoint,
        cable_id="902.001",
    )
    endpoint_id = service.get_bus(project_id, second.bus_id)["endpoints"][0]["id"]

    with pytest.raises(BusError, match="not found in the selected bus"):
        service.remove_rs485_endpoint(
            project_id=project_id,
            bus_id=first.bus_id,
            endpoint_id=endpoint_id,
        )
    assert len(service.get_bus(project_id, second.bus_id)["endpoints"]) == 1


def test_delete_rs485_bus_preserves_resources_relations_and_unrelated_bus(database):
    project_id = database.test_project_id
    root_1, endpoint_1, root_2, endpoint_2 = _rs485_resources(database, count=4)
    service = BusService(database.engine)
    first = _empty_rs485_bus(service, project_id, root_1, "901")
    second = _empty_rs485_bus(service, project_id, root_2, "902")
    service.add_rs485_endpoint(
        project_id=project_id,
        bus_id=first.bus_id,
        resource_id=endpoint_1,
        cable_id="901.001",
    )
    service.add_rs485_endpoint(
        project_id=project_id,
        bus_id=second.bus_id,
        resource_id=endpoint_2,
        cable_id="902.001",
    )
    with UnitOfWork(database.engine) as uow:
        uow.execute(
            functional_relation.insert().values(
                id=new_id(),
                project_id=project_id,
                relation_kind="TEST_UNRELATED",
                source_resource_id=root_1,
                target_resource_id=endpoint_2,
                parameters_json={},
                command_id=new_id(),
            )
        )
        uow.commit()
    with database.engine.connect() as connection:
        resource_count = connection.scalar(select(func.count()).select_from(instance_resource))

    service.delete_rs485_bus(project_id=project_id, bus_id=first.bus_id)

    with pytest.raises(BusError, match="Bus not found"):
        service.get_bus(project_id, first.bus_id)
    assert service.get_bus(project_id, second.bus_id)["endpoints"][0]["address"] == "902.001"
    with database.engine.connect() as connection:
        stored_resource_count = connection.scalar(
            select(func.count()).select_from(instance_resource)
        )
        assert stored_resource_count == resource_count
        assert (
            connection.scalar(
                select(func.count())
                .select_from(bus_endpoint)
                .where(bus_endpoint.c.bus_id == first.bus_id)
            )
            == 0
        )
        assert connection.scalar(select(func.count()).select_from(functional_relation)) == 1


def test_rs485_resource_candidates_are_project_scoped_labeled_and_read_only(database):
    project_id = database.test_project_id
    first = _create_rs485_resource(database, project_id, "A01")
    second = _create_rs485_resource(database, project_id, "A02")
    foreign_project_id = _second_project(database)
    foreign = _create_rs485_resource(database, foreign_project_id, "FOREIGN.02")
    service = BusService(database.engine)
    _empty_rs485_bus(service, project_id, first["id"])
    with database.engine.connect() as connection:
        before_revision = connection.scalar(
            select(project.c.project_revision).where(project.c.id == project_id)
        )
        before_counts = (
            connection.scalar(select(func.count()).select_from(bus)),
            connection.scalar(select(func.count()).select_from(bus_endpoint)),
            connection.scalar(select(func.count()).select_from(functional_relation)),
        )

    candidates = service.list_rs485_resource_candidates(project_id)

    assert candidates
    assert all(row["resource_designation"] == "RS485" for row in candidates)
    assert all(row["label"].endswith(" / RS485") for row in candidates)
    assert next(row for row in candidates if row["id"] == first["id"])["label"] == ("A01 / RS485")
    assert (
        next(row for row in candidates if row["id"] == first["id"])["technical_identity"]
        == "A01 / RS485[0]"
    )
    assert next(row for row in candidates if row["id"] == first["id"])["source_available"] is False
    assert next(row for row in candidates if row["id"] == second["id"])["source_available"] is True
    assert all(row["endpoint_available"] is True for row in candidates)
    assert foreign["id"] not in {row["id"] for row in candidates}
    with database.engine.connect() as connection:
        assert (
            connection.scalar(select(project.c.project_revision).where(project.c.id == project_id))
            == before_revision
        )
        assert (
            connection.scalar(select(func.count()).select_from(bus)),
            connection.scalar(select(func.count()).select_from(bus_endpoint)),
            connection.scalar(select(func.count()).select_from(functional_relation)),
        ) == before_counts


def test_wb8_rs485_passport_labels_preserve_ids_ordinals_and_bus_read_model(database):
    project_id = database.test_project_id
    automation = AutomationService(database.engine)
    receipt = automation.constructor.create_instance(
        project_id=project_id,
        designation="WB.01",
        passport_key="controller.wiren_board_8_5",
        product_key="product.wirenboard.wb8_4g_64g_ind",
        supply_scope="NEIROLINKS",
    )
    persisted = [
        row
        for row in automation.constructor.list_resources(project_id)
        if row["project_instance_id"] == receipt.instance_id and row["resource_key"] == "RS485"
    ]

    candidates = [
        row
        for row in BusService(database.engine).list_rs485_resource_candidates(project_id)
        if row["project_instance_id"] == receipt.instance_id
    ]
    labels = BusService(database.engine).list_bus_resource_labels(project_id)

    assert [(row["ordinal"], row["user_label"]) for row in persisted] == [
        (0, "WB.01 / RS485-1"),
        (1, "WB.01 / RS485-2"),
    ]
    assert [(row["id"], row["ordinal"]) for row in candidates] == [
        (row["id"], row["ordinal"]) for row in persisted
    ]
    assert [row["label"] for row in candidates] == [
        "WB.01 / RS485-1",
        "WB.01 / RS485-2",
    ]
    assert [labels[row["id"]]["label"] for row in persisted] == [
        "WB.01 / RS485-1",
        "WB.01 / RS485-2",
    ]


def test_rs485_endpoint_commands_persist_after_reopen(database):
    project_id = database.test_project_id
    root, endpoint_03, endpoint_01, endpoint_02 = _rs485_resources(database, count=4)
    service = BusService(database.engine)
    receipt = _empty_rs485_bus(service, project_id, root)
    for resource_id, cable_id in (
        (endpoint_03, "901.003"),
        (endpoint_01, "901.001"),
        (endpoint_02, "901.002"),
    ):
        service.add_rs485_endpoint(
            project_id=project_id,
            bus_id=receipt.bus_id,
            resource_id=resource_id,
            cable_id=cable_id,
        )
    endpoint_02_id = next(
        row["id"]
        for row in service.get_bus(project_id, receipt.bus_id)["endpoints"]
        if row["address"] == "901.002"
    )
    service.remove_rs485_endpoint(
        project_id=project_id,
        bus_id=receipt.bus_id,
        endpoint_id=endpoint_02_id,
    )

    path = database.path
    database.close()
    reopened = DatabaseManager().open_existing(path)
    try:
        stored = BusService(reopened.engine).get_bus(project_id, receipt.bus_id)
        assert stored["root_resource_id"] == root
        assert [(row["address"], row["endpoint_order"]) for row in stored["endpoints"]] == [
            ("901.001", 1),
            ("901.003", 2),
        ]
    finally:
        reopened.close()


def test_bus_journal_read_model_reuses_physical_topology(database):
    project_id = database.test_project_id
    root, *endpoints = _rs485_resources(database)
    service = BusService(database.engine)
    receipt = service.create_rs485_bus(
        project_id=project_id,
        designation="903",
        root_resource_id=root,
        points=tuple(
            {
                **point,
                "cable_id": point["cable_id"].replace("901.", "903."),
            }
            for point in _points(endpoints)
        ),
    )

    cards = service.journal_cards(project_id)
    card = next(item for item in cards if item["id"] == receipt.bus_id)
    assert card["network_kind"] == "BUS"
    assert card["designation"] == "903"
    assert card["system_kind"] == "RS485"
    assert card["board"]
    assert card["incomplete_segments"] == 4
    assert card["effective_m"] is None

    topology = service.journal_topology(project_id, receipt.bus_id)
    assert topology["network_kind"] == "BUS"
    assert topology["root_endpoint"]["reference"] == "903.000"
    assert [edge["target"]["label"] for edge in topology["edges"]] == [
        "903.001",
        "903.002",
        "903.003",
        "903.004",
    ]
    assert all(edge["calculation_status"] == "INCOMPLETE" for edge in topology["edges"])
