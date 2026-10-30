"""Issue #216: selecting one BOARD coordinate change must recalculate its dependents."""

from dataclasses import replace

from sqlalchemy import select
from test_p0003_reconciliation import _observation
from test_sync_service import _applicable, _batch, _project

import nl_project_2.cad_sync.service as sync_service_module
from nl_project_2.cad_sync import ChangeClass, DwgSyncService
from nl_project_2.persistence.schema import cable_line, cable_segment, field_device


def test_selected_board_move_recalculates_other_unchanged_lines(database, monkeypatch):
    project_id = _project(database)
    sync = DwgSyncService(database.engine)
    board = _observation(
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
    original = _batch(board, load1, load2)
    proposal = sync.preview(project_id=project_id, batch=original)
    assert proposal.can_apply, proposal.issues
    sync.apply_dwg_to_project(
        proposal,
        selected_paths=_applicable(proposal),
        confirmed=True,
    )
    with database.engine.connect() as connection:
        lengths = {
            designation: value
            for designation, value in connection.execute(
                select(cable_line.c.designation, cable_segment.c.calculated_length_m_decimal).join(
                    cable_segment, cable_segment.c.cable_line_id == cable_line.c.id
                )
            ).all()
            if designation in {"301", "302"}
        }
    assert len(lengths) == 2
    assert len(lengths) == 2
    with database.engine.connect() as connection:
        dependent_ids = set(
            connection.execute(
                select(cable_line.c.id).where(cable_line.c.designation.in_(("301", "302")))
            ).scalars()
        )
        board_device_id = connection.execute(
            select(field_device.c.id).where(field_device.c.entity_handle == "BOARD1")
        ).scalar_one()
    actual_recalculate = sync_service_module.recalculate_segments
    recalculations = []

    def record_recalculation(uow, project_id, **kwargs):
        result = actual_recalculate(uow, project_id, **kwargs)
        recalculations.append((kwargs, result))
        return result

    monkeypatch.setattr(sync_service_module, "recalculate_segments", record_recalculation)
    moved = _batch(replace(board, x=1000), load1, load2)
    candidate = sync.preview(project_id=project_id, batch=moved)
    coords = {
        change.field_path
        for change in candidate.changes
        if change.handle == "BOARD1"
        and change.change_class is ChangeClass.DWG_CHANGED
        and change.field in {"X", "Y"}
    }
    assert coords, [
        (c.field_path, str(c.change_class)) for c in candidate.changes if c.handle == "BOARD1"
    ]
    sync.apply_dwg_to_project(
        candidate,
        selected_paths=coords,
        confirmed=True,
    )
    assert any(
        kwargs.get("device_ids") == {board_device_id} and dependent_ids <= set(result.line_ids)
        for kwargs, result in recalculations
    ), [(kwargs, result.line_ids) for kwargs, result in recalculations]
    with database.engine.connect() as connection:
        board_device = (
            connection.execute(select(field_device).where(field_device.c.entity_handle == "BOARD1"))
            .mappings()
            .one()
        )
        assert board_device["normalized_fields_json"]["X"] == 1000
