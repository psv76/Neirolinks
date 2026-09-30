"""Transactional installation and explicit reconciliation of a catalog release."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, delete, select, update

from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    catalog_release,
    instance_resource,
    passport_definition,
    passport_property_definition,
    passport_resource_definition,
    passport_rule_definition,
    product_definition,
)
from nl_project_2.persistence.uow import UnitOfWork

from .payload import CatalogPayload
from .validation import validate_payload


class CatalogInstallError(RuntimeError):
    pass


class CatalogReconciliationError(CatalogInstallError):
    """The candidate cannot safely replace the installed catalog contract."""


@dataclass(frozen=True)
class InstallReceipt:
    release_id: str
    release_code: str
    content_sha256: str
    passport_count: int
    product_count: int
    already_installed: bool


@dataclass(frozen=True)
class ReconcileReceipt:
    release_id: str
    previous_release_code: str
    release_code: str
    content_sha256: str
    changed_passport_count: int
    refreshed_resource_count: int
    already_current: bool


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _value_type(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "BOOLEAN"
    if isinstance(value, (int, float)):
        return "NUMBER"
    if isinstance(value, str):
        return "STRING"
    if isinstance(value, list):
        return "ARRAY"
    return "OBJECT"


def _group_for(resource: dict[str, Any], label: str | None) -> str | None:
    for group, labels in (resource.get("groups") or {}).items():
        if label in labels:
            return group
    return None


def _expanded_resources(passport: dict[str, Any]):
    for resource in passport["resources"]:
        quantity = resource["quantity"]
        labels = resource.get("labels") or []
        ordinals = [0] if quantity == "PRODUCT_DEFINED" else range(int(quantity))
        for ordinal in ordinals:
            label = labels[ordinal] if ordinal < len(labels) else None
            display = dict(resource)
            display["materialization"] = (
                "PRODUCT_DEFINED" if quantity == "PRODUCT_DEFINED" else "FIXED"
            )
            display["label"] = label
            yield resource, ordinal, display, label


def _product_values(product: dict[str, Any]) -> dict[str, Any]:
    mapped = {
        "id",
        "product_id",
        "version",
        "name",
        "passport_id",
        "manufacturer",
        "series",
        "model",
        "article",
        "dimensions_mm",
        "din_modules",
        "parameters_used_by_project",
        "official_source",
    }
    dims = product.get("dimensions_mm") or {}
    extras = {key: value for key, value in product.items() if key not in mapped}
    return {
        "version": product["version"],
        "manufacturer": product["manufacturer"],
        "normalized_manufacturer": product["manufacturer"].strip().casefold(),
        "series": product.get("series"),
        "model": product.get("model"),
        "article": product.get("article"),
        "normalized_article": (
            product["article"].strip().casefold() if product.get("article") else None
        ),
        "name": product["name"],
        "width_mm_decimal": (str(dims.get("width")) if dims.get("width") is not None else None),
        "height_mm_decimal": (str(dims.get("height")) if dims.get("height") is not None else None),
        "depth_mm_decimal": (str(dims.get("depth")) if dims.get("depth") is not None else None),
        "din_width_decimal": (
            str(product.get("din_modules")) if product.get("din_modules") is not None else None
        ),
        "package_facts_json": extras,
        "project_parameters_json": product["parameters_used_by_project"],
        "supply_defaults_json": product.get("project_selection"),
        "evidence_json": product["official_source"],
        "lifecycle": "ACTIVE",
    }


class CatalogInstaller:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def install(self, payload: CatalogPayload) -> InstallReceipt:
        validate_payload(payload)
        manifest = payload.manifest
        release_code = manifest["release_code"]
        passports = payload.passports["passports"]
        products = payload.products["products"]
        with UnitOfWork(self._engine) as uow:
            existing = (
                uow.execute(
                    select(catalog_release).where(catalog_release.c.release_code == release_code)
                )
                .mappings()
                .one_or_none()
            )
            if existing:
                if existing["content_sha256"] != payload.content_sha256:
                    raise CatalogInstallError("Existing release code has different content hash")
                uow.commit()
                return InstallReceipt(
                    existing["id"],
                    release_code,
                    payload.content_sha256,
                    len(passports),
                    len(products),
                    True,
                )
            active = (
                uow.execute(
                    select(catalog_release).where(catalog_release.c.status == "ACTIVE")
                )
                .mappings()
                .one_or_none()
            )
            if active is not None:
                predecessor = active["release_code"]
                declaration = (manifest.get("additive_predecessors") or {}).get(
                    predecessor
                )
                if declaration is None:
                    raise CatalogInstallError(
                        f"Active immutable release {active['release_code']!r} is not the declared "
                        "additive predecessor"
                    )
                return self._install_additive_successor(
                    uow, active, payload, passports, products, declaration
                )

            release_id = new_id()
            uow.execute(
                catalog_release.insert().values(
                    id=release_id,
                    release_code=release_code,
                    schema_version=int(manifest["schema_version"]),
                    content_sha256=payload.content_sha256,
                    installed_at_utc=datetime.now(UTC),
                    status="ACTIVE",
                )
            )
            passport_db_ids: dict[str, str] = {}
            for passport in passports:
                passport_id = new_id()
                passport_db_ids[passport["id"]] = passport_id
                uow.execute(
                    passport_definition.insert().values(
                        id=passport_id,
                        catalog_release_id=release_id,
                        passport_key=passport["id"],
                        version=passport["version"],
                        name=passport["name"],
                        equipment_class=passport["equipment_class"],
                        functional_role=passport["functional_role"],
                        schema_version=1,
                        source_reference=_json(passport.get("normative_basis", [])),
                        content_sha256=_sha(passport),
                        lifecycle="ACTIVE",
                    )
                )
                for key, value in (passport.get("project_characteristics") or {}).items():
                    uow.execute(
                        passport_property_definition.insert().values(
                            id=new_id(),
                            passport_definition_id=passport_id,
                            property_key=key,
                            value_type=_value_type(value),
                            value_text=_json(value),
                            knowledge_status="UNKNOWN" if value is None else "KNOWN",
                            source_reference=_json(passport.get("normative_basis", [])),
                        )
                    )
                for resource, ordinal, display, label in _expanded_resources(passport):
                    uow.execute(
                        passport_resource_definition.insert().values(
                            id=new_id(),
                            passport_definition_id=passport_id,
                            resource_key=resource["resource_id"],
                            ordinal=ordinal,
                            resource_kind=resource["kind"],
                            direction=resource["direction"],
                            medium=resource.get("medium", resource["kind"]),
                            electrical_json=resource.get("electrical"),
                            signal_json=resource.get("signal"),
                            exclusive=bool(resource.get("exclusive", False)),
                            capacity_decimal=(
                                str(resource.get("capacity"))
                                if resource.get("capacity") is not None
                                else None
                            ),
                            group_key=_group_for(resource, label),
                            display_json=display,
                        )
                    )
                rule_number = 0
                for key in (
                    "compatibility",
                    "validation_parameters",
                    "din_layout",
                    "required_product_data",
                ):
                    if key not in passport:
                        continue
                    rule_number += 1
                    uow.execute(
                        passport_rule_definition.insert().values(
                            id=new_id(),
                            passport_definition_id=passport_id,
                            rule_key=key,
                            rule_kind=key.upper(),
                            rule_version=1,
                            parameters_json={"value": passport[key]},
                            resource_keys_json=[
                                resource["resource_id"] for resource in passport["resources"]
                            ],
                        )
                    )

            for product in products:
                uow.execute(
                    product_definition.insert().values(
                        id=new_id(),
                        catalog_release_id=release_id,
                        passport_definition_id=passport_db_ids[product["passport_id"]],
                        product_key=product["id"],
                        **_product_values(product),
                    )
                )
            uow.commit()
        return InstallReceipt(
            release_id,
            release_code,
            payload.content_sha256,
            len(passports),
            len(products),
            False,
        )

    def _install_additive_successor(
        self, uow, active, payload, passports, products, declaration
    ) -> InstallReceipt:
        manifest = payload.manifest
        installed_passports = {
            row["passport_key"]: dict(row)
            for row in uow.execute(
                select(passport_definition).where(
                    passport_definition.c.catalog_release_id == active["id"]
                )
            ).mappings()
        }
        candidate_passports = {item["id"]: item for item in passports}
        added_passports = set(candidate_passports) - set(installed_passports)
        if added_passports != set(declaration.get("passports", [])):
            raise CatalogInstallError("Catalog successor has undeclared passport changes")
        for key, current in installed_passports.items():
            candidate = candidate_passports.get(key)
            if candidate is None or current["content_sha256"] != _sha(candidate):
                raise CatalogInstallError(
                    f"Catalog successor changes existing passport {key!r}"
                )

        installed_products = {
            row["product_key"]: dict(row)
            for row in uow.execute(
                select(product_definition).where(
                    product_definition.c.catalog_release_id == active["id"]
                )
            ).mappings()
        }
        candidate_products = {item["id"]: item for item in products}
        added_products = set(candidate_products) - set(installed_products)
        if added_products != set(declaration.get("products", [])):
            raise CatalogInstallError("Catalog successor has undeclared product changes")
        for key, current in installed_products.items():
            candidate = candidate_products.get(key)
            if candidate is None:
                raise CatalogInstallError(f"Catalog successor removes product {key!r}")
            expected = _product_values(candidate)
            if any(current[field] != value for field, value in expected.items()):
                raise CatalogInstallError(
                    f"Catalog successor changes existing product {key!r}"
                )

        passport_ids = {key: row["id"] for key, row in installed_passports.items()}
        for key in sorted(added_passports):
            passport = candidate_passports[key]
            passport_id = new_id()
            passport_ids[key] = passport_id
            uow.execute(
                passport_definition.insert().values(
                    id=passport_id,
                    catalog_release_id=active["id"],
                    passport_key=key,
                    version=passport["version"],
                    name=passport["name"],
                    equipment_class=passport["equipment_class"],
                    functional_role=passport["functional_role"],
                    schema_version=1,
                    source_reference=_json(passport.get("normative_basis", [])),
                    content_sha256=_sha(passport),
                    lifecycle="ACTIVE",
                )
            )
            for property_key, value in (passport.get("project_characteristics") or {}).items():
                uow.execute(
                    passport_property_definition.insert().values(
                        id=new_id(),
                        passport_definition_id=passport_id,
                        property_key=property_key,
                        value_type=_value_type(value),
                        value_text=_json(value),
                        knowledge_status="UNKNOWN" if value is None else "KNOWN",
                        source_reference=_json(passport.get("normative_basis", [])),
                    )
                )
            for resource, ordinal, display, label in _expanded_resources(passport):
                uow.execute(
                    passport_resource_definition.insert().values(
                        id=new_id(),
                        passport_definition_id=passport_id,
                        resource_key=resource["resource_id"],
                        ordinal=ordinal,
                        resource_kind=resource["kind"],
                        direction=resource["direction"],
                        medium=resource.get("medium", resource["kind"]),
                        electrical_json=resource.get("electrical"),
                        signal_json=resource.get("signal"),
                        exclusive=bool(resource.get("exclusive", False)),
                        capacity_decimal=(
                            str(resource.get("capacity"))
                            if resource.get("capacity") is not None
                            else None
                        ),
                        group_key=_group_for(resource, label),
                        display_json=display,
                    )
                )
            for rule_key in (
                "compatibility",
                "validation_parameters",
                "din_layout",
                "required_product_data",
            ):
                if rule_key in passport:
                    uow.execute(
                        passport_rule_definition.insert().values(
                            id=new_id(),
                            passport_definition_id=passport_id,
                            rule_key=rule_key,
                            rule_kind=rule_key.upper(),
                            rule_version=1,
                            parameters_json={"value": passport[rule_key]},
                            resource_keys_json=[
                                resource["resource_id"] for resource in passport["resources"]
                            ],
                        )
                    )

        for key in sorted(added_products):
            product = candidate_products[key]
            uow.execute(
                product_definition.insert().values(
                    id=new_id(),
                    catalog_release_id=active["id"],
                    passport_definition_id=passport_ids[product["passport_id"]],
                    product_key=key,
                    **_product_values(product),
                )
            )
        uow.execute(
            update(catalog_release)
            .where(catalog_release.c.id == active["id"])
            .values(
                release_code=manifest["release_code"],
                schema_version=int(manifest["schema_version"]),
                content_sha256=payload.content_sha256,
                installed_at_utc=datetime.now(UTC),
            )
        )
        uow.commit()
        return InstallReceipt(
            active["id"],
            manifest["release_code"],
            payload.content_sha256,
            len(passports),
            len(products),
            False,
        )

    def reconcile_active(self, payload: CatalogPayload) -> ReconcileReceipt:
        """Atomically apply a versioned, topology-preserving passport correction.

        This explicit maintenance operation intentionally does not run during normal
        application startup.  It preserves release/definition/resource identifiers,
        user instances and relations.  Product or resource-topology changes are
        rejected because they require a separate migration design.
        """

        validate_payload(payload)
        manifest = payload.manifest
        release_code = manifest["release_code"]
        candidate_passports = {item["id"]: item for item in payload.passports["passports"]}
        candidate_products = {item["id"]: item for item in payload.products["products"]}
        with UnitOfWork(self._engine) as uow:
            active = (
                uow.execute(select(catalog_release).where(catalog_release.c.status == "ACTIVE"))
                .mappings()
                .one_or_none()
            )
            if active is None:
                raise CatalogReconciliationError(
                    "No active catalog exists; use immutable installation instead"
                )
            previous_release_code = active["release_code"]
            if (
                previous_release_code == release_code
                and active["content_sha256"] == payload.content_sha256
            ):
                uow.commit()
                return ReconcileReceipt(
                    active["id"],
                    previous_release_code,
                    release_code,
                    payload.content_sha256,
                    0,
                    0,
                    True,
                )
            collision = uow.execute(
                select(catalog_release.c.id).where(
                    catalog_release.c.release_code == release_code,
                    catalog_release.c.id != active["id"],
                )
            ).scalar_one_or_none()
            if collision is not None:
                raise CatalogReconciliationError(
                    f"Candidate release code {release_code!r} already exists"
                )

            installed_passports = {
                row["passport_key"]: dict(row)
                for row in uow.execute(
                    select(passport_definition).where(
                        passport_definition.c.catalog_release_id == active["id"]
                    )
                ).mappings()
            }
            if installed_passports.keys() != candidate_passports.keys():
                raise CatalogReconciliationError(
                    "Passport identity set changed; topology-preserving reconciliation refused"
                )

            installed_products = {
                row["product_key"]: dict(row)
                for row in uow.execute(
                    select(
                        product_definition,
                        passport_definition.c.passport_key.label("passport_key"),
                    )
                    .join(
                        passport_definition,
                        passport_definition.c.id == product_definition.c.passport_definition_id,
                    )
                    .where(product_definition.c.catalog_release_id == active["id"])
                ).mappings()
            }
            if installed_products.keys() != candidate_products.keys():
                raise CatalogReconciliationError(
                    "Product identity set changed; passport-only reconciliation refused"
                )
            for key, candidate in candidate_products.items():
                current = installed_products[key]
                expected = _product_values(candidate)
                if current["passport_key"] != candidate["passport_id"] or any(
                    current[field] != value for field, value in expected.items()
                ):
                    raise CatalogReconciliationError(
                        f"Product {key!r} changed; a product migration is required"
                    )

            plans: list[tuple[dict[str, Any], dict[str, Any], list[tuple]]] = []
            for key in sorted(candidate_passports):
                current = installed_passports[key]
                candidate = candidate_passports[key]
                candidate_hash = _sha(candidate)
                if current["content_sha256"] == candidate_hash:
                    if current["version"] != candidate["version"]:
                        raise CatalogReconciliationError(
                            f"Unchanged passport {key!r} has a different version"
                        )
                    continue
                if candidate["version"] <= current["version"]:
                    raise CatalogReconciliationError(
                        f"Changed passport {key!r} requires a monotonic version bump"
                    )
                current_resources = {
                    (row["resource_key"], row["ordinal"]): dict(row)
                    for row in uow.execute(
                        select(passport_resource_definition).where(
                            passport_resource_definition.c.passport_definition_id == current["id"]
                        )
                    ).mappings()
                }
                expanded = list(_expanded_resources(candidate))
                candidate_resource_keys = {
                    (resource["resource_id"], ordinal)
                    for resource, ordinal, _display, _label in expanded
                }
                if current_resources.keys() != candidate_resource_keys:
                    raise CatalogReconciliationError(
                        f"Resource topology changed for passport {key!r}"
                    )
                resource_plans = []
                for resource, ordinal, display, label in expanded:
                    current_resource = current_resources[(resource["resource_id"], ordinal)]
                    current_display = dict(current_resource["display_json"] or {})
                    structural_pairs = (
                        (current_resource["resource_kind"], resource["kind"]),
                        (current_resource["direction"], resource["direction"]),
                        (
                            current_resource["medium"],
                            resource.get("medium", resource["kind"]),
                        ),
                        (
                            current_display.get("materialization"),
                            display.get("materialization"),
                        ),
                        (current_display.get("quantity"), display.get("quantity")),
                        (current_display.get("grouping"), display.get("grouping")),
                        (current_display.get("groups"), display.get("groups")),
                        (current_resource["group_key"], _group_for(resource, label)),
                    )
                    if any(before != after for before, after in structural_pairs):
                        raise CatalogReconciliationError(
                            f"Resource structure changed for {key!r}/{resource['resource_id']}"
                        )
                    resource_plans.append((current_resource, resource, display, label))
                plans.append((current, candidate, resource_plans))

            refreshed = 0
            for current, candidate, resource_plans in plans:
                passport_id = current["id"]
                uow.execute(
                    update(passport_definition)
                    .where(passport_definition.c.id == passport_id)
                    .values(
                        version=candidate["version"],
                        name=candidate["name"],
                        equipment_class=candidate["equipment_class"],
                        functional_role=candidate["functional_role"],
                        source_reference=_json(candidate.get("normative_basis", [])),
                        content_sha256=_sha(candidate),
                    )
                )
                uow.execute(
                    delete(passport_property_definition).where(
                        passport_property_definition.c.passport_definition_id == passport_id
                    )
                )
                for key, value in (candidate.get("project_characteristics") or {}).items():
                    uow.execute(
                        passport_property_definition.insert().values(
                            id=new_id(),
                            passport_definition_id=passport_id,
                            property_key=key,
                            value_type=_value_type(value),
                            value_text=_json(value),
                            knowledge_status="UNKNOWN" if value is None else "KNOWN",
                            source_reference=_json(candidate.get("normative_basis", [])),
                        )
                    )
                uow.execute(
                    delete(passport_rule_definition).where(
                        passport_rule_definition.c.passport_definition_id == passport_id
                    )
                )
                for rule_key in (
                    "compatibility",
                    "validation_parameters",
                    "din_layout",
                    "required_product_data",
                ):
                    if rule_key not in candidate:
                        continue
                    uow.execute(
                        passport_rule_definition.insert().values(
                            id=new_id(),
                            passport_definition_id=passport_id,
                            rule_key=rule_key,
                            rule_kind=rule_key.upper(),
                            rule_version=candidate["version"],
                            parameters_json={"value": candidate[rule_key]},
                            resource_keys_json=[
                                resource["resource_id"] for resource in candidate["resources"]
                            ],
                        )
                    )
                for current_resource, resource, display, _label in resource_plans:
                    resource_id = current_resource["id"]
                    uow.execute(
                        update(passport_resource_definition)
                        .where(passport_resource_definition.c.id == resource_id)
                        .values(
                            electrical_json=resource.get("electrical"),
                            signal_json=resource.get("signal"),
                            exclusive=bool(resource.get("exclusive", False)),
                            capacity_decimal=(
                                str(resource.get("capacity"))
                                if resource.get("capacity") is not None
                                else None
                            ),
                            display_json=display,
                        )
                    )
                    snapshots = list(
                        uow.execute(
                            select(instance_resource).where(
                                instance_resource.c.passport_resource_definition_id == resource_id
                            )
                        ).mappings()
                    )
                    for row in snapshots:
                        snapshot = dict(row["snapshot_json"] or {})
                        snapshot["passport_resource"] = display
                        runtime_definition = dict(snapshot.get("resource_definition") or {})
                        for declarative_key in (
                            "branching",
                            "exclusive",
                            "assignable",
                            "required",
                        ):
                            runtime_definition.pop(declarative_key, None)
                        snapshot["resource_definition"] = runtime_definition
                        uow.execute(
                            update(instance_resource)
                            .where(instance_resource.c.id == row["id"])
                            .values(
                                snapshot_json=snapshot,
                                row_version=instance_resource.c.row_version + 1,
                            )
                        )
                        refreshed += 1

            uow.execute(
                update(catalog_release)
                .where(catalog_release.c.id == active["id"])
                .values(
                    release_code=release_code,
                    schema_version=int(manifest["schema_version"]),
                    content_sha256=payload.content_sha256,
                    installed_at_utc=datetime.now(UTC),
                )
            )
            uow.commit()
        return ReconcileReceipt(
            active["id"],
            previous_release_code,
            release_code,
            payload.content_sha256,
            len(plans),
            refreshed,
            False,
        )
