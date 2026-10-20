"""Read-only, FK-enforced SQLite proof of physical identity after migration 000000000014."""

from __future__ import annotations

from sqlalchemy import create_engine, event, func, select

from nl_project_2.cables.physical_identity_repository import (
    load_physical_segment_resolutions,
)
from nl_project_2.cables.conduit_audit import load_conduit_membership_audit
from nl_project_2.persistence.schema import (
    board,
    cable_line,
    cable_point,
    cable_segment,
    cable_topology_endpoint,
    conduit,
    conduit_segment_assignment,
    metadata,
    project,
)


def uid(number: int) -> str:
    return f"00000000-0000-4000-8000-{number:012d}"


def test_shared_box_with_different_line_local_endpoints_is_same_physical_interval():
    """Two lines can share cable_point.id while retaining their own endpoints."""

    engine = create_engine("sqlite+pysqlite:///:memory:")
    event.listen(
        engine,
        "connect",
        lambda dbapi_connection, _record: dbapi_connection.execute(
            "PRAGMA foreign_keys=ON"
        ),
    )
    metadata.create_all(engine)
    project_id, board_id, box_id = uid(1), uid(2), uid(3)
    with engine.begin() as connection:
        connection.execute(
            project.insert().values(
                id=project_id,
                project_code="TEST_216",
                name="Test Project",
                card_fields_json={},
            )
        )
        connection.execute(
            board.insert().values(
                id=board_id,
                project_id=project_id,
                designation="ЩР-1",
                board_kind="DISTRIBUTION",
            )
        )
        for index in (1, 2):
            line_id, source_id, source_endpoint_id = (
                uid(100 + index),
                uid(200 + index),
                uid(300 + index),
            )
            connection.execute(
                cable_line.insert().values(
                    id=line_id,
                    project_id=project_id,
                    designation=f"10{index}",
                    system_kind="POWER",
                    board_id=board_id,
                    cable_facts_json={"CABLE_TYPE": "ВВГнг"},
                )
            )
            connection.execute(
                cable_point.insert().values(
                    id=source_id,
                    project_id=project_id,
                    cable_line_id=line_id,
                    point_kind="INTERNAL_SOURCE",
                    ordinal=0,
                    logical_identity=f"root-{index}",
                )
            )
            connection.execute(
                cable_topology_endpoint.insert().values(
                    id=source_endpoint_id,
                    project_id=project_id,
                    cable_line_id=line_id,
                    endpoint_kind="TOPOLOGY_POINT",
                    cable_point_id=source_id,
                )
            )
        # One physical BOX point belongs to line 101's point inventory,
        # but line 102 uses it through its own endpoint after migration 14.
        connection.execute(
            cable_point.insert().values(
                id=box_id,
                project_id=project_id,
                cable_line_id=uid(101),
                point_kind="EL_BOX",
                ordinal=1,
                logical_identity="BOX.010",
            )
        )
        connection.execute(
            conduit.insert().values(
                id=uid(700),
                project_id=project_id,
                designation="001.PND25",
                conduit_number=1,
                conduit_type="ПНД25",
                length_m_decimal="12",
            )
        )
        for index in (1, 2):
            line_id = uid(100 + index)
            endpoint_id = uid(400 + index)
            connection.execute(
                cable_topology_endpoint.insert().values(
                    id=endpoint_id,
                    project_id=project_id,
                    cable_line_id=line_id,
                    endpoint_kind="TOPOLOGY_POINT",
                    cable_point_id=box_id,
                )
            )
            connection.execute(
                cable_segment.insert().values(
                    id=uid(500 + index),
                    project_id=project_id,
                    cable_line_id=line_id,
                    source_endpoint_id=uid(300 + index),
                    target_endpoint_id=endpoint_id,
                    mount_way="По полу",
                )
            )
            connection.execute(
                conduit_segment_assignment.insert().values(
                    id=uid(800 + index),
                    project_id=project_id,
                    conduit_id=uid(700),
                    cable_segment_id=uid(500 + index),
                )
            )

    with engine.connect() as connection:
        before = connection.execute(select(func.count()).select_from(cable_segment)).scalar_one()
        resolved = load_physical_segment_resolutions(connection, project_id)
        after = connection.execute(select(func.count()).select_from(cable_segment)).scalar_one()
        assert before == after == 2
        assert len(resolved) == 2
        assert all(s.complete for s in resolved)
        assert resolved[0].target.boundary.identity == box_id
        assert resolved[1].target.boundary.identity == box_id
        assert resolved[0].span.key() == resolved[1].span.key()
        assert resolved[0].source.boundary.identity == board_id
        audits = load_conduit_membership_audit(connection, project_id)
        assert len(audits) == 1
        assert audits[0].state == "PHYSICAL_MATCH"
        assert audits[0].ordinary_count == 2
        assert audits[0].bus_count == 0
        assert audits[0].physical_span.key() == resolved[0].span.key()

    engine.dispose()
