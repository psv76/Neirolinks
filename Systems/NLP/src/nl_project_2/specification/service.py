"""Read-derived specification with narrow commands for facts and allowed overrides."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import Engine, delete, select, update

from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    assembly_material_fact,
    cable_length_fact,
    cable_line,
    cable_line_product_selection,
    cable_product_definition,
    commercial_fact,
    conduit,
    field_device,
    field_device_product_selection,
    led_line_profile,
    passport_definition,
    product_definition,
    project,
    project_instance,
    specification_override,
)
from nl_project_2.persistence.uow import UnitOfWork

from .domain import (
    SpecificationIssue,
    SpecificationRow,
    SpecificationSource,
    group_sources,
)


class SpecificationError(ValueError):
    pass


class SpecificationService:
    def __init__(self, engine: Engine, automation_service=None, cable_service=None) -> None:
        self._engine = engine
        self._automation = automation_service
        self._cables = cable_service

    def build(self, project_id: str) -> dict:
        context = self._read_context(project_id)
        sources = tuple(self._all_sources(project_id, context))
        rows, structural_issues = group_sources(sources)
        issues = structural_issues + tuple(self._data_issues(sources))
        return {
            "rows": rows,
            "issues": issues,
            "workshop": self._workshop_control(project_id, context),
            "neirolinks_total": self._known_total(rows, "NEIROLINKS"),
            "unknown_budget_rows": sum(
                1 for row in rows if row.budget_included and row.cost is None
            ),
        }

    def source_navigation(self, project_id: str, row: SpecificationRow) -> list[dict]:
        context = self._read_context(project_id)
        current = {(s.source_kind, s.source_id): s for s in self._all_sources(project_id, context)}
        return [
            {
                "source_kind": kind,
                "source_id": identifier,
                "trace": current[(kind, identifier)].trace,
            }
            for kind, identifier in row.source_refs
            if (kind, identifier) in current
        ]

    def set_product_price(
        self,
        *,
        project_id: str,
        product_definition_id: str,
        price,
        currency: str,
        source_reference: str,
        effective_date: str | None = None,
    ) -> str:
        return self._save_commercial_fact(
            project_id=project_id,
            product_definition_id=product_definition_id,
            material_fact_id=None,
            price=_non_negative(price, "price"),
            currency=_currency(currency),
            source_reference=_required(source_reference, "source_reference"),
            effective_date=effective_date,
        )

    def set_material_price(
        self,
        *,
        project_id: str,
        material_fact_id: str,
        price,
        currency: str,
        source_reference: str,
        effective_date: str | None = None,
    ) -> str:
        return self._save_commercial_fact(
            project_id=project_id,
            product_definition_id=None,
            material_fact_id=material_fact_id,
            price=_non_negative(price, "price"),
            currency=_currency(currency),
            source_reference=_required(source_reference, "source_reference"),
            effective_date=effective_date,
        )

    def record_workshop_claim(
        self,
        *,
        project_id: str,
        calculated_material_fact_id: str,
        quantity,
        unit_price,
        currency: str,
        source_reference: str,
    ) -> str:
        claimed_quantity = _non_negative(quantity, "quantity")
        claimed_price = _non_negative(unit_price, "unit_price")
        now = datetime.now(UTC)
        with UnitOfWork(self._engine) as uow:
            calculated = (
                uow.execute(
                    select(assembly_material_fact).where(
                        assembly_material_fact.c.id == calculated_material_fact_id,
                        assembly_material_fact.c.project_id == project_id,
                        assembly_material_fact.c.source_kind != "WORKSHOP_CLAIM",
                    )
                )
                .mappings()
                .one_or_none()
            )
            if calculated is None:
                raise SpecificationError("Calculated internal material fact not found")
            claim_reason = f"WORKSHOP_FOR:{calculated_material_fact_id}"
            existing = uow.execute(
                select(assembly_material_fact.c.id).where(
                    assembly_material_fact.c.project_id == project_id,
                    assembly_material_fact.c.source_kind == "WORKSHOP_CLAIM",
                    assembly_material_fact.c.reason == claim_reason,
                )
            ).scalar_one_or_none()
            claim_id = existing or new_id()
            values = {
                "board_id": calculated["board_id"],
                "material_kind": calculated["material_kind"],
                "quantity_decimal": str(claimed_quantity),
                "unit": calculated["unit"],
                "reason": claim_reason,
                "source_kind": "WORKSHOP_CLAIM",
                "updated_at_utc": now,
            }
            if existing:
                uow.execute(
                    update(assembly_material_fact)
                    .where(assembly_material_fact.c.id == claim_id)
                    .values(**values, row_version=assembly_material_fact.c.row_version + 1)
                )
                uow.execute(
                    delete(commercial_fact).where(
                        commercial_fact.c.project_id == project_id,
                        commercial_fact.c.assembly_material_fact_id == claim_id,
                    )
                )
            else:
                uow.execute(
                    assembly_material_fact.insert().values(
                        id=claim_id, project_id=project_id, **values
                    )
                )
            uow.execute(
                commercial_fact.insert().values(
                    id=new_id(),
                    project_id=project_id,
                    assembly_material_fact_id=claim_id,
                    price_decimal=str(claimed_price),
                    currency=_currency(currency),
                    source_reference=_required(source_reference, "source_reference"),
                    knowledge_status="KNOWN",
                )
            )
            self._touch(uow, project_id, now)
            uow.commit()
        return claim_id

    def set_override(
        self,
        *,
        project_id: str,
        source_kind: str,
        source_id: str,
        reason: str,
        supply_scope: str | None = None,
        note: str | None = None,
        included: bool | None = None,
        quantity_correction=None,
    ) -> str:
        values = {
            "supply_scope": supply_scope,
            "note": note,
            "included": included,
            "quantity_correction_decimal": None
            if quantity_correction is None
            else str(_non_negative(quantity_correction, "quantity_correction")),
            "reason": _required(reason, "reason"),
            "updated_at_utc": datetime.now(UTC),
        }
        with UnitOfWork(self._engine) as uow:
            existing = uow.execute(
                select(specification_override.c.id).where(
                    specification_override.c.project_id == project_id,
                    specification_override.c.source_kind == source_kind,
                    specification_override.c.source_id == source_id,
                )
            ).scalar_one_or_none()
            identifier = existing or new_id()
            if existing:
                uow.execute(
                    update(specification_override)
                    .where(specification_override.c.id == identifier)
                    .values(**values, row_version=specification_override.c.row_version + 1)
                )
            else:
                uow.execute(
                    specification_override.insert().values(
                        id=identifier,
                        project_id=project_id,
                        source_kind=source_kind,
                        source_id=source_id,
                        **values,
                    )
                )
            self._touch(uow, project_id, datetime.now(UTC))
            uow.commit()
        return identifier

    def _all_sources(self, project_id: str, context: dict) -> list[SpecificationSource]:
        return (
            self._equipment_sources(project_id, context)
            + self._field_device_sources(project_id, context)
            + self._mounting_box_sources(project_id, context)
            + self._cable_sources(project_id, context)
            + self._conduit_sources(project_id, context)
            + self._led_sources(project_id, context)
            + self._material_sources(project_id, context)
        )

    def _equipment_sources(self, project_id: str, context: dict) -> list[SpecificationSource]:
        with self._engine.connect() as connection:
            rows = list(
                connection.execute(
                    select(
                        project_instance,
                        passport_definition.c.name.label("passport_name"),
                        passport_definition.c.passport_key,
                        product_definition.c.product_key,
                        product_definition.c.version.label("product_version"),
                        product_definition.c.name.label("product_name"),
                        product_definition.c.article,
                    )
                    .join(
                        passport_definition,
                        passport_definition.c.id == project_instance.c.passport_definition_id,
                    )
                    .outerjoin(
                        product_definition,
                        product_definition.c.id == project_instance.c.product_definition_id,
                    )
                    .where(
                        project_instance.c.project_id == project_id,
                        project_instance.c.lifecycle == "ACTIVE",
                    )
                ).mappings()
            )
        output = []
        for row in rows:
            override = context["overrides"].get(("PROJECT_INSTANCE", row["id"]), {})
            scope = _override_value(override, "supply_scope", row["supply_scope"])
            included = _override_value(override, "included", True)
            product_id = row["product_definition_id"]
            price, currency = context["product_prices"].get(product_id, (None, None))
            product_key = row["product_key"]
            item_key = (
                f"PRODUCT:{product_key}:v{row['product_version']}"
                if product_key
                else f"PASSPORT:{row['passport_key']}:UNSELECTED:{row['id']}"
            )
            note = _override_value(override, "note", row["notes"])
            if scope == "CUSTOMER":
                note = _join_note(note, "Поставка заказчика")
            output.append(
                SpecificationSource(
                    "PROJECT_INSTANCE",
                    row["id"],
                    item_key,
                    row["product_name"] or row["passport_name"],
                    row["article"],
                    _corrected_quantity(Decimal("1"), override),
                    "pcs",
                    scope,
                    bool(included),
                    scope == "NEIROLINKS",
                    unit_price=price,
                    currency=currency,
                    note=note,
                    trace=f"Экземпляр {row['designation']}; количество 1",
                )
            )
        return output

    def _field_device_sources(
        self, project_id: str, context: dict
    ) -> list[SpecificationSource]:
        rows = self._field_device_rows(project_id)
        output = []
        for row in rows:
            kind = _field_device_kind(row)
            if kind in {"BOARD", "CABLE_OUTLET", "LIGHT_LED"}:
                continue
            override = context["overrides"].get(("FIELD_DEVICE", row["id"]), {})
            confirmed = _confirmed_field_selection(row, kind)
            scope = _override_value(
                override, "supply_scope", row["selection_supply_scope"] if confirmed else None
            )
            included = _override_value(override, "included", True)
            if confirmed:
                configuration = _normalized_json(row["configuration_json"])
                item_key = (
                    f"PRODUCT:{row['product_key']}:v{row['product_version']}:"
                    f"CONFIG:{configuration}"
                )
                name = row["product_name"]
                article = row["article"]
                price, currency = context["product_prices"].get(
                    row["product_definition_id"], (None, None)
                )
                configuration_note = _configuration_note(row["configuration_json"])
                trace = (
                    f"Полевое устройство {row['entity_handle'] or row['id']}; "
                    f"тип {kind}; конфигурация {configuration}"
                )
            else:
                item_key = f"FIELD_DEMAND:{kind}:UNSELECTED"
                name = f"Требуется изделие: {kind}"
                article = None
                price = currency = None
                configuration_note = "Нужны данные: точное изделие и конфигурация не подтверждены"
                trace = (
                    f"Полевое устройство {row['entity_handle'] or row['id']}; "
                    f"физический тип {kind}; каталог не подтверждён"
                )
            note = _join_note(
                _override_value(override, "note", None), configuration_note
            )
            output.append(
                SpecificationSource(
                    "FIELD_DEVICE",
                    row["id"],
                    item_key,
                    name,
                    article,
                    _corrected_quantity(Decimal("1"), override),
                    "pcs",
                    scope,
                    bool(included),
                    bool(scope == "NEIROLINKS" and confirmed),
                    unit_price=price,
                    currency=currency,
                    note=note,
                    trace=trace,
                )
            )
        return output

    def _mounting_box_sources(
        self, project_id: str, context: dict
    ) -> list[SpecificationSource]:
        output = []
        eligible = {"SOCKET", "SWITCH", "BUTTON", "SENSOR_MSW", "CONTROL_PANEL"}
        for row in self._field_device_rows(project_id):
            kind = _field_device_kind(row)
            if kind not in eligible:
                continue
            override = context["overrides"].get(("MOUNTING_BOX_DEMAND", row["id"]), {})
            scope = _override_value(
                override, "supply_scope", row["selection_supply_scope"]
            )
            output.append(
                SpecificationSource(
                    "MOUNTING_BOX_DEMAND",
                    row["id"],
                    "MOUNTING_BOX_DEMAND:UNSELECTED",
                    "Монтажная коробка — требуется подбор",
                    None,
                    _corrected_quantity(Decimal("1"), override),
                    "pcs",
                    scope,
                    bool(_override_value(override, "included", True)),
                    False,
                    note=_join_note(
                        _override_value(override, "note", None),
                        "Нужны данные: точное изделие отсутствует в каталоге",
                    ),
                    trace=(
                        f"Физическое устройство {row['entity_handle'] or row['id']}; "
                        f"тип {kind}; потребность 1, без points-1"
                    ),
                )
            )
        return output

    def _field_device_rows(self, project_id: str) -> list[dict]:
        with self._engine.connect() as connection:
            return list(
                connection.execute(
                    select(
                        field_device.c.id,
                        field_device.c.block_kind,
                        field_device.c.normalized_fields_json,
                        field_device.c.entity_handle,
                        field_device_product_selection.c.product_definition_id,
                        field_device_product_selection.c.configuration_schema_version,
                        field_device_product_selection.c.configuration_json,
                        field_device_product_selection.c.supply_scope.label(
                            "selection_supply_scope"
                        ),
                        field_device_product_selection.c.knowledge_status,
                        field_device_product_selection.c.lifecycle.label("selection_lifecycle"),
                        product_definition.c.product_key,
                        product_definition.c.version.label("product_version"),
                        product_definition.c.name.label("product_name"),
                        product_definition.c.article,
                        product_definition.c.project_parameters_json,
                        product_definition.c.lifecycle.label("product_lifecycle"),
                    )
                    .outerjoin(
                        field_device_product_selection,
                        field_device_product_selection.c.field_device_id == field_device.c.id,
                    )
                    .outerjoin(
                        product_definition,
                        product_definition.c.id
                        == field_device_product_selection.c.product_definition_id,
                    )
                    .where(
                        field_device.c.project_id == project_id,
                        field_device.c.lifecycle == "ACTIVE",
                    )
                    .order_by(
                        field_device.c.block_kind,
                        field_device.c.entity_handle,
                        field_device.c.id,
                    )
                ).mappings()
            )

    def _cable_sources(self, project_id: str, context: dict) -> list[SpecificationSource]:
        with self._engine.connect() as connection:
            rows = list(
                connection.execute(
                    select(
                        cable_line.c.id,
                        cable_line.c.designation,
                        cable_line.c.system_kind,
                        cable_line.c.cable_facts_json,
                        cable_length_fact.c.calculated_length_m_decimal,
                        cable_length_fact.c.additional_length_m_decimal,
                        cable_length_fact.c.manual_full_length_m_decimal,
                        cable_product_definition,
                    )
                    .outerjoin(
                        cable_line_product_selection,
                        cable_line_product_selection.c.cable_line_id == cable_line.c.id,
                    )
                    .outerjoin(
                        cable_product_definition,
                        cable_product_definition.c.id
                        == cable_line_product_selection.c.cable_product_definition_id,
                    )
                    .outerjoin(
                        cable_length_fact, cable_length_fact.c.cable_line_id == cable_line.c.id
                    )
                    .where(
                        cable_line.c.project_id == project_id, cable_line.c.lifecycle == "ACTIVE"
                    )
                ).mappings()
            )
        output = []
        for row in rows:
            facts = row["cable_facts_json"] or {}
            override = context["overrides"].get(("CABLE_LINE", row["id"]), {})
            scope = _override_value(
                override, "supply_scope", facts.get("SUPPLY_SCOPE") or "NEIROLINKS"
            )
            included = _override_value(override, "included", True)
            category = row["category"]
            is_hdmi = category == "HDMI" or facts.get("LOAD_TYPE") == "HDMI"
            if is_hdmi:
                quantity, unit = Decimal("1"), "pcs"
                factory = row["factory_length_m_decimal"]
                name = row["model"] or row["article"] or row["product_key"] or "HDMI — нужен подбор"
                if factory:
                    name = f"{name}, {factory} m"
                trace = f"HDMI {row['designation']}; одна заводская сборка"
            else:
                quantity, unit = self._effective_cable_length(project_id, row), "m"
                demand = facts.get("CABLE_TYPE") or facts.get("LOAD_TYPE") or row["system_kind"]
                name = (
                    row["model"]
                    or row["article"]
                    or row["product_key"]
                    or f"Требуется кабель: {demand}"
                )
                trace = f"Кабель {row['designation']}; эффективная длина {quantity} m"
            selected = row["product_key"] is not None
            demand_key = facts.get("CABLE_TYPE") or facts.get("LOAD_TYPE") or row["system_kind"]
            output.append(
                SpecificationSource(
                    "CABLE_LINE",
                    row["id"],
                    (
                        f"CABLE_PRODUCT:{row['product_key']}:v{row['version']}"
                        if selected
                        else f"CABLE_DEMAND:{demand_key}:UNSELECTED"
                    ),
                    name,
                    row["article"] if selected else None,
                    _corrected_quantity(quantity, override),
                    unit,
                    scope,
                    bool(included),
                    bool(scope == "NEIROLINKS" and selected),
                    note=(
                        _override_value(override, "note", None)
                        if selected
                        else _join_note(
                            _override_value(override, "note", None),
                            "Нужны данные: точное кабельное изделие не выбрано",
                        )
                    ),
                    trace=trace,
                )
            )
        return output

    def _effective_cable_length(self, project_id: str, row) -> Decimal | None:
        if self._cables is not None:
            try:
                return self._cables.effective_length(project_id, row["id"]).effective_m
            except Exception:
                pass
        return _effective_cable_length(row)

    @staticmethod
    def _data_issues(sources: tuple[SpecificationSource, ...]):
        for source in sources:
            code = message = action = None
            if source.source_kind == "FIELD_DEVICE" and ":UNSELECTED" in source.item_key:
                code = "FIELD_PRODUCT_CONFIGURATION_REQUIRED"
                message = "Точное изделие или его каталоговая конфигурация не подтверждены"
                action = "Выбрать совместимое изделие и значения из версионной схемы каталога"
            elif source.source_kind == "MOUNTING_BOX_DEMAND":
                code = "MOUNTING_BOX_CATALOG_DATA_REQUIRED"
                message = "Потребность рассчитана, точное изделие монтажной коробки неизвестно"
                action = "Дополнить паспорт/каталог и выбрать точное изделие"
            elif source.source_kind == "CABLE_LINE" and ":UNSELECTED" in source.item_key:
                code = "CABLE_PRODUCT_REQUIRED"
                message = "Тип и длина кабеля рассчитаны, точное изделие не выбрано"
                action = "Выбрать кабель из активного каталога"
            if code:
                yield SpecificationIssue(
                    code,
                    source.source_kind,
                    source.source_id,
                    message,
                    status="DATA_REQUIRED",
                    blocking=False,
                    required_action=action,
                )

    def _conduit_sources(self, project_id: str, context: dict) -> list[SpecificationSource]:
        with self._engine.connect() as connection:
            rows = list(
                connection.execute(
                    select(
                        conduit,
                        product_definition.c.product_key,
                        product_definition.c.name.label("product_name"),
                        product_definition.c.article.label("product_article"),
                    )
                    .outerjoin(
                        product_definition,
                        product_definition.c.id == conduit.c.product_definition_id,
                    )
                    .where(
                        conduit.c.project_id == project_id, conduit.c.lifecycle == "ACTIVE"
                    )
                ).mappings()
            )
        output = []
        for row in rows:
            override = context["overrides"].get(("CONDUIT", row["id"]), {})
            scope = _override_value(override, "supply_scope", row["supply_scope"] or "NEIROLINKS")
            included = _override_value(override, "included", True)
            diameter = row["diameter_mm_decimal"] or "?"
            product_id = row["product_definition_id"]
            price, currency = context["product_prices"].get(product_id, (None, None))
            output.append(
                SpecificationSource(
                    "CONDUIT",
                    row["id"],
                    (
                        f"PRODUCT:{row['product_key']}"
                        if product_id
                        else f"CONDUIT:{row['conduit_type']}:{diameter}"
                    ),
                    row["product_name"] or f"Труба {row['conduit_type']} Ø{diameter} mm",
                    row["product_article"],
                    _corrected_quantity(_optional_decimal(row["length_m_decimal"]), override),
                    "m",
                    scope,
                    bool(included),
                    scope == "NEIROLINKS",
                    unit_price=price,
                    currency=currency,
                    note=_override_value(override, "note", None),
                    trace=(
                        f"Трасса {row['designation']}; сохранённая длина "
                        f"{row['length_m_decimal']} m"
                    ),
                )
            )
        return output

    def _led_sources(self, project_id: str, context: dict) -> list[SpecificationSource]:
        if self._automation is None:
            return []
        with self._engine.connect() as connection:
            products = {
                row["product_key"]: dict(row)
                for row in connection.execute(select(product_definition)).mappings()
            }
            profile_rows = list(
                connection.execute(
                    select(
                        led_line_profile.c.id,
                        led_line_profile.c.tape_product_definition_id,
                        led_line_profile.c.supply_scope,
                    ).where(led_line_profile.c.project_id == project_id)
                ).mappings()
            )
        profile_ids_by_product_scope: dict[tuple[str, str], list[str]] = {}
        for profile in profile_rows:
            key = (profile["tape_product_definition_id"], profile["supply_scope"])
            profile_ids_by_product_scope.setdefault(key, []).append(profile["id"])
        output = []
        for item in self._automation.calculate_project_packing(project_id):
            product = products[item["product_key"]]
            profile_ids = profile_ids_by_product_scope.get(
                (product["id"], item["supply_scope"]), []
            )
            if not profile_ids:
                continue
            packing = item["packing"]
            price, currency = context["product_prices"].get(product["id"], (None, None))
            for index, profile_id in enumerate(profile_ids):
                quantity = (
                    (Decimal(packing.purchased_reels) if index == 0 else Decimal())
                    if packing.status == "VERIFIED"
                    else None
                )
                output.append(
                    SpecificationSource(
                        "LED_PROFILE",
                        profile_id,
                        f"PRODUCT:{product['product_key']}:v{product['version']}",
                        product["name"],
                        product["article"],
                        quantity,
                        "reel",
                        item["supply_scope"],
                        True,
                        item["supply_scope"] == "NEIROLINKS",
                        unit_price=price,
                        currency=currency,
                        trace=(
                            f"LED profile {profile_id}; group packing={packing.status}; "
                            f"reels={packing.purchased_reels}"
                        ),
                    )
                )
        return output

    def _material_sources(self, project_id: str, context: dict) -> list[SpecificationSource]:
        with self._engine.connect() as connection:
            rows = list(
                connection.execute(
                    select(assembly_material_fact).where(
                        assembly_material_fact.c.project_id == project_id,
                        assembly_material_fact.c.source_kind != "WORKSHOP_CLAIM",
                    )
                ).mappings()
            )
        output = []
        for row in rows:
            price, currency = context["material_prices"].get(row["id"], (None, None))
            output.append(
                SpecificationSource(
                    "ASSEMBLY_MATERIAL",
                    row["id"],
                    f"INTERNAL:{row['material_kind']}:{row['unit']}",
                    row["material_kind"],
                    None,
                    _optional_decimal(row["quantity_decimal"]),
                    row["unit"],
                    "ASSEMBLY_WORKSHOP",
                    False,
                    False,
                    internal=True,
                    unit_price=price,
                    currency=currency,
                    note=row["reason"],
                    trace=f"Функциональный узел/щит {row['board_id']}; {row['reason']}",
                )
            )
        return output

    def _workshop_control(self, project_id: str, context: dict) -> tuple[dict, ...]:
        with self._engine.connect() as connection:
            calculated = list(
                connection.execute(
                    select(assembly_material_fact).where(
                        assembly_material_fact.c.project_id == project_id,
                        assembly_material_fact.c.source_kind != "WORKSHOP_CLAIM",
                    )
                ).mappings()
            )
            claims = list(
                connection.execute(
                    select(assembly_material_fact).where(
                        assembly_material_fact.c.project_id == project_id,
                        assembly_material_fact.c.source_kind == "WORKSHOP_CLAIM",
                    )
                ).mappings()
            )
        by_calculated = {row["reason"].removeprefix("WORKSHOP_FOR:"): row for row in claims}
        output = []
        for row in calculated:
            calc_qty = _optional_decimal(row["quantity_decimal"])
            calc_price, currency = context["material_prices"].get(row["id"], (None, None))
            claim = by_calculated.get(row["id"])
            workshop_qty = _optional_decimal(claim["quantity_decimal"]) if claim else None
            workshop_price, workshop_currency = (
                context["material_prices"].get(claim["id"], (None, None)) if claim else (None, None)
            )
            calc_cost = _cost(calc_qty, calc_price)
            claimed_cost = _cost(workshop_qty, workshop_price)
            output.append(
                {
                    "calculated_material_fact_id": row["id"],
                    "workshop_material_fact_id": claim["id"] if claim else None,
                    "material_kind": row["material_kind"],
                    "unit": row["unit"],
                    "calculated_quantity": calc_qty,
                    "calculated_price": calc_price,
                    "calculated_cost": calc_cost,
                    "workshop_quantity": workshop_qty,
                    "workshop_price": workshop_price,
                    "claimed_cost": claimed_cost,
                    "quantity_deviation": (
                        workshop_qty - calc_qty
                        if workshop_qty is not None and calc_qty is not None
                        else None
                    ),
                    "cost_deviation": (
                        claimed_cost - calc_cost
                        if claimed_cost is not None and calc_cost is not None
                        else None
                    ),
                    "currency": workshop_currency or currency,
                    "trace": f"Щит {row['board_id']}; {row['reason']}",
                }
            )
        return tuple(output)

    def _read_context(self, project_id: str) -> dict:
        with self._engine.connect() as connection:
            overrides = {
                (row["source_kind"], row["source_id"]): dict(row)
                for row in connection.execute(
                    select(specification_override).where(
                        specification_override.c.project_id == project_id
                    )
                ).mappings()
            }
            facts = list(
                connection.execute(
                    select(commercial_fact)
                    .where(
                        commercial_fact.c.project_id == project_id,
                        commercial_fact.c.knowledge_status == "KNOWN",
                    )
                    .order_by(commercial_fact.c.updated_at_utc.desc())
                ).mappings()
            )
        product_prices = {}
        material_prices = {}
        for row in facts:
            price = (_optional_decimal(row["price_decimal"]), row["currency"])
            if row["product_definition_id"] is not None:
                product_prices.setdefault(row["product_definition_id"], price)
            if row["assembly_material_fact_id"] is not None:
                material_prices.setdefault(row["assembly_material_fact_id"], price)
        return {
            "overrides": overrides,
            "product_prices": product_prices,
            "material_prices": material_prices,
        }

    def _save_commercial_fact(
        self,
        *,
        project_id,
        product_definition_id,
        material_fact_id,
        price,
        currency,
        source_reference,
        effective_date,
    ):
        identifier, now = new_id(), datetime.now(UTC)
        with UnitOfWork(self._engine) as uow:
            if product_definition_id:
                exists = uow.execute(
                    select(product_definition.c.id).where(
                        product_definition.c.id == product_definition_id
                    )
                ).scalar_one_or_none()
            else:
                exists = uow.execute(
                    select(assembly_material_fact.c.id).where(
                        assembly_material_fact.c.id == material_fact_id,
                        assembly_material_fact.c.project_id == project_id,
                    )
                ).scalar_one_or_none()
            if exists is None:
                raise SpecificationError("Commercial fact target not found")
            uow.execute(
                commercial_fact.insert().values(
                    id=identifier,
                    project_id=project_id,
                    product_definition_id=product_definition_id,
                    assembly_material_fact_id=material_fact_id,
                    price_decimal=str(price),
                    currency=currency,
                    effective_date=effective_date,
                    source_reference=source_reference,
                    knowledge_status="KNOWN",
                )
            )
            self._touch(uow, project_id, now)
            uow.commit()
        return identifier

    @staticmethod
    def _known_total(rows: tuple[SpecificationRow, ...], scope: str) -> Decimal:
        return sum(
            (
                row.cost
                for row in rows
                if row.supply_scope == scope and row.budget_included and row.cost is not None
            ),
            Decimal(),
        )

    @staticmethod
    def _touch(uow, project_id: str, now: datetime) -> None:
        result = uow.execute(
            update(project)
            .where(project.c.id == project_id, project.c.lifecycle == "ACTIVE")
            .values(
                project_revision=project.c.project_revision + 1,
                row_version=project.c.row_version + 1,
                updated_at_utc=now,
            )
        )
        if result.rowcount != 1:
            raise SpecificationError("Project not found")


def _field_device_kind(row) -> str:
    fields = row["normalized_fields_json"] or {}
    raw = str(fields.get("DEVICE_TYPE") or row["block_kind"] or "UNKNOWN").strip().upper()
    block = str(row["block_kind"] or "").strip().upper()
    if "SENSOR_MSW" in block:
        return "SENSOR_MSW"
    for prefix in (
        "CONTROL_PANEL",
        "CABLE_OUTLET",
        "LIGHT_LED",
        "TRACK_230V",
        "TRACK_48V",
        "TRACK_DALI",
        "SENSOR_MSW",
        "SENSOR",
        "SOCKET",
        "SWITCH",
        "BUTTON",
        "FRAME",
        "EL_BOX",
        "BOARD",
    ):
        if raw == prefix or raw.startswith(prefix + "_") or block.startswith(prefix + "_"):
            return prefix
    return raw


def _confirmed_field_selection(row, kind: str) -> bool:
    if (
        row["product_definition_id"] is None
        or row["selection_lifecycle"] != "ACTIVE"
        or row["product_lifecycle"] != "ACTIVE"
        or row["knowledge_status"] != "KNOWN"
    ):
        return False
    parameters = row["project_parameters_json"] or {}
    schema = parameters.get("field_configuration_schema")
    if not isinstance(schema, dict):
        return False
    try:
        if int(schema.get("schema_version")) != int(row["configuration_schema_version"]):
            return False
    except (TypeError, ValueError):
        return False
    block_kinds = {str(value).strip().upper() for value in schema.get("field_block_kinds", [])}
    if kind not in block_kinds and str(row["block_kind"]).strip().upper() not in block_kinds:
        return False
    configuration = row["configuration_json"]
    if not isinstance(configuration, dict):
        return False
    options = schema.get("options")
    if not isinstance(options, list):
        return False
    allowed_keys = set()
    for option in options:
        if not isinstance(option, dict):
            return False
        key = str(option.get("key", "")).strip()
        values = option.get("values")
        if not key or not isinstance(values, list):
            return False
        allowed = {
            str(value.get("id", "")).strip()
            for value in values
            if isinstance(value, dict)
        }
        allowed_keys.add(key)
        selected = configuration.get(key)
        if selected in (None, ""):
            if bool(option.get("required", True)):
                return False
        elif str(selected).strip() not in allowed:
            return False
    return not (set(configuration) - allowed_keys)


def _normalized_json(value) -> str:
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _configuration_note(value) -> str:
    configuration = value or {}
    if not configuration:
        return "Конфигурация: без дополнительных параметров"
    return "Конфигурация: " + ", ".join(
        f"{key}={configuration[key]}" for key in sorted(configuration)
    )


def _effective_cable_length(row) -> Decimal | None:
    manual = _optional_decimal(row["manual_full_length_m_decimal"])
    if manual is not None:
        return manual
    calculated = _optional_decimal(row["calculated_length_m_decimal"])
    return (
        None
        if calculated is None
        else calculated + (_optional_decimal(row["additional_length_m_decimal"]) or Decimal())
    )


def _override_value(override: dict, key: str, default):
    return default if override.get(key) is None else override[key]


def _corrected_quantity(value: Decimal | None, override: dict) -> Decimal | None:
    correction = _optional_decimal(override.get("quantity_correction_decimal"))
    return correction if correction is not None else value


def _optional_decimal(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise SpecificationError(f"Invalid decimal: {value}") from exc
    if not result.is_finite():
        raise SpecificationError("Decimal must be finite")
    return result


def _non_negative(value, field: str) -> Decimal:
    result = _optional_decimal(value)
    if result is None or result < 0:
        raise SpecificationError(f"{field} must be non-negative")
    return result


def _required(value, field: str) -> str:
    result = str(value).strip() if value is not None else ""
    if not result:
        raise SpecificationError(f"{field} is required")
    return result


def _currency(value: str) -> str:
    result = _required(value, "currency").upper()
    if len(result) != 3:
        raise SpecificationError("currency must contain three letters")
    return result


def _join_note(first: str | None, second: str) -> str:
    return f"{first}; {second}" if first else second


def _cost(quantity: Decimal | None, price: Decimal | None) -> Decimal | None:
    return quantity * price if quantity is not None and price is not None else None
