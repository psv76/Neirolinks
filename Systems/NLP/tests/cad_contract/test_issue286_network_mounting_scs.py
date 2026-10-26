"""Issue #286: Ethernet mounting frames and exact SCS board role on layer 800."""

import pytest

from nl_project_2.cad_contract import (
    CadContractValidator,
    CadObservationBatch,
    issue_codes,
)


def _validate(contract, observation):
    return CadContractValidator(contract).validate(
        CadObservationBatch("issue286-800", (observation,))
    )


@pytest.mark.parametrize("block_name", ["FRAME_1", "FRAME_2"])
@pytest.mark.parametrize("layer", ["800_Ethernet", "800_Internet sockets"])
def test_ethernet_frames_are_allowed_without_changing_other_layers(
    block_contract, make_observation, block_name, layer
):
    frame = make_observation(block_name, layer=layer)
    result = _validate(block_contract, frame)
    assert result.is_acceptable, result.issues
    assert result.observations[0].function_group == "NETWORK"


@pytest.mark.parametrize(
    "block_name,load_type,accepted",
    [
        ("BOARD_OUT", "BOARD_SCS", True),
        ("BOARD_OUT", "BOARD_DISTRIBUTION", False),
        ("BOARD_OUT", "BOARD_IN", False),
        ("BOARD_OUT", "BOARD_AV", False),
        ("BOARD_IN", "BOARD_SCS", False),
        ("BOARD_PANEL", "BOARD_SCS", False),
    ],
)
def test_only_board_out_scs_can_use_ethernet_layer(
    block_contract, make_observation, block_name, load_type, accepted
):
    cabinet = make_observation(
        block_name,
        layer="800_Ethernet",
        attributes={
            "BOARD_ID": "SCS-20",
            "LOAD_TYPE": load_type,
            "CABLE_ID": "",
            "CABLE_TYPE": "",
            "BOARD": "",
        },
    )
    result = _validate(block_contract, cabinet)
    assert ("LAYER_FUNCTION_GROUP_MISMATCH" not in issue_codes(result.issues)) is accepted
    if accepted:
        assert result.is_acceptable, result.issues
        assert result.observations[0].function_group == "NETWORK"


@pytest.mark.parametrize(
    "block_name,load_type,layer,valid",
    [
        ("BOARD_OUT", "BOARD_SCS", "100_Power", True),
        ("BOARD_OUT", "BOARD_DISTRIBUTION", "100_Power", True),
        ("BOARD_IN", "BOARD_SCS", "100_Power", True),
        ("BOARD_OUT", "BOARD_SCS", "700_AV", False),
    ],
)
def test_existing_power_board_and_av_boundary_unchanged(
    block_contract, make_observation, block_name, load_type, layer, valid
):
    board = make_observation(
        block_name,
        layer=layer,
        attributes={"BOARD_ID": "SCH-20", "LOAD_TYPE": load_type},
    )
    result = _validate(block_contract, board)
    assert result.is_acceptable is valid, result.issues
