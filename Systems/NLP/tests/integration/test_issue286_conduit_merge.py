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
    command.apply(plan, confirmed_same_physical_run=True)
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
