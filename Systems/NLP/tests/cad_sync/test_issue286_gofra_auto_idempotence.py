"""Issue #286: blank DWG GOFRA_ID is valid for a Project-auto conduit.

Only a Conduit with exact AUTO_SEGMENT provenance and the same physical owner
may remain unnumbered in DWG without a spurious three-way merge conflict.
"""

from sqlalchemy import select
from test_sync_service import _applicable, _batch, _project, _socket

from nl_project_2.cad_sync import ChangeClass, DwgSyncService
from nl_project_2.persistence.schema import (
    cable_segment,
    conduit,
    conduit_segment_assignment,
)


def _conduit_rows(database):
    with database.engine.connect() as conn:
        return (
            conn.execute(select(conduit).order_by(conduit.c.id)).all(),
            conn.execute(
                select(conduit_segment_assignment).order_by(conduit_segment_assignment.c.id)
            ).all(),
            conn.execute(select(cable_segment).order_by(cable_segment.c.id)).all(),
        )


def _initial_auto(database):
    pid = _project(database)
    service = DwgSyncService(database.engine)
    one = _socket(handle="AUTO1", cable_id="101", gofra_id="")
    first = service.preview(project_id=pid, batch=_batch(one))
    assert first.summary.invalid == 0, first.issues
    assert _applicable(first) == {"AUTO1:$"}
    service.apply_dwg_to_project(first, selected_paths=_applicable(first), confirmed=True)
    return pid, service, one


def test_blank_dwg_id_remains_outbound_writeback_without_auto_recreation(database):
    pid, service, one = _initial_auto(database)
    before = _conduit_rows(database)
    assert len(before[0]) == len(before[1]) == len(before[2]) == 1
    assert before[0][0]._mapping["path_json"]["origin"] == "AUTO_SEGMENT"

    repeated = service.preview(project_id=pid, batch=_batch(one))
    assert not _applicable(repeated)
    auto = [c for c in repeated.changes if c.field == "GOFRA_ID"]
    assert len(auto) == 1
    assert auto[0].change_class is ChangeClass.PROJECT_CHANGED
    assert auto[0].project_value
    assert auto[0].dwg_value == ""
    assert _conduit_rows(database) == before

    # A new manually supplied ID in DWG is a real proposal/conflict, never
    # suppressed just because the original Project ID was automatic.
    explicit = _socket(handle="AUTO1", cable_id="101", gofra_id="999.PND25")
    edited = service.preview(project_id=pid, batch=_batch(explicit))
    gofra_changes = [c for c in edited.changes if c.field == "GOFRA_ID"]
    assert len(gofra_changes) == 1
    assert gofra_changes[0].change_class is not ChangeClass.EQUAL
    assert _conduit_rows(database) == before


def test_new_line_selection_preserves_old_auto_ids_and_assignments(database):
    pid, service, one = _initial_auto(database)
    before = _conduit_rows(database)
    second = _socket(handle="AUTO2", cable_id="102", gofra_id="")
    batch = _batch(one, second)
    proposal = service.preview(project_id=pid, batch=batch)
    assert _applicable(proposal) == {"AUTO2:$"}
    service.apply_dwg_to_project(proposal, selected_paths={"AUTO2:$"}, confirmed=True)
    after = _conduit_rows(database)
    assert len(after[0]) == len(after[1]) == len(after[2]) == 2
    assert before[0][0] in after[0]
    assert before[1][0] in after[1]
    assert before[2][0] in after[2]
    assert len({row._mapping["designation"] for row in after[0]}) == 2
    assert all(row._mapping["path_json"]["origin"] == "AUTO_SEGMENT" for row in after[0])

    third = service.preview(project_id=pid, batch=batch)
    assert not _applicable(third)
    generated_outbound = [c for c in third.changes if c.field == "GOFRA_ID"]
    assert len(generated_outbound) == 2
    assert all(c.change_class is ChangeClass.PROJECT_CHANGED for c in generated_outbound)
    assert _conduit_rows(database) == after


def test_explicit_dwg_conduit_clearing_is_not_silently_accepted(database):
    pid = _project(database)
    service = DwgSyncService(database.engine)
    numbered = _socket(handle="NUMBERED1", cable_id="101", gofra_id="001.PND25")
    p1 = service.preview(project_id=pid, batch=_batch(numbered))
    service.apply_dwg_to_project(p1, selected_paths=_applicable(p1), confirmed=True)
    (rows, _, _) = _conduit_rows(database)
    assert rows[0]._mapping["path_json"]["origin"] == "DWG_PREEXISTING"

    erased = _socket(handle="NUMBERED1", cable_id="101", gofra_id="")
    p2 = service.preview(project_id=pid, batch=_batch(erased))
    changes = [c for c in p2.changes if c.field == "GOFRA_ID"]
    assert len(changes) == 1
    assert changes[0].change_class is not ChangeClass.EQUAL
