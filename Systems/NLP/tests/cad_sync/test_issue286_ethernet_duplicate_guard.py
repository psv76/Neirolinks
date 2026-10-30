"""Issue #286: unique Ethernet 8xx cable IDs across actual DWG insertions.

Bogdanovich House_2 had four SOCKET_ETHERNET blocks for 873/874 (two
different handles per cable ID), already accepted into field_device.
This regression must reject such a snapshot BEFORE any Apply.
"""

from dataclasses import replace

import pytest
from sqlalchemy import select
from test_issue286_ethernet_apply import _ethernet
from test_sync_service import _applicable, _batch, _project

from nl_project_2.cad_sync import DwgSyncError, DwgSyncService
from nl_project_2.persistence.schema import cable_line, field_device


@pytest.mark.parametrize("number", [801, 873, 874])
def test_duplicate_full_8xx_identity_is_blocking_and_preserves_database(database, number):
    project_id = _project(database)
    service = DwgSyncService(database.engine)
    original = _ethernet(number)
    second = replace(
        original,
        handle=f"DUPE{number}",
        x=original.x + 3500,
        y=original.y + 2800,
    )
    proposal = service.preview(
        project_id=project_id,
        batch=_batch(original, second),
    )
    issues = [i for i in proposal.issues if i.code == "DUPLICATE_ETHERNET_CABLE_ID"]
    assert len(issues) == 1
    issue = issues[0]
    assert issue.field == "CABLE_ID"
    assert set(issue.related_handles) == {original.handle, second.handle}
    assert issue.blocks_acceptance
    assert not proposal.can_apply
    with database.engine.connect() as connection:
        assert connection.execute(select(cable_line)).all() == []
        assert connection.execute(select(field_device)).all() == []
    with pytest.raises(DwgSyncError):
        service.apply_dwg_to_project(proposal, selected_paths=_applicable(proposal), confirmed=True)
    with database.engine.connect() as connection:
        assert connection.execute(select(cable_line)).all() == []
        assert connection.execute(select(field_device)).all() == []


def test_distinct_full_8xx_ids_continue_to_import(database):
    project_id = _project(database)
    service = DwgSyncService(database.engine)
    proposal = service.preview(
        project_id=project_id,
        batch=_batch(_ethernet(873), _ethernet(874)),
    )
    assert not any(i.code == "DUPLICATE_ETHERNET_CABLE_ID" for i in proposal.issues)
    assert proposal.can_apply
    service.apply_dwg_to_project(proposal, selected_paths=_applicable(proposal), confirmed=True)
    with database.engine.connect() as connection:
        assert {row[0] for row in connection.execute(select(cable_line.c.designation))} == {
            "873",
            "874",
        }
