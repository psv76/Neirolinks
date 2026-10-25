import json
from dataclasses import replace

import pytest

from nl_project_2.cad_contract import (
    CadContractValidator,
    CadObservationBatch,
    default_contract_path,
    issue_codes,
)
from nl_project_2.cad_contract.dali_layer_rules import is_valid_dali_group_layer


@pytest.mark.parametrize(
    "layer",
    [
        "300_Освещение",
        "300_Light 230V floor",
        "300_Свет__этаж",
        "400_LED карнизы",
        "400_DALI",
        "300_DALI",
        "400_Общий свет",
        "300__",
        "400__",
        "300_!?",
        "400_MixedCase",
    ],
)
def test_lighting_layers_have_no_suffix_whitelist(layer: str) -> None:
    assert is_valid_dali_group_layer(layer) is True


@pytest.mark.parametrize(
    "layer",
    [
        "DALI_GROUPS",
        "300",
        "300_",
        "300_ Свет",
        "400_Свет ",
        "350_Свет",
        "500_Датчики",
        "700_HDMI",
        "100_DALI",
        "200_DALI",
        "600_DALI",
        "800_DALI",
        "900_DALI",
        "000_Свет",
        "1000_Свет",
        " 300_Свет",
        "400_",
        "400_  ",
        "300_\tСвет",
        "400_Свет\n",
        "400_\u00a0Свет",
        "٣00_Свет",
        "",
        None,
        300,
        400.0,
        True,
        b"300_Light",
        [],
        {},
        object(),
    ],
)
def test_other_or_malformed_layers_are_rejected(layer: object) -> None:
    assert is_valid_dali_group_layer(layer) is False


def test_read_only_logical_contract_has_not_been_migrated(block_contract) -> None:
    raw = json.loads(default_contract_path().read_text(encoding="utf-8"))
    logical = raw["logical_blocks"]["DALI_GROUP"]
    assert logical["required"] == ["DALI_GROUP_ID"]
    assert logical["dynamic_if_metadata_available"] is True
    assert logical["ignored_project_data"] is False
    assert logical["layer"] == "DALI_GROUPS"
    rule = block_contract.block("DALI_GROUP")
    assert rule.block_class == "LOGICAL"
    assert rule.required_attributes == frozenset({"DALI_GROUP_ID"})
    assert rule.dynamic_if_metadata_available is True
    assert rule.ignored_project_data is False
    assert rule.logical_layer == "DALI_GROUPS"
    assert is_valid_dali_group_layer(rule.logical_layer) is False


@pytest.mark.parametrize(
    ("identifier", "valid"),
    [
        ("D.001", True),
        ("D.000", True),
        ("D.999", True),
        ("D.12", False),
        ("D.1000", False),
        ("D.ABC", False),
        ("D.１２３", False),
    ],
)
def test_current_validator_preserves_identifier_syntax(
    block_contract, make_observation, identifier: str, valid: bool
) -> None:
    observation = make_observation(
        "DALI_GROUP", layer="300_DALI", attributes={"DALI_GROUP_ID": identifier}
    )
    result = CadContractValidator(block_contract).validate(
        CadObservationBatch("doc", (observation,))
    )
    assert ("DALI_GROUP_ID_FORMAT" in issue_codes(result.issues)) is not valid
    assert result.is_acceptable is valid


@pytest.mark.parametrize("same_id", [True, False])
def test_current_validator_preserves_identifier_uniqueness(
    block_contract, make_observation, same_id
):
    observations = (
        make_observation(
            "DALI_GROUP", layer="300_DALI", handle="D1", attributes={"DALI_GROUP_ID": "D.001"}
        ),
        make_observation(
            "DALI_GROUP",
            layer="400_DALI",
            handle="D2",
            attributes={"DALI_GROUP_ID": "D.001" if same_id else "D.002"},
        ),
    )
    result = CadContractValidator(block_contract).validate(CadObservationBatch("doc", observations))
    assert ("DUPLICATE_DALI_GROUP_ID" in issue_codes(result.issues)) is same_id
    assert result.is_acceptable is not same_id


@pytest.mark.parametrize("dynamic", [True, False, None])
def test_current_validator_preserves_dynamic_metadata_rule(
    block_contract, make_observation, dynamic
):
    observation = make_observation("DALI_GROUP", layer="300_DALI")
    observation = replace(
        observation, definition=replace(observation.definition, is_dynamic=dynamic)
    )
    result = CadContractValidator(block_contract).validate(
        CadObservationBatch("doc", (observation,))
    )
    assert ("DALI_GROUP_NOT_DYNAMIC" in issue_codes(result.issues)) is (dynamic is False)
    assert result.is_acceptable is (dynamic is not False)


@pytest.mark.parametrize("layer", ["300_Общий свет", "400_Общий свет"])
def test_numeric_eligibility_is_applied_by_runtime(block_contract, make_observation, layer):
    assert is_valid_dali_group_layer(layer) is True
    observation = make_observation("DALI_GROUP", layer=layer)
    result = CadContractValidator(block_contract).validate(
        CadObservationBatch("doc", (observation,))
    )
    assert "LOGICAL_LAYER_MISMATCH" not in issue_codes(result.issues)
    assert result.is_acceptable


def test_current_logical_group_has_no_physical_cable_payload(block_contract, make_observation):
    result = CadContractValidator(block_contract).validate(
        CadObservationBatch("doc", (make_observation("DALI_GROUP", layer="300_DALI"),))
    )
    assert result.is_acceptable
    (group,) = result.observations
    assert group.block_class == "LOGICAL"
    assert group.device_type is None
    assert group.function_group is None
    assert group.read_payload is None
