from __future__ import annotations

from dataclasses import replace

import pytest

from nl_project_2.cad_contract import CadContractValidator, CadObservationBatch, load_contract

APPROVED_NAMES = tuple(sorted(load_contract().blocks))


@pytest.mark.parametrize("name", APPROVED_NAMES)
def test_every_approved_name_has_a_valid_metadata_observation(
    block_contract, make_observation, name
):
    observation = make_observation(name, handle="A1")
    observations = (observation,)
    if block_contract.block(name).key_count:
        observations += (make_observation("DALI_GROUP", handle="D1"),)
    result = CadContractValidator(block_contract).validate(
        CadObservationBatch("doc-all-names", observations)
    )
    assert result.is_acceptable, (name, result.issues)


@pytest.mark.parametrize(
    "name",
    [
        "FRAME_1",
        "LIGHT_IN",
        "LIGHT_LED",
        "TRACK_230V",
        "TRACK_48V",
        "TRACK_DALI",
        "SOCKET_IN",
        "CABLE_OUTLET",
        "SENSOR_WATER",
        "FAN",
        "AIR_VALVE",
        "CONTROL_PANEL_4",
        "BOARD_OUT",
    ],
)
def test_representative_of_each_non_key_physical_family_is_valid(
    block_contract, make_observation, name
):
    result = CadContractValidator(block_contract).validate(
        CadObservationBatch("doc-1", (make_observation(name),))
    )
    assert result.is_acceptable, result.issues


def test_complete_batch_covers_multidevice_line_keys_dali_frame_room_and_av(
    block_contract, make_observation
):
    observations = (
        make_observation(
            "BOARD_IN",
            handle="B1",
            attributes={"LOAD_TYPE": "BOARD_SCS", "BOARD_ID": "AV.01"},
        ),
        make_observation(
            "CABLE_OUTLET",
            handle="AV1",
            layer="AV",
            cable_id="  hdmi-a  ",
            attributes={
                "CABLE_TYPE": "HDMI 2.1",
                "BOARD": "AV.01",
                "LOAD_TYPE": "HDMI",
            },
        ),
        make_observation("LIGHT_IN", handle="L1", cable_id="301"),
        make_observation("LIGHT_IN", handle="L2", cable_id="301.01"),
        make_observation("DALI_GROUP", handle="D1"),
        make_observation("SW_IN_1", handle="S1", cable_id="201"),
        make_observation(
            "BTN_IN_2",
            handle="K1",
            cable_id="202",
            attributes={"KEY_1": "301", "KEY_2": "D.001"},
        ),
        make_observation("FRAME_2", handle="F1"),
        make_observation(
            "ROOM_NAME",
            handle="",
            attributes={"CONTACT_1": "legacy", "ARTICLE": "ignored"},
            x="not-a-number",
            y="not-a-number",
        ),
    )
    result = CadContractValidator(block_contract).validate(
        CadObservationBatch("doc-1", observations)
    )
    assert result.is_acceptable, result.issues
    assert result.ignored_count == 1
    av = next(item for item in result.observations if item.observation.handle == "AV1")
    assert av.normalized_attributes["CABLE_ID"] == "HDMI-A"
    assert av.function_group == "AV"


def test_dali_dynamic_flag_is_optional_when_definition_metadata_does_not_expose_it(
    block_contract, make_observation
):
    observation = make_observation("DALI_GROUP")
    observation = replace(
        observation,
        definition=replace(observation.definition, is_dynamic=None),
    )
    result = CadContractValidator(block_contract).validate(
        CadObservationBatch("doc", (observation,))
    )
    assert result.is_acceptable
