"""D7 canonical physical DALI graph in isolated Project SQLite, never live."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select, update
from test_issue237_passive_physical_ownership import _accept, _batch, _box, _track
from test_issue237_project_bus_context import _insert_root, _project

from nl_project_2.cad_contract import BlockDefinitionMetadata, CadObservation, load_contract
from nl_project_2.cad_sync import ChangeClass, DwgSyncService
from nl_project_2.cad_sync.physical_dali_store import read_project_physical_sources
from nl_project_2.persistence.migration import (
    HEAD_REVISION,
    SHARED_BOX_ENDPOINT_REVISION,
    current_revision_read_only,
    downgrade_database,
)
from nl_project_2.persistence.schema import (
    bus_endpoint,
    bus_physical_link,
    bus_physical_node,
    bus_segment,
    project,
)


def _links(conn, pid):
    return read_project_physical_sources(conn, project_id=pid)


def _node_ids(conn):
    query = select(bus_physical_node.c.physical_id, bus_physical_node.c.id)
    return dict(conn.execute(query).all())


def _light():
    contract = load_contract()
    rule = contract.block("LIGHT_TRACK_DALI_48V")
    assert rule is not None
    group = contract.functional_groups["LIGHTING_LED"]
    attrs = {tag: "" for tag in rule.required_definition_attributes}
    sample = {
        "DEVICE_NAME": "Track 48 V light",
        "BUILDING": "House",
        "ROOM": "Hall",
        "MOUNT_HEIGHT": "2500",
        "BUS_POINT_ID": "905.001",
        "BUS_SOURCE": "TRACK.023",
        # D7 isolates physical DALI membership. The 48 V track feeder is
        # a separate power graph and must not be inferred from this light.
        "CABLE_ID": "",
        "CABLE_TYPE": "",
        "BOARD": "",
        "MOUNT_WAY": "",
        "BUS_MOUNT_WAY": "",
    }
    attrs.update({tag: value for tag, value in sample.items() if tag in attrs})
    return CadObservation.from_mapping(
        effective_name="LIGHT_TRACK_DALI_48V",
        layer=sorted(group.layers)[0],
        raw_attributes=attrs,
        x=130,
        y=0,
        handle="LIGHT-A",
        definition=BlockDefinitionMetadata(tuple(attrs)),
    )


def _change_observation(observation, tag, value):
    attrs = {row.tag: row.value for row in observation.raw_attributes}
    attrs[tag] = value
    return CadObservation.from_mapping(
        effective_name=observation.effective_name,
        layer=observation.layer,
        x=observation.x,
        y=observation.y,
        handle=observation.handle,
        raw_attributes=attrs,
        definition=BlockDefinitionMetadata(tuple(attrs)),
    )


def test_box_track_graph_is_persisted_with_stable_owners_and_no_phantom_addresses(database):
    pid = _project(database)
    _insert_root(database, pid)
    sync = DwgSyncService(database.engine)
    _accept(sync, pid, _batch(_box(), _track()))
    with database.engine.connect() as conn:
        rows = _links(conn, pid)
        assert [(r.target_identity, r.source_reference, r.link_kind) for r in rows] == [
            ("BOX.023", "905.000", "CABLE"),
            ("TRACK.023", "BOX.023", "CABLE"),
        ]
        ids = _node_ids(conn)
        edge_ids = sorted(conn.execute(select(bus_physical_link.c.id)).scalars())
        assert set(ids) == {"BOX.023", "TRACK.023"}
        assert conn.scalar(select(func.count()).select_from(bus_endpoint)) == 0
        assert conn.scalar(select(func.count()).select_from(bus_segment)) == 0
        assert conn.exec_driver_sql("PRAGMA foreign_key_check").all() == []

    no_op = DwgSyncService(database.engine).preview(project_id=pid, batch=_batch(_box(), _track()))
    assert no_op.can_apply, no_op.issues
    assert not [x for x in no_op.changes if x.change_class is ChangeClass.NEW_DWG_INSERTION]
    with database.engine.connect() as conn:
        assert _node_ids(conn) == ids
        assert sorted(conn.execute(select(bus_physical_link.c.id)).scalars()) == edge_ids


def test_partial_box_scan_cannot_delete_existing_track_and_link(database):
    pid = _project(database)
    _insert_root(database, pid)
    sync = DwgSyncService(database.engine)
    _accept(sync, pid, _batch(_box(), _track()))
    selected_box = _change_observation(_box(), "DEVICE_NAME", "Updated BOX name")
    preview = sync.preview(project_id=pid, batch=_batch(selected_box))
    changed = {
        c.field_path
        for c in preview.changes
        if c.field == "DEVICE_NAME" and c.change_class is ChangeClass.DWG_CHANGED
    }
    assert changed, preview.changes
    sync.apply_dwg_to_project(preview, selected_paths=changed, confirmed=True)
    with database.engine.connect() as conn:
        assert [(x.target_identity, x.source_reference) for x in _links(conn, pid)] == [
            ("BOX.023", "905.000"),
            ("TRACK.023", "BOX.023"),
        ]
        assert conn.scalar(select(func.count()).select_from(bus_physical_node)) == 2
        assert conn.scalar(select(func.count()).select_from(bus_physical_link)) == 2


def test_physical_dali_source_link_to_addressable_light_has_no_fake_root_segment(database):
    pid = _project(database)
    _insert_root(database, pid)
    sync = DwgSyncService(database.engine)
    batch = _batch(_box(), _track(), _light())
    preview = sync.preview(project_id=pid, batch=batch)
    assert preview.can_apply, preview.issues
    _accept(sync, pid, batch)
    with database.engine.connect() as conn:
        sources = _links(conn, pid)
        assert [(r.target_identity, r.source_reference, r.link_kind) for r in sources] == [
            ("905.001", "TRACK.023", "TRACK"),
            ("BOX.023", "905.000", "CABLE"),
            ("TRACK.023", "BOX.023", "CABLE"),
        ]
        assert conn.scalar(select(func.count()).select_from(bus_endpoint)) == 1
        assert conn.scalar(select(func.count()).select_from(bus_segment)) == 0
        assert conn.exec_driver_sql("PRAGMA foreign_key_check").all() == []


def test_canonical_project_edge_supplies_preview_and_validated_write_plan(database):
    """Readback is typed Project graph, not stale field_device BUS_SOURCE."""
    pid = _project(database)
    _insert_root(database, pid)
    sync = DwgSyncService(database.engine)
    batch = _batch(_box(), _track())
    _accept(sync, pid, batch)
    with database.engine.begin() as conn:
        target = conn.scalar(
            select(bus_physical_node.c.id).where(
                bus_physical_node.c.project_id == pid,
                bus_physical_node.c.physical_id == "TRACK.023",
            )
        )
        assert target is not None
        conn.execute(
            update(bus_physical_link)
            .where(bus_physical_link.c.target_physical_node_id == target)
            .values(
                source_kind="ROOT",
                source_physical_node_id=None,
                source_bus_endpoint_id=None,
            )
        )
        conn.execute(
            update(project)
            .where(project.c.id == pid)
            .values(project_revision=project.c.project_revision + 1)
        )
    proposal = sync.preview(project_id=pid, batch=batch)
    candidates = [
        row for row in proposal.changes if row.handle == "TRACK-A" and row.field == "BUS_SOURCE"
    ]
    assert len(candidates) == 1, proposal.changes
    change = candidates[0]
    assert change.change_class is ChangeClass.IDENTITY_COLLISION
    assert change.project_value == "905.000"
    assert change.dwg_value == "BOX.023"
    plan = sync.plan_project_to_dwg(proposal, selected_paths={change.field_path})
    assert len(plan.targets) == 1
    assert plan.targets[0].handle == "TRACK-A"
    assert plan.targets[0].tag == "BUS_SOURCE"
    assert plan.targets[0].new_value == "905.000"
    # No call to CAD execute_write_plan; no real DWG modified.


def test_nonempty_dali_graph_cannot_be_silently_downgraded(database, tmp_path):
    pid = _project(database)
    _insert_root(database, pid)
    _accept(DwgSyncService(database.engine), pid, _batch(_box(), _track()))
    database.close()
    backup_folder = tmp_path / "safe-downgrade"
    with pytest.raises(RuntimeError, match="DALI_PHYSICAL_DOWNGRADE_REQUIRES_EXPLICIT_REVIEW"):
        downgrade_database(database.path, backup_folder, target=SHARED_BOX_ENDPOINT_REVISION)
    assert current_revision_read_only(database.path) == HEAD_REVISION
    backups = list(backup_folder.glob("*.backup.sqlite"))
    assert len(backups) == 1
    assert current_revision_read_only(backups[0]) == HEAD_REVISION
