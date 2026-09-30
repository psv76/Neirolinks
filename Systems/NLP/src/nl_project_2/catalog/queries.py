"""Read-only SQLite catalog projections for UI and diagnostics."""

from __future__ import annotations

import copy
import json

from sqlalchemy import Engine, func, select

from nl_project_2.persistence.schema import (
    catalog_release,
    passport_definition,
    passport_resource_definition,
    product_definition,
)


class CatalogQueries:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def active_release(self) -> dict | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    select(catalog_release).where(catalog_release.c.status == "ACTIVE")
                )
                .mappings()
                .one_or_none()
            )
            return None if row is None else dict(row)

    def passports(self) -> list[dict]:
        statement = (
            select(
                passport_definition.c.id,
                passport_definition.c.passport_key,
                passport_definition.c.version,
                passport_definition.c.name,
                passport_definition.c.equipment_class,
                func.count(func.distinct(passport_resource_definition.c.id)).label(
                    "resource_definition_count"
                ),
                func.count(func.distinct(product_definition.c.id)).label("product_count"),
            )
            .select_from(passport_definition)
            .join(
                catalog_release,
                catalog_release.c.id == passport_definition.c.catalog_release_id,
            )
            .outerjoin(
                passport_resource_definition,
                passport_resource_definition.c.passport_definition_id == passport_definition.c.id,
            )
            .outerjoin(
                product_definition,
                product_definition.c.passport_definition_id == passport_definition.c.id,
            )
            .where(catalog_release.c.status == "ACTIVE")
            .group_by(passport_definition.c.id)
            .order_by(passport_definition.c.passport_key)
        )
        with self._engine.connect() as connection:
            return [dict(row) for row in connection.execute(statement).mappings()]

    def products(self, passport_key: str | None = None) -> list[dict]:
        statement = (
            select(
                product_definition.c.id,
                product_definition.c.product_key,
                product_definition.c.version,
                product_definition.c.manufacturer,
                product_definition.c.article,
                product_definition.c.name,
                passport_definition.c.passport_key,
            )
            .select_from(product_definition)
            .join(
                passport_definition,
                passport_definition.c.id == product_definition.c.passport_definition_id,
            )
            .join(
                catalog_release,
                catalog_release.c.id == product_definition.c.catalog_release_id,
            )
            .where(catalog_release.c.status == "ACTIVE")
            .order_by(product_definition.c.manufacturer, product_definition.c.name)
        )
        if passport_key is not None:
            statement = statement.where(passport_definition.c.passport_key == passport_key)
        with self._engine.connect() as connection:
            return [dict(row) for row in connection.execute(statement).mappings()]


class ImmutableCatalogEditor:
    """Validation gateway: published rows are never edited in place."""

    def validate_candidate(self, payload) -> None:
        from .validation import validate_payload

        validate_payload(payload)

    def begin_draft(self, payload):
        return CatalogDraft(payload)

    def edit_published(self, *_args, **_kwargs) -> None:
        raise PermissionError(
            "Published catalog rows are immutable; prepare a new validated release instead"
        )


class CatalogDraft:
    """In-memory copy-on-write draft; installation still requires full hash validation."""

    def __init__(self, payload) -> None:
        self._source = payload
        self.passports = copy.deepcopy(payload.passports)
        self.products = copy.deepcopy(payload.products)

    def replace_product(self, product_key: str, replacement: dict) -> None:
        rows = self.products["products"]
        for index, row in enumerate(rows):
            if row.get("id") == product_key:
                rows[index] = copy.deepcopy(replacement)
                return
        raise KeyError(product_key)

    def add_product(self, product: dict) -> None:
        if any(row.get("id") == product.get("id") for row in self.products["products"]):
            raise ValueError(f"Duplicate product id: {product.get('id')}")
        self.products["products"].append(copy.deepcopy(product))

    def candidate(self, approved_manifest: dict | None = None):
        """Build a candidate; the old manifest deliberately makes edited data fail hash checks."""
        from .payload import CatalogPayload

        raw = {
            "equipment_passports.json": json.dumps(
                self.passports, ensure_ascii=False, indent=2
            ).encode("utf-8"),
            "products.json": json.dumps(self.products, ensure_ascii=False, indent=2).encode(
                "utf-8"
            ),
        }
        return CatalogPayload(
            manifest=copy.deepcopy(approved_manifest or self._source.manifest),
            passports=copy.deepcopy(self.passports),
            products=copy.deepcopy(self.products),
            raw_files=raw,
        )
