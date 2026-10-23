"""#237 D9: explicit legacy DALI approval and atomic, backup-gated graph mapping."""

from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import func, select
from test_issue237_legacy_dali_audit import _forget_typed_graph, _set_fields, _setup
from test_issue237_project_bus_context import _insert_root, _project

from nl_project_2.cad_sync.approved_dali_mapping import (
    LegacyDaliMappingError,
    apply_approved_legacy_dali_mapping,
    preview_legacy_dali_mapping,
)
from nl_project_2.cad_sync.legacy_dali_audit import audit_accepted_dali_project
from nl_project_2.cad_sync.physical_dali_store import read_project_physical_sources
from nl_project_2.persistence.migration import HEAD_REVISION, current_revision_read_only
from nl_project_2.persistence.schema import (
    bus_physical_link,
    bus_physical_node,
    field_device,
)


def _owner_ids(database, project_id, *handles):
    with database.engine.connect() as conn:
        return tuple(
            conn.execute(
                select(field_device.c.id).where(
                    field_device.c.project_id == project_id,
                    field_device.c.entity_handle.in_(handles),
                )
            ).scalars()
        )


def _plan(database, project_id, *handles):
    return preview_legacy_dali_mapping(
        database.engine,
        project_id=project_id,
        selected_field_device_ids=_owner_ids(database, project_id, *handles),
    )


def _apply(database, plan, tmp_path, *, confirmation=True, digest=None):
    return apply_approved_legacy_dali_mapping(
        database.engine,
        plan,
        confirmed=confirmation,
        approved_plan_sha256=digest if digest is not None else plan.plan_sha256,
        backup_directory=tmp_path / "verified-backups",
    )


def _counts(database):
    with database.engine.connect() as conn:
        return (
            conn.scalar(select(func.count()).select_from(bus_physical_node)),
            conn.scalar(select(func.count()).select_from(bus_physical_link)),
        )


def test_readonly_preview_contains_explicit_owner_actions_and_is_stable(database):
    pid = _setup(database)
    _forget_typed_graph(database, pid)
    before = database.path.read_bytes()
    plan = _plan(database, pid, "BOX-A", "TRACK-A")
    assert len(plan.actions) == 2
    assert {a.operation for a in plan.actions} == {"INSERT_PHYSICAL_NODE_AND_LINK"}
    assert {a.identity for a in plan.actions} == {"BOX.023", "TRACK.023"}
    assert plan == _plan(database, pid, "BOX-A", "TRACK-A")
    assert len(plan.plan_sha256) == 64
    assert plan.plan_sha256 in plan.to_json()
    assert database.path.read_bytes() == before
    assert _counts(database) == (0, 0)


def test_validated_backup_then_apply_creates_physical_graph_once(database, tmp_path):
    pid = _setup(database, light=True)
    _forget_typed_graph(database, pid)
    plan = _plan(database, pid, "BOX-A", "TRACK-A", "LIGHT-A")
    assert len(plan.changes) == 3
    receipt = _apply(database, plan, tmp_path)
    assert (receipt.inserted_physical_nodes, receipt.inserted_links) == (2, 3)
    assert receipt.backup.path.is_file()
    assert len(receipt.backup.sha256) == 64
    assert receipt.backup.source_revision == HEAD_REVISION
    assert current_revision_read_only(receipt.backup.path) == HEAD_REVISION
    with sqlite3.connect(f"file:{receipt.backup.path.as_posix()}?mode=ro", uri=True) as backup:
        assert backup.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert backup.execute("SELECT COUNT(*) FROM bus_physical_node").fetchone() == (0,)
    assert _counts(database) == (2, 3)
    with database.engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        assert conn.exec_driver_sql("PRAGMA integrity_check").scalar_one() == "ok"
        saved = read_project_physical_sources(conn, project_id=pid)
        assert {(r.target_identity, r.source_reference) for r in saved} == {
            ("BOX.023", "905.000"),
            ("TRACK.023", "BOX.023"),
            ("905.001", "TRACK.023"),
        }
        report = audit_accepted_dali_project(conn, project_id=pid)
    assert all(row.disposition == "ALREADY_MAPPED" for row in report.rows)
    assert len(report.rows) == 3


def test_already_mapped_row_is_explicit_idempotent_noop(database, tmp_path):
    pid = _setup(database)
    plan = _plan(database, pid, "BOX-A", "TRACK-A")
    assert not plan.changes
    assert {a.operation for a in plan.actions} == {"NOOP"}
    before = _counts(database)
    receipt = _apply(database, plan, tmp_path)
    assert receipt.inserted_physical_nodes == 0
    assert receipt.inserted_links == 0
    assert _counts(database) == before


@pytest.mark.parametrize("confirmed,wrong_digest", [(False, False), (True, True)])
def test_missing_or_wrong_human_approval_refuses_before_backup(
    database, tmp_path, confirmed, wrong_digest
):
    pid = _setup(database)
    _forget_typed_graph(database, pid)
    plan = _plan(database, pid, "BOX-A")
    backup_path = tmp_path / "verified-backups"
    with pytest.raises(LegacyDaliMappingError, match="EXPLICIT_APPROVAL_REQUIRED"):
        _apply(
            database,
            plan,
            tmp_path,
            confirmation=confirmed,
            digest="0" * 64 if wrong_digest else None,
        )
    assert not backup_path.exists()
    assert _counts(database) == (0, 0)


def test_d8_candidate_is_not_approval_and_review_row_is_blocked(database):
    pid = _setup(database)
    _forget_typed_graph(database, pid)
    _set_fields(database, pid, "BOX-A", {"BUS_POINT_ID": "905.041"})
    with pytest.raises(LegacyDaliMappingError, match="REVIEW_BLOCKED"):
        _plan(database, pid, "BOX-A")


def test_partial_track_requires_selected_or_already_accepted_parent(database, tmp_path):
    pid = _setup(database)
    _forget_typed_graph(database, pid)
    with pytest.raises(LegacyDaliMappingError, match="PARENT_NOT_SELECTED"):
        _plan(database, pid, "TRACK-A")
    root_plan = _plan(database, pid, "BOX-A")
    first = _apply(database, root_plan, tmp_path)
    assert first.inserted_physical_nodes == 1
    assert _counts(database) == (1, 1)
    second_plan = _plan(database, pid, "TRACK-A")
    assert len(second_plan.changes) == 1
    second = _apply(database, second_plan, tmp_path / "later")
    assert second.inserted_physical_nodes == 1
    assert _counts(database) == (2, 2)


def test_stale_accepted_owner_change_refuses_with_no_mutation(database, tmp_path):
    pid = _setup(database)
    _forget_typed_graph(database, pid)
    plan = _plan(database, pid, "BOX-A", "TRACK-A")
    _set_fields(database, pid, "BOX-A", {"BUS_SOURCE": "BOX.999"})
    with pytest.raises(LegacyDaliMappingError):
        _apply(database, plan, tmp_path)
    assert _counts(database) == (0, 0)


def test_cross_project_owner_is_not_in_project_audit(database):
    first = _setup(database)
    second = _project(database, code="D9-FOREIGN")
    _insert_root(database, second)
    alien = _owner_ids(database, first, "BOX-A")[0]
    with pytest.raises(LegacyDaliMappingError, match="OWNER_NOT_IN_AUDIT"):
        preview_legacy_dali_mapping(
            database.engine, project_id=second, selected_field_device_ids=(alien,)
        )


def test_sqlite_injected_failure_rolls_back_nodes_and_links_with_backup(database, tmp_path):
    pid = _setup(database)
    _forget_typed_graph(database, pid)
    plan = _plan(database, pid, "BOX-A", "TRACK-A")
    with database.engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TRIGGER d9_reject_track BEFORE INSERT ON bus_physical_link "
            "WHEN NEW.source_kind = 'PHYSICAL' BEGIN "
            "SELECT RAISE(ABORT, 'synthetic reject physical link'); END"
        )
    with pytest.raises(Exception, match="synthetic reject physical link"):
        _apply(database, plan, tmp_path)
    assert _counts(database) == (0, 0)
    with database.engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        assert conn.exec_driver_sql("PRAGMA integrity_check").scalar_one() == "ok"
    assert len(list((tmp_path / "verified-backups").glob("*.backup.sqlite"))) == 1


def test_same_address_other_bus_is_rejected_not_rebound(database):
    pid = _setup(database)
    _forget_typed_graph(database, pid)
    _insert_root(database, pid, designation="906")
    _set_fields(database, pid, "BOX-A", {"BUS_ID": "906"})
    with pytest.raises(LegacyDaliMappingError, match="REVIEW_BLOCKED"):
        _plan(database, pid, "BOX-A")


def test_mixed_box_addressed_track_cycle_is_rejected_at_preview(database):
    pid = _setup(database, light=True)
    _forget_typed_graph(database, pid)
    # Accepted chain becomes BOX.023 -> 905.001 -> TRACK.023 -> BOX.023.
    # A physical-only cycle check is insufficient; D9 must fail closed.
    _set_fields(database, pid, "BOX-A", {"BUS_SOURCE": "905.001"})
    with pytest.raises(LegacyDaliMappingError, match="DALI_MAPPING_TOPOLOGY_CYCLE"):
        _plan(database, pid, "BOX-A", "TRACK-A", "LIGHT-A")
    assert _counts(database) == (0, 0)
