from __future__ import annotations

import pytest
from sqlalchemy import select

from nl_project_2.cables import CableError, CableService
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import cable_line, project


@pytest.fixture(autouse=True)
def _project(database):
    project_id = new_id()
    with database.engine.begin() as connection:
        connection.execute(
            project.insert().values(
                id=project_id,
                project_code="LINES-SPREADSHEET",
                name="Lines spreadsheet",
                card_fields_json={},
                lifecycle="ACTIVE",
            )
        )
    database.test_project_id = project_id


def _line(database, designation: str, *, board: str, cable_type: str) -> str:
    line_id = new_id()
    with database.engine.begin() as connection:
        connection.execute(
            cable_line.insert().values(
                id=line_id,
                project_id=database.test_project_id,
                designation=designation,
                system_kind="POWER",
                cable_facts_json={"BOARD": board, "CABLE_TYPE": cable_type},
                lifecycle="ACTIVE",
            )
        )
    return line_id


def _revision(database) -> int:
    with database.engine.connect() as connection:
        return int(
            connection.scalar(
                select(project.c.project_revision).where(project.c.id == database.test_project_id)
            )
        )


def _facts(database, line_id: str) -> dict:
    with database.engine.connect() as connection:
        return dict(
            connection.scalar(
                select(cable_line.c.cable_facts_json).where(cable_line.c.id == line_id)
            )
        )


def test_batch_scalar_edit_validates_every_cell_and_commits_once(database):
    first = _line(database, "2", board="ЩР-1", cable_type="3x1,5")
    second = _line(database, "10", board="ЩР-2", cable_type="3x2,5")
    service = CableService(database.engine)
    before = _revision(database)

    service.batch_update_line_fields(
        project_id=database.test_project_id,
        edits=(
            {"cable_line_id": first, "field": "BOARD", "value": "ЩР-3"},
            {"cable_line_id": second, "field": "CABLE_TYPE", "value": "5x2,5"},
        ),
    )

    assert _facts(database, first)["BOARD"] == "ЩР-3"
    assert _facts(database, second)["CABLE_TYPE"] == "5x2,5"
    assert _revision(database) == before + 1


@pytest.mark.parametrize(
    ("field", "value"),
    (("LOAD_NAME", "Нельзя"), ("BOARD", "")),
)
def test_batch_scalar_edit_rejects_read_only_or_invalid_value_without_partial_write(
    database, field, value
):
    first = _line(database, "1", board="ЩР-1", cable_type="3x1,5")
    second = _line(database, "2", board="ЩР-2", cable_type="3x2,5")
    service = CableService(database.engine)
    before = _revision(database)
    facts_before = (_facts(database, first), _facts(database, second))

    with pytest.raises(CableError):
        service.batch_update_line_fields(
            project_id=database.test_project_id,
            edits=(
                {"cable_line_id": first, "field": "BOARD", "value": "ЩР-X"},
                {"cable_line_id": second, "field": field, "value": value},
            ),
        )

    assert (_facts(database, first), _facts(database, second)) == facts_before
    assert _revision(database) == before
