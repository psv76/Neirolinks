"""Confirm approved Ethernet frame placement without inventing endpoint ownership."""

import pytest

from nl_project_2.cad_contract import CadContractValidator, CadObservationBatch


@pytest.mark.parametrize("name", ["FRAME_1", "FRAME_2"])
def test_frame_ethernet_layer_is_approved_mounting_placement(
    block_contract, make_observation, name
):
    rule = block_contract.block(name)
    assert rule.block_class == "MOUNTING"
    observation = make_observation(name, layer="800_Ethernet")
    result = CadContractValidator(block_contract).validate(
        CadObservationBatch("synthetic", (observation,))
    )
    assert "LAYER_FUNCTION_GROUP_MISMATCH" not in {issue.code for issue in result.issues}
    assert rule.cable_link_kind is None
    assert rule.bus_link_kind is None
