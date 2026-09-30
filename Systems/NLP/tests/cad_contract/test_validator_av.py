from __future__ import annotations

from nl_project_2.cad_contract import CadContractValidator, CadObservationBatch, issue_codes


def test_av_cable_id_is_free_text_trimmed_uppercase_and_not_xYY_validated(
    block_contract, make_observation
):
    av = make_observation(
        "CABLE_OUTLET",
        layer="AV",
        cable_id="  hdmi rack 1  ",
        attributes={"BOARD": "AV.01", "LOAD_TYPE": "HDMI", "CABLE_TYPE": "HDMI"},
    )
    result = CadContractValidator(block_contract).validate(CadObservationBatch("doc", (av,)))
    assert "CABLE_ID_FORMAT" not in issue_codes(result.issues)
    assert result.observations[0].normalized_attributes["CABLE_ID"] == "HDMI RACK 1"
    assert "AV_BOARD_NOT_FOUND" in issue_codes(result.issues)
    assert result.is_acceptable


def test_av_missing_fields_are_diagnostic_but_scannable(block_contract, make_observation):
    base = make_observation("CABLE_OUTLET", layer="AV")
    values = {
        item.tag: item.value
        for item in base.raw_attributes
        if item.tag not in {"BOARD", "CABLE_ID", "LOAD_TYPE", "CABLE_TYPE"}
    }
    incomplete = make_observation("CABLE_OUTLET", layer="AV", attributes=values)
    incomplete = type(incomplete).from_mapping(
        effective_name=incomplete.effective_name,
        layer=incomplete.layer,
        raw_attributes=values,
        x=incomplete.x,
        y=incomplete.y,
        handle=incomplete.handle,
        definition=None,
    )
    result = CadContractValidator(block_contract).validate(
        CadObservationBatch("doc", (incomplete,))
    )
    missing = [issue for issue in result.issues if issue.code == "REQUIRED_ATTRIBUTE_MISSING"]
    assert {issue.field for issue in missing} == {"BOARD", "CABLE_ID", "LOAD_TYPE", "CABLE_TYPE"}
    assert all(not issue.blocks_acceptance for issue in missing)
    assert result.is_acceptable


def test_av_duplicate_identity_is_blocking_after_normalization(block_contract, make_observation):
    first = make_observation(
        "CABLE_OUTLET",
        handle="A1",
        layer="AV",
        cable_id=" hdmi-1 ",
        attributes={"BOARD": "AV.01", "LOAD_TYPE": "HDMI", "CABLE_TYPE": "HDMI"},
    )
    second = make_observation(
        "CABLE_OUTLET",
        handle="A2",
        layer="AV",
        cable_id="HDMI-1",
        attributes={"BOARD": "AV.01", "LOAD_TYPE": "HDMI", "CABLE_TYPE": "HDMI"},
    )
    result = CadContractValidator(block_contract).validate(
        CadObservationBatch("doc", (first, second))
    )
    assert "DUPLICATE_AV_IDENTITY" in issue_codes(result.issues)
    assert not result.is_acceptable


def test_av_board_must_exist_and_have_board_av_role(block_contract, make_observation):
    ordinary_board = make_observation(
        "BOARD_OUT", handle="B1", attributes={"BOARD_ID": "B.01", "LOAD_TYPE": "BOARD_SCS"}
    )
    av = make_observation(
        "CABLE_OUTLET",
        handle="A1",
        layer="AV",
        cable_id="SPK-L",
        attributes={
            "BOARD": "B.01",
            "LOAD_TYPE": "SPEAKER_CABLE",
            "CABLE_TYPE": "Speaker cable",
        },
    )
    result = CadContractValidator(block_contract).validate(
        CadObservationBatch("doc", (ordinary_board, av))
    )
    assert "AV_BOARD_WRONG_ROLE" in issue_codes(result.issues)
    assert result.is_acceptable


def test_invalid_av_load_type_is_nonblocking_diagnostic(block_contract, make_observation):
    av = make_observation(
        "CABLE_OUTLET",
        layer="AV",
        cable_id="AUX",
        attributes={"BOARD": "AV.01", "LOAD_TYPE": "UNKNOWN", "CABLE_TYPE": "Cable"},
    )
    result = CadContractValidator(block_contract).validate(CadObservationBatch("doc", (av,)))
    issue = next(issue for issue in result.issues if issue.code == "LOAD_TYPE_NOT_ALLOWED")
    assert issue.blocks_acceptance is False
    assert result.is_acceptable


def test_av_uses_only_cable_outlet_block_name(block_contract, make_observation):
    av = make_observation(
        "CABLE_OUTLET_FRAME",
        layer="AV",
        cable_id="AUX",
        attributes={"BOARD": "AV.01", "LOAD_TYPE": "HDMI", "CABLE_TYPE": "HDMI"},
    )
    result = CadContractValidator(block_contract).validate(CadObservationBatch("doc", (av,)))
    assert "AV_BLOCK_NAME" in issue_codes(result.issues)
    assert not result.is_acceptable
