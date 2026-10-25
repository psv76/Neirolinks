import copy
import json

import pytest
from jsonschema import Draft202012Validator

from nl_project_2.cad_contract import (
    CadContractValidator,
    CadObservationBatch,
    default_contract_path,
    issue_codes,
)

GROUPS = {
    100: "POWER",
    200: "SWITCHES",
    300: "LIGHTING_230V",
    400: "LIGHTING_LED",
    500: "SENSORS",
    600: "HVAC",
    700: "AV",
    800: "NETWORK",
    900: "BUS",
}


@pytest.mark.parametrize(("prefix", "group"), GROUPS.items())
@pytest.mark.parametrize("suffix", ["Произвольное имя", "Mixed__Suffix", "_"])
def test_numeric_group_mapping(block_contract, prefix, group, suffix):
    assert block_contract.groups_for_layer(f"{prefix}_{suffix}") == frozenset({group})


@pytest.mark.parametrize(
    "layer",
    [
        "300",
        "300_",
        "300_ Свет",
        "300_Свет ",
        "350_X",
        "ARCH_WALLS",
        "DALI_GROUPS",
        None,
        700,
        [],
        {},
    ],
)
def test_foreign_or_invalid_layers_do_not_match(block_contract, layer):
    assert block_contract.groups_for_layer(layer) == frozenset()


def test_explicit_legacy_compatibility_and_track_voltage_overlap(block_contract):
    assert block_contract.groups_for_layer("POWER") == {"POWER"}
    assert block_contract.groups_for_layer("POWER", include_legacy=False) == frozenset()
    assert block_contract.groups_for_layer("HEATING") == {"HVAC"}
    assert block_contract.groups_for_layer("VENTILATION") == {"HVAC"}
    assert block_contract.groups_for_layer("TRACK_DALI") == {"LIGHTING_230V", "LIGHTING_LED"}
    assert block_contract.block("TRACK_DALI").allowed_groups == {"LIGHTING_230V", "LIGHTING_LED"}
    assert block_contract.block("LIGHT_TRACK_DALI_48V").allowed_groups == {"LIGHTING_LED"}
    assert block_contract.block("CABLE_OUTLET_BUS").allowed_groups == {"BUS"}


def test_nine_groups_hvac_union_and_special_profiles(block_contract):
    assert set(block_contract.functional_groups) == set(GROUPS.values())
    ventilation = {"AIR_VALVE", "MOTOR", "CABLE_OUTLET", "EL_BOX"}
    heating = {"HEATING_DEVICE", "CABLE_OUTLET", "EL_BOX"}
    hvac = block_contract.functional_groups["HVAC"]
    assert hvac.device_types == ventilation | heating
    assert hvac.cable_prefix == "6"
    for name in ("FAN", "AIR_VALVE"):
        assert "HVAC" in block_contract.block(name).allowed_groups
        assert block_contract.block(name).attribute_profile == "EQUIPMENT"
    assert block_contract.block("FAN").allowed_groups == {"POWER", "HVAC"}
    assert block_contract.block("AIR_VALVE").allowed_groups == {"HVAC"}
    assert block_contract.functional_groups["AV"].cable_prefix is None
    assert block_contract.functional_groups["AV"].device_types == {"CABLE_OUTLET"}
    assert "AV" in block_contract.block("CABLE_OUTLET").allowed_groups
    assert block_contract.av_rules["identity"] == ["BOARD", "CABLE_ID"]


@pytest.mark.parametrize("layer", ["700_Аудио", "700_AV boards", "700_A__B"])
def test_staged_av_board_exception(block_contract, layer):
    assert block_contract.groups_for_board_layer("BOARD_IN", "BOARD_AV", layer) == {"AV"}
    assert block_contract.groups_for_board_layer("BOARD_IN", "BOARD_DISTRIBUTION", layer) == set()
    assert block_contract.block("BOARD_IN").allowed_groups == {"POWER"}


@pytest.mark.parametrize(
    "name", ["BOARD_OUT", "BOARD_OUT_IP44", "BOARD_OUT_IP54", "BOARD_OUT_IP67", "BOARD_PANEL"]
)
def test_other_board_families_never_gain_av_role_or_group(block_contract, name):
    assert "BOARD_AV" not in block_contract.block(name).allowed_load_types
    assert block_contract.block(name).allowed_groups == {"POWER"}
    assert block_contract.groups_for_board_layer(name, "BOARD_AV", "700_Audio") == set()


@pytest.mark.parametrize("layer", ["100_Power", "600_HVAC", "AV", "700_", "700_ Audio"])
def test_av_board_other_groups_or_legacy_not_allowed(block_contract, layer):
    assert block_contract.groups_for_board_layer("BOARD_IN", "BOARD_AV", layer) == set()


def test_ordinary_board_and_restored_role_metadata(block_contract):
    assert block_contract.groups_for_board_layer("BOARD_IN", "BOARD_DISTRIBUTION", "100_Main") == {
        "POWER"
    }
    assert block_contract.board_rules["av_role"] == "BOARD_AV"
    assert block_contract.board_rules["av_block_name"] == "BOARD_IN"
    assert block_contract.board_rules["av_function_group"] == "AV"
    assert "BOARD_AV" in block_contract.load_types["BOARD"]


def test_schema_accepts_nine_groups_rejects_fewer():
    path = default_contract_path()
    data = json.loads(path.read_text(encoding="utf-8"))
    schema = json.loads(path.with_name("block_contract.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    validator.validate(data)
    assert len(data["functional_groups"]) == 9
    invalid = copy.deepcopy(data)
    del invalid["functional_groups"]["HVAC"]
    assert any(e.validator == "minProperties" for e in validator.iter_errors(invalid))


@pytest.mark.parametrize("layer", ["700_Аудио", "100_Power"])
def test_runtime_applies_conditional_av_board_placement(block_contract, make_observation, layer):
    observation = make_observation(
        "BOARD_IN", layer=layer, attributes={"LOAD_TYPE": "BOARD_AV", "BOARD_ID": "AV.01"}
    )
    result = CadContractValidator(block_contract).validate(
        CadObservationBatch("fixture", (observation,))
    )
    codes = issue_codes(result.issues)
    assert ("LAYER_FUNCTION_GROUP_MISMATCH" in codes) is not layer.startswith("700_")
    assert "LOAD_TYPE_NOT_ALLOWED" not in codes
    assert "AV_BLOCK_NAME" not in codes
    assert result.is_acceptable is layer.startswith("700_")
