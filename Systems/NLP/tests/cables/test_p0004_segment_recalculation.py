# ruff: noqa: E501
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import func, select, update

from nl_project_2.cables import (
    CablePointInput,
    CableService,
    RouteMethod,
    calculate_segment_length,
    conduit_is_present,
)
from nl_project_2.objects.models import ProjectCard, ProjectSettings
from nl_project_2.objects.service import ObjectService
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    board,
    cable_length_fact,
    cable_line,
    cable_point,
    cable_point_field_device,
    cable_segment,
    cable_topology_endpoint,
    conduit,
    conduit_segment_assignment,
    field_device,
    field_port,
    instance_resource,
    passport_resource_definition,
    project,
    project_instance,
)
from nl_project_2.persistence.uow import UnitOfWork


def _project(database):
    objects = ObjectService(database.engine)
    project_id = objects.create_project(ProjectCard(name="P0_004", project_code="P0004"))
    building_id = objects.add_building(project_id, "B")
    room_a = objects.add_room(
        project_id=project_id,
        building_id=building_id,
        name="A",
        base_mark_mm=-250,
        height_m="2.8",
        marking_color="#FFFFFF",
    )
    room_b = objects.add_room(
        project_id=project_id,
        building_id=building_id,
        name="B",
        base_mark_mm=-150,
        height_m="3.0",
        marking_color="#FFFFFF",
    )
    objects.save_settings(project_id, ProjectSettings(cable_reserve_at_board_m=Decimal("1.5")))
    return objects, project_id, room_a, room_b, building_id


def _point(uow, project_id, line_id, room_id, ordinal, x, y, h=300, *, mechanisms=1):
    point_id = new_id()
    uow.execute(
        cable_point.insert().values(
            id=point_id,
            project_id=project_id,
            cable_line_id=line_id,
            field_device_id=None,
            point_kind="DEVICE_POINT",
            ordinal=ordinal,
            logical_identity=f"{line_id}:{ordinal}",
            origin_kind="PROJECT",
            migration_state="CONFIRMED",
            location_json={"x": x, "y": y},
        )
    )
    for index in range(mechanisms):
        device_id = new_id()
        uow.execute(
            field_device.insert().values(
                id=device_id,
                project_id=project_id,
                block_kind="SOCKET_IN",
                room_id=room_id,
                normalized_fields_json={"MOUNT_HEIGHT": str(h), "MECHANISM": index},
            )
        )
        uow.execute(
            cable_point_field_device.insert().values(
                id=new_id(),
                project_id=project_id,
                cable_point_id=point_id,
                field_device_id=device_id,
            )
        )
    endpoint_id = new_id()
    uow.execute(
        cable_topology_endpoint.insert().values(
            id=endpoint_id,
            project_id=project_id,
            cable_line_id=line_id,
            endpoint_kind="TOPOLOGY_POINT",
            cable_point_id=point_id,
        )
    )
    return endpoint_id, point_id


def _graph(database, project_id, rooms, *, routes, coords=None, shared_mechanisms=1):
    coords = coords or [(0, 0, 300), (1000, 2000, 300), (2000, 2000, 600)]
    line_id = new_id()
    with UnitOfWork(database.engine) as uow:
        uow.execute(
            cable_line.insert().values(
                id=line_id,
                project_id=project_id,
                designation=line_id[:8],
                system_kind="POWER",
                cable_facts_json={"CABLE_TYPE": "NYM"},
            )
        )
        endpoints = []
        for ordinal, (x, y, h) in enumerate(coords):
            endpoints.append(
                _point(
                    uow,
                    project_id,
                    line_id,
                    rooms[min(ordinal, len(rooms) - 1)],
                    ordinal,
                    x,
                    y,
                    h,
                    mechanisms=shared_mechanisms if ordinal == 1 else 1,
                )[0]
            )
        segment_ids = []
        for source_index, target_index, route, tube in routes:
            segment_id = new_id()
            segment_ids.append(segment_id)
            uow.execute(
                cable_segment.insert().values(
                    id=segment_id,
                    project_id=project_id,
                    cable_line_id=line_id,
                    source_endpoint_id=endpoints[source_index],
                    target_endpoint_id=endpoints[target_index],
                    mount_way=route,
                    gofra_type=tube or None,
                    origin_kind="PROJECT",
                    migration_state="CONFIRMED",
                )
            )
        uow.commit()
    return line_id, segment_ids, endpoints


def _rows(database):
    with database.engine.connect() as connection:
        return (
            [dict(r) for r in connection.execute(select(cable_segment)).mappings()],
            [dict(r) for r in connection.execute(select(cable_length_fact)).mappings()],
            [dict(r) for r in connection.execute(select(conduit)).mappings()],
            [dict(r) for r in connection.execute(select(conduit_segment_assignment)).mappings()],
        )


@pytest.mark.parametrize(
    ("route", "expected"),
    [
        (RouteMethod.FLOOR, "4.1"),
        (RouteMethod.CEILING, "8.4"),
        (RouteMethod.WALL, "3"),
        (RouteMethod.CABLE_CHANNEL, "3"),
    ],
)
def test_geometry_contract(route, expected):
    first = CablePointInput.from_values(
        x_mm=0, y_mm=0, mount_height_mm=300, base_mark_mm=-250, room_height_m="2.8"
    )
    second = CablePointInput.from_values(
        x_mm=1000, y_mm=2000, mount_height_mm=300, base_mark_mm=-150, room_height_m="3.0"
    )
    assert calculate_segment_length(first, second, route)[0] == Decimal(expected)


def test_missing_geometry_is_incomplete_not_zero(database):
    _objects, project_id, room_a, room_b, _building = _project(database)
    line_id, segments, _ = _graph(
        database, project_id, (room_a, room_b), routes=[(0, 1, "По полу", "ПНД25")]
    )
    with database.engine.begin() as connection:
        point_id = connection.scalar(select(cable_point.c.id).order_by(cable_point.c.ordinal))
        connection.execute(
            update(cable_point).where(cable_point.c.id == point_id).values(location_json={})
        )
    result = CableService(database.engine).recalculate(project_id=project_id, segment_ids=segments)
    segment_rows, facts, _tubes, _assignments = _rows(database)
    assert result.incomplete_segment_ids == tuple(segments)
    assert segment_rows[0]["calculated_length_m_decimal"] is None
    assert facts[0]["knowledge_status"] == "INCOMPLETE"


@pytest.mark.parametrize(
    ("routes", "expected"),
    [
        ([(0, 1, "В кабель-канале", "")], "3"),
        ([(0, 1, "В кабель-канале", ""), (1, 2, "В кабель-канале", "")], "4"),
        ([(0, 1, "В кабель-канале", ""), (1, 2, "В стене", "")], "4.3"),
    ],
)
def test_unique_segment_aggregation(database, routes, expected):
    _objects, project_id, room_a, room_b, _building = _project(database)
    line_id, segments, _ = _graph(database, project_id, (room_a, room_b), routes=routes)
    CableService(database.engine).recalculate(project_id=project_id, segment_ids=segments)
    assert CableService(database.engine).effective_length(
        project_id, line_id
    ).automatic_m == Decimal(expected)


def test_branch_and_shared_socket_are_not_duplicated(database):
    _objects, project_id, room_a, room_b, _building = _project(database)
    routes = [(0, 1, "В кабель-канале", ""), (1, 2, "В кабель-канале", "")]
    line_id, segments, _ = _graph(
        database, project_id, (room_a, room_b), routes=routes, shared_mechanisms=3
    )
    CableService(database.engine).recalculate(project_id=project_id, segment_ids=segments)
    assert CableService(database.engine).effective_length(project_id, line_id).automatic_m == 4
    assert len(_rows(database)[0]) == 2


def _replace_source(database, project_id, room_id, line_id, segment_id, *, board_owned):
    with UnitOfWork(database.engine) as uow:
        if board_owned:
            board_id = new_id()
            uow.execute(
                board.insert().values(
                    id=board_id, project_id=project_id, designation="QB", board_kind="POWER"
                )
            )
            resource_row = uow.execute(
                select(
                    passport_resource_definition.c.id,
                    passport_resource_definition.c.passport_definition_id,
                )
            ).first()
            resource_definition_id, passport_id = resource_row
            instance_id = new_id()
            uow.execute(
                project_instance.insert().values(
                    id=instance_id,
                    project_id=project_id,
                    designation="QB.I",
                    board_id=board_id,
                    room_id=room_id,
                    passport_definition_id=passport_id,
                    parameters_json={"x": 0, "y": 0, "MOUNT_HEIGHT": 300},
                )
            )
            resource_id = new_id()
            uow.execute(
                instance_resource.insert().values(
                    id=resource_id,
                    project_id=project_id,
                    project_instance_id=instance_id,
                    resource_key="OUT",
                    ordinal=0,
                    passport_resource_definition_id=resource_definition_id,
                    resource_kind="POWER",
                    direction="OUT",
                    medium="COPPER",
                    snapshot_json={},
                )
            )
            endpoint_id = new_id()
            uow.execute(
                cable_topology_endpoint.insert().values(
                    id=endpoint_id,
                    project_id=project_id,
                    cable_line_id=line_id,
                    endpoint_kind="INSTANCE_RESOURCE",
                    instance_resource_id=resource_id,
                )
            )
        else:
            device_id = new_id()
            port_id = new_id()
            uow.execute(
                field_device.insert().values(
                    id=device_id,
                    project_id=project_id,
                    block_kind="FIELD_SOURCE",
                    room_id=room_id,
                    normalized_fields_json={"X": 0, "Y": 0, "MOUNT_HEIGHT": 300},
                )
            )
            uow.execute(
                field_port.insert().values(
                    id=port_id,
                    project_id=project_id,
                    field_device_id=device_id,
                    port_tag="OUT",
                    port_kind="RELAY_OUTPUT",
                    direction="OUT",
                    contract_version=1,
                )
            )
            endpoint_id = new_id()
            uow.execute(
                cable_topology_endpoint.insert().values(
                    id=endpoint_id,
                    project_id=project_id,
                    cable_line_id=line_id,
                    endpoint_kind="FIELD_PORT",
                    field_port_id=port_id,
                )
            )
        uow.execute(
            update(cable_segment)
            .where(cable_segment.c.id == segment_id)
            .values(source_endpoint_id=endpoint_id)
        )
        uow.commit()


@pytest.mark.parametrize(("board_owned", "reserve"), [(False, "0"), (True, "1.5")])
def test_board_reserve_depends_on_physical_source(database, board_owned, reserve):
    _objects, project_id, room_a, room_b, _building = _project(database)
    line_id, segments, _ = _graph(
        database, project_id, (room_a, room_b), routes=[(0, 1, "В кабель-канале", "")]
    )
    _replace_source(database, project_id, room_a, line_id, segments[0], board_owned=board_owned)
    CableService(database.engine).recalculate(project_id=project_id, segment_ids=segments)
    result = CableService(database.engine).effective_length(project_id, line_id)
    assert result.board_reserve_m == Decimal(reserve)


@pytest.mark.parametrize(
    ("mount_way", "tube", "present"),
    [
        ("По полу", "ПНД25", True),
        ("По потолку", "", False),
        ("По потолку", "ПНД25", True),
        ("В стене", "", False),
        ("В стене", "ПНД25", True),
        ("В кабель-канале", "", False),
    ],
)
def test_conduit_presence_matrix(mount_way, tube, present):
    assert conduit_is_present(mount_way, tube) is present


def test_manual_precedence_and_geometry_independence(database):
    _objects, project_id, room_a, room_b, _building = _project(database)
    line_id, segments, _ = _graph(
        database, project_id, (room_a, room_b), routes=[(0, 1, "По полу", "ПНД25")]
    )
    service = CableService(database.engine)
    service.recalculate(project_id=project_id, segment_ids=segments)
    conduit_before = _rows(database)[2][0]["length_m_decimal"]
    assert service.set_line_length_adjustments(
        project_id=project_id, cable_line_id=line_id, additional_m=2
    ).effective_m == Decimal("6.1")
    assert (
        service.set_line_length_adjustments(
            project_id=project_id, cable_line_id=line_id, additional_m=99, manual_full_m=5
        ).effective_m
        == 5
    )
    assert _rows(database)[2][0]["length_m_decimal"] == conduit_before


def test_deterministic_number_and_no_gap_fill(database):
    _objects, project_id, room_a, room_b, _building = _project(database)
    service = CableService(database.engine)
    service.create_empty_conduit(
        project_id=project_id, designation="002.PND25", conduit_type="ПНД25"
    )
    service.create_empty_conduit(
        project_id=project_id, designation="010.PND25", conduit_type="ПНД25"
    )
    _line, segments, _ = _graph(
        database, project_id, (room_a, room_b), routes=[(0, 1, "По полу", "ПНД25")]
    )
    service.recalculate(project_id=project_id, segment_ids=segments)
    assert {row["designation"] for row in _rows(database)[2]} == {
        "002.PND25",
        "010.PND25",
        "011.PND25",
    }


def test_dedicated_shared_and_confirmed_conduit_lengths(database):
    _objects, project_id, room_a, room_b, _building = _project(database)
    service = CableService(database.engine)
    first_line, first_segments, _ = _graph(
        database, project_id, (room_a, room_b), routes=[(0, 1, "По полу", "ПНД25")]
    )
    second_line, second_segments, _ = _graph(
        database, project_id, (room_a, room_b), routes=[(0, 1, "По полу", "ПНД25")]
    )
    service.recalculate(project_id=project_id, segment_ids=first_segments + second_segments)
    tubes = _rows(database)[2]
    assignments = _rows(database)[3]
    first_tube_id = next(
        row["conduit_id"] for row in assignments if row["cable_segment_id"] == first_segments[0]
    )
    first_tube = next(row for row in tubes if row["id"] == first_tube_id)
    assert Decimal(first_tube["length_m_decimal"]) == Decimal("4.1")
    service.move_segment_to_conduit(
        project_id=project_id,
        cable_segment_id=second_segments[0],
        target_conduit_id=first_tube["id"],
    )
    assert (
        next(row for row in _rows(database)[2] if row["id"] == first_tube["id"])["length_m_decimal"]
        is None
    )
    service.update_conduit_length(
        project_id=project_id, conduit_id=first_tube["id"], length_m="12.5"
    )
    service.recalculate(project_id=project_id, segment_ids=first_segments + second_segments)
    assert Decimal(
        next(row for row in _rows(database)[2] if row["id"] == first_tube["id"])["length_m_decimal"]
    ) == Decimal("12.5")
    assert {row["cable_line_id"] for row in _rows(database)[0]} == {first_line, second_line}


def test_move_one_segment_does_not_move_sibling(database):
    _objects, project_id, room_a, room_b, _building = _project(database)
    line_id, segments, _ = _graph(
        database,
        project_id,
        (room_a, room_b),
        routes=[(0, 1, "По полу", "ПНД25"), (1, 2, "По полу", "ПНД25")],
    )
    service = CableService(database.engine)
    service.recalculate(project_id=project_id, segment_ids=segments)
    target = service.create_empty_conduit(
        project_id=project_id, designation="050.PND32", conduit_type="ПНД32"
    )
    service.move_segment_to_conduit(
        project_id=project_id, cable_segment_id=segments[0], target_conduit_id=target
    )
    assignments = {row["cable_segment_id"]: row["conduit_id"] for row in _rows(database)[3]}
    assert assignments[segments[0]] == target
    assert assignments[segments[1]] != target


def test_auto_empty_deleted_user_empty_retained(database):
    _objects, project_id, room_a, room_b, _building = _project(database)
    line_id, segments, _ = _graph(
        database, project_id, (room_a, room_b), routes=[(0, 1, "По полу", "ПНД25")]
    )
    service = CableService(database.engine)
    service.recalculate(project_id=project_id, segment_ids=segments)
    user = service.create_empty_conduit(
        project_id=project_id, designation="050.PND25", conduit_type="ПНД25"
    )
    service.update_segment_route(
        project_id=project_id,
        cable_segment_id=segments[0],
        route_method=RouteMethod.CABLE_CHANNEL,
    )
    assert [row["id"] for row in _rows(database)[2]] == [user]


def test_room_affected_recalculation_and_idempotent_reopen(database):
    objects, project_id, room_a, room_b, building_id = _project(database)
    first_line, first_segments, _ = _graph(
        database, project_id, (room_a, room_b), routes=[(0, 1, "По полу", "ПНД25")]
    )
    second_line, second_segments, _ = _graph(
        database, project_id, (room_b, room_b), routes=[(0, 1, "По полу", "ПНД25")]
    )
    service = CableService(database.engine)
    service.recalculate(project_id=project_id, segment_ids=first_segments + second_segments)
    before = {
        row["id"]: (row["calculated_length_m_decimal"], row["row_version"])
        for row in _rows(database)[0]
    }
    service.recalculate(project_id=project_id, segment_ids=first_segments + second_segments)
    identical = {
        row["id"]: (row["calculated_length_m_decimal"], row["row_version"])
        for row in _rows(database)[0]
    }
    assert identical == before
    objects.update_room(
        project_id=project_id,
        room_id=room_a,
        building_id=building_id,
        name="A",
        base_mark_mm=-350,
        height_m="2.8",
        marking_color="#FFFFFF",
    )
    after = {
        row["id"]: (row["calculated_length_m_decimal"], row["row_version"])
        for row in _rows(database)[0]
    }
    assert after[first_segments[0]] != before[first_segments[0]]
    assert after[second_segments[0]] == before[second_segments[0]]
    path = database.path
    database.close()
    from nl_project_2.persistence.database import DatabaseManager

    reopened = DatabaseManager().open_existing(path)
    try:
        assert CableService(reopened.engine).effective_length(
            project_id, first_line
        ).automatic_m == Decimal("4.3")
        assert CableService(reopened.engine).effective_length(
            project_id, second_line
        ).automatic_m == Decimal("3.9")
        with reopened.engine.connect() as connection:
            assert (
                connection.scalar(select(func.count()).select_from(conduit_segment_assignment)) == 2
            )
    finally:
        reopened.close()


def test_preview_boundary_does_not_recalculate(database):
    """P0_003 preview boundary is represented by a read-only snapshot of derived rows."""
    _objects, project_id, room_a, room_b, _building = _project(database)
    _line, segments, _ = _graph(
        database, project_id, (room_a, room_b), routes=[(0, 1, "В кабель-канале", "")]
    )
    service = CableService(database.engine)
    service.recalculate(project_id=project_id, segment_ids=segments)
    before = _rows(database)[:2]
    with database.engine.connect() as connection:
        list(
            connection.execute(select(project.c.project_revision).where(project.c.id == project_id))
        )
    assert _rows(database)[:2] == before
