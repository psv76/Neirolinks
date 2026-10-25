from dataclasses import replace

import pytest

from nl_project_2.cad_contract import CadContractValidator, CadObservationBatch, issue_codes


def validate(catalog, *observations):
    return CadContractValidator(catalog).validate(CadObservationBatch("synthetic", observations))


def av_board(make_observation, **kwargs):
    attributes = {
        "LOAD_TYPE": "BOARD_AV",
        "BOARD_ID": "AV.01",
        "CABLE_ID": "",
        "CABLE_TYPE": "",
        "BOARD": "",
    }
    attributes.update(kwargs.pop("attributes", {}))
    return make_observation("BOARD_IN", attributes=attributes, **kwargs)


@pytest.mark.parametrize("layer", ["700_Аудио", "700_Any arbitrary__suffix"])
@pytest.mark.parametrize("cable_id", ["", " free cable text ", "701"])
def test_av_destination_is_board_not_line(block_contract, make_observation, layer, cable_id):
    board = av_board(make_observation, layer=layer, attributes={"CABLE_ID": cable_id})
    result = validate(block_contract, board)
    assert result.is_acceptable, result.issues
    assert not result.issues
    item = result.observations[0]
    assert item.device_type == "BOARD"
    assert item.function_group == "AV"
    assert item.normalized_attributes["CABLE_ID"] == cable_id
    assert item.normalized_attributes["BOARD_ID"] == "AV.01"
    assert item.read_payload.device_type == "BOARD"
    assert item.read_payload.handle == board.handle
    assert item.read_payload.cable_identity is None
    assert item.read_payload.cable_link_kind is None
    assert item.read_payload.cable_source is None


@pytest.mark.parametrize("layer", ["100_Power", "600_HVAC", "BOARD", "AV", "700_", "700_ Audio"])
def test_av_board_wrong_layer_blocks(block_contract, make_observation, layer):
    result = validate(block_contract, av_board(make_observation, layer=layer))
    assert not result.is_acceptable
    assert "LAYER_FUNCTION_GROUP_MISMATCH" in issue_codes(result.issues)
    assert "AV_BLOCK_NAME" not in issue_codes(result.issues)
    assert result.observations[0].read_payload.cable_identity is None


@pytest.mark.parametrize(
    "layer,acceptable", [("100_Power", True), ("BOARD", True), ("700_AV", False)]
)
def test_ordinary_board_keeps_power_placement(block_contract, make_observation, layer, acceptable):
    board = make_observation(
        "BOARD_IN", layer=layer, attributes={"LOAD_TYPE": "BOARD_DISTRIBUTION"}
    )
    result = validate(block_contract, board)
    assert result.is_acceptable is acceptable, result.issues
    assert ("LAYER_FUNCTION_GROUP_MISMATCH" in issue_codes(result.issues)) is not acceptable
    assert result.observations[0].read_payload.cable_identity is not None


@pytest.mark.parametrize(
    "name", ["BOARD_OUT", "BOARD_OUT_IP44", "BOARD_OUT_IP54", "BOARD_OUT_IP67", "BOARD_PANEL"]
)
def test_av_exception_never_extends_to_other_boards(block_contract, make_observation, name):
    board = make_observation(name, layer="700_AV", attributes={"LOAD_TYPE": "BOARD_AV"})
    result = validate(block_contract, board)
    assert not result.is_acceptable
    assert "LAYER_FUNCTION_GROUP_MISMATCH" in issue_codes(result.issues)
    assert "LOAD_TYPE_NOT_ALLOWED" in issue_codes(result.issues)


@pytest.mark.parametrize("tag", ["BOARD_ID", "CABLE_ID", "CABLE_TYPE", "BOARD"])
def test_av_board_preserves_attdefs(block_contract, make_observation, tag):
    board = av_board(make_observation, layer="700_AV")
    board = replace(
        board,
        definition=replace(
            board.definition,
            attribute_definition_tags=tuple(
                t for t in board.definition.attribute_definition_tags if t != tag
            ),
        ),
    )
    result = validate(block_contract, board)
    assert not result.is_acceptable
    assert any(i.field == tag and i.blocks_acceptance for i in result.issues)


@pytest.mark.parametrize("same_board", [True, False])
def test_av_outlet_identity_and_destination(block_contract, make_observation, same_board):
    boards = (
        av_board(make_observation, layer="700_Boards", handle="B1"),
        av_board(
            make_observation, layer="700_Boards", handle="B2", attributes={"BOARD_ID": "AV.02"}
        ),
    )
    outlets = tuple(
        make_observation(
            "CABLE_OUTLET",
            layer="700_Outputs",
            handle=f"O{i}",
            cable_id=identifier,
            attributes={"BOARD": destination, "LOAD_TYPE": "HDMI", "CABLE_TYPE": "HDMI"},
        )
        for i, (identifier, destination) in enumerate(
            [(" hdmi rack 1 ", "AV.01"), ("HDMI RACK 1", "AV.01" if same_board else "AV.02")]
        )
    )
    result = validate(block_contract, *boards, *outlets)
    codes = issue_codes(result.issues)
    assert result.is_acceptable is not same_board, result.issues
    assert ("DUPLICATE_AV_IDENTITY" in codes) is same_board
    assert not codes & {
        "AV_BOARD_NOT_FOUND",
        "AV_BOARD_WRONG_ROLE",
        "AV_BLOCK_NAME",
        "CABLE_ID_FORMAT",
    }
    assert result.observations[2].normalized_attributes["CABLE_ID"] == "HDMI RACK 1"


@pytest.mark.parametrize(
    "layer",
    [
        "DALI_GROUPS",
        "350_X",
        "300_",
        "400_",
        "300_ Light",
        "400_Light ",
        " 300_Light",
        "100_X",
        "200_X",
        "500_X",
        "600_X",
        "700_X",
        "800_X",
        "900_X",
    ],
)
def test_dali_group_rejects_other_or_malformed_layers(block_contract, make_observation, layer):
    result = validate(block_contract, make_observation("DALI_GROUP", layer=layer))
    assert not result.is_acceptable
    assert "LOGICAL_LAYER_MISMATCH" in issue_codes(result.issues)
    assert result.observations[0].read_payload is None


@pytest.mark.parametrize("layer", ["300_Любой свет", "400_Any__suffix"])
@pytest.mark.parametrize("identifier", ["D.000", "D.123", "D.999"])
def test_dali_group_numeric_placement(block_contract, make_observation, layer, identifier):
    result = validate(
        block_contract,
        make_observation("DALI_GROUP", layer=layer, attributes={"DALI_GROUP_ID": identifier}),
    )
    assert result.is_acceptable, result.issues
    assert result.observations[0].read_payload is None


@pytest.mark.parametrize("name", ["FAN", "AIR_VALVE", "CABLE_OUTLET"])
@pytest.mark.parametrize(
    "layer,acceptable",
    [
        ("600_Климат", True),
        ("600_Any__suffix", True),
        ("600_", False),
        ("600_ HVAC", False),
        ("600_HVAC ", False),
    ],
)
def test_hvac_combines_heating_and_ventilation(
    block_contract, make_observation, name, layer, acceptable
):
    result = validate(
        block_contract,
        make_observation(
            name,
            layer=layer,
            cable_id="601",
            attributes={"LOAD_TYPE": "CABLE_HEAT"} if name == "CABLE_OUTLET" else {},
        ),
    )
    assert result.is_acceptable is acceptable, result.issues
    assert ("LAYER_FUNCTION_GROUP_MISMATCH" in issue_codes(result.issues)) is not acceptable


@pytest.mark.parametrize(
    "layer,cable_id,acceptable",
    [
        ("100_Power", "101", True),
        ("100_Power", "601", False),
        ("600_HVAC", "601", True),
        ("600_HVAC", "101", False),
    ],
)
def test_fan_keeps_group_specific_prefix(
    block_contract, make_observation, layer, cable_id, acceptable
):
    result = validate(block_contract, make_observation("FAN", layer=layer, cable_id=cable_id))
    assert result.is_acceptable is acceptable, result.issues


def test_air_valve_never_gains_power_group(block_contract, make_observation):
    result = validate(
        block_contract, make_observation("AIR_VALVE", layer="100_Power", cable_id="101")
    )
    assert not result.is_acceptable
    assert "LAYER_FUNCTION_GROUP_MISMATCH" in issue_codes(result.issues)


@pytest.mark.parametrize("layer", ["350_X", "300_", "300_ Light", " 300_Light", "300_Light "])
def test_physical_malformed_layers_block(block_contract, make_observation, layer):
    result = validate(block_contract, make_observation("CABLE_OUTLET", layer=layer, cable_id="301"))
    assert not result.is_acceptable
    assert "LAYER_FUNCTION_GROUP_MISMATCH" in issue_codes(result.issues)
