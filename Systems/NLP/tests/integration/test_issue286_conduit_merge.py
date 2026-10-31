"""Issue #286: actual transactional conduit merge and segment transfer."""

from pathlib import Path

import pytest
from sqlalchemy import select, update

from nl_project_2.cables import CableService
from nl_project_2.cables.route_commands import RouteConduitCommands, RouteMutationError
from nl_project_2.persistence.schema import (
    cable_segment,
    conduit,
    conduit_segment_assignment,
    project,
)


@pytest.fixture
def routing(database, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "cables"))
    from test_p0004_segment_recalculation import _graph, _project

    _objects, pid, a, b, _building = _project(database)
    line_id, segments, _ = _graph(
        database,
        pid,
        (a, b),
        routes=[
            (0, 1, "По потолку", "ПНД25"),
            (1, 2, "По потолку", "ПНД25"),
        ],
    )
    cables = CableService(database.engine)
    cables.recalculate(project_id=pid, segment_ids=segments)
    assignments = {
        sid: cid
        for sid, cid in database.engine.connect().execute(
            select(
                conduit_segment_assignment.c.cable_segment_id,
                conduit_segment_assignment.c.conduit_id,
            )
        )
    }
    assert set(assignments) == set(segments)
    return pid, line_id, segments, assignments, cables


def test_merge_requires_explicit_confirmation_preserves_line_and_retires_only_empty_source(
    database, routing
):
    pid, line, segments, assignments, cables = routing
    first, second = (assignments[sid] for sid in segments)
    command = RouteConduitCommands(database.engine)
    before = dict(assignments)
    plan = command.preview_merge(pid, (first, second), first)
    assert plan.count == 1
    with pytest.raises(RouteMutationError, match="подтверждение"):
        command.apply(plan)
    with database.engine.connect() as conn:
        assert (
            dict(
                conn.execute(
                    select(
                        conduit_segment_assignment.c.cable_segment_id,
                        conduit_segment_assignment.c.conduit_id,
                    )
                ).all()
            )
            == before
        )
    command.apply(plan, confirmed_same_physical_run=True)
    with database.engine.connect() as conn:
        assigned = dict(
            conn.execute(
                select(
                    conduit_segment_assignment.c.cable_segment_id,
                    conduit_segment_assignment.c.conduit_id,
                )
            ).all()
        )
        sources = dict(conn.execute(select(conduit.c.id, conduit.c.lifecycle)).all())
        segments_after = conn.execute(
            select(cable_segment.c.id, cable_segment.c.cable_line_id)
        ).all()
        assert conn.exec_driver_sql("pragma foreign_key_check").all() == []
    assert assigned == {segments[0]: first, segments[1]: first}
    assert sources[first] == "ACTIVE"
    assert sources[second] == "RETIRED"
    assert set(segments_after) == {(sid, line) for sid in segments}
    assert len(cables.list_conduits(pid)) == 1
    with pytest.raises(RouteMutationError):
        command.apply(plan, confirmed_same_physical_run=True)


def test_move_one_segment_not_entire_line_and_stale_plan_rolls_back(database, routing):
    pid, line, segments, assignments, _ = routing
    first, second = (assignments[sid] for sid in segments)
    command = RouteConduitCommands(database.engine)
    plan = command.preview_move(pid, (("CABLE", segments[0]),), second)
    with database.engine.begin() as conn:
        conn.execute(
            update(project)
            .where(project.c.id == pid)
            .values(project_revision=project.c.project_revision + 1)
        )
    with pytest.raises(RouteMutationError, match="изменились"):
        command.apply(plan, confirmed_same_physical_run=True)
    with database.engine.connect() as conn:
        assert (
            conn.scalar(
                select(conduit_segment_assignment.c.conduit_id).where(
                    conduit_segment_assignment.c.cable_segment_id == segments[0]
                )
            )
            == first
        )
    latest = command.preview_move(pid, (("CABLE", segments[0]),), second)
    command.apply(latest, confirmed_same_physical_run=True)
    with database.engine.connect() as conn:
        assert set(conn.execute(select(conduit_segment_assignment.c.conduit_id)).scalars()) == {
            second
        }


def test_incompatible_conduits_fail_closed_without_writes(database, routing):
    pid, _line, segments, assignments, _ = routing
    first, second = (assignments[sid] for sid in segments)
    with database.engine.begin() as conn:
        conn.execute(update(conduit).where(conduit.c.id == second).values(color="Красный"))
    command = RouteConduitCommands(database.engine)
    with pytest.raises(RouteMutationError, match="различаются"):
        command.preview_merge(pid, (first, second), first)
    with database.engine.connect() as conn:
        assert set(conn.execute(select(conduit.c.lifecycle)).scalars()) == {"ACTIVE"}


def test_merge_rollback_on_cable_fact_update_failure(database, routing, monkeypatch):
    pid, _line, segments, assignments, _ = routing
    first, second = (assignments[sid] for sid in segments)
    command = RouteConduitCommands(database.engine)
    plan = command.preview_merge(pid, (first, second), first)

    def fail(*_args, **_kwargs):
        raise RuntimeError("injected mid-transaction fault")

    monkeypatch.setattr(CableService, "_set_segment_conduit_facts", fail)
    with pytest.raises(RuntimeError, match="injected"):
        command.apply(plan, confirmed_same_physical_run=True)
    with database.engine.connect() as conn:
        assert (
            conn.scalar(
                select(conduit_segment_assignment.c.conduit_id).where(
                    conduit_segment_assignment.c.cable_segment_id == segments[1]
                )
            )
            == second
        )
        assert set(conn.execute(select(conduit.c.lifecycle)).scalars()) == {"ACTIVE"}


def test_merge_mixed_cable_and_bus_membership_is_one_transaction(database, routing):
    from nl_project_2.automation import AutomationService
    from nl_project_2.buses import BusService
    from nl_project_2.persistence.ids import new_id
    from nl_project_2.persistence.schema import (
        bus_segment,
        bus_segment_conduit_assignment,
    )

    pid, _line, cable_segments, assignments, _ = routing
    first, second = (assignments[sid] for sid in cable_segments)
    automation = AutomationService(database.engine)
    resources = []
    for ordinal in range(2):
        result = automation.constructor.create_instance(
            project_id=pid,
            designation=f"BUS-ROUTE-{ordinal}",
            passport_key="controller.wb_mr6c_v2",
            product_key="product.wirenboard.wb_mr6c_v2",
            supply_scope="NEIROLINKS",
        )
        resources.append(
            next(
                row["id"]
                for row in automation.list_resources(pid)
                if row["project_instance_id"] == result.instance_id
                and row["resource_kind"] == "RS485_INTERFACE"
            )
        )
    bus = BusService(database.engine).create_rs485_bus(
        project_id=pid,
        designation="901",
        root_resource_id=resources[0],
        points=({"resource_id": resources[1], "cable_id": "901.001", "x_mm": 1000, "y_mm": 0},),
    )
    with database.engine.begin() as conn:
        bsid = conn.scalar(select(bus_segment.c.id).where(bus_segment.c.bus_id == bus.bus_id))
        conn.execute(
            update(bus_segment)
            .where(bus_segment.c.id == bsid)
            .values(mount_way="По потолку", gofra_type="???25")
        )
        conn.execute(
            bus_segment_conduit_assignment.insert().values(
                id=new_id(),
                project_id=pid,
                bus_segment_id=bsid,
                conduit_id=second,
            )
        )
    command = RouteConduitCommands(database.engine)
    plan = command.preview_merge(pid, (first, second), first)
    assert {(kind, sid) for kind, sid, _source, _version in plan.members} == {
        ("CABLE", cable_segments[1]),
        ("BUS", bsid),
    }
    assert plan.position.requires_exception
    with pytest.raises(RouteMutationError):
        command.apply(plan, confirmed_same_physical_run=True)
    command.apply(
        plan,
        confirmed_same_physical_run=True,
        confirmed_position_exception=True,
    )
    with database.engine.connect() as conn:
        assert (
            conn.scalar(
                select(bus_segment_conduit_assignment.c.conduit_id).where(
                    bus_segment_conduit_assignment.c.bus_segment_id == bsid
                )
            )
            == first
        )
        bus_row = conn.execute(
            select(bus_segment.c.gofra_id, bus_segment.c.gofra_type).where(bus_segment.c.id == bsid)
        ).one()
        assert bus_row.gofra_id is not None and bus_row.gofra_type == "ПНД25"
        assert conn.scalar(select(conduit.c.lifecycle).where(conduit.c.id == second)) == "RETIRED"
        assert conn.exec_driver_sql("pragma foreign_key_check").all() == []


def test_disagreeing_saved_lengths_become_unconfirmed_not_added(database, routing):
    pid, _line, segments, assignments, _ = routing
    first, second = (assignments[sid] for sid in segments)
    with database.engine.begin() as conn:
        conn.execute(
            update(conduit)
            .where(conduit.c.id == first)
            .values(length_m_decimal="23", path_json={"length_source": "USER_CONFIRMED"})
        )
        conn.execute(
            update(conduit)
            .where(conduit.c.id == second)
            .values(length_m_decimal="32", path_json={"length_source": "USER_CONFIRMED"})
        )
    command = RouteConduitCommands(database.engine)
    plan = command.preview_merge(pid, (first, second), first)
    assert any("длины" in warning.lower() for warning in plan.warnings)
    command.apply(plan, confirmed_same_physical_run=True)
    with database.engine.connect() as conn:
        row = conn.execute(
            select(conduit.c.length_m_decimal, conduit.c.path_json).where(conduit.c.id == first)
        ).one()
        assert row.length_m_decimal is None
        assert row.path_json["length_source"] == "INCOMPLETE_SHARED"


def _change_target_position(database, segment_id, *, x=None, y=None, height=None):
    """Edit stored DWG evidence only in pytest's ephemeral database."""
    from nl_project_2.persistence.schema import (
        cable_point,
        cable_point_field_device,
        cable_topology_endpoint,
        field_device,
    )

    with database.engine.begin() as conn:
        target = conn.scalar(
            select(cable_segment.c.target_endpoint_id).where(cable_segment.c.id == segment_id)
        )
        point_id = conn.scalar(
            select(cable_topology_endpoint.c.cable_point_id).where(
                cable_topology_endpoint.c.id == target
            )
        )
        if x is not None or y is not None:
            current = dict(
                conn.scalar(select(cable_point.c.location_json).where(cable_point.c.id == point_id))
            )
            if x is not None:
                current["x"] = x
            if y is not None:
                current["y"] = y
            conn.execute(
                update(cable_point)
                .where(cable_point.c.id == point_id)
                .values(location_json=current, row_version=cable_point.c.row_version + 1)
            )
        if height is not None:
            device_id = conn.scalar(
                select(cable_point_field_device.c.field_device_id).where(
                    cable_point_field_device.c.cable_point_id == point_id
                )
            )
            current = dict(
                conn.scalar(
                    select(field_device.c.normalized_fields_json).where(
                        field_device.c.id == device_id
                    )
                )
            )
            current["MOUNT_HEIGHT"] = height
            conn.execute(
                update(field_device)
                .where(field_device.c.id == device_id)
                .values(
                    normalized_fields_json=current,
                    row_version=field_device.c.row_version + 1,
                )
            )


def test_position_tolerance_exact_xy_one_metre_is_allowed(database, routing):
    pid, _line, segments, assignment, _ = routing
    first, second = (assignment[sid] for sid in segments)
    plan = RouteConduitCommands(database.engine).preview_merge(pid, (first, second), first)
    assert plan.position.point_count == 2
    assert plan.position.max_xy_mm == 1000
    assert plan.position.max_height_mm == 300
    assert not plan.position.requires_exception


def test_position_tolerance_xy_over_one_metre_requires_separate_ack(database, routing):
    pid, _line, segments, assignment, _ = routing
    first, second = (assignment[sid] for sid in segments)
    _change_target_position(database, segments[1], x=2001)
    cmd = RouteConduitCommands(database.engine)
    plan = cmd.preview_merge(pid, (first, second), first)
    assert plan.position.max_xy_mm == 1001
    assert plan.position.requires_exception
    assert any("XY" in r for r in plan.position.reasons)
    with pytest.raises(RouteMutationError, match="отдельное"):
        cmd.apply(plan, confirmed_same_physical_run=True)
    with database.engine.connect() as conn:
        assert (
            conn.scalar(
                select(conduit_segment_assignment.c.conduit_id).where(
                    conduit_segment_assignment.c.cable_segment_id == segments[1]
                )
            )
            == second
        )
    cmd.apply(
        plan,
        confirmed_same_physical_run=True,
        confirmed_position_exception=True,
    )
    with database.engine.connect() as conn:
        assert conn.scalar(select(conduit.c.lifecycle).where(conduit.c.id == second)) == "RETIRED"


def test_position_tolerance_exact_two_metres_height_is_allowed(database, routing):
    pid, _line, segments, assignment, _ = routing
    first, second = (assignment[sid] for sid in segments)
    _change_target_position(database, segments[0], height="0")
    _change_target_position(database, segments[1], height="2000")
    plan = RouteConduitCommands(database.engine).preview_merge(pid, (first, second), first)
    assert plan.position.max_height_mm == 2000
    assert not plan.position.requires_exception


def test_position_tolerance_height_over_two_metres_requires_extra_ack(database, routing):
    pid, _line, segments, assignment, _ = routing
    first, second = (assignment[sid] for sid in segments)
    _change_target_position(database, segments[0], height="0")
    _change_target_position(database, segments[1], height="2001")
    plan = RouteConduitCommands(database.engine).preview_merge(pid, (first, second), first)
    assert plan.position.max_height_mm == 2001
    assert plan.position.requires_exception


def test_position_unknown_height_is_not_silently_accepted(database, routing):
    pid, _line, segments, assignment, _ = routing
    first, second = (assignment[sid] for sid in segments)
    _change_target_position(database, segments[1], height="")
    cmd = RouteConduitCommands(database.engine)
    plan = cmd.preview_merge(pid, (first, second), first)
    assert plan.position.requires_exception
    assert plan.position.max_xy_mm is None
    assert plan.position.max_height_mm is None
    with pytest.raises(RouteMutationError):
        cmd.apply(plan, confirmed_same_physical_run=True)


def test_position_change_after_preview_invalidates_even_exception_confirmation(database, routing):
    pid, _line, segments, assignment, _ = routing
    first, second = (assignment[sid] for sid in segments)
    cmd = RouteConduitCommands(database.engine)
    plan = cmd.preview_merge(pid, (first, second), first)
    _change_target_position(database, segments[1], x=3000)
    with pytest.raises(RouteMutationError, match="измен"):
        cmd.apply(
            plan,
            confirmed_same_physical_run=True,
            confirmed_position_exception=True,
        )
    with database.engine.connect() as conn:
        assert conn.scalar(select(conduit.c.lifecycle).where(conduit.c.id == second)) == "ACTIVE"


def test_position_maximum_across_three_terminal_devices(database, monkeypatch):
    from nl_project_2.cables.route_position_check import assess_terminal_positions

    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "cables"))
    from test_p0004_segment_recalculation import _graph, _project

    _objects, pid, a, b, _ = _project(database)
    _line, segments, _ = _graph(
        database,
        pid,
        (a, b),
        coords=[(-200, 0, 500), (0, 0, 500), (900, 0, 500), (1800, 0, 500)],
        routes=[
            (0, 1, "По потолку", "ПНД25"),
            (1, 2, "По потолку", "ПНД25"),
            (2, 3, "По потолку", "ПНД25"),
        ],
    )
    with database.engine.connect() as conn:
        assessment = assess_terminal_positions(conn, pid, [("CABLE", sid) for sid in segments])
    assert assessment.point_count == 3
    assert assessment.max_xy_mm == 1800
    assert assessment.requires_exception


# Issue #216 Q08 — manual final quantity belongs to one confirmed physical Conduit.
def test_confirm_shared_conduit_length_once_without_changing_electrical_ends(database, routing):
    from nl_project_2.cables.conduit_length_confirmation import (
        ConduitLengthConfirmation,
        ConduitLengthConfirmationError,
    )

    pid, line_id, segments, assignments, cables = routing
    first, second = (assignments[sid] for sid in segments)
    merge = RouteConduitCommands(database.engine)
    merge.apply(
        merge.preview_merge(pid, (first, second), first),
        confirmed_same_physical_run=True,
    )
    service = ConduitLengthConfirmation(database.engine)
    plan = service.preview(pid, first)
    assert {(kind, sid) for kind, sid, _version in plan.members} == {
        ("CABLE", segments[0]),
        ("CABLE", segments[1]),
    }
    with pytest.raises(ConduitLengthConfirmationError, match="подтверждение"):
        service.apply(
            plan,
            final_length_m="16.5",
            justification="Проверенный маршрут трубы по плану",
        )
    with database.engine.connect() as conn:
        assert conn.scalar(select(conduit.c.length_m_decimal).where(conduit.c.id == first)) is None
        before = dict(
            conn.execute(
                select(
                    conduit_segment_assignment.c.cable_segment_id,
                    conduit_segment_assignment.c.conduit_id,
                )
            ).all()
        )
        line_lengths_before = dict(
            conn.execute(
                select(cable_segment.c.id, cable_segment.c.calculated_length_m_decimal)
            ).all()
        )
        rev_before = conn.scalar(select(project.c.project_revision).where(project.c.id == pid))
    service.apply(
        plan,
        final_length_m="16.5",
        justification="Проверенный маршрут трубы по плану",
        confirmed_physical_length=True,
    )
    with database.engine.connect() as conn:
        tube = conn.execute(
            select(conduit.c.length_m_decimal, conduit.c.path_json).where(conduit.c.id == first)
        ).one()
        assert tube.length_m_decimal == "16.5"
        assert tube.path_json["length_source"] == "USER_CONFIRMED"
        assert len(tube.path_json["manual_length_member_keys"]) == 2
        assert (
            dict(
                conn.execute(
                    select(
                        conduit_segment_assignment.c.cable_segment_id,
                        conduit_segment_assignment.c.conduit_id,
                    )
                ).all()
            )
            == before
        )
        assert (
            dict(
                conn.execute(
                    select(cable_segment.c.id, cable_segment.c.calculated_length_m_decimal)
                ).all()
            )
            == line_lengths_before
        )
        assert (
            conn.scalar(select(project.c.project_revision).where(project.c.id == pid))
            == rev_before + 1
        )
        assert conn.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    cables.recalculate(project_id=pid, segment_ids=segments)
    with database.engine.connect() as conn:
        assert (
            conn.scalar(select(conduit.c.length_m_decimal).where(conduit.c.id == first)) == "16.5"
        )
    with pytest.raises(ConduitLengthConfirmationError, match="изменились"):
        service.apply(
            plan,
            final_length_m="17",
            justification="Повтор устаревшего подтверждения",
            confirmed_physical_length=True,
        )


@pytest.mark.parametrize("bad", [None, "", "-1", "0", "NaN", "Infinity", "abc"])
def test_manual_tube_length_rejects_invalid_values(database, routing, bad):
    from nl_project_2.cables.conduit_length_confirmation import (
        ConduitLengthConfirmation,
        ConduitLengthConfirmationError,
    )

    pid, _line, segments, assigned, _cables = routing
    tube_id = assigned[segments[0]]
    service = ConduitLengthConfirmation(database.engine)
    plan = service.preview(pid, tube_id)
    with pytest.raises(ConduitLengthConfirmationError):
        service.apply(
            plan,
            final_length_m=bad,
            justification="Сверено",
            confirmed_physical_length=True,
        )


def test_manual_length_is_rejected_after_stale_project_revision(database, routing):
    from nl_project_2.cables.conduit_length_confirmation import (
        ConduitLengthConfirmation,
        ConduitLengthConfirmationError,
    )

    pid, _line, segments, assigned, _cables = routing
    tube_id = assigned[segments[0]]
    service = ConduitLengthConfirmation(database.engine)
    plan = service.preview(pid, tube_id)
    with database.engine.begin() as conn:
        conn.execute(
            update(project)
            .where(project.c.id == pid)
            .values(project_revision=project.c.project_revision + 1)
        )
    with pytest.raises(ConduitLengthConfirmationError, match="изменились"):
        service.apply(
            plan,
            final_length_m="18",
            justification="Сверено",
            confirmed_physical_length=True,
        )
    with database.engine.connect() as conn:
        assert (
            conn.scalar(select(conduit.c.path_json).where(conduit.c.id == tube_id))["length_source"]
            != "USER_CONFIRMED"
        )


def test_manual_length_blocked_for_empty_tube(database, routing):
    from nl_project_2.cables.conduit_length_confirmation import (
        ConduitLengthConfirmation,
        ConduitLengthConfirmationError,
    )
    from nl_project_2.persistence.ids import new_id

    pid, _line, _segments, _assigned, _cables = routing
    tube_id = new_id()
    with database.engine.begin() as conn:
        conn.execute(
            conduit.insert().values(
                id=tube_id,
                project_id=pid,
                designation="999.ПНД25",
                conduit_number=999,
                conduit_type="ПНД25",
                path_json={"origin": "AUTO_SEGMENT"},
                lifecycle="ACTIVE",
            )
        )
    with pytest.raises(ConduitLengthConfirmationError, match="пустой трубы"):
        ConduitLengthConfirmation(database.engine).preview(pid, tube_id)


def test_manual_length_requires_auditable_reason(database, routing):
    from nl_project_2.cables.conduit_length_confirmation import (
        ConduitLengthConfirmation,
        ConduitLengthConfirmationError,
    )

    pid, _line, segments, assigned, _cables = routing
    service = ConduitLengthConfirmation(database.engine)
    plan = service.preview(pid, assigned[segments[0]])
    for note in ("", " " * 10, "x" * 501):
        with pytest.raises(ConduitLengthConfirmationError, match="основание"):
            service.apply(
                plan,
                final_length_m="16",
                justification=note,
                confirmed_physical_length=True,
            )
