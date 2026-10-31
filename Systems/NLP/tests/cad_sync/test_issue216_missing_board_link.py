"""#216: restore exact active BOARD reference without importing an unselected BOARD."""

from dataclasses import replace

from sqlalchemy import select, update
from test_p0003_reconciliation import _observation
from test_sync_service import _applicable, _batch, _project

from nl_project_2.cad_sync import ChangeClass, DwgSyncService
from nl_project_2.persistence.schema import board, cable_line


def test_existing_board_rebinds_nullable_line_during_selective_load_move(database):
    pid = _project(database)
    sync = DwgSyncService(database.engine)
    board_observation = _observation(
        "BOARD_IN",
        handle="BOARD1",
        cable_id="101",
        attributes={"BOARD_ID": "B.01", "BOARD": "B.00", "LOAD_TYPE": "BOARD_DISTRIBUTION"},
        x=0,
        y=0,
    )
    load1 = _observation(
        "LIGHT_IN_230V",
        handle="LIGHT1",
        cable_id="301.01",
        attributes={"BOARD": "B.01"},
        x=10000,
        y=3000,
    )
    load2 = _observation(
        "LIGHT_IN_230V",
        handle="LIGHT2",
        cable_id="302.01",
        attributes={"BOARD": "B.01"},
        x=15000,
        y=4000,
    )
    baseline = sync.preview(project_id=pid, batch=_batch(board_observation, load1, load2))
    assert baseline.can_apply, baseline.issues
    sync.apply_dwg_to_project(baseline, selected_paths=_applicable(baseline), confirmed=True)

    with database.engine.connect() as connection:
        board_id = connection.scalar(
            select(board.c.id).where(
                board.c.project_id == pid,
                board.c.designation == "B.01",
                board.c.lifecycle == "ACTIVE",
            )
        )
        old_other_id = connection.scalar(
            select(cable_line.c.board_id).where(
                cable_line.c.project_id == pid, cable_line.c.designation == "302"
            )
        )
    assert board_id is not None and old_other_id == board_id
    # Reproduce historical Bogdanovich state with a correct BOARD fact and
    # missing canonical foreign key while an identical BOARD already exists.
    with database.engine.begin() as connection:
        connection.execute(
            update(cable_line)
            .where(cable_line.c.project_id == pid, cable_line.c.designation == "301")
            .values(board_id=None)
        )

    batch = _batch(board_observation, replace(load1, x=11000), load2)
    preview = sync.preview(project_id=pid, batch=batch)
    choices = {
        change.field_path
        for change in preview.changes
        if change.handle == "LIGHT1"
        and change.field == "X"
        and change.change_class is ChangeClass.DWG_CHANGED
    }
    assert choices == {"LIGHT1:X"}
    assert not any(
        change.handle == "BOARD1" and change.field_path in choices for change in preview.changes
    )
    sync.apply_dwg_to_project(preview, selected_paths=choices, confirmed=True)
    with database.engine.connect() as connection:
        row = connection.execute(
            select(cable_line.c.board_id, cable_line.c.cable_facts_json).where(
                cable_line.c.project_id == pid, cable_line.c.designation == "301"
            )
        ).one()
        untouched = connection.scalar(
            select(cable_line.c.board_id).where(
                cable_line.c.project_id == pid, cable_line.c.designation == "302"
            )
        )
    assert row.board_id == board_id
    assert row.cable_facts_json["BOARD"] == "B.01"
    assert untouched == board_id
