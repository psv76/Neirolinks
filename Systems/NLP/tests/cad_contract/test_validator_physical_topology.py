from __future__ import annotations

from nl_project_2.cad_contract import (
    CableSuffixKind,
    CadContractValidator,
    CadObservationBatch,
    issue_codes,
)


def _validate(contract, *observations, metadata=None):
    return CadContractValidator(contract).validate(
        CadObservationBatch("fixture-doc", tuple(observations), metadata or {})
    )


def test_el_box_uses_ordinary_cable_id_source_and_rejects_legacy_fields(
    block_contract, make_observation
):
    valid = make_observation(
        "EL_BOX_OUT_100x100",
        handle="E1",
        layer="LIGHTING_230V",
        cable_id="301.02",
        attributes={
            "BOX_ID": "BOX.001",
            "CABLE_SOURCE": "301.01",
            "BUS_POINT_ID": "",
            "BUS_SOURCE": "",
        },
    )
    invalid_zero = make_observation(
        "EL_BOX_OUT_100x100",
        handle="E2",
        layer="LIGHTING_230V",
        cable_id="301.RK0",
        attributes={"IN": "301.01"},
    )
    wrong_device = make_observation("LIGHT_IN", handle="L1", cable_id="301.RK1")
    result = _validate(block_contract, valid, invalid_zero, wrong_device)
    codes = issue_codes(result.issues)
    assert "CABLE_ID_FORMAT" in codes
    assert "EL_BOX_CABLE_ID_REQUIRED" in codes
    assert "EL_BOX_SUFFIX_NOT_ALLOWED" in codes
    assert "UNDECLARED_ATTRIBUTE" in codes
    payload = result.observations[0].read_payload
    assert payload is not None
    assert payload.cable_identity is not None
    assert payload.cable_identity.suffix_kind is CableSuffixKind.POINT
    assert payload.cable_identity.suffix_order == 2
    assert payload.cable_source == "301.01"
    assert payload.topology_outputs == ()


def test_el_box_graph_valid_missing_self_cycle_double_parent_and_deterministic(
    block_contract, make_observation
):
    root = make_observation(
        "EL_BOX_OUT_100x100",
        handle="E1",
        layer="LIGHTING_230V",
        cable_id="301.RK1",
        attributes={"OUT_1": "301.01"},
    )
    target = make_observation("LIGHT_IN", handle="L1", cable_id="301.01")
    assert "EL_BOX_TARGET_NOT_FOUND" not in issue_codes(
        _validate(block_contract, root, target).issues
    )

    missing = make_observation(
        "EL_BOX_OUT_100x100",
        handle="E2",
        layer="LIGHTING_230V",
        cable_id="302.RK1",
        attributes={"OUT_1": "302.01"},
    )
    self_ref = make_observation(
        "EL_BOX_OUT_100x100",
        handle="E3",
        layer="LIGHTING_230V",
        cable_id="303.RK1",
        attributes={"OUT_1": "303.RK1"},
    )
    cycle_a = make_observation(
        "EL_BOX_OUT_100x100",
        handle="E4",
        layer="LIGHTING_230V",
        cable_id="304.RK1",
        attributes={"OUT_1": "304.RK2"},
    )
    cycle_b = make_observation(
        "EL_BOX_OUT_100x100",
        handle="E5",
        layer="LIGHTING_230V",
        cable_id="304.RK2",
        attributes={"OUT_1": "304.RK1"},
    )
    parent_a = make_observation(
        "EL_BOX_OUT_100x100",
        handle="E6",
        layer="LIGHTING_230V",
        cable_id="305.RK1",
        attributes={"OUT_1": "305.01"},
    )
    parent_b = make_observation(
        "EL_BOX_OUT_100x100",
        handle="E7",
        layer="LIGHTING_230V",
        cable_id="305.RK2",
        attributes={"OUT_1": "305.01"},
    )
    child = make_observation("LIGHT_IN", handle="L5", cable_id="305.01")
    duplicate = make_observation(
        "EL_BOX_OUT_100x100",
        handle="E8",
        layer="LIGHTING_230V",
        cable_id="306.RK1",
        attributes={"OUT_1": "306.01", "OUT_2": "306.01"},
    )
    duplicate_target = make_observation("LIGHT_IN", handle="L6", cable_id="306.01")
    observations = (
        missing,
        self_ref,
        cycle_a,
        cycle_b,
        parent_a,
        parent_b,
        child,
        duplicate,
        duplicate_target,
    )
    forward = _validate(block_contract, *observations)
    reverse = _validate(block_contract, *reversed(observations))
    expected = {
        "EL_BOX_TARGET_NOT_FOUND",
        "EL_BOX_SELF_REFERENCE",
        "EL_BOX_CYCLE",
        "EL_BOX_DOUBLE_PARENT",
        "EL_BOX_AMBIGUOUS_ROOT",
        "EL_BOX_DUPLICATE_EDGE",
    }
    assert expected <= issue_codes(forward.issues)
    signature = lambda result: sorted(  # noqa: E731
        (
            issue.code,
            issue.handle,
            issue.field,
            issue.message,
            issue.related_handles,
        )
        for issue in result.issues
    )
    assert signature(forward) == signature(reverse)


def test_cross_line_out_is_local_and_does_not_join_same_base_graph(
    block_contract, make_observation
):
    box = make_observation(
        "EL_BOX_OUT_100x100",
        handle="E1",
        layer="LIGHTING_230V",
        cable_id="301.RK1",
        attributes={"OUT_1": "901.01"},
    )
    bus_target = make_observation("SENSOR_1WIRE", handle="S1", layer="BUS", cable_id="901.01")
    result = _validate(block_contract, box, bus_target)
    codes = issue_codes(result.issues)
    assert "EL_BOX_CROSS_LINE_TARGET_NOT_FOUND" not in codes
    assert "EL_BOX_AMBIGUOUS_ROOT" not in codes


def test_route_is_segment_owned_wall_is_allowed_and_shared_socket_is_strict(
    block_contract, make_observation
):
    first = make_observation(
        "SOCKET_IN",
        handle="S1",
        cable_id="101.01",
        attributes={"MOUNT_WAY": "В стене"},
    )
    second = make_observation(
        "SOCKET_IN",
        handle="S2",
        cable_id="101.02",
        attributes={"MOUNT_WAY": "По потолку"},
    )
    result = _validate(block_contract, first, second)
    assert not any(
        code.startswith("LINE_MOUNT_WAY") or code.startswith("LINE_GOFRA")
        for code in issue_codes(result.issues)
    )

    shared = make_observation(
        "SOCKET_IN",
        handle="S3",
        cable_id="101.01",
        attributes={"MOUNT_WAY": "В стене"},
    )
    assert "DUPLICATE_FULL_CABLE_ID" not in issue_codes(
        _validate(block_contract, first, shared).issues
    )
    inconsistent = make_observation(
        "SOCKET_IN",
        handle="S4",
        cable_id="101.01",
        attributes={"MOUNT_WAY": "По полу", "GOFRA_TYPE": "ПНД25"},
    )
    assert "SHARED_SOCKET_POINT_INCONSISTENT" in issue_codes(
        _validate(block_contract, first, inconsistent).issues
    )
    non_socket = make_observation("LIGHT_IN", handle="L1", cable_id="301.01")
    non_socket_2 = make_observation("LIGHT_IN", handle="L2", cable_id="301.01")
    assert "DUPLICATE_FULL_CABLE_ID" in issue_codes(
        _validate(block_contract, non_socket, non_socket_2).issues
    )
    mixed_socket = make_observation(
        "SOCKET_ETHERNET", handle="S5", layer="NETWORK", cable_id="801.01"
    )
    mixed_outlet = make_observation(
        "CABLE_OUTLET",
        handle="C1",
        layer="NETWORK",
        cable_id="801.01",
        attributes={"LOAD_TYPE": "CABLE_TECH"},
    )
    assert "SHARED_SOCKET_DEVICE_TYPE_MISMATCH" in issue_codes(
        _validate(block_contract, mixed_socket, mixed_outlet).issues
    )


def test_led_type_exact_enum_required_definition_and_line_consistency(
    block_contract, make_observation
):
    for index, value in enumerate(("MONO", "CCT", "RGB", "RGBW"), 1):
        result = _validate(
            block_contract,
            make_observation(
                "LIGHT_LED",
                handle=f"L{index}",
                cable_id=f"4{index:02d}",
                attributes={"LED_TYPE": value},
            ),
        )
        assert "LED_TYPE_NOT_ALLOWED" not in issue_codes(result.issues)

    mixed = make_observation("LIGHT_LED", attributes={"LED_TYPE": "MIX"})
    missing_definition = make_observation(
        "LIGHT_LED",
        handle="L6",
        definition_tags=tuple(
            tag
            for tag in block_contract.block("LIGHT_LED").required_definition_attributes
            if tag != "LED_TYPE"
        ),
    )
    rgb = make_observation(
        "LIGHT_LED", handle="L7", cable_id="407.01", attributes={"LED_TYPE": "RGB"}
    )
    rgbw = make_observation(
        "LIGHT_LED", handle="L8", cable_id="407.02", attributes={"LED_TYPE": "RGBW"}
    )
    codes = issue_codes(_validate(block_contract, mixed, missing_definition, rgb, rgbw).issues)
    assert {
        "LED_TYPE_NOT_ALLOWED",
        "REQUIRED_ATTRIBUTE_DEFINITION_MISSING",
        "LINE_LED_TYPE_INCONSISTENT",
    } <= codes


def test_grouped_switch_order_keys_and_machine_capacity(block_contract, make_observation):
    later = make_observation("SW_IN_4", handle="S2", cable_id="201.02")
    earlier = make_observation("SW_IN_3", handle="S1", cable_id="201.01")
    passing = _validate(
        block_contract,
        later,
        earlier,
        metadata={"cable_type_conductors": {"TEST CABLE": 8}},
    )
    assert "SWITCH_CONDUCTOR_CAPACITY_EXCEEDED" not in issue_codes(passing.issues)
    payloads = [item.read_payload for item in passing.observations]
    assert [payload.cable_identity.suffix_order for payload in payloads] == [2, 1]
    assert [fact.tag for fact in payloads[0].keys] == ["KEY_1", "KEY_2", "KEY_3", "KEY_4"]

    too_many = _validate(
        block_contract,
        make_observation("SW_IN_4", handle="S3", cable_id="202.02"),
        make_observation("SW_IN_4", handle="S4", cable_id="202.01"),
        metadata={"cable_type_conductors": {"TEST CABLE": 8}},
    )
    assert "SWITCH_CONDUCTOR_CAPACITY_EXCEEDED" in issue_codes(too_many.issues)
    unknown = _validate(block_contract, earlier)
    issue = next(
        item for item in unknown.issues if item.code == "SWITCH_CONDUCTOR_CAPACITY_UNKNOWN"
    )
    assert not issue.blocks_acceptance


def test_mrm2_m1w2_references_and_bus_endpoint_payload(block_contract, make_observation):
    key_source = make_observation("SW_IN_2", handle="K1", cable_id="201.01")
    output = make_observation("LIGHT_IN_230V", handle="L1", cable_id="301")
    wire_target = make_observation("SENSOR_1WIRE", handle="W1", cable_id="501.01")
    mrm = make_observation(
        "WB_MRM2_MINI",
        handle="M1",
        layer="BUS",
        cable_id="901.01",
        attributes={"K1": "301", "IN_1": "201.01"},
    )
    sensor = make_observation(
        "WB_M1W2",
        handle="M2",
        cable_id="501.02",
        attributes={"W1": "501.01"},
    )
    result = _validate(block_contract, key_source, output, wire_target, mrm, sensor)
    codes = issue_codes(result.issues)
    assert (
        not {
            "MRM2_OUTPUT_TARGET_NOT_FOUND",
            "MRM2_INPUT_KEY_NOT_FOUND",
            "M1W2_CHANNEL_TARGET_NOT_FOUND",
        }
        & codes
    )
    mrm_payload = next(
        item.read_payload for item in result.observations if item.observation.handle == "M1"
    )
    assert [fact.tag for fact in mrm_payload.field_ports] == [
        "COM1",
        "COM2",
        "K1",
        "K2",
        "IN_1",
        "IN_2",
    ]

    bad = make_observation(
        "WB_MRM2_MINI",
        handle="M3",
        layer="BUS",
        cable_id="902.01",
        attributes={"K1": "301.01", "IN_1": "201.01/KEY_9"},
    )
    bad_sensor = make_observation(
        "WB_M1W2", handle="M4", cable_id="502.01", attributes={"W1": "bad"}
    )
    bad_codes = issue_codes(_validate(block_contract, bad, bad_sensor).issues)
    assert "FIELD_PORT_REFERENCE_FORMAT" in bad_codes
    missing = make_observation(
        "WB_MRM2_MINI",
        handle="M5",
        layer="BUS",
        cable_id="903.01",
        attributes={"K1": "399", "IN_1": "299.01"},
    )
    missing_sensor = make_observation(
        "WB_M1W2",
        handle="M6",
        cable_id="503.01",
        attributes={"W1": "599.01"},
    )
    missing_codes = issue_codes(_validate(block_contract, missing, missing_sensor).issues)
    assert "FIELD_PORT_REFERENCE_FORMAT" not in missing_codes


def test_frame_mechanism_ip44_issues_are_project_level_nonblocking(
    block_contract, make_observation
):
    passing = _validate(
        block_contract,
        make_observation("FRAME_2", handle="F1"),
        make_observation("SOCKET_IN", handle="S1", layer="POWER", cable_id="101.01"),
        make_observation("SW_IN_1", handle="S2", cable_id="201.01"),
    )
    assert not {code for code in issue_codes(passing.issues) if code.startswith("FRAME_")}

    attention = _validate(
        block_contract,
        make_observation("FRAME_1", handle="F2"),
        make_observation("SOCKET_IN_IP44", handle="S3", layer="POWER", cable_id="102.01"),
        make_observation("SOCKET_IN", handle="S4", layer="POWER", cable_id="102.02"),
    )
    frame_issues = [issue for issue in attention.issues if issue.code.startswith("FRAME_")]
    assert {issue.code for issue in frame_issues} == {
        "FRAME_POSTS_DEFICIT",
        "FRAME_IP44_POSTS_DEFICIT",
    }
    assert all(not issue.blocks_acceptance for issue in frame_issues)
    assert all(issue.related_handles for issue in frame_issues)
    assert attention.is_acceptable

    excess = _validate(
        block_contract,
        make_observation("FRAME_2", handle="F3"),
        make_observation("SOCKET_IN", handle="S5", layer="POWER", cable_id="103.01"),
    )
    excess_issue = next(issue for issue in excess.issues if issue.code == "FRAME_POSTS_EXCESS")
    assert not excess_issue.blocks_acceptance
