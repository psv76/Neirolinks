"""D10: 4YY rail power owner is a TRACK, not another installed cable run."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select, update
from test_issue237_passive_physical_ownership import _accept, _batch, _box, _track
from test_issue237_physical_dali_storage import _change_observation, _light
from test_issue237_project_bus_context import _insert_root, _project

from nl_project_2.cad_sync import ChangeClass, DwgSyncError, DwgSyncService
from nl_project_2.cad_sync.track_power import (
    TrackInternalPowerError,
    selected_internal_track_power,
)
from nl_project_2.persistence.schema import (
    bus_physical_link,
    cable_line,
    cable_point,
    cable_point_field_device,
    cable_segment,
    field_device,
)


def _mounted_light(**attrs):
    light = _light()
    for tag, value in {
        "CABLE_ID": "401",
        "CABLE_SOURCE": "TRACK.023",
        **attrs,
    }.items():
        light = _change_observation(light, tag, value)
    return light


def _accepted_track_batch(*, light=None, track=None):
    return _batch(_box(), track or _track(), light or _mounted_light())


def _count(connection, table):
    return connection.scalar(select(func.count()).select_from(table))


def test_d10_accepted_48v_track_power_keeps_rail_member_without_cable_segment(database):
    pid = _project(database)
    _insert_root(database, pid)
    sync = DwgSyncService(database.engine)
    batch = _accepted_track_batch()
    _accept(sync, pid, batch)
    with database.engine.connect() as conn:
        rows = list(
            conn.execute(
                select(field_device.c.block_kind, field_device.c.normalized_fields_json).where(
                    field_device.c.project_id == pid
                )
            )
        )
        values = {name: data for name, data in rows}
        assert values["LIGHT_TRACK_DALI_48V"]["CABLE_SOURCE"] == "TRACK.023"
        assert values["LIGHT_TRACK_DALI_48V"]["CABLE_ID"] == "401"
        assert values["TRACK_DALI"]["TRACK_ID"] == "TRACK.023"
        # External feed to TRACK is a cable, but rail-mounted lamp has none.
        assert _count(conn, cable_segment) == 1
        assert _count(conn, cable_line) == 1
        assert _count(conn, bus_physical_link) == 3
        assert conn.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        assert conn.exec_driver_sql("PRAGMA integrity_check").scalar_one() == "ok"
        links = selected_internal_track_power(
            conn,
            project_id=pid,
            active_handles={"LIGHT-A"},
            device_ids={
                row.entity_handle: row.id
                for row in conn.execute(
                    select(field_device.c.entity_handle, field_device.c.id).where(
                        field_device.c.project_id == pid
                    )
                )
            },
        )
        assert len(links) == 1
        assert links[0].track_id == "TRACK.023"
        assert links[0].cable_base == "401"
        assert links[0].bus_id == "905"
        assert links[0].length_m_decimal is None
        assert links[0].conduit_id is None
    again = DwgSyncService(database.engine).preview(project_id=pid, batch=batch)
    assert again.can_apply, again.issues
    assert not [c for c in again.changes if c.change_class is ChangeClass.NEW_DWG_INSERTION]
    unexpected_source = [
        c for c in again.changes if c.handle == "LIGHT-A" and c.field == "CABLE_SOURCE"
    ]
    assert len(unexpected_source) == 1
    assert unexpected_source[0].change_class is ChangeClass.EQUAL
    assert (
        unexpected_source[0].baseline_value,
        unexpected_source[0].project_value,
        unexpected_source[0].dwg_value,
    ) == ("TRACK.023", "TRACK.023", "TRACK.023")


@pytest.mark.parametrize(
    "attrs,expected",
    [
        ({"CABLE_ID": "402"}, "TRACK_POWER_CABLE_OWNER_MISMATCH"),
        ({"CABLE_ID": "301"}, "TRACK_POWER_4YY_REQUIRED"),
        ({"BUS_SOURCE": "905.000"}, "TRACK_POWER_BUS_OWNER_MISMATCH"),
        ({"CABLE_SOURCE": "TRACK.999"}, "TRACK_POWER_OWNER_MISSING_OR_AMBIGUOUS"),
    ],
)
def test_invalid_internal_power_source_rejects_atomically(database, attrs, expected):
    pid = _project(database)
    _insert_root(database, pid)
    sync = DwgSyncService(database.engine)
    # Source must already be accepted; the scenario selects only the lamp
    # for a transactional mismatch test rather than guessing a new track.
    _accept(sync, pid, _batch(_box(), _track()))
    before = database.path.read_bytes()
    invalid = _mounted_light(**attrs)
    batch = _batch(_box(), _track(), invalid)
    preview = sync.preview(project_id=pid, batch=batch)
    if not preview.can_apply:
        assert preview.issues
        assert database.path.read_bytes() == before
        return
    selected = {
        c.field_path for c in preview.changes if c.change_class is ChangeClass.NEW_DWG_INSERTION
    }
    assert selected
    with pytest.raises(DwgSyncError, match=expected):
        sync.apply_dwg_to_project(preview, selected_paths=selected, confirmed=True)
    with database.engine.connect() as conn:
        assert _count(conn, cable_segment) == 1
        assert (
            conn.scalar(
                select(func.count())
                .select_from(field_device)
                .where(field_device.c.block_kind == "LIGHT_TRACK_DALI_48V")
            )
            == 0
        )
        assert conn.exec_driver_sql("PRAGMA foreign_key_check").all() == []


def test_accepted_rail_source_cannot_be_silently_reinterpreted_as_external_run(database):
    pid = _project(database)
    _insert_root(database, pid)
    _accept(DwgSyncService(database.engine), pid, _accepted_track_batch())
    # Artificial old external segment, if present, must not be overwritten
    # or silently adopted as internal rail power.
    with database.engine.connect() as conn:
        light_id = conn.scalar(
            select(field_device.c.id).where(
                field_device.c.project_id == pid,
                field_device.c.block_kind == "LIGHT_TRACK_DALI_48V",
            )
        )
        assert light_id
    # Direct helper rejects a changed accepted track power owner without
    # editing the imported light or its accepted DALI short address.
    with database.engine.begin() as conn:
        track = (
            conn.execute(
                select(field_device).where(
                    field_device.c.project_id == pid,
                    field_device.c.block_kind == "TRACK_DALI",
                )
            )
            .mappings()
            .one()
        )
        fields = dict(track["normalized_fields_json"])
        fields["CABLE_ID"] = "402"
        conn.execute(
            update(field_device)
            .where(field_device.c.id == track["id"])
            .values(normalized_fields_json=fields)
        )
    with database.engine.connect() as conn:
        with pytest.raises(TrackInternalPowerError, match="TRACK_POWER_CABLE_OWNER_MISMATCH"):
            selected_internal_track_power(
                conn,
                project_id=pid,
                active_handles={"LIGHT-A"},
                device_ids={"LIGHT-A": light_id},
            )


def test_pre_d10_track_base_point_requires_explicit_legacy_review(database):
    pid = _project(database)
    _insert_root(database, pid)
    sync = DwgSyncService(database.engine)
    _accept(sync, pid, _batch(_box(), _track()))
    # Synthetic legacy evidence: pre-D10 used the bare base 401 as the
    # physical TRACK point identity. Do not rewrite it without approval.
    with database.engine.begin() as conn:
        conn.execute(
            update(cable_point)
            .where(
                cable_point.c.project_id == pid,
                cable_point.c.id.in_(
                    select(cable_point_field_device.c.cable_point_id)
                    .join(
                        field_device,
                        field_device.c.id == cable_point_field_device.c.field_device_id,
                    )
                    .where(field_device.c.block_kind == "TRACK_DALI")
                ),
            )
            .values(logical_identity="401")
        )
    with database.engine.connect() as conn:
        existing = _count(conn, cable_segment)
        assert existing == 1
    proposal = sync.preview(project_id=pid, batch=_accepted_track_batch())
    assert proposal.can_apply, proposal.issues
    selected = {
        c.field_path for c in proposal.changes if c.change_class is ChangeClass.NEW_DWG_INSERTION
    }
    assert selected
    with pytest.raises(DwgSyncError, match="TRACK_POWER_LEGACY_POINT_REQUIRES_REVIEW"):
        sync.apply_dwg_to_project(proposal, selected_paths=selected, confirmed=True)
    with database.engine.connect() as conn:
        assert _count(conn, cable_segment) == existing
        assert (
            conn.scalar(
                select(func.count())
                .select_from(field_device)
                .where(field_device.c.block_kind == "LIGHT_TRACK_DALI_48V")
            )
            == 0
        )
