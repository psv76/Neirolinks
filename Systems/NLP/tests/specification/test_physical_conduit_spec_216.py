"""Issue #216/Q06: physical protective tubes are one specification source each.

Synthetic FK-enforced SQLite, production specification pipeline, no DWG/working DB.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select, update

from nl_project_2.automation import AutomationService
from nl_project_2.cables import CableService
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    bus,
    bus_endpoint,
    bus_segment,
    bus_segment_conduit_assignment,
    cable_line,
    cable_point,
    cable_segment,
    cable_topology_endpoint,
    conduit,
    conduit_segment_assignment,
)
from nl_project_2.specification import SpecificationService


def _bus_resources(database, count: int):
    automation = AutomationService(database.engine)
    results = []
    for index in range(count):
        instance = automation.constructor.create_instance(
            project_id=database.test_project_id,
            designation=f"BUS-SPEC-{index}-{new_id()[:5]}",
            passport_key="controller.wb_mr6c_v2",
            product_key="product.wirenboard.wb_mr6c_v2",
            supply_scope="NEIROLINKS",
        )
        results.append(
            next(
                row["id"]
                for row in automation.list_resources(database.test_project_id)
                if row["project_instance_id"] == instance.instance_id
                and row["resource_kind"] == "RS485_INTERFACE"
            )
        )
    return results


def _create_bus_segments(
    database,
    quantity: int,
    conduit_id: str | None = None,
    *,
    gofra_type: str = "ПНД25",
    route_lengths=None,
):
    pid = database.test_project_id
    resources = _bus_resources(database, quantity + 1)
    bus_id = new_id()
    segment_ids = []
    with database.engine.begin() as conn:
        conn.execute(
            bus.insert().values(
                id=bus_id,
                project_id=pid,
                designation=f"9{new_id()[:4]}",
                bus_kind="RS485",
                root_resource_id=resources[0],
                topology_policy="LINEAR_SUFFIX_ORDER",
                cable_type="UTP Cat5e",
            )
        )
        prev_endpoint = None
        for i, resource_id in enumerate(resources[1:]):
            endpoint_id, segment_id = new_id(), new_id()
            conn.execute(
                bus_endpoint.insert().values(
                    id=endpoint_id,
                    project_id=pid,
                    bus_id=bus_id,
                    endpoint_kind="INSTANCE_RESOURCE",
                    resource_id=resource_id,
                    endpoint_role="DEVICE",
                    address=f"901.{i + 1:02d}",
                )
            )
            conn.execute(
                bus_segment.insert().values(
                    id=segment_id,
                    project_id=pid,
                    bus_id=bus_id,
                    source_endpoint_id=prev_endpoint,
                    target_endpoint_id=endpoint_id,
                    connection_kind="CABLE",
                    mount_way="По полу",
                    gofra_type=gofra_type,
                    gofra_color="Синий",
                    gofra_id="001.PND25",
                    length_m_decimal=(route_lengths[i] if route_lengths else "5"),
                )
            )
            if conduit_id is not None:
                conn.execute(
                    bus_segment_conduit_assignment.insert().values(
                        id=new_id(),
                        project_id=pid,
                        conduit_id=conduit_id,
                        bus_segment_id=segment_id,
                    )
                )
            segment_ids.append(segment_id)
            prev_endpoint = endpoint_id
    return segment_ids


def _ordinary_segment(database, conduit_id: str):
    pid, line_id = database.test_project_id, new_id()
    start_point, end_point, start_ep, end_ep, segment_id = (new_id() for _ in range(5))
    with database.engine.begin() as conn:
        conn.execute(
            cable_line.insert().values(
                id=line_id,
                project_id=pid,
                designation="601",
                system_kind="POWER",
                cable_facts_json={"CABLE_TYPE": "3x1.5"},
            )
        )
        for index, (point_id, kind) in enumerate(
            ((start_point, "INTERNAL_SOURCE"), (end_point, "EL_BOX"))
        ):
            conn.execute(
                cable_point.insert().values(
                    id=point_id,
                    project_id=pid,
                    cable_line_id=line_id,
                    point_kind=kind,
                    ordinal=index,
                    logical_identity=f"p:{point_id}",
                )
            )
        for endpoint_id, point_id in ((start_ep, start_point), (end_ep, end_point)):
            conn.execute(
                cable_topology_endpoint.insert().values(
                    id=endpoint_id,
                    project_id=pid,
                    cable_line_id=line_id,
                    endpoint_kind="TOPOLOGY_POINT",
                    cable_point_id=point_id,
                )
            )
        conn.execute(
            cable_segment.insert().values(
                id=segment_id,
                project_id=pid,
                cable_line_id=line_id,
                source_endpoint_id=start_ep,
                target_endpoint_id=end_ep,
                mount_way="По полу",
                gofra_type="ПНД25",
                gofra_color="Синий",
            )
        )
        conn.execute(
            conduit_segment_assignment.insert().values(
                id=new_id(),
                project_id=pid,
                conduit_id=conduit_id,
                cable_segment_id=segment_id,
            )
        )
    return segment_id


def _physical_tube_rows(service, pid):
    return [row for row in service.build(pid)["rows"] if row.item_key == "CONDUIT:ПНД25:25"]


def test_one_shared_ordinary_bus_tube_manual_10m_not_15m(database):
    pid = database.test_project_id
    cid = CableService(database.engine).create_empty_conduit(
        project_id=pid,
        designation="001.PND25",
        conduit_type="ПНД25",
        diameter_mm=25,
        length_m="10",
    )
    _ordinary_segment(database, cid)
    bus_id = _create_bus_segments(database, 1, cid, route_lengths=["5"])[0]
    service = SpecificationService(database.engine)
    raw_conduit_sources = service._conduit_sources(pid, service._read_context(pid))
    assert any(s.source_id == cid and s.quantity == Decimal("10") for s in raw_conduit_sources)
    rows = _physical_tube_rows(service, pid)
    assert len(rows) == 1
    assert rows[0].quantity == Decimal("10")  # on old main it is 15
    assert ("CONDUIT", cid) in rows[0].source_refs
    assert ("BUS_SEGMENT_CONDUIT", bus_id) not in rows[0].source_refs
    with database.engine.connect() as conn:
        tube = conn.execute(select(conduit).where(conduit.c.id == cid)).mappings().one()
        assert tube["length_m_decimal"] == "10"
        assert tube["path_json"]["length_source"] == "USER_CONFIRMED"


def test_two_bus_segments_share_one_tube_not_counted_twice(database):
    pid = database.test_project_id
    cid = CableService(database.engine).create_empty_conduit(
        project_id=pid,
        designation="001.PND25",
        conduit_type="ПНД25",
        diameter_mm=25,
        length_m="10",
    )
    _create_bus_segments(database, 2, cid, route_lengths=["5", "5"])
    rows = _physical_tube_rows(SpecificationService(database.engine), pid)
    assert len(rows) == 1 and rows[0].quantity == Decimal("10")
    assert rows[0].source_refs == (("CONDUIT", cid),)


def test_distinct_parallel_tubes_still_count_separately(database):
    pid = database.test_project_id
    cables = CableService(database.engine)
    first = cables.create_empty_conduit(
        project_id=pid,
        designation="001.PND25",
        conduit_type="ПНД25",
        diameter_mm=25,
        length_m="10",
    )
    second = cables.create_empty_conduit(
        project_id=pid,
        designation="002.PND25",
        conduit_type="ПНД25",
        diameter_mm=25,
        length_m="10",
    )
    _create_bus_segments(database, 1, first)
    _create_bus_segments(database, 1, second)
    rows = _physical_tube_rows(SpecificationService(database.engine), pid)
    assert len(rows) == 1 and rows[0].quantity == Decimal("20")
    assert set(rows[0].source_refs) == {("CONDUIT", first), ("CONDUIT", second)}


def test_auto_bus_origin_uses_physical_conduit_when_confirmed(database):
    pid = database.test_project_id
    cid = CableService(database.engine).create_empty_conduit(
        project_id=pid,
        designation="001.PND25",
        conduit_type="ПНД25",
        diameter_mm=25,
        length_m="10",
    )
    with database.engine.begin() as conn:
        conn.execute(
            update(conduit)
            .where(conduit.c.id == cid)
            .values(path_json={"origin": "AUTO_BUS_SEGMENT", "length_source": "USER_CONFIRMED"})
        )
    _create_bus_segments(database, 1, cid)
    rows = _physical_tube_rows(SpecificationService(database.engine), pid)
    assert len(rows) == 1 and rows[0].quantity == Decimal("10")
    assert rows[0].source_refs == (("CONDUIT", cid),)


def test_legacy_bus_without_physical_assignment_is_not_fake_5m_tube(database):
    pid = database.test_project_id
    seg_id = _create_bus_segments(database, 1, None, route_lengths=["5"])[0]
    result = SpecificationService(database.engine).build(pid)
    assert all(
        ("BUS_SEGMENT_CONDUIT", seg_id) not in row.source_refs
        for row in result["rows"]
        if row.quantity is not None
    )
    pending = [row for row in result["rows"] if ("BUS_SEGMENT_CONDUIT", seg_id) in row.source_refs]
    assert len(pending) == 1 and pending[0].quantity is None
    assert any(
        issue.code == "CONDUIT_ASSIGNMENT_REQUIRED" and issue.source_id == seg_id
        for issue in result["issues"]
    )


def test_bus_only_assigned_conduit_unknown_length_stays_unknown(database):
    pid = database.test_project_id
    cid = CableService(database.engine).create_empty_conduit(
        project_id=pid,
        designation="001.PND25",
        conduit_type="ПНД25",
        diameter_mm=25,
    )
    seg_id = _create_bus_segments(database, 1, cid, route_lengths=["5"])[0]
    result = SpecificationService(database.engine).build(pid)
    tube_row = next(row for row in result["rows"] if ("CONDUIT", cid) in row.source_refs)
    assert tube_row.quantity is None
    assert all(("BUS_SEGMENT_CONDUIT", seg_id) not in row.source_refs for row in result["rows"])
    assert any(
        issue.code == "CONDUIT_LENGTH_REQUIRED" and issue.source_id == cid
        for issue in result["issues"]
    )


def test_assigned_bus_to_inactive_conduit_reports_unresolved(database):
    pid = database.test_project_id
    cid = CableService(database.engine).create_empty_conduit(
        project_id=pid,
        designation="001.PND25",
        conduit_type="ПНД25",
        diameter_mm=25,
        length_m="10",
    )
    seg_id = _create_bus_segments(database, 1, cid)[0]
    with database.engine.begin() as conn:
        conn.execute(update(conduit).where(conduit.c.id == cid).values(lifecycle="RETIRED"))
    result = SpecificationService(database.engine).build(pid)
    pending = [row for row in result["rows"] if ("BUS_SEGMENT_CONDUIT", seg_id) in row.source_refs]
    assert len(pending) == 1 and pending[0].quantity is None
    assert any(
        issue.code == "CONDUIT_ASSIGNMENT_REQUIRED" and issue.source_id == seg_id
        for issue in result["issues"]
    )


def test_ordinary_assignment_to_retired_tube_is_not_hidden(database):
    pid = database.test_project_id
    cid = CableService(database.engine).create_empty_conduit(
        project_id=pid,
        designation="001.PND25",
        conduit_type="ПНД25",
        diameter_mm=25,
        length_m="10",
    )
    sid = _ordinary_segment(database, cid)
    with database.engine.begin() as conn:
        conn.execute(update(conduit).where(conduit.c.id == cid).values(lifecycle="RETIRED"))
    result = SpecificationService(database.engine).build(pid)
    pending = [row for row in result["rows"] if ("CABLE_SEGMENT_CONDUIT", sid) in row.source_refs]
    assert len(pending) == 1
    assert pending[0].quantity is None
    assert any(
        issue.code == "CONDUIT_ASSIGNMENT_REQUIRED"
        and issue.source_kind == "CABLE_SEGMENT_CONDUIT"
        and issue.source_id == sid
        and issue.blocking
        for issue in result["issues"]
    )
    assert not any(("CONDUIT", cid) in row.source_refs for row in result["rows"])
