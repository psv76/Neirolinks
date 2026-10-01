from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from nl_project_2.persistence.ids import is_canonical_id, new_id
from nl_project_2.persistence.schema import building, project, room
from nl_project_2.persistence.uow import UnitOfWork


def project_row(project_id: str, code: str = "TEST") -> dict[str, object]:
    return {
        "id": project_id,
        "project_code": code,
        "name": "Temporary test project",
        "card_fields_json": {},
    }


def building_row(building_id: str, project_id: str, code: str = "B") -> dict[str, object]:
    return {
        "id": building_id,
        "project_id": project_id,
        "code": code,
        "normalized_code": code.casefold(),
        "name": "Temporary test building",
        "display_order": 0,
    }


def count_rows(engine, table) -> int:
    with engine.connect() as connection:
        return connection.execute(select(func.count()).select_from(table)).scalar_one()


def test_stable_id_is_uuid4_and_independent_of_designation() -> None:
    value = new_id()
    assert is_canonical_id(value)
    assert UUID(value).version == 4
    assert value != "BOARD.01"


def test_multientity_commit_is_atomic(database) -> None:
    project_id = new_id()
    with UnitOfWork(database.engine) as work:
        work.execute(project.insert().values(**project_row(project_id)))
        work.execute(building.insert().values(**building_row(new_id(), project_id)))
        work.commit()

    assert count_rows(database.engine, project) == 1
    assert count_rows(database.engine, building) == 1


def test_exception_rolls_back_every_entity(database) -> None:
    project_id = new_id()
    with pytest.raises(RuntimeError, match="force rollback"):
        with UnitOfWork(database.engine) as work:
            work.execute(project.insert().values(**project_row(project_id)))
            work.execute(building.insert().values(**building_row(new_id(), project_id)))
            raise RuntimeError("force rollback")

    assert count_rows(database.engine, project) == 0
    assert count_rows(database.engine, building) == 0


def test_no_commit_rolls_back_on_normal_exit(database) -> None:
    with UnitOfWork(database.engine) as work:
        work.execute(project.insert().values(**project_row(new_id())))
    assert count_rows(database.engine, project) == 0


def test_unique_constraint_rejects_duplicate_normalized_code(database) -> None:
    project_id = new_id()
    with UnitOfWork(database.engine) as work:
        work.execute(project.insert().values(**project_row(project_id)))
        work.execute(building.insert().values(**building_row(new_id(), project_id, "A")))
        work.commit()

    with pytest.raises(IntegrityError):
        with UnitOfWork(database.engine) as work:
            row = building_row(new_id(), project_id, "a")
            row["normalized_code"] = "a"
            work.execute(building.insert().values(**row))
            work.commit()
    assert count_rows(database.engine, building) == 1


def test_foreign_key_rejects_orphan_without_partial_write(database) -> None:
    with pytest.raises(IntegrityError):
        with UnitOfWork(database.engine) as work:
            work.execute(building.insert().values(**building_row(new_id(), new_id())))
            work.commit()
    assert count_rows(database.engine, building) == 0


def test_check_constraint_rejects_negative_order(database) -> None:
    project_id = new_id()
    with UnitOfWork(database.engine) as work:
        work.execute(project.insert().values(**project_row(project_id)))
        work.commit()
    row = building_row(new_id(), project_id)
    row["display_order"] = -1
    with pytest.raises(IntegrityError):
        with UnitOfWork(database.engine) as work:
            work.execute(building.insert().values(**row))
            work.commit()


def test_composite_foreign_key_rejects_cross_project_reference(database) -> None:
    first_project = new_id()
    second_project = new_id()
    building_id = new_id()
    with UnitOfWork(database.engine) as work:
        work.execute(project.insert().values(**project_row(first_project, "P1")))
        work.execute(project.insert().values(**project_row(second_project, "P2")))
        work.execute(building.insert().values(**building_row(building_id, first_project)))
        work.commit()

    with pytest.raises(IntegrityError):
        with UnitOfWork(database.engine) as work:
            work.execute(
                room.insert().values(
                    id=new_id(),
                    project_id=second_project,
                    building_id=building_id,
                    name="Cross-project room",
                    normalized_name="cross-project room",
                )
            )
            work.commit()
