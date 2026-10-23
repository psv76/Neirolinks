"""#237 D8: read-only legacy DALI plan, no mutation or automatic backfill."""

from __future__ import annotations

from sqlalchemy import delete, select, update
from test_issue237_passive_physical_ownership import _accept, _batch, _box, _track
from test_issue237_physical_dali_storage import _light
from test_issue237_project_bus_context import _insert_root, _project

from nl_project_2.cad_sync import DwgSyncService
from nl_project_2.cad_sync.legacy_dali_audit import audit_accepted_dali_project
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    bus,
    bus_physical_link,
    bus_physical_node,
    field_device,
    instance_resource,
)


def _audit(database, project_id):
    with database.engine.connect() as connection:
        return audit_accepted_dali_project(connection, project_id=project_id)


def _setup(database, *, light=False):
    project_id = _project(database)
    _insert_root(database, project_id)
    scan = _batch(_box(), _track(), *([_light()] if light else []))
    _accept(DwgSyncService(database.engine), project_id, scan)
    return project_id


def _forget_typed_graph(database, project_id):
    # Reproduce *accepted* legacy field_device evidence in a temporary rev15
    # test DB; no production downgrade and no legacy mutation in D8 code.
    with database.engine.begin() as connection:
        connection.execute(
            delete(bus_physical_link).where(bus_physical_link.c.project_id == project_id)
        )
        connection.execute(
            delete(bus_physical_node).where(bus_physical_node.c.project_id == project_id)
        )


def _set_fields(database, project_id, handle, updates):
    with database.engine.begin() as connection:
        row = (
            connection.execute(
                select(field_device).where(
                    field_device.c.project_id == project_id,
                    field_device.c.entity_handle == handle,
                )
            )
            .mappings()
            .one()
        )
        values = dict(row["normalized_fields_json"])
        values.update(updates)
        connection.execute(
            update(field_device)
            .where(field_device.c.id == row["id"])
            .values(normalized_fields_json=values)
        )


def _statuses(audit):
    return {row.identity: (row.disposition, row.reasons) for row in audit.rows}


def test_accepted_canonical_graph_is_already_mapped_and_audit_is_read_only(database):
    pid = _setup(database, light=True)
    path = database.path
    before = path.read_bytes()
    first = _audit(database, pid)
    second = _audit(database, pid)
    assert first == second
    assert first.fingerprint_sha256 == second.fingerprint_sha256
    assert len(first.fingerprint_sha256) == 64
    assert all(row.disposition == "ALREADY_MAPPED" for row in first.rows), first
    assert set(_statuses(first)) == {"BOX.023", "TRACK.023", "905.001"}
    assert dict(first.summary)["TOTAL"] == 3
    assert dict(first.summary)["ALREADY_MAPPED"] == 3
    assert first.to_json() == second.to_json()
    assert path.read_bytes() == before


def test_unmaterialized_legacy_box_and_track_are_candidates_never_written(database):
    pid = _setup(database)
    _forget_typed_graph(database, pid)
    before = database.path.read_bytes()
    review = _audit(database, pid)
    assert _statuses(review) == {
        "BOX.023": ("CANDIDATE", ()),
        "TRACK.023": ("CANDIDATE", ()),
    }
    assert database.path.read_bytes() == before
    with database.engine.connect() as connection:
        assert (
            connection.execute(
                select(bus_physical_node.c.id).where(bus_physical_node.c.project_id == pid)
            ).all()
            == []
        )
        assert (
            connection.execute(
                select(bus_physical_link.c.id).where(bus_physical_link.c.project_id == pid)
            ).all()
            == []
        )


def test_missing_physical_parent_is_review_not_inferred_from_root(database):
    pid = _setup(database)
    _forget_typed_graph(database, pid)
    _set_fields(database, pid, "TRACK-A", {"BUS_SOURCE": "BOX.999"})
    review = _audit(database, pid)
    assert "SOURCE_PHYSICAL_MISSING_OR_AMBIGUOUS" in _statuses(review)["TRACK.023"][1]
    assert _statuses(review)["BOX.023"][0] == "CANDIDATE"


def test_accepted_duplicate_physical_id_blocks_both_owners(database):
    pid = _setup(database)
    _forget_typed_graph(database, pid)
    with database.engine.begin() as connection:
        old = (
            connection.execute(
                select(field_device).where(
                    field_device.c.project_id == pid,
                    field_device.c.entity_handle == "BOX-A",
                )
            )
            .mappings()
            .one()
        )
        connection.execute(
            field_device.insert().values(
                id=new_id(),
                project_id=pid,
                block_kind=old["block_kind"],
                dwg_document_binding_id=old["dwg_document_binding_id"],
                entity_handle="BOX-COLLISION",
                normalized_fields_json=dict(old["normalized_fields_json"]),
                lifecycle="ACTIVE",
            )
        )
    report = _audit(database, pid)
    collisions = [r for r in report.rows if r.identity == "BOX.023"]
    assert len(collisions) == 2
    assert all(r.disposition == "REVIEW" for r in collisions)
    assert all("PHYSICAL_ID_DUPLICATE_ACROSS_ACCEPTED" in r.reasons for r in collisions)
    assert "SOURCE_PHYSICAL_MISSING_OR_AMBIGUOUS" in _statuses(report)["TRACK.023"][1]


def test_wrong_bus_and_inconsistent_persisted_owner_are_not_adopted(database):
    pid = _setup(database)
    _insert_root(database, pid, designation="906")
    _set_fields(database, pid, "TRACK-A", {"BUS_ID": "906"})
    report = _audit(database, pid)
    track = _statuses(report)["TRACK.023"]
    assert track[0] == "REVIEW"
    assert "SOURCE_PHYSICAL_OTHER_BUS" in track[1]
    assert "PERSISTED_PHYSICAL_ID_OR_BUS_CONFLICT" in track[1]
    assert "PERSISTED_LINK_OTHER_BUS" in track[1]


def test_legacy_passive_short_address_is_reviewed_not_adopted(database):
    pid = _setup(database)
    _forget_typed_graph(database, pid)
    _set_fields(database, pid, "BOX-A", {"BUS_POINT_ID": "905.041"})
    r = _statuses(_audit(database, pid))["BOX.023"]
    assert r[0] == "REVIEW"
    assert "PASSIVE_HAS_PROTOCOL_ADDRESS" in r[1]


def test_repair_source_conflict_is_reported_without_rewriting_edge(database):
    pid = _setup(database)
    with database.engine.begin() as conn:
        target = conn.scalar(
            select(bus_physical_node.c.id).where(
                bus_physical_node.c.project_id == pid,
                bus_physical_node.c.physical_id == "TRACK.023",
            )
        )
        conn.execute(
            update(bus_physical_link)
            .where(bus_physical_link.c.target_physical_node_id == target)
            .values(
                source_kind="ROOT",
                source_physical_node_id=None,
                source_bus_endpoint_id=None,
            )
        )
    before = database.path.read_bytes()
    review = _audit(database, pid)
    assert "PERSISTED_LINK_SOURCE_CONFLICT" in _statuses(review)["TRACK.023"][1]
    assert database.path.read_bytes() == before


def test_legacy_physical_source_cycle_is_review_only(database):
    pid = _setup(database)
    _forget_typed_graph(database, pid)
    _set_fields(database, pid, "BOX-A", {"BUS_SOURCE": "TRACK.023"})
    report = _audit(database, pid)
    assert all(
        "BUS_SOURCE_CYCLE" in _statuses(report)[identity][1]
        for identity in ("BOX.023", "TRACK.023")
    )


def test_project_scope_never_uses_owners_from_other_project(database):
    owner_project = _setup(database)
    other_project = _project(database, code="OTHER-DALI-D8")
    _insert_root(database, other_project)
    with database.engine.begin() as connection:
        old = (
            connection.execute(
                select(field_device).where(
                    field_device.c.project_id == owner_project,
                    field_device.c.entity_handle == "TRACK-A",
                )
            )
            .mappings()
            .one()
        )
        connection.execute(
            field_device.insert().values(
                id=new_id(),
                project_id=other_project,
                block_kind="TRACK_DALI",
                normalized_fields_json=dict(old["normalized_fields_json"]),
                lifecycle="ACTIVE",
            )
        )
    report = _audit(database, other_project)
    assert len(report.rows) == 1
    row = report.rows[0]
    assert row.disposition == "REVIEW"
    assert "OWNER_DWG_BINDING_OR_HANDLE_MISSING" in row.reasons
    assert "SOURCE_PHYSICAL_MISSING_OR_AMBIGUOUS" in row.reasons


def test_unverified_inactive_root_blocks_all_legacy_candidates(database):
    pid = _setup(database)
    _forget_typed_graph(database, pid)
    with database.engine.begin() as connection:
        root_resource_id = connection.scalar(
            select(bus.c.root_resource_id).where(
                bus.c.project_id == pid,
                bus.c.designation == "905",
            )
        )
        assert root_resource_id
        connection.execute(
            update(instance_resource)
            .where(instance_resource.c.id == root_resource_id)
            .values(active=False)
        )
    review = _audit(database, pid)
    assert len(review.rows) == 2
    assert all(row.disposition == "REVIEW" for row in review.rows)
    assert all("BUS_ROOT_UNVERIFIED" in row.reasons for row in review.rows)


def test_blocked_upstream_box_cascades_review_to_dependent_track(database):
    pid = _setup(database)
    _forget_typed_graph(database, pid)
    _set_fields(database, pid, "BOX-A", {"BUS_SOURCE": "BOX.999"})
    statuses = _statuses(_audit(database, pid))
    assert "SOURCE_PHYSICAL_MISSING_OR_AMBIGUOUS" in statuses["BOX.023"][1]
    assert statuses["TRACK.023"][0] == "REVIEW"
    assert "SOURCE_PHYSICAL_REQUIRES_REVIEW" in statuses["TRACK.023"][1]
