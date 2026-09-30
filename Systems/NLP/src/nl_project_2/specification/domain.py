"""Pure grouping, costing and validation for a derived specification."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class SpecificationSource:
    source_kind: str
    source_id: str
    item_key: str
    name: str
    article: str | None
    quantity: Decimal | None
    unit: str
    supply_scope: str | None
    specification_included: bool
    budget_included: bool
    internal: bool = False
    unit_price: Decimal | None = None
    currency: str | None = None
    note: str | None = None
    trace: str = ""


@dataclass(frozen=True, slots=True)
class SpecificationIssue:
    code: str
    source_kind: str
    source_id: str
    message: str
    status: str = "PROJECT_ERROR"
    blocking: bool = True
    required_action: str | None = None


@dataclass(frozen=True, slots=True)
class SpecificationRow:
    item_key: str
    name: str
    article: str | None
    quantity: Decimal | None
    unit: str
    supply_scope: str | None
    specification_included: bool
    budget_included: bool
    internal: bool
    unit_price: Decimal | None
    cost: Decimal | None
    currency: str | None
    note: str | None
    source_refs: tuple[tuple[str, str], ...]
    trace: tuple[str, ...]


def group_sources(
    sources: tuple[SpecificationSource, ...],
) -> tuple[tuple[SpecificationRow, ...], tuple[SpecificationIssue, ...]]:
    """Group exact item/version + scope + unit while retaining every source reference."""
    issues: list[SpecificationIssue] = []
    groups: dict[tuple, list[SpecificationSource]] = {}
    for source in sources:
        if source.supply_scope is None:
            issues.append(
                SpecificationIssue(
                    "SUPPLY_SCOPE_MISSING",
                    source.source_kind,
                    source.source_id,
                    "Область поставки не задана",
                    status="DATA_REQUIRED",
                    blocking=False,
                    required_action="Укажите подтверждённую область поставки",
                )
            )
        if source.supply_scope == "CUSTOMER" and source.budget_included:
            issues.append(
                _issue("CUSTOMER_IN_NEIROLINKS_BUDGET", source, "Поставка заказчика в смете")
            )
        if source.internal and source.specification_included:
            issues.append(
                _issue(
                    "INTERNAL_IN_CUSTOMER_SPECIFICATION",
                    source,
                    "Внутренний материал в заказной спецификации",
                )
            )
        groups.setdefault(
            (
                source.item_key,
                source.supply_scope,
                source.unit,
                source.specification_included,
                source.budget_included,
                source.internal,
                source.unit_price,
                source.currency,
            ),
            [],
        ).append(source)

    rows: list[SpecificationRow] = []
    for key, members in groups.items():
        members = sorted(members, key=lambda item: (item.source_kind, item.source_id))
        quantities = [item.quantity for item in members]
        quantity = (
            None if any(value is None for value in quantities) else sum(quantities, Decimal())
        )
        price = members[0].unit_price
        cost = quantity * price if quantity is not None and price is not None else None
        notes = tuple(dict.fromkeys(item.note for item in members if item.note))
        rows.append(
            SpecificationRow(
                item_key=key[0],
                name=members[0].name,
                article=members[0].article,
                quantity=quantity,
                unit=key[2],
                supply_scope=key[1],
                specification_included=key[3],
                budget_included=key[4],
                internal=key[5],
                unit_price=price,
                cost=cost,
                currency=key[7],
                note="; ".join(notes) or None,
                source_refs=tuple((item.source_kind, item.source_id) for item in members),
                trace=tuple(item.trace for item in members),
            )
        )
    rows.sort(key=lambda row: (row.internal, row.supply_scope or "", row.name, row.item_key))
    return tuple(rows), tuple(issues)


def _issue(code: str, source: SpecificationSource, message: str) -> SpecificationIssue:
    return SpecificationIssue(code, source.source_kind, source.source_id, message)
