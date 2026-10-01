from nl_project_2.cad_contract import CadContractValidator, CadObservationBatch, issue_codes


def test_base_only_box_chain_has_distinct_graph_nodes(block_contract, make_observation):
    boxes = tuple(
        make_observation(
            "EL_BOX_OUT_100x100",
            handle=f"E{i}",
            cable_id="111",
            layer="POWER",
            attributes={
                "BOX_ID": f"BOX.{20 + i:03d}",
                "CABLE_SOURCE": "" if i == 1 else f"BOX.{19 + i:03d}",
                "BUS_POINT_ID": "",
                "BUS_SOURCE": "",
            },
        )
        for i in range(1, 5)
    )
    result = CadContractValidator(block_contract).validate(CadObservationBatch("doc", boxes))
    assert result.issues == ()
    assert issue_codes(result.issues) == frozenset()


def test_box_self_reference_and_duplicate_box_identity_are_invalid(
    block_contract, make_observation
):
    validator = CadContractValidator(block_contract)
    first = make_observation(
        "EL_BOX_OUT_100x100",
        handle="E1",
        cable_id="111",
        layer="POWER",
        attributes={
            "BOX_ID": "BOX.021",
            "CABLE_SOURCE": "BOX.021",
            "BUS_POINT_ID": "",
            "BUS_SOURCE": "",
        },
    )
    assert "CABLE_SOURCE_CYCLE" in issue_codes(
        validator.validate(CadObservationBatch("doc", (first,))).issues
    )
    duplicate = make_observation(
        "EL_BOX_OUT_100x100",
        handle="E2",
        cable_id="112",
        layer="POWER",
        attributes={"BOX_ID": "BOX.021", "BUS_POINT_ID": "", "BUS_SOURCE": ""},
    )
    assert "DUPLICATE_BOX_ID" in issue_codes(
        validator.validate(CadObservationBatch("doc", (first, duplicate))).issues
    )
