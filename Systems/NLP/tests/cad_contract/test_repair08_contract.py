from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from nl_project_2.cad_contract import CadContractValidator, CadObservationBatch, issue_codes
from nl_project_2.cad_sync.reconciliation import (
    normalize_validated_snapshot,
    reconcile_edge_projections,
    reconcile_snapshot_edge_projections,
)

_FIXTURE_GROUPS = json.loads(
    (Path(__file__).parent / "fixtures" / "repair08_exact_attdef_sha256.json").read_text(
        encoding="utf-8"
    )
)
_EXPECTED_HASHES = {name: digest for digest, names in _FIXTURE_GROUPS.items() for name in names}


def _attdef_hash(tags) -> str:
    return hashlib.sha256("\n".join(sorted(tags)).encode()).hexdigest()


def test_exact_71_names_and_attdef_fixture(block_contract):
    assert len(_EXPECTED_HASHES) == 71
    assert set(block_contract.blocks) == set(_EXPECTED_HASHES)
    assert {
        name: _attdef_hash(rule.required_definition_attributes)
        for name, rule in block_contract.blocks.items()
    } == _EXPECTED_HASHES


@pytest.mark.parametrize("name", sorted(_EXPECTED_HASHES))
def test_each_canonical_block_has_exact_attdef_hash(block_contract, name):
    assert (
        _attdef_hash(block_contract.block(name).required_definition_attributes)
        == _EXPECTED_HASHES[name]
    )


@pytest.mark.parametrize(
    "tag",
    ["DEVICE_TYPE", "POSTS", "CABLE_LINK", "BUS_LINK", "LINE_ROLE", "BUS_ID", "BUS_TYPE"],
)
def test_project_only_tags_are_not_attdefs(block_contract, tag):
    assert all(
        tag not in rule.required_definition_attributes for rule in block_contract.blocks.values()
    )


def test_device_name_and_removed_names(block_contract):
    physical = [rule for rule in block_contract.blocks.values() if rule.block_class != "LOGICAL"]
    assert all("DEVICE_NAME" in rule.required_definition_attributes for rule in physical)
    assert not {"LIGHT_IN", "LIGHT_OUT", "SENSOR_M1W2", "SENSOR_MAI2"} & set(block_contract.blocks)


@pytest.mark.parametrize(
    ("name", "present", "absent"),
    [
        ("SOCKET_ETHERNET", {"LOAD_TYPE"}, {"CALC_POWER", "PHASE"}),
        ("SOCKET_IN", {"CALC_POWER"}, {"PHASE"}),
        ("SOCKET_OUT_380V", {"CALC_POWER"}, {"PHASE"}),
        ("SW_IN_1", {"KEY_1"}, {"CABLE_SOURCE", "LOAD_TYPE"}),
        ("BTN_IN_4", {"KEY_1", "KEY_4"}, {"CABLE_SOURCE", "LOAD_TYPE"}),
        ("LIGHT_OUT_230V", {"CABLE_SOURCE"}, {"BUS_POINT_ID", "BUS_SOURCE"}),
        ("LIGHT_OUT_DALI_230V", {"CABLE_SOURCE", "BUS_POINT_ID", "BUS_SOURCE"}, set()),
        ("LIGHT_TRACK_230V", {"CABLE_SOURCE"}, {"CABLE_TYPE", "MOUNT_WAY"}),
        ("LIGHT_TRACK_DALI_48V", {"CABLE_SOURCE", "BUS_SOURCE"}, {"CABLE_TYPE", "BUS_CABLE_TYPE"}),
        ("CABLE_OUTLET", {"PHASE"}, {"BUS_POINT_ID"}),
        ("CABLE_OUTLET_DALI", {"PHASE", "BUS_POINT_ID", "BUS_SOURCE"}, set()),
        ("WB_MRM2_MINI", {"COM1", "COM2", "K1", "K2", "IN_1", "IN_2"}, {"LOAD_TYPE"}),
    ],
)
def test_representative_exact_attribute_boundaries(block_contract, name, present, absent):
    tags = block_contract.block(name).required_definition_attributes
    assert present <= tags
    assert not (absent & tags)


def test_load_type_and_derived_semantics(block_contract):
    assert block_contract.block("SOCKET_OUT_380V").allowed_load_types == {
        "SOCKET_KITCHEN_3PH",
        "SOCKET_EQUIPMENT",
    }
    assert block_contract.block("SOCKET_OUT_380V").derived_phase == 3
    assert block_contract.block("SOCKET_IN").derived_phase == 1
    assert block_contract.block("LIGHT_TRACK_DALI_48V").cable_link_kind == "TRACK"
    assert block_contract.block("LIGHT_TRACK_DALI_48V").bus_link_kind == "TRACK"


@pytest.mark.parametrize("source", ["BOX.010", "331.02", "902.003/K1"])
def test_cable_source_accepted(block_contract, make_observation, source):
    source_rows = []
    if source == "BOX.010":
        source_rows.append(
            make_observation(
                "EL_BOX_OUT_100x100",
                handle="B",
                cable_id="331.01",
                attributes={"BOX_ID": "BOX.010"},
            )
        )
    elif source == "331.02":
        source_rows.append(make_observation("LIGHT_IN_230V", handle="U", cable_id="331.02"))
    else:
        source_rows.append(
            make_observation(
                "WB_MRM2_MINI",
                handle="M",
                cable_id="101.01",
                attributes={"BUS_POINT_ID": "902.003"},
            )
        )
    target = make_observation(
        "LIGHT_IN_230V", handle="T", cable_id="331.03", attributes={"CABLE_SOURCE": source}
    )
    result = CadContractValidator(block_contract).validate(
        CadObservationBatch("doc", (*source_rows, target))
    )
    assert "CABLE_SOURCE_FORMAT" not in issue_codes(result.issues)
    assert "CABLE_SOURCE_NOT_FOUND" not in issue_codes(result.issues)


def test_missing_exact_port_is_actionable(block_contract, make_observation):
    target = make_observation(
        "LIGHT_IN_230V", cable_id="331.03", attributes={"CABLE_SOURCE": "902.003/K1"}
    )
    result = CadContractValidator(block_contract).validate(CadObservationBatch("doc", (target,)))
    assert "CABLE_SOURCE_NOT_FOUND" in issue_codes(result.issues)


@pytest.mark.parametrize(
    ("baseline", "downstream", "port", "status", "canonical"),
    [
        ("331.02", "331.02", "331.02", "AGREE", "331.02"),
        ("331.02", "331.03", "331.02", "DOWNSTREAM_CHANGED", "331.03"),
        ("331.02", "331.02", "331.03", "PORT_CHANGED", "331.03"),
        ("331.02", "331.03", "331.03", "AGREE", "331.03"),
        ("331.02", "331.03", "331.04", "REQUIRES_ATTENTION", None),
        (None, None, None, "AGREE", None),
    ],
)
def test_dual_projection_three_way(baseline, downstream, port, status, canonical):
    result = reconcile_edge_projections(baseline, downstream, port)
    assert result.status == status
    assert result.canonical_target == canonical


def test_bus_root_cross_bus_and_cycle(block_contract, make_observation):
    root = make_observation(
        "LIGHT_OUT_DALI_230V",
        handle="D1",
        cable_id="301.01",
        attributes={"BUS_POINT_ID": "905.001", "BUS_SOURCE": "905.000"},
    )
    branch = make_observation(
        "LIGHT_IN_DALI_230V",
        handle="D2",
        cable_id="301.02",
        attributes={"BUS_POINT_ID": "905.002", "BUS_SOURCE": "905.001"},
    )
    good = CadContractValidator(block_contract).validate(CadObservationBatch("doc", (root, branch)))
    assert not (
        {"BUS_ROOT_RESERVED", "BUS_SOURCE_CROSS_BUS", "BUS_SOURCE_CYCLE"} & issue_codes(good.issues)
    )
    reserved = make_observation("SENSOR_MSW", handle="R", attributes={"BUS_POINT_ID": "905.000"})
    assert "BUS_ROOT_RESERVED" in issue_codes(
        CadContractValidator(block_contract)
        .validate(CadObservationBatch("doc", (reserved,)))
        .issues
    )
    cross = make_observation(
        "LIGHT_OUT_DALI_230V",
        handle="X",
        attributes={"BUS_POINT_ID": "905.003", "BUS_SOURCE": "906.000"},
    )
    assert "BUS_SOURCE_CROSS_BUS" in issue_codes(
        CadContractValidator(block_contract).validate(CadObservationBatch("doc", (cross,))).issues
    )


def test_rs485_has_no_source_and_numeric_identity(block_contract, make_observation):
    point = make_observation("SENSOR_MSW", attributes={"BUS_POINT_ID": "901.010"})
    result = CadContractValidator(block_contract).validate(CadObservationBatch("doc", (point,)))
    assert "RS485_BUS_SOURCE_FORBIDDEN" not in issue_codes(result.issues)
    assert point.raw_attributes


def _projection_snapshot(
    block_contract, make_observation, *, port_value, source_value, second=False
):
    observations = [
        make_observation(
            "WB_MRM2_MINI",
            handle="M",
            cable_id="101.01",
            attributes={"BUS_POINT_ID": "902.003", "K1": port_value, "K2": ""},
        ),
        make_observation(
            "LIGHT_IN_230V",
            handle="T1",
            cable_id="331.02",
            attributes={"CABLE_SOURCE": source_value},
        ),
    ]
    if second:
        observations.append(
            make_observation(
                "LIGHT_IN_230V",
                handle="T2",
                cable_id="331.03",
                attributes={"CABLE_SOURCE": ""},
            )
        )
    validation = CadContractValidator(block_contract).validate(
        CadObservationBatch("doc", tuple(observations))
    )
    return normalize_validated_snapshot(validation.observations)


def test_downstream_only_projection_materializes_port_source(block_contract, make_observation):
    snapshot = _projection_snapshot(
        block_contract,
        make_observation,
        port_value="",
        source_value="902.003/K1",
    )
    resolved = reconcile_snapshot_edge_projections(snapshot, {})
    segment = next(item for item in resolved.segments if item.target_point_key.endswith("331.02"))
    assert segment.source_reference == "902.003/K1"
    assert resolved.structural_reviews == ()


def test_port_only_projection_materializes_downstream_source(block_contract, make_observation):
    snapshot = _projection_snapshot(
        block_contract,
        make_observation,
        port_value="331.02",
        source_value="",
    )
    resolved = reconcile_snapshot_edge_projections(snapshot, {})
    segment = next(item for item in resolved.segments if item.target_point_key.endswith("331.02"))
    assert segment.source_reference == "902.003/K1"
    assert resolved.structural_reviews == ()


def test_previous_baseline_resolves_one_side_stale_projection(block_contract, make_observation):
    snapshot = _projection_snapshot(
        block_contract,
        make_observation,
        port_value="331.02",
        source_value="902.003/K2",
    )
    resolved = reconcile_snapshot_edge_projections(
        snapshot,
        {
            "edge:331.02:CABLE_SOURCE": "902.003/K1",
            "port:M:K1": "331.02",
            "port:M:K2": "",
        },
    )
    segment = next(item for item in resolved.segments if item.target_point_key.endswith("331.02"))
    assert segment.source_reference == "902.003/K2"
    assert resolved.structural_reviews == ()


def test_incompatible_dual_projection_requires_attention(block_contract, make_observation):
    snapshot = _projection_snapshot(
        block_contract,
        make_observation,
        port_value="331.02",
        source_value="902.003/K2",
    )
    resolved = reconcile_snapshot_edge_projections(snapshot, {})
    assert resolved.structural_reviews == ("331:DUAL_PROJECTION_CONFLICT:331.02",)


def test_bus_cable_type_is_line_owned_and_routes_stay_independent(block_contract, make_observation):
    first = make_observation(
        "LIGHT_OUT_DALI_230V",
        handle="D1",
        cable_id="301.01",
        attributes={
            "BUS_POINT_ID": "905.001",
            "BUS_SOURCE": "905.000",
            "BUS_CABLE_TYPE": "BUS-A",
            "BUS_MOUNT_WAY": "По потолку",
            "MOUNT_WAY": "В стене",
        },
    )
    second = make_observation(
        "LIGHT_IN_DALI_230V",
        handle="D2",
        cable_id="301.02",
        attributes={
            "BUS_POINT_ID": "905.002",
            "BUS_SOURCE": "905.001",
            "BUS_CABLE_TYPE": "BUS-B",
        },
    )
    result = CadContractValidator(block_contract).validate(
        CadObservationBatch("doc", (first, second))
    )
    assert "BUS_CABLE_TYPE_INCONSISTENT" in issue_codes(result.issues)
    payload = result.observations[0].read_payload
    assert payload is not None
    assert {fact.tag: fact.value for fact in payload.route_fields}["MOUNT_WAY"] == "В стене"
    assert {fact.tag: fact.value for fact in payload.bus_route_fields}[
        "BUS_MOUNT_WAY"
    ] == "По потолку"
