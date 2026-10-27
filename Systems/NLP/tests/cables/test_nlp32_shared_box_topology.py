"""NL Project 3.2: shared physical junction-box is reusable across cable lines."""
from sqlalchemy import select, update

from nl_project_2.cables import CableService
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import cable_point, cable_topology_endpoint, cable_segment
from nl_project_2.persistence.uow import UnitOfWork
from test_p0004_segment_recalculation import _project, _graph


def test_cross_line_shared_box_is_expanded_without_raw_uuid_error(database):
    _obj, pid, room_a, room_b, _building = _project(database)
    first, _segments_a, endpoints_a = _graph(
        database, pid, (room_a, room_b),
        routes=[(0, 1, "По полу", "ПНД25")],
    )
    second, segments_b, _endpoints_b = _graph(
        database, pid, (room_a, room_b),
        routes=[(0, 1, "По полу", "ПНД25")],
    )
    with UnitOfWork(database.engine) as uow:
        shared_point = uow.execute(
            select(cable_topology_endpoint.c.cable_point_id)
            .where(cable_topology_endpoint.c.id == endpoints_a[1])
        ).scalar_one()
        reference = new_id()
        uow.execute(cable_topology_endpoint.insert().values(
            id=reference, project_id=pid, cable_line_id=second,
            endpoint_kind="TOPOLOGY_POINT", cable_point_id=shared_point,
        ))
        uow.execute(
            update(cable_segment)
            .where(cable_segment.c.id==segments_b[0])
            .values(target_endpoint_id=reference)
        )
        uow.commit()
    service = CableService(database.engine)
    topology = service.topology(pid, second)
    assert len(topology["edges"]) == 1
    target = topology["edges"][0]["target"]
    assert target["endpoint_id"] == reference
    assert target["kind"] == "TOPOLOGY_POINT"
    assert "Точка" not in target["label"] or "отсутств" not in target["label"]
    with database.engine.connect() as conn:
        row = conn.execute(
            select(cable_point.c.cable_line_id)
            .where(cable_point.c.id == shared_point)
        ).scalar_one()
        assert row == first
