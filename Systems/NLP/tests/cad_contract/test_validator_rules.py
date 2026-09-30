from __future__ import annotations

from dataclasses import fields, replace

import pytest

from nl_project_2.cad_contract import (
    BlockDefinitionMetadata,
    CadContractValidator,
    CadObservation,
    CadObservationBatch,
    issue_codes,
)


def _without(observation: CadObservation, *tags: str) -> CadObservation:
    values = {item.tag: item.value for item in observation.raw_attributes if item.tag not in tags}
    definition = observation.definition
    definition_tags = None if definition is None else definition.attribute_definition_tags
    if definition_tags is not None:
        definition = replace(
            definition,
            attribute_definition_tags=tuple(tag for tag in definition_tags if tag not in tags),
        )
    return CadObservation.from_mapping(
        effective_name=observation.effective_name,
        layer=observation.layer,
        raw_attributes=values,
        x=observation.x,
        y=observation.y,
        handle=observation.handle,
        definition=definition,
    )


def test_unmanaged_unknown_block_without_nl_attributes_is_ignored(block_contract):
    observation = CadObservation.from_mapping(
        effective_name="bad block",
        layer="POWER",
        raw_attributes={},
        x=0,
        y=0,
        handle="A1",
    )
    result = CadContractValidator(block_contract).validate(
        CadObservationBatch("doc", (observation,))
    )
    assert result.issues == ()
    assert result.observations[0].block_class == "UNMANAGED"
    assert result.observations[0].ignored_project_data


def test_many_unmanaged_blocks_do_not_create_issue_explosion(block_contract):
    observations = tuple(
        CadObservation.from_mapping(
            effective_name=name,
            layer="INTERIOR",
            raw_attributes={},
            x=index,
            y=index,
            handle=f"F{index}",
        )
        for index, name in enumerate(("Chair 01", "DOOR-modern", "ковер", "TABLE_round"))
    )
    result = CadContractValidator(block_contract).validate(CadObservationBatch("doc", observations))
    assert result.issues == ()
    assert result.ignored_count == len(observations)


def test_unknown_block_claiming_nl_attribute_is_rejected(block_contract):
    observation = CadObservation.from_mapping(
        effective_name="bad block",
        layer="POWER",
        raw_attributes={"CABLE_ID": "101.01"},
        x=0,
        y=0,
        handle="A1",
        definition=BlockDefinitionMetadata(("CABLE_ID",), False),
    )
    codes = issue_codes(
        CadContractValidator(block_contract)
        .validate(CadObservationBatch("doc", (observation,)))
        .issues
    )
    assert {"BLOCK_NAME_FORMAT", "UNKNOWN_BLOCK_NAME"} <= codes


def test_document_identity_and_handle_are_unique(block_contract, make_observation):
    first = make_observation("LIGHT_IN", handle="A1")
    second = make_observation("LIGHT_OUT", handle="A1")
    codes = issue_codes(
        CadContractValidator(block_contract)
        .validate(CadObservationBatch("", (first, second)))
        .issues
    )
    assert {"DOCUMENT_IDENTITY_REQUIRED", "DUPLICATE_DWG_HANDLE"} <= codes


def test_device_type_layer_and_cable_prefix_are_independent_rules(block_contract, make_observation):
    wrong_type = make_observation("LIGHT_IN", attributes={"DEVICE_TYPE": "SOCKET"})
    wrong_layer = make_observation("LIGHT_IN", handle="A2", layer="POWER")
    wrong_prefix = make_observation("LIGHT_IN", handle="A3", cable_id="401")
    codes = issue_codes(
        CadContractValidator(block_contract)
        .validate(CadObservationBatch("doc", (wrong_type, wrong_layer, wrong_prefix)))
        .issues
    )
    assert {"LAYER_FUNCTION_GROUP_MISMATCH", "CABLE_GROUP_PREFIX_MISMATCH"} <= codes
    assert "FORBIDDEN_ATTRIBUTE" in codes


def test_required_and_numeric_fields_are_validated(block_contract, make_observation):
    missing = _without(make_observation("LIGHT_IN"), "BOARD")
    invalid = make_observation(
        "LIGHT_LED",
        handle="A2",
        attributes={"CALC_POWER": "-1", "LENGTH": "zero", "PHASE": "1.5"},
    )
    result = CadContractValidator(block_contract).validate(
        CadObservationBatch("doc", (missing, invalid))
    )
    codes = issue_codes(result.issues)
    assert "REQUIRED_ATTRIBUTE_DEFINITION_MISSING" in codes
    assert sum(issue.code == "NUMERIC_ATTRIBUTE_FORMAT" for issue in result.issues) == 3


def test_closed_load_type_classifier_is_blocking_for_ordinary_line(
    block_contract, make_observation
):
    socket = make_observation("SOCKET_IN", attributes={"LOAD_TYPE": "UNKNOWN"})
    result = CadContractValidator(block_contract).validate(CadObservationBatch("doc", (socket,)))
    assert "LOAD_TYPE_NOT_ALLOWED" in issue_codes(result.issues)
    assert not result.is_acceptable


def test_frame_posts_and_switch_key_contract(block_contract, make_observation):
    wrong_posts = make_observation("FRAME_2", attributes={"POSTS": "3"})
    extra_key = make_observation("SW_IN_1", handle="A2", attributes={"KEY_2": "301"})
    bad_target = make_observation("BTN_IN_1", handle="A3", attributes={"KEY_1": "301.01"})
    missing_key = _without(make_observation("BTN_IN_2", handle="A4"), "KEY_2")
    codes = issue_codes(
        CadContractValidator(block_contract)
        .validate(CadObservationBatch("doc", (wrong_posts, extra_key, bad_target, missing_key)))
        .issues
    )
    assert {"FORBIDDEN_ATTRIBUTE", "UNDECLARED_ATTRIBUTE", "KEY_TARGET_FORMAT"} <= codes
    assert "REQUIRED_ATTRIBUTE_DEFINITION_MISSING" in codes


def test_key_target_must_exist_in_same_observation_batch(block_contract, make_observation):
    switch = make_observation("SW_IN_1", attributes={"KEY_1": "399"})
    codes = issue_codes(
        CadContractValidator(block_contract).validate(CadObservationBatch("doc", (switch,))).issues
    )
    assert "KEY_TARGET_NOT_FOUND" in codes


@pytest.mark.parametrize(
    "forbidden",
    [
        "ID",
        "KEY",
        "CONTACT",
        "CONTACT_1",
        "CONTACT_CUSTOM",
        "ARTICLE",
        "BRAND",
        "SERIES",
        "ROUTER_ID",
    ],
)
def test_all_legacy_attribute_families_are_forbidden(block_contract, make_observation, forbidden):
    observation = make_observation("LIGHT_IN", attributes={forbidden: "legacy"})
    codes = issue_codes(
        CadContractValidator(block_contract)
        .validate(CadObservationBatch("doc", (observation,)))
        .issues
    )
    assert "FORBIDDEN_ATTRIBUTE" in codes
    assert "FORBIDDEN_ATTRIBUTE_DEFINITION" in codes


def test_definition_metadata_checks_required_and_forbidden_tags(block_contract, make_observation):
    base = make_observation("LIGHT_IN")
    assert base.definition and base.definition.attribute_definition_tags
    tags = tuple(tag for tag in base.definition.attribute_definition_tags if tag != "ROOM") + (
        "ARTICLE",
    )
    observation = replace(base, definition=BlockDefinitionMetadata(tags, False))
    codes = issue_codes(
        CadContractValidator(block_contract)
        .validate(CadObservationBatch("doc", (observation,)))
        .issues
    )
    assert "REQUIRED_ATTRIBUTE_DEFINITION_MISSING" in codes
    assert "FORBIDDEN_ATTRIBUTE_DEFINITION" in codes
    assert "ATTRIBUTE_NOT_IN_DEFINITION" in codes


def test_dali_group_contract_is_metadata_only_and_has_no_dynamic_property_names(
    block_contract, make_observation
):
    wrong = make_observation(
        "DALI_GROUP",
        layer="SWITCHES",
        dynamic=False,
        attributes={"DALI_GROUP_ID": "D.12", "CABLE_ID": "901", "ARTICLE": "x"},
    )
    duplicate = make_observation("DALI_GROUP", handle="D2")
    codes = issue_codes(
        CadContractValidator(block_contract)
        .validate(CadObservationBatch("doc", (wrong, duplicate)))
        .issues
    )
    assert {
        "LOGICAL_LAYER_MISMATCH",
        "DALI_GROUP_NOT_DYNAMIC",
        "DALI_GROUP_ID_FORMAT",
        "UNDECLARED_ATTRIBUTE",
        "FORBIDDEN_ATTRIBUTE",
    } <= codes
    assert block_contract.block("DALI_GROUP").required_attributes == frozenset({"DALI_GROUP_ID"})
    assert {field.name for field in fields(BlockDefinitionMetadata)} == {
        "attribute_definition_tags",
        "is_dynamic",
    }


def test_dali_group_id_board_id_and_full_point_are_unique(block_contract, make_observation):
    observations = (
        make_observation("DALI_GROUP", handle="D1"),
        make_observation("DALI_GROUP", handle="D2"),
        make_observation("BOARD_OUT", handle="B1"),
        make_observation("BOARD_PANEL", handle="B2"),
        make_observation("LIGHT_IN", handle="L1", cable_id="301.01"),
        make_observation("LIGHT_IN", handle="L2", cable_id="301.01"),
    )
    codes = issue_codes(
        CadContractValidator(block_contract)
        .validate(CadObservationBatch("doc", observations))
        .issues
    )
    assert {"DUPLICATE_DALI_GROUP_ID", "DUPLICATE_BOARD_ID", "DUPLICATE_FULL_CABLE_ID"} <= codes


def test_line_level_cable_type_board_and_group_are_consistent(block_contract, make_observation):
    first = make_observation("LIGHT_IN", handle="L1", cable_id="301")
    second = make_observation(
        "LIGHT_IN",
        handle="L2",
        cable_id="301.01",
        attributes={"CABLE_TYPE": "OTHER", "BOARD": "B.02"},
    )
    codes = issue_codes(
        CadContractValidator(block_contract)
        .validate(CadObservationBatch("doc", (first, second)))
        .issues
    )
    assert {"LINE_CABLE_TYPE_INCONSISTENT", "LINE_BOARD_INCONSISTENT"} <= codes


def test_line_level_function_group_conflict_is_reported(block_contract, make_observation):
    light = make_observation("LIGHT_IN", handle="L1", cable_id="301")
    outlet = make_observation(
        "CABLE_OUTLET",
        handle="L2",
        layer="POWER",
        cable_id="301.01",
        attributes={"LOAD_TYPE": "CABLE_TECH"},
    )
    codes = issue_codes(
        CadContractValidator(block_contract)
        .validate(CadObservationBatch("doc", (light, outlet)))
        .issues
    )
    assert {"CABLE_GROUP_PREFIX_MISMATCH", "LINE_FUNCTION_GROUP_INCONSISTENT"} <= codes


def test_line_conduit_attributes_matrix_format_and_definition_are_validated(
    block_contract, make_observation
):
    missing_definition = make_observation(
        "SOCKET_IN",
        definition_tags=(
            "DEVICE_TYPE",
            "DEVICE_NAME",
            "BUILDING",
            "ROOM",
            "MOUNT_HEIGHT",
            "CABLE_ID",
            "CABLE_TYPE",
            "BOARD",
            "LOAD_TYPE",
            "LOAD_NAME",
            "MOUNT_WAY",
            "GOFRA_TYPE",
            "GOFRA_COLOR",
        ),
        attributes={
            "MOUNT_WAY": "По полу",
            "GOFRA_TYPE": "ПНД25",
            "GOFRA_COLOR": "Черный",
            "GOFRA_ID": "001.PND25",
        },
    )
    wrong_suffix = make_observation(
        "SOCKET_IN",
        handle="A2",
        attributes={
            "MOUNT_WAY": "По полу",
            "GOFRA_TYPE": "ПНД32",
            "GOFRA_COLOR": "Черный",
            "GOFRA_ID": "001.PND25",
        },
    )
    cable_channel = make_observation(
        "SOCKET_IN",
        handle="A3",
        attributes={
            "MOUNT_WAY": "В кабель-канале",
            "GOFRA_TYPE": "",
            "GOFRA_COLOR": "Черный",
            "GOFRA_ID": "",
        },
    )
    result = CadContractValidator(block_contract).validate(
        CadObservationBatch("doc", (missing_definition, wrong_suffix, cable_channel))
    )
    codes = issue_codes(result.issues)
    assert {
        "REQUIRED_ATTRIBUTE_DEFINITION_MISSING",
        "GOFRA_ID_TYPE_MISMATCH",
        "GOFRA_FIELDS_WITHOUT_CONDUIT",
    } <= codes


def test_pp25_and_numbered_room_are_valid_project_line_data(block_contract, make_observation):
    observation = make_observation(
        "SOCKET_IN",
        attributes={
            "ROOM": "5. Кухня-ниша",
            "MOUNT_WAY": "По полу",
            "GOFRA_TYPE": "ППЛ25",
            "GOFRA_COLOR": "синий",
            "GOFRA_ID": "001.PP25",
        },
    )
    result = CadContractValidator(block_contract).validate(
        CadObservationBatch("doc", (observation,))
    )
    assert not any(
        issue.field in {"ROOM", "GOFRA_TYPE", "GOFRA_COLOR", "GOFRA_ID"} and issue.blocks_acceptance
        for issue in result.issues
    )


def test_line_and_shared_conduit_values_are_consistent(block_contract, make_observation):
    first = make_observation(
        "SOCKET_IN",
        handle="A1",
        cable_id="101.01",
        attributes={
            "MOUNT_WAY": "По полу",
            "GOFRA_TYPE": "ПНД25",
            "GOFRA_COLOR": "Черный",
            "GOFRA_ID": "001.PND25",
        },
    )
    same_line = make_observation(
        "SOCKET_IN",
        handle="A2",
        cable_id="101.02",
        attributes={
            "MOUNT_WAY": "По потолку",
            "GOFRA_TYPE": "ПНД25",
            "GOFRA_COLOR": "Черный",
            "GOFRA_ID": "001.PND25",
        },
    )
    shared_other_line = make_observation(
        "SOCKET_IN",
        handle="A3",
        cable_id="102.01",
        attributes={
            "MOUNT_WAY": "По полу",
            "GOFRA_TYPE": "ПНД25",
            "GOFRA_COLOR": "Серый",
            "GOFRA_ID": "001.PND25",
        },
    )
    result = CadContractValidator(block_contract).validate(
        CadObservationBatch("doc", (first, same_line, shared_other_line))
    )
    codes = issue_codes(result.issues)
    assert not any(code.startswith("LINE_MOUNT_WAY") for code in codes)
    assert not any(code.startswith("LINE_GOFRA") for code in codes)
    assert "CONDUIT_COLOR_INCONSISTENT" in codes


def test_board_feed_roles_require_feed_fields(block_contract, make_observation):
    board = make_observation("BOARD_IN", attributes={"LOAD_TYPE": "BOARD_IN"})
    result = CadContractValidator(block_contract).validate(CadObservationBatch("doc", (board,)))
    assert not {
        issue.field for issue in result.issues if issue.code == "REQUIRED_ATTRIBUTE_MISSING"
    }
    assert {"CABLE_ID", "CABLE_TYPE"} <= block_contract.block(
        "BOARD_IN"
    ).required_definition_attributes


def test_board_av_requires_approved_board_in_name(block_contract, make_observation):
    board = make_observation("BOARD_OUT", attributes={"LOAD_TYPE": "BOARD_AV"})
    result = CadContractValidator(block_contract).validate(CadObservationBatch("doc", (board,)))
    assert "LOAD_TYPE_NOT_ALLOWED" in issue_codes(result.issues)


def test_room_name_is_fully_ignored_even_with_legacy_content(block_contract, make_observation):
    observation = make_observation(
        "ROOM_NAME",
        handle="",
        attributes={"CONTACT_1": "legacy", "ARTICLE": "legacy"},
        x="NaN",
        y="Infinity",
    )
    result = CadContractValidator(block_contract).validate(
        CadObservationBatch("doc", (observation,))
    )
    assert result.is_acceptable
    assert result.issues == ()
    assert result.observations[0].ignored_project_data is True
    assert result.observations[0].normalized_attributes == {}


def test_handle_coordinates_and_definition_tag_format_are_validated(
    block_contract, make_observation
):
    first = make_observation("LIGHT_IN", handle="", x="NaN", y=float("inf"))
    second = make_observation("LIGHT_IN", handle="A2", definition_tags=("device_type",))
    codes = issue_codes(
        CadContractValidator(block_contract)
        .validate(CadObservationBatch("doc", (first, second)))
        .issues
    )
    assert {
        "DWG_HANDLE_REQUIRED",
        "COORDINATE_NOT_FINITE",
        "ATTRIBUTE_DEFINITION_TAG_FORMAT",
    } <= codes


def test_arbitrary_geometry_cannot_influence_validation(block_contract, make_observation):
    assert "geometry" not in {field.name for field in fields(CadObservation)}
    observation = make_observation("LIGHT_IN")
    validator = CadContractValidator(block_contract)
    plain = validator.validate(CadObservationBatch("doc", (observation,)))
    decorated = validator.validate(
        CadObservationBatch("doc", (observation,), source_metadata={"arbitrary_geometry": object()})
    )
    assert plain.issues == decorated.issues
    assert plain.observations == decorated.observations


@pytest.mark.parametrize("prefix", ["", "BUS_"])
@pytest.mark.parametrize(
    ("conduit_type", "suffix"),
    [
        ("ППЛ20", "PP20"),
        ("ППЛ25", "PP25"),
        ("МПТ16", "MPT16"),
        ("ПНД20", "PND20"),
        ("ПНД25", "PND25"),
        ("ПВХ20", "PVH20"),
        ("Металлорукав25", "MR25"),
    ],
)
def test_ordinary_and_bus_conduit_types_and_ids_are_validated(
    block_contract, make_observation, prefix, conduit_type, suffix
):
    route = {
        f"{prefix}MOUNT_WAY": "По полу",
        f"{prefix}GOFRA_TYPE": conduit_type,
        f"{prefix}GOFRA_COLOR": "",
        f"{prefix}GOFRA_ID": f"003.{suffix}",
    }
    observation = make_observation("LIGHT_OUT_DALI_230V", attributes=route)
    validator = CadContractValidator(block_contract)
    result = validator.validate(CadObservationBatch("doc", (observation,)))
    assert not [issue for issue in result.issues if issue.blocks_acceptance]
    payload = result.observations[0].read_payload
    assert payload is not None
    fields = payload.bus_route_fields if prefix else payload.route_fields
    assert {item.tag: item.value for item in fields}.items() >= route.items()

    wrong_id = make_observation(
        "LIGHT_OUT_DALI_230V", attributes={**route, f"{prefix}GOFRA_ID": "003.WRONG16"}
    )
    failure = validator.validate(CadObservationBatch("doc", (wrong_id,)))
    assert any(
        issue.code == f"{prefix}GOFRA_ID_TYPE_MISMATCH"
        and issue.field == f"{prefix}GOFRA_ID"
        and issue.blocks_acceptance
        for issue in failure.issues
    )


@pytest.mark.parametrize("prefix", ["", "BUS_"])
@pytest.mark.parametrize("invalid_type", ["ПП25", "МПТ16.5", "Неизвестная16"])
def test_invalid_conduit_type_is_rejected_in_both_networks(
    block_contract, make_observation, prefix, invalid_type
):
    observation = make_observation(
        "LIGHT_OUT_DALI_230V",
        attributes={
            f"{prefix}MOUNT_WAY": "По полу",
            f"{prefix}GOFRA_TYPE": invalid_type,
            f"{prefix}GOFRA_ID": "",
        },
    )
    result = CadContractValidator(block_contract).validate(
        CadObservationBatch("doc", (observation,))
    )
    assert any(
        issue.code == f"{prefix}GOFRA_TYPE_FORMAT"
        and issue.field == f"{prefix}GOFRA_TYPE"
        and issue.blocks_acceptance
        for issue in result.issues
    )


@pytest.mark.parametrize("prefix", ["", "BUS_"])
@pytest.mark.parametrize("conduit_type", ["ППЛ20", "ППЛ25"])
def test_timber_mount_way_accepts_only_ppl_conduits(
    block_contract, make_observation, prefix, conduit_type
):
    route = {
        f"{prefix}MOUNT_WAY": "В брусе",
        f"{prefix}GOFRA_TYPE": conduit_type,
        f"{prefix}GOFRA_COLOR": "",
        f"{prefix}GOFRA_ID": "",
    }
    observation = make_observation("LIGHT_OUT_DALI_230V", attributes=route)
    result = CadContractValidator(block_contract).validate(
        CadObservationBatch("doc", (observation,))
    )
    route_fields = {
        f"{prefix}MOUNT_WAY",
        f"{prefix}GOFRA_TYPE",
        f"{prefix}GOFRA_COLOR",
        f"{prefix}GOFRA_ID",
    }
    assert not [
        issue for issue in result.issues if issue.blocks_acceptance and issue.field in route_fields
    ]


@pytest.mark.parametrize("prefix", ["", "BUS_"])
@pytest.mark.parametrize("conduit_type", ["", "ПНД25", "ПВХ20", "МПТ16"])
def test_timber_mount_way_rejects_missing_or_non_ppl_conduit(
    block_contract, make_observation, prefix, conduit_type
):
    observation = make_observation(
        "LIGHT_OUT_DALI_230V",
        attributes={
            f"{prefix}MOUNT_WAY": "В брусе",
            f"{prefix}GOFRA_TYPE": conduit_type,
            f"{prefix}GOFRA_COLOR": "",
            f"{prefix}GOFRA_ID": "",
        },
    )
    result = CadContractValidator(block_contract).validate(
        CadObservationBatch("doc", (observation,))
    )
    expected_code = (
        f"{prefix}GOFRA_TYPE_REQUIRED" if not conduit_type else f"{prefix}GOFRA_TYPE_FORMAT"
    )
    assert any(
        issue.code == expected_code
        and issue.field == f"{prefix}GOFRA_TYPE"
        and issue.blocks_acceptance
        for issue in result.issues
    )
