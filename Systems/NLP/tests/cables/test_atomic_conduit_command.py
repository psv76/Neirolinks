"""Transactional regression tests for Issue #216. No working DB or DWG."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, event, select, update

from nl_project_2.cables.atomic_conduit_command import (
    ApprovedPhysicalFacts,
    AtomicConduitAssignmentService,
)
from nl_project_2.cables.physical_conduit import (
    AssignmentChange,
    ConduitFact,
    PhysicalAssignmentError,
    PhysicalBoundary,
    PhysicalSpan,
)
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    board,
    bus,
    bus_endpoint,
    bus_segment,
    bus_segment_conduit_assignment,
    cable_line,
    cable_point,
    cable_segment,
    cable_topology_endpoint,
    catalog_release,
    conduit,
    conduit_segment_assignment,
    instance_resource,
    metadata,
    passport_definition,
    passport_resource_definition,
    project,
    project_instance,
)


def uid(index: int) -> str:
    return f"00000000-0000-4000-8000-{index:012d}"


PROJECT = uid(1)
BOARD = uid(2)
BOX = uid(3)
TUBE1 = uid(10)
TUBE2 = uid(11)
S1 = uid(101)
S2 = uid(102)
S3 = uid(103)


def _conduit_facts(tube_id: str, *, mismatched: bool = False) -> ConduitFact:
    return ConduitFact(
        conduit_id=tube_id,
        span=PhysicalSpan(
            PhysicalBoundary("BOARD", BOARD),
            PhysicalBoundary(
                "EL_BOX" if not mismatched else "FIELD_DEVICE",
                BOX if not mismatched else uid(1000),
            ),
        ),
        mount_way="По полу",
        permitted_cable_classes=frozenset({"AC_230"}),
    )


def _seed(connection) -> None:
    connection.execute(
        project.insert().values(
            id=PROJECT,
            project_code="TEST_216",
            name="Test Project",
            card_fields_json={},
        )
    )
    connection.execute(
        board.insert().values(
            id=BOARD,
            project_id=PROJECT,
            designation="ЩР-1",
            board_kind="DISTRIBUTION",
        )
    )
    connection.execute(
        conduit.insert().values(
            id=TUBE1,
            project_id=PROJECT,
            designation="001.PND25",
            conduit_number=1,
            conduit_type="ПНД25",
            color="Синий",
            length_m_decimal="17",
            path_json={"origin": "USER_EMPTY", "length_source": "SEGMENT_GEOMETRY"},
        )
    )
    connection.execute(
        conduit.insert().values(
            id=TUBE2,
            project_id=PROJECT,
            designation="002.PND25",
            conduit_number=2,
            conduit_type="ПНД25",
            color="Синий",
            length_m_decimal="30",
            path_json={"origin": "USER_EMPTY", "length_source": "USER_CONFIRMED"},
        )
    )
    for i, segment_id in enumerate((S1, S2, S3), start=1):
        line_id = uid(200 + i)
        root_point_id = uid(300 + i)
        root_endpoint_id = uid(400 + i)
        box_endpoint_id = uid(500 + i)
        connection.execute(
            cable_line.insert().values(
                id=line_id,
                project_id=PROJECT,
                designation=f"10{i}",
                system_kind="POWER",
                board_id=BOARD,
                cable_facts_json={"CABLE_TYPE": "ВВГнг"},
            )
        )
        connection.execute(
            cable_point.insert().values(
                id=root_point_id,
                project_id=PROJECT,
                cable_line_id=line_id,
                point_kind="INTERNAL_SOURCE",
                ordinal=0,
                logical_identity=f"ROOT-{i}",
            )
        )
        connection.execute(
            cable_topology_endpoint.insert().values(
                id=root_endpoint_id,
                project_id=PROJECT,
                cable_line_id=line_id,
                endpoint_kind="TOPOLOGY_POINT",
                cable_point_id=root_point_id,
            )
        )
        if i == 1:
            connection.execute(
                cable_point.insert().values(
                    id=BOX,
                    project_id=PROJECT,
                    cable_line_id=line_id,
                    point_kind="EL_BOX",
                    ordinal=1,
                    logical_identity="BOX.010",
                )
            )
        connection.execute(
            cable_topology_endpoint.insert().values(
                id=box_endpoint_id,
                project_id=PROJECT,
                cable_line_id=line_id,
                endpoint_kind="TOPOLOGY_POINT",
                cable_point_id=BOX,
            )
        )
        connection.execute(
            cable_segment.insert().values(
                id=segment_id,
                project_id=PROJECT,
                cable_line_id=line_id,
                source_endpoint_id=root_endpoint_id,
                target_endpoint_id=box_endpoint_id,
                mount_way="По полу",
            )
        )
        if i == 1:
            connection.execute(
                conduit_segment_assignment.insert().values(
                    id=new_id(),
                    project_id=PROJECT,
                    cable_segment_id=segment_id,
                    conduit_id=TUBE1,
                )
            )


@pytest.fixture
def database():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    event.listen(
        engine,
        "connect",
        lambda dbapi, _record: dbapi.execute("PRAGMA foreign_keys=ON"),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        _seed(connection)
    try:
        yield engine
    finally:
        engine.dispose()


def _revision(engine) -> int:
    with engine.connect() as connection:
        return connection.execute(
            select(project.c.project_revision).where(project.c.id == PROJECT)
        ).scalar_one()


def _memberships(engine) -> tuple[tuple[str, str], ...]:
    with engine.connect() as connection:
        return tuple(
            sorted(
                connection.execute(
                    select(
                        conduit_segment_assignment.c.cable_segment_id,
                        conduit_segment_assignment.c.conduit_id,
                    )
                ).all()
            )
        )


def _approval(*, incompatible: bool = False):
    def provider(uow, project_id, affected_tubes, affected_segments):
        assert project_id == PROJECT
        assert set(affected_tubes).issubset({TUBE1, TUBE2})
        return ApprovedPhysicalFacts(
            conduit_facts={
                tube_id: _conduit_facts(tube_id, mismatched=incompatible and tube_id == TUBE2)
                for tube_id in affected_tubes
            },
            segment_classes={key: "AC_230" for key in affected_segments},
        )

    return provider


def _mirror(uow, project_id, segment_id, chosen):
    assert project_id == PROJECT
    uow.execute(
        update(cable_segment)
        .where(
            cable_segment.c.project_id == project_id,
            cable_segment.c.id == segment_id,
        )
        .values(
            gofra_type=chosen["conduit_type"] if chosen else None,
            gofra_color=chosen["color"] if chosen else None,
            row_version=cable_segment.c.row_version + 1,
        )
    )


def _service(engine, *, incompatible=False):
    return AtomicConduitAssignmentService(
        engine,
        approval_provider=_approval(incompatible=incompatible),
        cable_mirror_updater=_mirror,
    )


def test_atomic_two_cable_move_commits_once_and_invalidates_auto_length(database):
    service = _service(database)
    result = service.apply(
        project_id=PROJECT,
        expected_project_revision=0,
        expected_current_assignments={("CABLE", S1): TUBE1, ("CABLE", S2): None},
        changes=(
            AssignmentChange("CABLE", S1, TUBE2),
            AssignmentChange("CABLE", S2, TUBE2),
        ),
    )
    assert result.project_revision == 1
    assert result.affected_conduits == (TUBE1, TUBE2)
    assert _revision(database) == 1
    assert _memberships(database) == ((S1, TUBE2), (S2, TUBE2))
    with database.connect() as connection:
        tubes = {row["id"]: row for row in connection.execute(select(conduit)).mappings()}
        assert tubes[TUBE1]["length_m_decimal"] is None
        assert tubes[TUBE1]["path_json"]["length_source"] == "STALE_AFTER_ASSIGNMENT"
        assert tubes[TUBE2]["length_m_decimal"] == "30"
        assert tubes[TUBE2]["path_json"]["length_source"] == "USER_CONFIRMED"


def test_batch_rejection_of_one_wrong_span_rolls_back_everything(database):
    before = _memberships(database)
    with pytest.raises(PhysicalAssignmentError, match="physical boundaries differ"):
        _service(database, incompatible=True).apply(
            project_id=PROJECT,
            expected_project_revision=0,
            expected_current_assignments={("CABLE", S1): TUBE1, ("CABLE", S2): None},
            changes=(
                AssignmentChange("CABLE", S1, TUBE2),
                AssignmentChange("CABLE", S2, TUBE2),
            ),
        )
    assert _revision(database) == 0
    assert _memberships(database) == before


def test_failure_after_changes_still_rolls_back_project_revision_and_tubes(database):
    before = _memberships(database)

    def fail() -> None:
        raise RuntimeError("injected abort before commit")

    with pytest.raises(RuntimeError, match="injected abort"):
        _service(database).apply(
            project_id=PROJECT,
            expected_project_revision=0,
            expected_current_assignments={("CABLE", S1): TUBE1},
            changes=(AssignmentChange("CABLE", S1, TUBE2),),
            failure_hook=fail,
        )
    assert _revision(database) == 0
    assert _memberships(database) == before
    with database.connect() as connection:
        source = connection.execute(select(conduit).where(conduit.c.id == TUBE1)).mappings().one()
        assert source["length_m_decimal"] == "17"


def test_stale_expected_project_revision_denied_before_any_mutation(database):
    with pytest.raises(PhysicalAssignmentError, match="Project was changed"):
        _service(database).apply(
            project_id=PROJECT,
            expected_project_revision=7,
            expected_current_assignments={("CABLE", S1): TUBE1},
            changes=(AssignmentChange("CABLE", S1, TUBE2),),
        )
    assert _revision(database) == 0
    assert _memberships(database) == ((S1, TUBE1),)


def test_without_trusted_approval_or_mirror_callbacks_no_writes(database):
    for service in (
        AtomicConduitAssignmentService(database),
        AtomicConduitAssignmentService(database, approval_provider=_approval()),
    ):
        with pytest.raises(PhysicalAssignmentError):
            service.apply(
                project_id=PROJECT,
                expected_project_revision=0,
                expected_current_assignments={("CABLE", S1): TUBE1},
                changes=(AssignmentChange("CABLE", S1, TUBE2),),
            )
    assert _revision(database) == 0
    assert _memberships(database) == ((S1, TUBE1),)


def test_noop_repeated_request_is_idempotent_and_does_not_invalidate(database):
    result = _service(database).apply(
        project_id=PROJECT,
        expected_project_revision=0,
        expected_current_assignments={("CABLE", S1): TUBE1},
        changes=(AssignmentChange("CABLE", S1, TUBE1),),
    )
    assert not result.applied
    assert result.project_revision == 0
    assert _revision(database) == 0
    with database.connect() as connection:
        tube = connection.execute(select(conduit).where(conduit.c.id == TUBE1)).mappings().one()
        assert tube["length_m_decimal"] == "17"


def test_duplicated_or_unknown_member_in_a_batch_never_writes(database):
    for changes in (
        (AssignmentChange("CABLE", S1, TUBE2), AssignmentChange("CABLE", S1, None)),
        (AssignmentChange("CABLE", S1, TUBE2), AssignmentChange("CABLE", uid(999), TUBE2)),
    ):
        with pytest.raises(PhysicalAssignmentError):
            _service(database).apply(
                project_id=PROJECT,
                expected_project_revision=0,
                expected_current_assignments={("CABLE", S1): TUBE1},
                changes=changes,
            )
        assert _revision(database) == 0
        assert _memberships(database) == ((S1, TUBE1),)


def test_remove_one_of_multiple_segments_is_one_transaction(database):
    result = _service(database).apply(
        project_id=PROJECT,
        expected_project_revision=0,
        expected_current_assignments={("CABLE", S1): TUBE1},
        changes=(AssignmentChange("CABLE", S1, None),),
    )
    assert result.affected_conduits == (TUBE1,)
    assert _memberships(database) == ()
    assert _revision(database) == 1


def test_stale_membership_snapshot_rejected_without_any_write(database):
    with pytest.raises(PhysicalAssignmentError, match="reassigned"):
        _service(database).apply(
            project_id=PROJECT,
            expected_project_revision=0,
            expected_current_assignments={("CABLE", S1): None},
            changes=(AssignmentChange("CABLE", S1, TUBE2),),
        )
    assert _revision(database) == 0
    assert _memberships(database) == ((S1, TUBE1),)


def test_missing_snapshot_identity_rejected_before_commit(database):
    with pytest.raises(PhysicalAssignmentError, match="Exact expected"):
        _service(database).apply(
            project_id=PROJECT,
            expected_project_revision=0,
            expected_current_assignments={},
            changes=(AssignmentChange("CABLE", S1, TUBE2),),
        )
    assert _revision(database) == 0



BUS_TUBE = uid(900)
BUS_SEGMENT = uid(901)
BUS_ROOT_RESOURCE = uid(902)
BUS_TARGET_RESOURCE = uid(903)


def _seed_isolated_bus(connection):
    catalog_id = uid(910)
    passport_id = uid(911)
    passport_resource_id = uid(912)
    instance_id = uid(913)
    bus_id = uid(914)
    endpoint_id = uid(915)
    connection.execute(
        catalog_release.insert().values(
            id=catalog_id,
            release_code="TEST_PHYSICAL_216",
            schema_version=1,
            content_sha256="a" * 64,
            installed_at_utc=datetime.now(UTC),
            status="ACTIVE",
        )
    )
    connection.execute(
        passport_definition.insert().values(
            id=passport_id,
            catalog_release_id=catalog_id,
            passport_key="PHYSICAL_216_CONTROLLER",
            version=1,
            name="Test controller",
            equipment_class="CONTROLLER",
            functional_role="BUS",
            schema_version=1,
            source_reference="TEST_ONLY",
            content_sha256="b" * 64,
        )
    )
    connection.execute(
        passport_resource_definition.insert().values(
            id=passport_resource_id,
            passport_definition_id=passport_id,
            resource_key="RS485",
            ordinal=0,
            resource_kind="RS485_INTERFACE",
            direction="BIDIRECTIONAL",
            medium="RS485",
        )
    )
    connection.execute(
        project_instance.insert().values(
            id=instance_id,
            project_id=PROJECT,
            designation="TEST_A01",
            passport_definition_id=passport_id,
            parameters_json={},
        )
    )
    for n, resource_id in enumerate((BUS_ROOT_RESOURCE, BUS_TARGET_RESOURCE)):
        connection.execute(
            instance_resource.insert().values(
                id=resource_id,
                project_id=PROJECT,
                project_instance_id=instance_id,
                resource_key="RS485",
                ordinal=n,
                passport_resource_definition_id=passport_resource_id,
                resource_kind="RS485_INTERFACE",
                direction="BIDIRECTIONAL",
                medium="RS485",
                snapshot_json={},
            )
        )
    connection.execute(
        bus.insert().values(
            id=bus_id,
            project_id=PROJECT,
            designation="901",
            bus_kind="RS485",
            root_resource_id=BUS_ROOT_RESOURCE,
            topology_policy="LINEAR_SUFFIX_ORDER",
            cable_type="UTP Cat5e",
        )
    )
    connection.execute(
        bus_endpoint.insert().values(
            id=endpoint_id,
            project_id=PROJECT,
            bus_id=bus_id,
            endpoint_kind="INSTANCE_RESOURCE",
            resource_id=BUS_TARGET_RESOURCE,
            endpoint_role="DEVICE",
            address="901.01",
        )
    )
    connection.execute(
        bus_segment.insert().values(
            id=BUS_SEGMENT,
            project_id=PROJECT,
            bus_id=bus_id,
            source_endpoint_id=None,
            target_endpoint_id=endpoint_id,
            connection_kind="CABLE",
            mount_way="По полу",
        )
    )
    connection.execute(
        conduit.insert().values(
            id=BUS_TUBE,
            project_id=PROJECT,
            designation="003.PND25",
            conduit_number=3,
            conduit_type="ПНД25",
            color="Синий",
            length_m_decimal="25",
            path_json={"origin": "USER_EMPTY", "length_source": "SEGMENT_GEOMETRY"},
        )
    )


def _mixed_approval(uow, project_id, affected_tubes, affected_segments):
    assert project_id == PROJECT
    spans = {}
    for tube_id in affected_tubes:
        if tube_id == BUS_TUBE:
            spans[tube_id] = ConduitFact(
                conduit_id=BUS_TUBE,
                span=PhysicalSpan(
                    PhysicalBoundary("INSTANCE_RESOURCE", BUS_ROOT_RESOURCE),
                    PhysicalBoundary("INSTANCE_RESOURCE", BUS_TARGET_RESOURCE),
                ),
                mount_way="По полу",
                permitted_cable_classes=frozenset({"DATA"}),
            )
        else:
            spans[tube_id] = _conduit_facts(tube_id)
    return ApprovedPhysicalFacts(
        conduit_facts=spans,
        segment_classes={
            key: "DATA" if key[0] == "BUS" else "AC_230"
            for key in affected_segments
        },
    )


def _mixed_changes():
    return (
        AssignmentChange("CABLE", S1, TUBE2),
        AssignmentChange("BUS", BUS_SEGMENT, BUS_TUBE),
    )


def _mixed_expected():
    return {("CABLE", S1): TUBE1, ("BUS", BUS_SEGMENT): None}


def test_mixed_ordinary_and_bus_batch_writes_both_tables_once(database):
    with database.begin() as connection:
        _seed_isolated_bus(connection)
    service = AtomicConduitAssignmentService(
        database,
        approval_provider=_mixed_approval,
        cable_mirror_updater=_mirror,
    )
    result = service.apply(
        project_id=PROJECT,
        expected_project_revision=0,
        expected_current_assignments=_mixed_expected(),
        changes=_mixed_changes(),
    )
    assert result.project_revision == 1
    assert result.affected_conduits == (TUBE1, TUBE2, BUS_TUBE)
    assert _memberships(database) == ((S1, TUBE2),)
    with database.connect() as connection:
        bus_assignments = connection.execute(
            select(
                bus_segment_conduit_assignment.c.bus_segment_id,
                bus_segment_conduit_assignment.c.conduit_id,
            )
        ).all()
        bus_fact = connection.execute(
            select(bus_segment).where(bus_segment.c.id == BUS_SEGMENT)
        ).mappings().one()
        assert bus_assignments == [(BUS_SEGMENT, BUS_TUBE)]
        assert bus_fact["gofra_id"] == "003.PND25"
    assert _revision(database) == 1


def test_mixed_ordinary_bus_rolls_back_both_assignment_tables(database):
    with database.begin() as connection:
        _seed_isolated_bus(connection)
    service = AtomicConduitAssignmentService(
        database,
        approval_provider=_mixed_approval,
        cable_mirror_updater=_mirror,
    )

    def fail():
        raise RuntimeError("abort both networks")

    with pytest.raises(RuntimeError, match="abort both"):
        service.apply(
            project_id=PROJECT,
            expected_project_revision=0,
            expected_current_assignments=_mixed_expected(),
            changes=_mixed_changes(),
            failure_hook=fail,
        )
    assert _memberships(database) == ((S1, TUBE1),)
    with database.connect() as connection:
        assert connection.execute(
            select(bus_segment_conduit_assignment)
        ).all() == []
        assert connection.execute(
            select(bus_segment.c.gofra_id).where(bus_segment.c.id == BUS_SEGMENT)
        ).scalar_one() is None
    assert _revision(database) == 0
