from decimal import Decimal

import pytest
from sqlalchemy import select, update
from test_p0004_segment_recalculation import _graph, _project, _replace_source

from nl_project_2.cables import CableService
from nl_project_2.persistence.schema import (
    cable_point,
    cable_point_field_device,
    field_device,
    room,
)


@pytest.mark.parametrize(
    ("route", "column", "reason"),
    [
        ("По полу", "base_mark", "отметки основания пола"),
        ("По потолку", "height_m_decimal", "высоты потолка"),
        ("По полу", "room_id", "помещения"),
    ],
)
def test_room_geometry_missing_reason_is_specific(database, route, column, reason):
    _, pid, ra, rb, _ = _project(database)
    line, segments, _ = _graph(database, pid, (ra, rb), routes=[(0, 1, route, "ПНД25")])
    with database.engine.begin() as c:
        if column == "room_id":
            c.execute(update(field_device).where(field_device.c.room_id == ra).values(room_id=None))
        else:
            c.execute(update(room).where(room.c.id == ra).values({column: None}))
    service = CableService(database.engine)
    service.recalculate(project_id=pid)
    edge = service.topology(pid, line)["edges"][0]
    assert edge["segment_id"] == segments[0]
    assert edge["physical_length_m"] is None
    assert reason in edge["calculation_reason"]
    assert "координаты" not in edge["calculation_reason"]


@pytest.mark.parametrize(
    ("mount", "expected"), [("301", "неоднозначная"), ("", "высоты установки"), ("300.0", "")]
)
def test_shared_endpoint_requires_consistent_complete_geometry(database, mount, expected):
    _, pid, ra, rb, _ = _project(database)
    line, _, _ = _graph(
        database, pid, (ra, rb), routes=[(0, 1, "По полу", "ПНД25")], shared_mechanisms=2
    )
    with database.engine.begin() as c:
        device = (
            c.execute(
                select(field_device)
                .join(
                    cable_point_field_device,
                    cable_point_field_device.c.field_device_id == field_device.c.id,
                )
                .join(cable_point, cable_point.c.id == cable_point_field_device.c.cable_point_id)
                .where(cable_point.c.ordinal == 1)
            )
            .mappings()
            .first()
        )
        fields = {**device["normalized_fields_json"], "MOUNT_HEIGHT": mount}
        c.execute(
            update(field_device)
            .where(field_device.c.id == device["id"])
            .values(normalized_fields_json=fields)
        )
    service = CableService(database.engine)
    service.recalculate(project_id=pid)
    edge = service.topology(pid, line)["edges"][0]
    if expected:
        assert expected in edge["calculation_reason"]
        assert edge["cable_length_m"] is None
    else:
        assert edge["calculation_reason"] == ""
        assert Decimal(edge["cable_length_m"]) == Decimal("4.1")


def test_resource_endpoint_uses_proven_label_instead_of_uuid(database):
    _, pid, ra, rb, _ = _project(database)
    line, segments, _ = _graph(database, pid, (ra, rb), routes=[(0, 1, "По полу", "ПНД25")])
    _replace_source(database, pid, ra, line, segments[0], board_owned=True)
    service = CableService(database.engine)
    service.recalculate(project_id=pid)
    source = service.topology(pid, line)["edges"][0]["source"]
    assert source["label"].startswith("QB.I / ")
    assert source["resource_id"] not in source["label"]


def test_no_false_ready_before_persisted_calculation(database):
    _, pid, ra, rb, _ = _project(database)
    line, _, _ = _graph(database, pid, (ra, rb), routes=[(0, 1, "По полу", "ПНД25")])
    edge = CableService(database.engine).topology(pid, line)["edges"][0]
    assert edge["calculation_status"] == "INCOMPLETE"
    assert "пересчёт" in edge["calculation_reason"]
