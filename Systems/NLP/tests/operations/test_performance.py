from __future__ import annotations

from sqlalchemy import event

from nl_project_2.catalog.equipment import EquipmentService
from nl_project_2.specification import SpecificationService


def test_specification_query_count_is_bounded(database):
    equipment = EquipmentService(database.engine)
    for index in range(40):
        equipment.create_instance(
            project_id=database.test_project_id,
            designation=f"QF.PERF.{index + 1}",
            passport_key="protection.circuit_breaker.1p",
            product_key="product.schneider.a9f84116",
            supply_scope="NEIROLINKS",
        )

    statements: list[str] = []

    def count_statement(*args) -> None:
        statements.append(args[2])

    event.listen(database.engine, "before_cursor_execute", count_statement)
    try:
        result = SpecificationService(database.engine).build(database.test_project_id)
    finally:
        event.remove(database.engine, "before_cursor_execute", count_statement)

    assert result["rows"]
    assert len(statements) <= 15, f"specification executed {len(statements)} SQL statements"
