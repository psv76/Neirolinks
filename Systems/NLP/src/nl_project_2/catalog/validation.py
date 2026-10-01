"""Closed, deterministic validation for catalog import and editor previews."""

from __future__ import annotations

import hashlib

from .payload import CatalogPayload

ALLOWED_DIRECTIONS = {"IN", "OUT", "BIDIRECTIONAL", "PASSIVE", "INTERNAL"}
ALLOWED_BRANCHING = {
    "ALLOWED",
    "BUS_TOPOLOGY_ONLY",
    "FORBIDDEN",
    "INTERNAL_TO_FOUR_CHANNELS",
    "INTERNAL_TO_THREE_RELAYS",
    "NETWORK_TOPOLOGY",
    "ONLY_THROUGH_DISTRIBUTION_NODE",
    "PROTOCOL_DEPENDENT",
    "READ_ONLY",
    "VIA_SUPPORTED_WBIO_TOPOLOGY",
    "WITHIN_SELECTED_BUS_ONLY",
}


class CatalogValidationError(ValueError):
    def __init__(self, issues: list[str]) -> None:
        super().__init__("; ".join(issues))
        self.issues = tuple(issues)


def _duplicates(values: list[str]) -> set[str]:
    return {value for value in values if values.count(value) > 1}


def validate_payload(payload: CatalogPayload) -> None:
    issues: list[str] = []
    manifest = payload.manifest
    for name, expected in manifest.get("files", {}).items():
        actual = hashlib.sha256(payload.raw_files.get(name, b"")).hexdigest()
        if actual != expected:
            issues.append(f"HASH_MISMATCH:{name}:{actual}")
    if payload.content_sha256 != manifest.get("content_sha256"):
        issues.append("CONTENT_HASH_MISMATCH")

    passports_root = payload.passports
    products_root = payload.products
    for label, root, array_name in (
        ("passports", passports_root, "passports"),
        ("products", products_root, "products"),
    ):
        if not isinstance(root, dict):
            issues.append(f"{label}:ROOT_NOT_OBJECT")
            continue
        if root.get("schema_version") != "1.0":
            issues.append(f"{label}:SCHEMA_VERSION")
        if root.get("status") != "CANONICAL":
            issues.append(f"{label}:NOT_CANONICAL")
        if not isinstance(root.get(array_name), list):
            issues.append(f"{label}:{array_name.upper()}_NOT_ARRAY")

    passports = passports_root.get("passports", [])
    products = products_root.get("products", [])
    expected = manifest.get("expected_counts", {})
    if len(passports) != expected.get("passports"):
        issues.append(f"PASSPORT_COUNT:{len(passports)}")
    if len(products) != expected.get("products"):
        issues.append(f"PRODUCT_COUNT:{len(products)}")

    passport_ids = [item.get("id") for item in passports if isinstance(item, dict)]
    product_ids = [item.get("id") for item in products if isinstance(item, dict)]
    if None in passport_ids or _duplicates(passport_ids):
        issues.append("PASSPORT_IDS_NOT_UNIQUE")
    if None in product_ids or _duplicates(product_ids):
        issues.append("PRODUCT_IDS_NOT_UNIQUE")
    passport_set = set(passport_ids)
    required_runtime_passports = {
        "gateway.wirenboard.wb_dali3",
        "module.wirenboard.wbe2_i_knx",
        "module.wirenboard.wb_mcm8",
    }
    if not required_runtime_passports.issubset(passport_set):
        issues.append("REQUIRED_RUNTIME_PASSPORTS_MISSING")

    for item in passports:
        if not isinstance(item, dict):
            issues.append("PASSPORT_NOT_OBJECT")
            continue
        key = item.get("id", "?")
        required = (
            "passport_id",
            "version",
            "name",
            "equipment_class",
            "functional_role",
            "resources",
        )
        for field in required:
            if field not in item:
                issues.append(f"{key}:MISSING:{field}")
        if (
            item.get("passport_id") != key
            or not isinstance(item.get("version"), int)
            or item.get("version", 0) < 1
        ):
            issues.append(f"{key}:IDENTITY_OR_VERSION")
        resources = item.get("resources")
        if not isinstance(resources, list) or not resources:
            issues.append(f"{key}:RESOURCES_EMPTY")
            continue
        resource_ids = [
            resource.get("resource_id") for resource in resources if isinstance(resource, dict)
        ]
        if None in resource_ids or _duplicates(resource_ids):
            issues.append(f"{key}:RESOURCE_IDS_NOT_UNIQUE")
        for resource in resources:
            if not isinstance(resource, dict):
                issues.append(f"{key}:RESOURCE_NOT_OBJECT")
                continue
            quantity = resource.get("quantity")
            if quantity != "PRODUCT_DEFINED" and (not isinstance(quantity, int) or quantity < 1):
                issues.append(f"{key}:{resource.get('resource_id')}:BAD_QUANTITY")
            if resource.get("direction") not in ALLOWED_DIRECTIONS:
                issues.append(f"{key}:{resource.get('resource_id')}:BAD_DIRECTION")
            if resource.get("branching") not in ALLOWED_BRANCHING:
                issues.append(f"{key}:{resource.get('resource_id')}:BAD_BRANCHING")

        if key == "module.wirenboard.wb_mcm8" and isinstance(resources, list):
            by_id = {resource.get("resource_id"): resource for resource in resources}
            if set(by_id) != {"ELECTRONICS_POWER", "RS485", "INPUT"}:
                issues.append(f"{key}:RESOURCE_SET")
            input_resource = by_id.get("INPUT") or {}
            if (
                input_resource.get("kind") != "DRY_CONTACT_INPUT"
                or input_resource.get("direction") != "IN"
                or input_resource.get("quantity") != 8
                or input_resource.get("exclusive") is not True
                or input_resource.get("labels") != [f"Input {index}" for index in range(1, 9)]
            ):
                issues.append(f"{key}:INPUT_CONTRACT")

    forbidden = {str(value).casefold() for value in manifest.get("forbidden_manufacturers", [])}
    for item in products:
        if not isinstance(item, dict):
            issues.append("PRODUCT_NOT_OBJECT")
            continue
        key = item.get("id", "?")
        required = (
            "product_id",
            "version",
            "name",
            "passport_id",
            "manufacturer",
            "parameters_used_by_project",
            "official_source",
        )
        for field in required:
            if field not in item:
                issues.append(f"{key}:MISSING:{field}")
        if (
            item.get("product_id") != key
            or not isinstance(item.get("version"), int)
            or item.get("version", 0) < 1
        ):
            issues.append(f"{key}:IDENTITY_OR_VERSION")
        if item.get("passport_id") not in passport_set:
            issues.append(f"{key}:UNKNOWN_PASSPORT")
        if str(item.get("manufacturer", "")).casefold() in forbidden:
            issues.append(f"{key}:FORBIDDEN_MANUFACTURER")
        if not isinstance(item.get("parameters_used_by_project"), dict):
            issues.append(f"{key}:PROJECT_PARAMETERS_NOT_OBJECT")
        source = item.get("official_source")
        if not isinstance(source, dict) or not source.get("url") or not source.get("checked_on"):
            issues.append(f"{key}:OFFICIAL_SOURCE_INCOMPLETE")

    if issues:
        raise CatalogValidationError(sorted(set(issues)))
