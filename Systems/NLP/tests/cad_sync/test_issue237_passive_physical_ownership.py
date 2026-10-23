"""#237 D6: passive DALI physical identities survive selected Project insertion.

This is an explicit intermediate gate: accepted field_device evidence is
preserved; physical DALI edges are NOT yet BusSegment records. No schema,
DWG or live database changes. Tests use only an isolated temporary SQLite.
"""

from __future__ import annotations

from sqlalchemy import func, select
from test_issue237_project_bus_context import _insert_root, _observation, _project

from nl_project_2.cad_contract import (
    BlockDefinitionMetadata,
    CadObservation,
    CadObservationBatch,
    load_contract,
)
from nl_project_2.cad_sync import ChangeClass, DwgSyncError, DwgSyncService
from nl_project_2.cad_sync.reconciliation import normalize_validated_snapshot
from nl_project_2.persistence.schema import bus_endpoint, bus_segment, field_device


def _box(*, handle="BOX-A", identity="BOX.023", bus="905", source=None):
    original = _observation()
    attrs = {tag.tag: tag.value for tag in original.raw_attributes}
    attrs.update(
        BOX_ID=identity,
        BUS_ID=bus,
        BUS_SOURCE=source if source is not None else f"{bus}.000",
    )
    return CadObservation.from_mapping(
        effective_name="EL_BOX_OUT_100x100",
        layer="BUS",
        raw_attributes=attrs,
        x=0,
        y=0,
        handle=handle,
        definition=BlockDefinitionMetadata(tuple(attrs)),
    )


def _track(*, handle="TRACK-A", identity="TRACK.023", bus="905", source="BOX.023"):
    rule = load_contract().block("TRACK_DALI")
    assert rule is not None
    attrs = {tag: "" for tag in rule.required_definition_attributes}
    attrs.update(
        DEVICE_NAME="Physical DALI track",
        BUILDING="House",
        ROOM="Hall",
        MOUNT_HEIGHT="2500",
        TRACK_ID=identity,
        BUS_ID=bus,
        BUS_SOURCE=source,
        CABLE_ID="401",
        CABLE_TYPE="",
        BOARD="",
        LENGTH="1500",
    )
    return CadObservation.from_mapping(
        effective_name="TRACK_DALI",
        layer="TRACK_DALI",
        raw_attributes=attrs,
        x=100,
        y=0,
        handle=handle,
        definition=BlockDefinitionMetadata(tuple(attrs)),
    )


def _batch(*observations, name="physical-dali-sample.dwg"):
    return CadObservationBatch(name, observations)


def _accept(sync, pid, batch, *, structural=False):
    preview = sync.preview(project_id=pid, batch=batch)
    assert preview.can_apply, preview.issues
    selected = {
        change.field_path
        for change in preview.changes
        if change.change_class is ChangeClass.NEW_DWG_INSERTION
    }
    assert selected
    sync.apply_dwg_to_project(
        preview,
        selected_paths=selected,
        confirmed=True,
        allow_structural=structural,
    )


def test_normalized_snapshot_retains_passive_owners_without_bus_addresses(database):
    pid = _project(database)
    _insert_root(database, pid)
    service = DwgSyncService(database.engine)
    validated = service._validator_for_project(pid).validate(_batch(_box(), _track()))
    assert validated.is_acceptable, validated.issues
    snapshot = normalize_validated_snapshot(validated.observations)
    assert [
        (node.physical_id, node.bus_id, node.bus_kind, node.source, node.handle)
        for node in snapshot.bus_physical_nodes
    ] == [
        ("BOX.023", "905", "DALI", "905.000", "BOX-A"),
        ("TRACK.023", "905", "DALI", "BOX.023", "TRACK-A"),
    ]
    assert snapshot.bus_points == ()
    assert all(
        fact.structural
        for fact in snapshot.facts
        if fact.field in {"BOX_ID", "TRACK_ID", "BUS_ID", "BUS_SOURCE"}
    )


def test_selected_passive_fields_survive_reopen_without_fabricated_bus_endpoint(database):
    pid = _project(database)
    _insert_root(database, pid)
    sync = DwgSyncService(database.engine)
    batch = _batch(_box(), _track())
    _accept(sync, pid, batch)
    with database.engine.connect() as connection:
        fields = {
            row.entity_handle: row.normalized_fields_json
            for row in connection.execute(
                select(field_device.c.entity_handle, field_device.c.normalized_fields_json)
                .where(field_device.c.project_id == pid)
            )
        }
        assert set(fields) == {"BOX-A", "TRACK-A"}
        assert fields["BOX-A"]["BOX_ID"] == "BOX.023"
        assert fields["BOX-A"]["BUS_ID"] == "905"
        assert fields["BOX-A"]["BUS_SOURCE"] == "905.000"
        assert fields["TRACK-A"]["TRACK_ID"] == "TRACK.023"
        assert fields["TRACK-A"]["BUS_ID"] == "905"
        assert fields["TRACK-A"]["BUS_SOURCE"] == "BOX.023"
        assert not fields["BOX-A"].get("BUS_POINT_ID")
        assert not fields["TRACK-A"].get("BUS_POINT_ID")
        assert connection.scalar(select(func.count()).select_from(bus_endpoint)) == 0
        assert connection.scalar(select(func.count()).select_from(bus_segment)) == 0
    reopened = DwgSyncService(database.engine).preview(project_id=pid, batch=batch)
    assert not [
        row for row in reopened.changes if row.change_class is ChangeClass.NEW_DWG_INSERTION
    ]


def test_another_dwg_cannot_claim_existing_box_identity(database):
    pid = _project(database)
    _insert_root(database, pid)
    sync = DwgSyncService(database.engine)
    _accept(sync, pid, _batch(_box(handle="FIRST"), name="physical-A.dwg"))
    incoming = _batch(_box(handle="SECOND"), name="physical-B.dwg")
    preview = sync.preview(project_id=pid, batch=incoming)
    selected = {
        change.field_path
        for change in preview.changes
        if change.change_class is ChangeClass.NEW_DWG_INSERTION
    }
    assert selected
    import pytest

    with pytest.raises(DwgSyncError, match="BUS_PHYSICAL_ID_OWNER_CONFLICT:BOX.023"):
        sync.apply_dwg_to_project(preview, selected_paths=selected, confirmed=True)
    with database.engine.connect() as connection:
        owners = list(
            connection.execute(
                select(field_device.c.entity_handle).where(field_device.c.project_id == pid)
            ).scalars()
        )
        assert owners == ["FIRST"]
        assert connection.scalar(select(func.count()).select_from(bus_endpoint)) == 0


def test_accepted_passive_node_cannot_move_to_another_dali_bus(database):
    import pytest

    pid = _project(database)
    _insert_root(database, pid, designation="905")
    _insert_root(database, pid, designation="906")
    sync = DwgSyncService(database.engine)
    _accept(sync, pid, _batch(_box()))
    changed = _batch(_box(bus="906", source="906.000"))
    preview = sync.preview(project_id=pid, batch=changed)
    to_change = {
        change.field_path
        for change in preview.changes
        if change.field in {"BUS_ID", "BUS_SOURCE"}
        and change.change_class in {ChangeClass.DWG_CHANGED, ChangeClass.IDENTITY_COLLISION}
    }
    assert to_change, preview.changes
    with pytest.raises(DwgSyncError, match="BUS_PHYSICAL_BUS_REASSIGN_REQUIRES_ATTENTION"):
        sync.apply_dwg_to_project(
            preview, selected_paths=to_change, confirmed=True, allow_structural=True
        )
    with database.engine.connect() as connection:
        saved = connection.execute(
            select(field_device.c.normalized_fields_json).where(
                field_device.c.entity_handle == "BOX-A",
                field_device.c.project_id == pid,
            )
        ).scalar_one()
        assert saved["BUS_ID"] == "905"
        assert saved["BUS_SOURCE"] == "905.000"
