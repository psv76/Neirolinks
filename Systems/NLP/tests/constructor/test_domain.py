from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from nl_project_2.constructor import (
    RelationDefinition,
    ResourceFacts,
    find_cycle,
    has_path,
    validate_relation,
)


def _resource(identifier, direction, **properties):
    return ResourceFacts(
        id=identifier,
        instance_id=f"instance-{identifier}",
        key=identifier,
        kind=properties.pop("kind", "GENERIC_POWER"),
        direction=direction,
        medium="synthetic",
        properties=properties,
        exclusive=properties.pop("exclusive", False),
        branching=properties.pop("branching", "ALLOWED"),
    )


def test_ac_dc_direction_voltage_capacity_exclusivity_and_branching():
    definition = RelationDefinition("SYNTHETIC_POWER", "POWER")
    source = _resource(
        "source",
        "OUT",
        family="POWER",
        current_kind="DC",
        voltage_value=24,
        capacity=40,
        branching="ALLOWED",
    )
    target = _resource(
        "target",
        "IN",
        family="POWER",
        current_kind="DC",
        voltage_range=[20, 28],
        demand=10,
    )
    preview = validate_relation(
        definition,
        source,
        target,
        existing_target_demands=(Decimal("20"),),
    )
    assert preview.allowed
    assert {result.rule_id: result.outcome for result in preview.results}[
        "constructor.voltage_range"
    ] == "PASS"

    wrong_current = _resource(
        "ac-target",
        "IN",
        family="POWER",
        current_kind="AC",
        voltage_value=24,
        demand=1,
    )
    assert not validate_relation(definition, source, wrong_current).allowed
    assert not validate_relation(definition, target, wrong_current).allowed

    overloaded = _resource(
        "large-load",
        "IN",
        family="POWER",
        current_kind="DC",
        voltage_value=24,
        demand=25,
    )
    assert not validate_relation(
        definition,
        source,
        overloaded,
        existing_target_demands=(Decimal("20"),),
    ).allowed

    exclusive = replace(target, id="exclusive", exclusive=True)
    assert not validate_relation(definition, source, exclusive, target_relation_count=1).allowed

    no_branch = replace(source, branching="FORBIDDEN")
    assert not validate_relation(definition, no_branch, target, source_relation_count=1).allowed

    distribution_only = replace(source, branching="ONLY_THROUGH_DISTRIBUTION_NODE")
    preview = validate_relation(definition, distribution_only, target, source_relation_count=1)
    assert not preview.allowed
    assert any(
        result.rule_id == "constructor.branching" and "распределительный узел" in result.message
        for result in preview.results
    )


def test_analog_range_and_signal_type_are_definition_driven():
    definition = RelationDefinition(
        "ANALOG_RANGE",
        "ANALOG",
        check_current_kind=False,
        check_voltage=False,
        check_capacity=False,
    )
    source = _resource(
        "analog-out",
        "OUT",
        kind="ANALOG_OUTPUT",
        family="ANALOG",
        signal_type="VOLTAGE",
        signal_range={"min": 0, "max": 10, "unit": "V"},
    )
    target = _resource(
        "analog-in",
        "IN",
        kind="ANALOG_INPUT",
        family="ANALOG",
        signal_type="VOLTAGE",
        signal_range={"min": 0, "max": 10, "unit": "V"},
    )
    assert validate_relation(definition, source, target).allowed

    current_input = _resource(
        "current-in",
        "IN",
        kind="ANALOG_INPUT",
        family="ANALOG",
        signal_type="CURRENT",
        signal_range={"min": 4, "max": 20, "unit": "mA"},
    )
    mismatch = validate_relation(definition, source, current_input)
    assert not mismatch.allowed
    assert {result.rule_id for result in mismatch.results if result.outcome == "ERROR"} == {
        "constructor.signal_type",
        "constructor.signal_range",
    }


def test_graph_path_and_cycle_are_generic():
    edges = (("source", "protection"), ("protection", "load"))
    assert has_path(edges, "source", "load")
    assert not has_path(edges, "load", "source")
    assert find_cycle(edges) is None
    cycle = find_cycle(edges + (("load", "source"),))
    assert cycle == ("source", "protection", "load", "source")


def test_relation_definition_can_allow_cross_family_without_core_branch():
    definition = RelationDefinition(
        "FEED_CONTROL_COMMON",
        "POWER",
        source_families=frozenset({"POWER"}),
        target_families=frozenset({"CONTROL"}),
        check_signal=False,
        check_capacity=False,
    )
    source = _resource(
        "power-output",
        "OUT",
        family="POWER",
        current_kind="AC",
        voltage_value=230,
    )
    target = _resource(
        "control-common",
        "IN",
        kind="RELAY_COMMON_INPUT",
        family="CONTROL",
        current_kind="AC",
        voltage_range=[220, 240],
    )
    assert validate_relation(definition, source, target).allowed
