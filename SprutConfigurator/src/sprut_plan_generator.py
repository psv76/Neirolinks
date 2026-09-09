from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import re

DIRECT_OUTPUT_RE = re.compile(r"^[A-Za-z0-9_.-]+/(?:K\d+|Channel \d+)$")


@dataclass
class GenerationResult:
    plan: dict[str, Any]
    errors: list[str]
    warnings: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _render(template: str, line: dict[str, Any]) -> str:
    return template.format(
        id=_clean(line.get("id")),
        room=_clean(line.get("room")),
        purpose=_clean(line.get("purpose")),
        connection_point=_clean(line.get("connection_point")),
        board=_clean(line.get("board")),
    )


def _copy_presentation(
    service_spec: dict[str, Any],
    service: dict[str, Any],
) -> None:
    if "visible" in service_spec:
        service["visible"] = service_spec["visible"]
    if "status" in service_spec:
        service["status"] = dict(service_spec["status"])
    if "bridge" in service_spec:
        service["bridge"] = dict(service_spec["bridge"])


def _resolve_serial(
    spec: dict[str, Any],
    line: dict[str, Any],
) -> tuple[str, str | None]:
    if "serial" in spec:
        serial = _clean(spec["serial"])
        return serial, None if serial else "literal serial is empty"

    source = spec.get("serial_from")
    if source == "connection_point":
        serial = _clean(line.get("connection_point"))
        if not serial:
            return "", "connection_point is empty"
        if spec.get("require_direct_output", False) and not DIRECT_OUTPUT_RE.fullmatch(serial):
            return "", (
                f"connection_point {serial!r} is not a direct WB output identity"
            )
        return serial, None

    return "", "serial or supported serial_from is required"


def _normalize_room_map(
    raw_room_map: Any,
    errors: list[str],
) -> dict[str, str]:
    if raw_room_map is None:
        return {}
    if not isinstance(raw_room_map, dict):
        errors.append("policy.room_map must be a mapping")
        return {}

    result: dict[str, str] = {}
    for raw_source, raw_target in raw_room_map.items():
        source = _clean(raw_source)
        target = _clean(raw_target)
        if not source:
            errors.append("policy.room_map contains an empty source room")
            continue
        if not target:
            errors.append(f"policy.room_map[{source!r}] target room is empty")
            continue
        result[source] = target
    return result


def generate_sprut_plan(
    source_model: dict[str, Any],
    policy: dict[str, Any],
) -> GenerationResult:
    """Generate Sprut YAML-compatible desired state from Project source model.

    The source adapter owns extraction from NL Project. This generator owns only
    the reusable normalized-source-model -> Sprut Plan transformation.

    Runtime Sprut IDs, hub serial and WebUI session identity never enter the
    generated plan.
    """
    errors: list[str] = []
    warnings: list[str] = []

    if policy.get("policy_version") != 1:
        errors.append(
            f"Unsupported policy_version={policy.get('policy_version')!r}; expected 1."
        )

    room_map = _normalize_room_map(policy.get("room_map"), errors)

    source_lines = source_model.get("lines")
    if not isinstance(source_lines, list):
        return GenerationResult(
            {"format_version": 2, "accessories": []},
            [*errors, "source_model.lines must be a list"],
            [],
        )

    by_id: dict[str, list[dict[str, Any]]] = {}
    for line in source_lines:
        if isinstance(line, dict):
            by_id.setdefault(_clean(line.get("id")), []).append(line)

    source_meta = source_model.get("source")
    source_object = (
        _clean(source_meta.get("object_name"))
        if isinstance(source_meta, dict)
        else ""
    )
    object_name = _clean(policy.get("object")) or source_object

    plan: dict[str, Any] = {
        "format_version": 2,
        "object": object_name,
        "accessories": [],
    }

    seen_serials: set[str] = set()
    targets = policy.get("targets")
    if not isinstance(targets, list):
        errors.append("policy.targets must be a list")
        return GenerationResult(plan, errors, warnings)

    for idx, spec in enumerate(targets, start=1):
        prefix = f"targets[{idx}]"
        if not isinstance(spec, dict):
            errors.append(f"{prefix}: must be an object")
            continue

        line_id = _clean(spec.get("source_line"))
        if not line_id:
            errors.append(f"{prefix}: source_line is required")
            continue

        matches = by_id.get(line_id, [])
        if len(matches) != 1:
            errors.append(
                f"{prefix}: source_line {line_id!r} resolved to {len(matches)} rows; "
                "expected exactly 1"
            )
            continue
        line = matches[0]

        serial, serial_error = _resolve_serial(spec, line)
        if serial_error:
            errors.append(f"{prefix} line {line_id}: {serial_error}")
            continue
        if serial in seen_serials:
            errors.append(
                f"{prefix} line {line_id}: duplicate generated serial {serial!r}"
            )
            continue
        seen_serials.add(serial)

        name_template = spec.get("name", "{id} {purpose}")
        if not isinstance(name_template, str):
            errors.append(f"{prefix}: name must be a string")
            continue

        name = _render(name_template, line).strip()
        if "room" in spec:
            room_template = spec.get("room")
            if not isinstance(room_template, str):
                errors.append(f"{prefix}: room must be a string")
                continue
            room = _render(room_template, line).strip()
        else:
            source_room = _clean(line.get("room"))
            room = room_map.get(source_room, source_room)
            if source_room in room_map and room != source_room:
                warnings.append(
                    f"line {line_id}: room mapped {source_room!r} -> {room!r}"
                )

        if not name:
            errors.append(f"{prefix} line {line_id}: generated name is empty")
            continue
        if len(name) > 32:
            errors.append(
                f"{prefix} line {line_id}: generated name exceeds Sprut 32-char "
                f"limit: {name!r}"
            )
            continue
        if not room:
            errors.append(f"{prefix} line {line_id}: generated room is empty")
            continue

        service_specs = spec.get("services")
        if not isinstance(service_specs, list) or not service_specs:
            errors.append(
                f"{prefix} line {line_id}: services must be a non-empty list"
            )
            continue

        services: list[dict[str, Any]] = []
        seen_types: set[str] = set()
        for sidx, service_spec in enumerate(service_specs, start=1):
            sprefix = f"{prefix}.services[{sidx}]"
            if not isinstance(service_spec, dict):
                errors.append(f"{sprefix}: must be an object")
                continue

            service_type = _clean(service_spec.get("type"))
            if not service_type:
                errors.append(f"{sprefix}: type is required")
                continue
            if service_type in seen_types:
                errors.append(
                    f"{sprefix}: duplicate service type {service_type!r} is "
                    "ambiguous for Configurator"
                )
                continue
            seen_types.add(service_type)

            service_name_template = service_spec.get("name", name_template)
            if not isinstance(service_name_template, str):
                errors.append(f"{sprefix}: name must be a string")
                continue
            service_name = _render(service_name_template, line).strip()
            if len(service_name) > 32:
                errors.append(
                    f"{sprefix}: generated service name exceeds 32 chars: "
                    f"{service_name!r}"
                )
                continue

            service: dict[str, Any] = {
                "type": service_type,
                "name": service_name,
            }
            _copy_presentation(service_spec, service)
            services.append(service)

        if not services:
            continue

        plan["accessories"].append(
            {
                "serial": serial,
                "name": name,
                "room": room,
                "services": services,
            }
        )

    return GenerationResult(plan, errors, warnings)
