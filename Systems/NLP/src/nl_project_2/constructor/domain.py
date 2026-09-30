"""Pure generic relation validation and graph algorithms."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any


@dataclass(frozen=True, slots=True)
class RelationDefinition:
    kind: str
    family: str
    version: int = 1
    source_families: frozenset[str] = frozenset()
    target_families: frozenset[str] = frozenset()
    source_kinds: frozenset[str] = frozenset()
    target_kinds: frozenset[str] = frozenset()
    check_current_kind: bool = True
    check_voltage: bool = True
    check_signal: bool = True
    check_capacity: bool = True
    allow_self_loop: bool = False


@dataclass(frozen=True, slots=True)
class ResourceFacts:
    id: str
    instance_id: str
    key: str
    kind: str
    direction: str
    medium: str
    properties: dict[str, Any] = field(default_factory=dict)
    exclusive: bool = False
    branching: str = "FORBIDDEN"
    assignable: bool = True
    required: bool = False
    group_key: str | None = None


@dataclass(frozen=True, slots=True)
class RuleResult:
    rule_id: str
    rule_version: int
    outcome: str
    blocking: bool
    entity_ids: tuple[str, ...]
    actual: Any
    required: Any
    message: str


@dataclass(frozen=True, slots=True)
class RelationPreview:
    definition: RelationDefinition
    source: ResourceFacts
    target: ResourceFacts
    results: tuple[RuleResult, ...]

    @property
    def allowed(self) -> bool:
        return not any(result.blocking and result.outcome == "ERROR" for result in self.results)


def default_relation_definitions() -> dict[str, RelationDefinition]:
    """Finite registered relation families; callers may supply additional definitions."""

    return {
        "POWER_FLOW": RelationDefinition("POWER_FLOW", "POWER"),
        "CONTROL": RelationDefinition("CONTROL", "CONTROL"),
        "SIGNAL": RelationDefinition("SIGNAL", "SIGNAL"),
        "ANALOG_SIGNAL": RelationDefinition("ANALOG_SIGNAL", "ANALOG"),
        "INTERFACE": RelationDefinition(
            "INTERFACE", "INTERFACE", check_current_kind=False, check_voltage=False
        ),
        "BUS_LINK": RelationDefinition(
            "BUS_LINK", "BUS", check_current_kind=False, check_voltage=False
        ),
    }


def validate_relation(
    definition: RelationDefinition,
    source: ResourceFacts,
    target: ResourceFacts,
    *,
    source_relation_count: int = 0,
    target_relation_count: int = 0,
    existing_target_demands: tuple[Decimal, ...] = (),
) -> RelationPreview:
    results: list[RuleResult] = []
    ids = (source.id, target.id)

    def add(rule, outcome, actual, required, message, *, blocking=True):
        results.append(
            RuleResult(
                f"constructor.{rule}",
                definition.version,
                outcome,
                blocking,
                ids,
                actual,
                required,
                message,
            )
        )

    if source.id == target.id and not definition.allow_self_loop:
        add("self_loop", "ERROR", source.id, "different endpoints", "Self-loop is forbidden")
    else:
        add("self_loop", "PASS", source.id, "different endpoints", "Endpoints differ")

    direction_ok = source.direction in {"OUT", "BIDIRECTIONAL"} and target.direction in {
        "IN",
        "BIDIRECTIONAL",
    }
    add(
        "direction",
        "PASS" if direction_ok else "ERROR",
        [source.direction, target.direction],
        ["OUT|BIDIRECTIONAL", "IN|BIDIRECTIONAL"],
        "Resource directions are compatible"
        if direction_ok
        else "Relation requires an output source and an input target",
    )

    assignable = source.assignable and target.assignable
    add(
        "assignable",
        "PASS" if assignable else "ERROR",
        [source.assignable, target.assignable],
        True,
        "Resources are assignable" if assignable else "Internal/non-assignable resource selected",
    )

    source_family = _resource_family(source)
    target_family = _resource_family(target)
    allowed_source_families = definition.source_families or frozenset({definition.family})
    allowed_target_families = definition.target_families or frozenset({definition.family})
    family_ok = (
        source_family in allowed_source_families and target_family in allowed_target_families
    )
    add(
        "resource_family",
        "PASS" if family_ok else "ERROR",
        [source_family, target_family],
        {
            "source": sorted(allowed_source_families),
            "target": sorted(allowed_target_families),
        },
        "Resource families match relation"
        if family_ok
        else "Resource family does not match relation definition",
    )

    if definition.source_kinds:
        ok = source.kind in definition.source_kinds
        add(
            "source_kind",
            "PASS" if ok else "ERROR",
            source.kind,
            sorted(definition.source_kinds),
            "Source kind is allowed" if ok else "Source kind is not allowed",
        )
    if definition.target_kinds:
        ok = target.kind in definition.target_kinds
        add(
            "target_kind",
            "PASS" if ok else "ERROR",
            target.kind,
            sorted(definition.target_kinds),
            "Target kind is allowed" if ok else "Target kind is not allowed",
        )

    if definition.check_current_kind:
        _compare_equal_property(results, definition, source, target, "current_kind")
    if definition.check_voltage:
        _compare_ranges(results, definition, source, target, "voltage", "V")
    if definition.check_signal:
        _compare_equal_property(results, definition, source, target, "signal_type")
        _compare_ranges(results, definition, source, target, "signal", None)

    source_limit = 1 if source.exclusive else None
    target_limit = 1 if target.exclusive else None
    source_free = source_limit is None or source_relation_count < source_limit
    target_free = target_limit is None or target_relation_count < target_limit
    add(
        "exclusivity",
        "PASS" if source_free and target_free else "ERROR",
        {"source": source_relation_count, "target": target_relation_count},
        {"source_max": source_limit, "target_max": target_limit},
        "Exclusive resources are available"
        if source_free and target_free
        else "An exclusive resource is already occupied",
    )

    branch_ok = source_relation_count == 0 or source.branching in {
        "ALLOWED",
        "UNRESTRICTED",
        "WITHIN_SELECTED_BUS_ONLY",
    }
    add(
        "branching",
        "PASS" if branch_ok else "ERROR",
        {"existing_outgoing": source_relation_count, "policy": source.branching},
        "allowed by source branching policy",
        "Branching policy permits this relation"
        if branch_ok
        else (
            "Повторное ответвление от источника разрешено только через "
            "оформленный распределительный узел"
            if source.branching == "ONLY_THROUGH_DISTRIBUTION_NODE"
            else "Source branching policy forbids another outgoing relation"
        ),
    )

    if definition.check_capacity:
        capacity = _decimal_or_none(source.properties.get("capacity"))
        demand = _decimal_or_none(target.properties.get("demand"))
        if capacity is None or demand is None:
            add(
                "capacity",
                "INCOMPLETE",
                {"capacity": capacity, "new_demand": demand},
                "known capacity and demand",
                "Capacity check is incomplete because a value is unknown",
                blocking=False,
            )
        else:
            used = sum(existing_target_demands, Decimal("0"))
            ok = used + demand <= capacity
            add(
                "capacity",
                "PASS" if ok else "ERROR",
                {"used": str(used), "new_demand": str(demand)},
                {"capacity": str(capacity)},
                "Capacity is sufficient" if ok else "Resource capacity would be exceeded",
            )

    return RelationPreview(definition, source, target, tuple(results))


def find_cycle(edges: tuple[tuple[str, str], ...]) -> tuple[str, ...] | None:
    adjacency: dict[str, list[str]] = {}
    for source, target in edges:
        adjacency.setdefault(source, []).append(target)
    visited: set[str] = set()
    active: list[str] = []
    active_set: set[str] = set()

    def visit(node: str) -> tuple[str, ...] | None:
        if node in active_set:
            start = active.index(node)
            return tuple(active[start:] + [node])
        if node in visited:
            return None
        visited.add(node)
        active.append(node)
        active_set.add(node)
        for following in adjacency.get(node, []):
            cycle = visit(following)
            if cycle:
                return cycle
        active.pop()
        active_set.remove(node)
        return None

    for node in tuple(adjacency):
        cycle = visit(node)
        if cycle:
            return cycle
    return None


def has_path(edges: tuple[tuple[str, str], ...], source: str, target: str) -> bool:
    adjacency: dict[str, list[str]] = {}
    for start, end in edges:
        adjacency.setdefault(start, []).append(end)
    pending = [source]
    seen: set[str] = set()
    while pending:
        node = pending.pop()
        if node == target:
            return True
        if node in seen:
            continue
        seen.add(node)
        pending.extend(adjacency.get(node, []))
    return False


def _resource_family(resource: ResourceFacts) -> str:
    explicit = resource.properties.get("family")
    if explicit:
        return str(explicit).upper()
    kind = resource.kind.upper()
    if "ANALOG" in kind or "MEASUREMENT" in kind:
        return "ANALOG"
    if any(token in kind for token in ("RELAY", "PWM", "CONTROL", "DRY_CONTACT")):
        return "CONTROL"
    if any(token in kind for token in ("POWER", "VOUT", "VIN", "LINE", "NEUTRAL", "BUSBAR")):
        return "POWER"
    if "RS485" in kind or kind.startswith("BUS_"):
        return "BUS"
    if any(token in kind for token in ("ETHERNET", "USB", "INTERFACE", "PORT", "SLOT")):
        return "INTERFACE"
    return "SIGNAL"


def _compare_equal_property(results, definition, source, target, key):
    left = source.properties.get(key)
    right = target.properties.get(key)
    if left is None or right is None:
        results.append(
            RuleResult(
                f"constructor.{key}",
                definition.version,
                "INCOMPLETE",
                False,
                (source.id, target.id),
                [left, right],
                "both values known and equal",
                f"{key} compatibility is incomplete because a value is unknown",
            )
        )
        return
    ok = str(left).upper() == str(right).upper()
    results.append(
        RuleResult(
            f"constructor.{key}",
            definition.version,
            "PASS" if ok else "ERROR",
            True,
            (source.id, target.id),
            [left, right],
            "equal",
            f"{key} values are compatible" if ok else f"{key} values are incompatible",
        )
    )


def _compare_ranges(results, definition, source, target, prefix, default_unit):
    source_range = _range(source.properties, prefix, default_unit)
    target_range = _range(target.properties, prefix, default_unit)
    if source_range is None or target_range is None:
        results.append(
            RuleResult(
                f"constructor.{prefix}_range",
                definition.version,
                "INCOMPLETE",
                False,
                (source.id, target.id),
                [source_range, target_range],
                "known compatible ranges",
                f"{prefix} range compatibility is incomplete because a value is unknown",
            )
        )
        return
    source_min, source_max, source_unit = source_range
    target_min, target_max, target_unit = target_range
    ok = source_unit == target_unit and target_min <= source_min and source_max <= target_max
    results.append(
        RuleResult(
            f"constructor.{prefix}_range",
            definition.version,
            "PASS" if ok else "ERROR",
            True,
            (source.id, target.id),
            {
                "source": [str(source_min), str(source_max), source_unit],
                "target": [str(target_min), str(target_max), target_unit],
            },
            "source range contained in target range with the same unit",
            f"{prefix} ranges are compatible" if ok else f"{prefix} ranges are incompatible",
        )
    )


def _range(properties: dict[str, Any], prefix: str, default_unit: str | None):
    range_value = properties.get(f"{prefix}_range")
    unit = properties.get(f"{prefix}_unit", default_unit)
    if range_value is not None:
        if isinstance(range_value, dict):
            unit = range_value.get("unit", unit)
            values = (range_value.get("min"), range_value.get("max"))
        else:
            values = tuple(range_value)
        if len(values) != 2:
            return None
        low, high = (_decimal_or_none(values[0]), _decimal_or_none(values[1]))
        if low is None or high is None or low > high:
            return None
        return low, high, unit
    point = properties.get(f"{prefix}_value")
    if point is None:
        return None
    value = _decimal_or_none(point)
    return None if value is None else (value, value, unit)


def _decimal_or_none(value) -> Decimal | None:
    if value is None:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None
