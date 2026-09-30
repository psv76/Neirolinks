"""Reusable user-facing labels for persisted functional resources."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def resource_display_name(resource: Mapping[str, Any] | None) -> str:
    """Return a proven passport label, otherwise a non-invented technical name."""

    if not resource:
        return "<missing>"
    display = _display(resource)
    label = display.get("label")
    if label not in (None, ""):
        return str(label)
    resource_key = str(resource.get("resource_key", "<missing>"))
    quantity = display.get("quantity")
    if quantity == 1 or quantity == "1":
        return resource_key
    ordinal = resource.get("ordinal")
    return resource_key if ordinal is None else f"{resource_key}[{ordinal}]"


def resource_user_label(resource: Mapping[str, Any] | None) -> str:
    """Return the instance-qualified label used by primary UI/read models."""

    if not resource:
        return "<missing>"
    designation = resource.get("instance_designation")
    name = resource_display_name(resource)
    return name if designation in (None, "") else f"{designation} / {name}"


def resource_technical_identity(resource: Mapping[str, Any] | None) -> str:
    """Return stable machine identity for tooltips, diagnostics and reports."""

    if not resource:
        return "<missing>"
    designation = resource.get("instance_designation")
    resource_key = str(resource.get("resource_key", "<missing>"))
    ordinal = resource.get("ordinal")
    identity = resource_key if ordinal is None else f"{resource_key}[{ordinal}]"
    return identity if designation in (None, "") else f"{designation} / {identity}"


def _display(resource: Mapping[str, Any]) -> dict[str, Any]:
    snapshot = dict(resource.get("snapshot_json") or {})
    return dict(resource.get("display_json") or snapshot.get("passport_resource") or {})
