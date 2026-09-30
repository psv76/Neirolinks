"""Typed read-only functional trace assembled from authoritative project facts."""

from __future__ import annotations

import re
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Any


@dataclass(frozen=True, slots=True)
class FunctionalEdge:
    source_resource_id: str
    target_resource_id: str
    edge_kind: str
    behavior: str
    rule_id: str
    status: str = "VERIFIED"
    message: str = ""
    persisted_id: str | None = None
    dependency_resource_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FunctionalTraceStep:
    source_id: str
    target_id: str
    source_label: str
    target_label: str
    edge_kind: str
    behavior: str
    status: str
    message: str
    persisted_id: str | None = None


@dataclass(frozen=True, slots=True)
class FunctionalTrace:
    status: str
    source_resource_id: str | None
    target_resource_id: str
    cable_line_id: str | None
    steps: tuple[FunctionalTraceStep, ...]
    message: str


def compile_internal_edges(
    resources: Iterable[dict[str, Any]],
    compatibility_by_instance: dict[str, dict[str, Any]],
) -> tuple[FunctionalEdge, ...]:
    """Compile typed apparatus paths only from declared passport/resource metadata."""

    grouped: dict[str, list[dict[str, Any]]] = {}
    for resource in resources:
        grouped.setdefault(resource["project_instance_id"], []).append(resource)
    edges: dict[tuple[str, str], FunctionalEdge] = {}

    def add(
        source: dict[str, Any],
        target: dict[str, Any],
        *,
        behavior: str,
        rule_id: str,
        message: str,
        dependencies: Iterable[dict[str, Any]] = (),
    ) -> None:
        key = (source["id"], target["id"])
        edges.setdefault(
            key,
            FunctionalEdge(
                source["id"],
                target["id"],
                "INTERNAL",
                behavior,
                rule_id,
                message=message,
                dependency_resource_ids=tuple(item["id"] for item in dependencies),
            ),
        )

    for instance_id, instance_resources in grouped.items():
        ordered = sorted(
            instance_resources,
            key=lambda item: (item["resource_key"], int(item["ordinal"]), item["id"]),
        )
        by_key: dict[str, list[dict[str, Any]]] = {}
        for resource in ordered:
            by_key.setdefault(resource["resource_key"], []).append(resource)
        compatibility = dict(compatibility_by_instance.get(instance_id) or {})

        # Product-defined positions are connected only within their declared group identity.
        distribution_groups: dict[str, list[dict[str, Any]]] = {}
        for resource in ordered:
            display = _display(resource)
            if display.get("grouping") and resource.get("group_key"):
                distribution_groups.setdefault(resource["group_key"], []).append(resource)
        for group_key, members in distribution_groups.items():
            for source in members:
                for target in members:
                    if source["id"] != target["id"]:
                        add(
                            source,
                            target,
                            behavior="DISTRIBUTION",
                            rule_id="passport.product_defined_grouping",
                            message=f"Связь внутри изолированной группы {group_key}",
                        )

        # Explicit RESOURCE_A_TO_RESOURCE_B contract.
        encoded_pair = compatibility.get("input_output_pairing")
        if isinstance(encoded_pair, str):
            matches = [
                (source_key, target_key)
                for source_key in by_key
                for target_key in by_key
                if encoded_pair == f"{source_key}_TO_{target_key}"
            ]
            if len(matches) == 1:
                source_key, target_key = matches[0]
                for source, target in _same_ordinal_pairs(by_key[source_key], by_key[target_key]):
                    add(
                        source,
                        target,
                        behavior="PASS_THROUGH",
                        rule_id="passport.input_output_pairing",
                        message="Защитный аппарат передаёт питание на защищённый выход",
                    )

        # Ordered paired_resources contract: declared IN sequence maps to declared OUT sequence.
        paired_keys = compatibility.get("paired_resources")
        if isinstance(paired_keys, list):
            input_keys = [
                key for key in paired_keys if _template_direction(by_key.get(key)) == "IN"
            ]
            output_keys = [
                key for key in paired_keys if _template_direction(by_key.get(key)) == "OUT"
            ]
            if input_keys and len(input_keys) == len(output_keys):
                for source_key, target_key in zip(input_keys, output_keys, strict=True):
                    for source, target in _same_ordinal_pairs(
                        by_key[source_key], by_key[target_key]
                    ):
                        add(
                            source,
                            target,
                            behavior="PASS_THROUGH",
                            rule_id="passport.paired_resources",
                            message="Парный полюс защиты передаёт соответствующий проводник",
                        )

        # Per-resource one-to-one pairing contract, used by repeated switched contacts.
        control_dependencies = [
            resource for resource in ordered if resource["resource_kind"] == "CONTROL_POWER_INPUT"
        ]
        for target in ordered:
            pairing = _display(target).get("pairing")
            match = (
                re.fullmatch(r"one-to-one with ([A-Za-z0-9_.-]+)", pairing)
                if isinstance(pairing, str)
                else None
            )
            if not match or match.group(1) not in by_key:
                continue
            sources = by_key[match.group(1)]
            source = next(
                (item for item in sources if int(item["ordinal"]) == int(target["ordinal"])),
                None,
            )
            if source is not None:
                add(
                    source,
                    target,
                    behavior="CONTROLLED",
                    rule_id="passport.one_to_one_pairing",
                    message="Силовой контакт проводит только при активной цепи управления",
                    dependencies=control_dependencies,
                )

        power_inputs = [
            resource
            for resource in ordered
            if resource["direction"] == "IN" and _family(resource) == "POWER"
        ]
        power_outputs = [
            resource
            for resource in ordered
            if resource["direction"] == "OUT" and _family(resource) == "POWER"
        ]
        if compatibility.get("series_connection_required") is True:
            _add_single_power_path(
                add,
                power_inputs,
                power_outputs,
                behavior="PASS_THROUGH",
                rule_id="passport.series_connection_required",
                message="Последовательный аппарат передаёт питание на ограниченный выход",
            )
        if compatibility.get("input_signal_type") and compatibility.get("output_signal_type"):
            _add_single_power_path(
                add,
                power_inputs,
                power_outputs,
                behavior="TRANSFORM",
                rule_id="passport.input_output_signal_transform",
                message=(
                    f"Преобразование {compatibility['input_signal_type']} → "
                    f"{compatibility['output_signal_type']}"
                ),
            )
        if compatibility.get("output_setpoint_must_match_loads") is True:
            _add_single_power_path(
                add,
                power_inputs,
                power_outputs,
                behavior="BUFFERED_TRANSFORM",
                rule_id="passport.buffered_power_path",
                message="Резервированный внутренний путь питания VIN → VOUT",
            )

        # Group labels are the machine contract linking COM inputs to relay outputs.
        electronics_dependencies = [
            resource for resource in ordered if resource["resource_kind"] == "DC_POWER_INPUT"
        ]
        group_inputs = {
            _display(resource).get("label"): resource
            for resource in ordered
            if resource["direction"] == "IN" and _display(resource).get("label")
        }
        for target in ordered:
            source = group_inputs.get(target.get("group_key"))
            if source is None or "RELAY" not in target["resource_kind"]:
                continue
            add(
                source,
                target,
                behavior="CONTROLLED",
                rule_id="passport.resource_group",
                message="Управляемый релейный выход получает потенциал своей группы COM",
                dependencies=electronics_dependencies,
            )

        # A single unlabelled INTERNAL_TO_* input feeds declared controlled outputs.
        internal_inputs = [
            resource
            for resource in ordered
            if resource["direction"] == "IN"
            and str(_display(resource).get("branching", "")).startswith("INTERNAL_TO_")
            and not _display(resource).get("label")
        ]
        if len(internal_inputs) == 1:
            source = internal_inputs[0]
            for target in ordered:
                if target["direction"] == "OUT" and _family(target) == "CONTROL":
                    add(
                        source,
                        target,
                        behavior="CONTROLLED",
                        rule_id="passport.internal_to_outputs",
                        message="Вход нагрузки питает управляемый выходной канал",
                        dependencies=[
                            item for item in electronics_dependencies if item["id"] != source["id"]
                        ],
                    )

    return tuple(
        sorted(
            edges.values(),
            key=lambda item: (
                item.source_resource_id,
                item.target_resource_id,
                item.rule_id,
            ),
        )
    )


def best_path(
    edges: Iterable[FunctionalEdge], target_resource_id: str
) -> tuple[FunctionalEdge, ...]:
    """Return a deterministic longest-root/shortest-target path in the derived graph."""

    edge_list = tuple(edges)
    outgoing: dict[str, list[FunctionalEdge]] = {}
    incoming_count: dict[str, int] = {}
    nodes = {target_resource_id}
    for edge in edge_list:
        outgoing.setdefault(edge.source_resource_id, []).append(edge)
        incoming_count[edge.target_resource_id] = incoming_count.get(edge.target_resource_id, 0) + 1
        nodes.update((edge.source_resource_id, edge.target_resource_id))
    roots = sorted(node for node in nodes if incoming_count.get(node, 0) == 0)
    candidates: list[tuple[FunctionalEdge, ...]] = []
    for root in roots:
        path = _shortest_path(outgoing, root, target_resource_id)
        if path is not None:
            candidates.append(path)
    if not candidates:
        for source in sorted(nodes):
            path = _shortest_path(outgoing, source, target_resource_id)
            if path:
                candidates.append(path)
    return max(
        candidates,
        key=lambda path: (
            len(path),
            tuple((edge.source_resource_id, edge.target_resource_id) for edge in path),
        ),
        default=(),
    )


def resolve_dependency_statuses(
    external_edges: Iterable[FunctionalEdge],
    internal_edges: Iterable[FunctionalEdge],
    *,
    label_for,
) -> tuple[tuple[FunctionalEdge, ...], tuple[FunctionalEdge, ...]]:
    """Propagate missing controlled-source dependencies without persisting edges."""

    base_external = tuple(external_edges)
    base_internal = tuple(internal_edges)
    current_external = base_external
    current_internal = base_internal
    for _ in range(len(base_external) + len(base_internal) + 1):
        producers: dict[str, list[FunctionalEdge]] = {}
        for edge in current_internal:
            producers.setdefault(edge.target_resource_id, []).append(edge)

        next_external = []
        for edge in base_external:
            source_producers = producers.get(edge.source_resource_id, ())
            incomplete = source_producers and not any(
                item.status == "VERIFIED" for item in source_producers
            )
            if not incomplete:
                next_external.append(edge)
                continue
            causes = _messages(source_producers)
            next_external.append(
                replace(
                    edge,
                    status="INCOMPLETE",
                    message=(
                        f"{edge.message}; источник управляемого выхода неполон"
                        + (f": {causes}" if causes else "")
                    ),
                )
            )

        incoming: dict[str, list[FunctionalEdge]] = {}
        for edge in (*next_external, *current_internal):
            incoming.setdefault(edge.target_resource_id, []).append(edge)

        next_internal = []
        for edge in base_internal:
            missing = []
            causes = []
            for resource_id in edge.dependency_resource_ids:
                candidate_edges = incoming.get(resource_id, ())
                if any(item.status == "VERIFIED" for item in candidate_edges):
                    continue
                missing.append(label_for(resource_id))
                detail = _messages(candidate_edges)
                if detail:
                    causes.append(detail)
            if not missing:
                next_internal.append(edge)
                continue
            message = f"{edge.message}; не назначено или не запитано: {', '.join(missing)}"
            if causes:
                message += f"; upstream: {'; '.join(dict.fromkeys(causes))}"
            next_internal.append(replace(edge, status="INCOMPLETE", message=message))

        resolved_external = tuple(next_external)
        resolved_internal = tuple(next_internal)
        if resolved_external == current_external and resolved_internal == current_internal:
            return resolved_external, resolved_internal
        current_external = resolved_external
        current_internal = resolved_internal
    return current_external, current_internal


def _shortest_path(outgoing, source, target):
    pending = deque([(source, ())])
    seen: set[str] = set()
    while pending:
        node, path = pending.popleft()
        if node == target:
            return path
        if node in seen:
            continue
        seen.add(node)
        for edge in sorted(
            outgoing.get(node, ()), key=lambda item: (item.target_resource_id, item.rule_id)
        ):
            if edge.target_resource_id not in seen:
                pending.append((edge.target_resource_id, path + (edge,)))
    return None


def _messages(edges):
    return "; ".join(dict.fromkeys(edge.message for edge in edges if edge.message))


def _add_single_power_path(add, inputs, outputs, **kwargs):
    if len(inputs) == 1 and len(outputs) == 1:
        add(inputs[0], outputs[0], **kwargs)


def _same_ordinal_pairs(sources, targets):
    targets_by_ordinal = {int(item["ordinal"]): item for item in targets}
    return [
        (source, targets_by_ordinal[int(source["ordinal"])])
        for source in sources
        if int(source["ordinal"]) in targets_by_ordinal
    ]


def _template_direction(resources):
    directions = {item["direction"] for item in resources or ()}
    return next(iter(directions)) if len(directions) == 1 else None


def _display(resource):
    snapshot = dict(resource.get("snapshot_json") or {})
    return dict(resource.get("display_json") or snapshot.get("passport_resource") or {})


def _family(resource):
    kind = str(resource["resource_kind"]).upper()
    if "ANALOG" in kind or "MEASUREMENT" in kind:
        return "ANALOG"
    if any(token in kind for token in ("RELAY", "PWM", "CONTROL", "DRY_CONTACT")):
        return "CONTROL"
    if any(token in kind for token in ("POWER", "VOUT", "VIN", "LINE", "NEUTRAL", "BUSBAR")):
        return "POWER"
    if "RS485" in kind or kind.startswith("BUS_"):
        return "BUS"
    return "SIGNAL"
