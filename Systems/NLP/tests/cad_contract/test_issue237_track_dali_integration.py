"""#237 stacked D2/D1: approved feeder voltage and physical DALI graph coexist.

No database mutation, synthetic DWG observations and Project-owned root facts.
"""

from __future__ import annotations

import pytest

from nl_project_2.cad_contract import CadContractValidator, CadObservationBatch, issue_codes


def _full_graph(make_observation, feeder: str, bus: str = "905"):
    box = make_observation(
        "EL_BOX_OUT_100x100",
        handle="BOX-A",
        layer="BUS",
        attributes={
            "BOX_ID": "BOX.003",
            "BUS_ID": bus,
            "BUS_SOURCE": f"{bus}.000",
            "CABLE_ID": "",
            "CABLE_SOURCE": "",
            "CABLE_TYPE": "",
            "BOARD": "",
        },
    )
    track = make_observation(
        "TRACK_DALI",
        handle="TRACK-A",
        layer="TRACK_DALI",
        cable_id=feeder,
        attributes={
            # The fixture defaults blank cable_id to 301; force the explicit
            # empty string too, so this really tests a missing feeder.
            "CABLE_ID": feeder,
            "TRACK_ID": "TRACK.003",
            "BUS_ID": bus,
            "BUS_SOURCE": "BOX.003",
            "LENGTH": "1500",
        },
    )
    return CadObservationBatch("synthetic-dali-voltage.dwg", (box, track))


@pytest.mark.parametrize(
    ("feeder", "group"),
    [
        ("301", "LIGHTING_230V"),
        ("301.01", "LIGHTING_230V"),
        ("401", "LIGHTING_LED"),
        ("401.01", "LIGHTING_LED"),
    ],
)
def test_power_group_and_project_dali_root_are_independent(
    block_contract, make_observation, feeder, group
):
    result = CadContractValidator(
        block_contract,
        project_bus_kinds={"905": "DALI"},
        project_bus_roots={"905.000"},
    ).validate(_full_graph(make_observation, feeder))
    track = result.observations[1]
    assert track.function_group == group
    assert track.read_payload is not None
    assert track.read_payload.bus_id == "905"
    assert track.read_payload.bus_type == "DALI"
    assert track.read_payload.bus_point_id is None
    assert track.read_payload.bus_source == "BOX.003"
    assert not (
        issue_codes(result.issues)
        & {
            "TRACK_DALI_POWER_GROUP_UNRESOLVED",
            "LAYER_FUNCTION_GROUP_MISMATCH",
            "BUS_SOURCE_UNREACHABLE",
            "BUS_SOURCE_NOT_FOUND",
            "BUS_SOURCE_CROSS_BUS",
            "BUS_ROOT_NOT_FOUND",
            "BUS_ROOT_UNVERIFIED",
        }
    ), result.issues


@pytest.mark.parametrize("feeder", ["", "501", "foo", "301-1"])
def test_invalid_feeder_does_not_infer_voltage_from_dali_id(
    block_contract, make_observation, feeder
):
    result = CadContractValidator(
        block_contract,
        project_bus_kinds={"905": "DALI"},
        project_bus_roots={"905.000"},
    ).validate(_full_graph(make_observation, feeder))
    assert result.observations[1].function_group is None
    assert "TRACK_DALI_POWER_GROUP_UNRESOLVED" in issue_codes(result.issues)
    assert "BUS_SOURCE_UNREACHABLE" not in issue_codes(result.issues)
    assert not result.is_acceptable


def test_other_tracks_keep_unique_layer_policy(block_contract, make_observation):
    observations = (
        make_observation("TRACK_230V", handle="T230", layer="TRACK_230V", cable_id="301"),
        make_observation("TRACK_48V", handle="T48", layer="TRACK_48V", cable_id="401"),
    )
    result = CadContractValidator(block_contract).validate(
        CadObservationBatch("synthetic-tracks.dwg", observations)
    )
    assert [item.function_group for item in result.observations] == [
        "LIGHTING_230V",
        "LIGHTING_LED",
    ]
    assert "TRACK_DALI_POWER_GROUP_UNRESOLVED" not in issue_codes(result.issues)


def test_wrong_project_bus_type_blocks_even_valid_power_feeder(block_contract, make_observation):
    result = CadContractValidator(
        block_contract,
        project_bus_kinds={"905": "KNX"},
        project_bus_roots=set(),
    ).validate(_full_graph(make_observation, "301"))
    assert result.observations[1].function_group == "LIGHTING_230V"
    assert "BUS_TYPE_CONFLICT" in issue_codes(result.issues)
    assert "BUS_ROOT_NOT_FOUND" in issue_codes(result.issues)
    assert not result.is_acceptable
