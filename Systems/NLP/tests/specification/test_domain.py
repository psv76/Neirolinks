from decimal import Decimal

from nl_project_2.specification import SpecificationSource, group_sources


def _source(identifier: str, **changes):
    values = {
        "source_kind": "TEST",
        "source_id": identifier,
        "item_key": "product:v1",
        "name": "Item",
        "article": "A",
        "quantity": Decimal("1"),
        "unit": "pcs",
        "supply_scope": "NEIROLINKS",
        "specification_included": True,
        "budget_included": True,
        "unit_price": Decimal("10"),
        "currency": "RUB",
        "trace": identifier,
    }
    values.update(changes)
    return SpecificationSource(**values)


def test_exact_grouping_quantity_cost_and_trace():
    rows, issues = group_sources((_source("one"), _source("two", quantity=Decimal("2"))))
    assert not issues
    assert len(rows) == 1
    assert rows[0].quantity == Decimal("3")
    assert rows[0].cost == Decimal("30")
    assert rows[0].source_refs == (("TEST", "one"), ("TEST", "two"))
    assert rows[0].trace == ("one", "two")


def test_unknown_is_not_zero_and_invalid_scope_combinations_are_explained():
    rows, issues = group_sources(
        (
            _source("missing", quantity=None, unit_price=None, supply_scope=None),
            _source("customer", supply_scope="CUSTOMER", budget_included=True),
            _source(
                "internal",
                internal=True,
                specification_included=True,
                budget_included=False,
                supply_scope="ASSEMBLY_WORKSHOP",
            ),
        )
    )
    assert next(row for row in rows if row.source_refs[0][1] == "missing").cost is None
    assert {issue.code for issue in issues} == {
        "SUPPLY_SCOPE_MISSING",
        "CUSTOMER_IN_NEIROLINKS_BUDGET",
        "INTERNAL_IN_CUSTOMER_SPECIFICATION",
    }
