"""D5: accepted BUS endpoint ownership and RS485 topology in temporary Project DB.

The tests are scoped to addressable CABLE_OUTLET_BUS and do not claim
persistence support for passive BOX.NNN / TRACK.NNN bus graph nodes.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from test_issue134_box_identity import _rs485_root
from test_issue237_bus_outlet_owner_gate import _batch, _outlet
from test_issue237_project_bus_context import _insert_root, _project

from nl_project_2.cad_contract import CadObservation
from nl_project_2.cad_sync import ChangeClass, DwgSyncError, DwgSyncService
from nl_project_2.persistence.schema import (
    bus_endpoint,
    bus_segment,
    cable_line,
    field_device,
)


def _wired_outlet(*, handle: str, point_id: str, source: str = "", note: str = ""):
    base = _outlet(handle=handle, point_id=point_id, source=source)
    attrs = {entry.tag: entry.value for entry in base.raw_attributes}
    attrs.update(
        BUS_MOUNT_WAY="По полу",
        BUS_GOFRA_TYPE="ППЛ20",
        BUS_GOFRA_COLOR="Синий",
        COMMENT_1=note,
    )
    return CadObservation.from_mapping(
        effective_name=base.effective_name,
        layer=base.layer,
        handle=base.handle,
        x=base.x,
        y=base.y,
        raw_attributes=attrs,
        definition=base.definition,
    )


def _accept_new(sync: DwgSyncService, pid: str, *rows):
    proposal = sync.preview(project_id=pid, batch=_batch(*rows))
    assert proposal.can_apply, proposal.issues
    selected = {
        change.field_path
        for change in proposal.changes
        if change.change_class is ChangeClass.NEW_DWG_INSERTION
    }
    assert selected, proposal.changes
    sync.apply_dwg_to_project(proposal, selected_paths=selected, confirmed=True)


def _edges(connection):
    addresses = {
        row.id: row.address
        for row in connection.execute(select(bus_endpoint.c.id, bus_endpoint.c.address))
    }
    return {
        (
            addresses.get(row.source_endpoint_id, "ROOT"),
            addresses[row.target_endpoint_id],
        )
        for row in connection.execute(
            select(bus_segment.c.source_endpoint_id, bus_segment.c.target_endpoint_id)
        )
    }


def test_dali_numeric_bus_outlet_persists_owner_and_explicit_edges(database):
    pid = _project(database)
    _insert_root(database, pid, designation="920", kind="DALI")
    sync = DwgSyncService(database.engine)
    first = _wired_outlet(handle="D1", point_id="920.001", source="920.000")
    second = _wired_outlet(handle="D2", point_id="920.002", source="920.001")
    _accept_new(sync, pid, first, second)
    with database.engine.connect() as conn:
        owners = dict(
            conn.execute(
                select(bus_endpoint.c.address, field_device.c.entity_handle)
                .join(field_device, field_device.c.id == bus_endpoint.c.field_device_id)
                .where(bus_endpoint.c.project_id == pid)
            )
        )
        assert owners == {"920.001": "D1", "920.002": "D2"}
        assert _edges(conn) == {("ROOT", "920.001"), ("920.001", "920.002")}
        assert conn.scalar(select(func.count()).select_from(cable_line)) == 0
        assert conn.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    second_scan = sync.preview(project_id=pid, batch=_batch(first, second))
    assert second_scan.can_apply, second_scan.issues
    with database.engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(bus_endpoint)) == 2
        assert conn.scalar(select(func.count()).select_from(bus_segment)) == 2


def test_accepted_dali_address_cannot_be_claimed_by_new_dwg_handle(database):
    pid = _project(database)
    _insert_root(database, pid, designation="920", kind="DALI")
    sync = DwgSyncService(database.engine)
    accepted = _wired_outlet(handle="D1", point_id="920.001", source="920.000")
    _accept_new(sync, pid, accepted)
    substitute = _wired_outlet(handle="OTHER", point_id="920.001", source="920.000")
    proposal = sync.preview(project_id=pid, batch=_batch(substitute))
    assert proposal.can_apply, proposal.issues
    selected = {
        c.field_path
        for c in proposal.changes
        if c.change_class is ChangeClass.NEW_DWG_INSERTION
    }
    assert selected
    with pytest.raises(DwgSyncError, match="BUS_POINT_ID_OWNER_CONFLICT"):
        sync.apply_dwg_to_project(proposal, selected_paths=selected, confirmed=True)
    with database.engine.connect() as conn:
        owners = list(
            conn.execute(
                select(bus_endpoint.c.address, field_device.c.entity_handle)
                .join(field_device, field_device.c.id == bus_endpoint.c.field_device_id)
            )
        )
        assert owners == [("920.001", "D1")]
        assert conn.scalar(select(func.count()).select_from(field_device)) == 1
        assert _edges(conn) == {("ROOT", "920.001")}


def test_rs485_missing_middle_does_not_bypass_accepted_endpoint(database):
    pid = _project(database)
    _rs485_root(database, pid)
    sync = DwgSyncService(database.engine)
    first = _wired_outlet(handle="R1", point_id="902.001")
    middle = _wired_outlet(handle="R2", point_id="902.002")
    last = _wired_outlet(handle="R3", point_id="902.003")
    _accept_new(sync, pid, first, middle, last)
    expected = {
        ("ROOT", "902.001"),
        ("902.001", "902.002"),
        ("902.002", "902.003"),
    }
    with database.engine.connect() as conn:
        assert _edges(conn) == expected
    changed = _wired_outlet(handle="R3", point_id="902.003", note="Selected note")
    partial = sync.preview(project_id=pid, batch=_batch(first, changed))
    note = next(
        change
        for change in partial.changes
        if change.handle == "R3" and change.field == "COMMENT_1"
    )
    assert note.change_class is ChangeClass.DWG_CHANGED
    sync.apply_dwg_to_project(partial, selected_paths={note.field_path}, confirmed=True)
    with database.engine.connect() as conn:
        assert _edges(conn) == expected
        assert conn.scalar(select(func.count()).select_from(bus_endpoint)) == 3


def test_rs485_inserting_middle_repairs_successor_without_changing_route(database):
    pid = _project(database)
    _rs485_root(database, pid)
    sync = DwgSyncService(database.engine)
    first = _wired_outlet(handle="R1", point_id="902.001")
    middle = _wired_outlet(handle="R2", point_id="902.002")
    last = _wired_outlet(handle="R3", point_id="902.003")
    _accept_new(sync, pid, first, last)
    with database.engine.connect() as conn:
        assert _edges(conn) == {("ROOT", "902.001"), ("902.001", "902.003")}
        route_before = conn.execute(
            select(bus_segment.c.mount_way, bus_segment.c.gofra_type)
            .join(bus_endpoint, bus_endpoint.c.id == bus_segment.c.target_endpoint_id)
            .where(bus_endpoint.c.address == "902.003")
        ).one()
    _accept_new(sync, pid, first, middle, last)
    with database.engine.connect() as conn:
        assert _edges(conn) == {
            ("ROOT", "902.001"),
            ("902.001", "902.002"),
            ("902.002", "902.003"),
        }
        route_after = conn.execute(
            select(bus_segment.c.mount_way, bus_segment.c.gofra_type)
            .join(bus_endpoint, bus_endpoint.c.id == bus_segment.c.target_endpoint_id)
            .where(bus_endpoint.c.address == "902.003")
        ).one()
        assert route_after == route_before
        assert conn.scalar(select(func.count()).select_from(bus_endpoint)) == 3
        assert conn.scalar(select(func.count()).select_from(bus_segment)) == 3
