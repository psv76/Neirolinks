from pathlib import Path

import pytest

from nl_project_2.cad_contract import CadContractValidator, CadObservationBatch, issue_codes

TAGS = frozenset(
    "DEVICE_NAME BUILDING ROOM MOUNT_HEIGHT BUS_POINT_ID BUS_CABLE_TYPE "
    "BUS_MOUNT_WAY BUS_GOFRA_TYPE BUS_GOFRA_COLOR BUS_GOFRA_ID LOAD_NAME "
    "COMMENT_1 COMMENT_2 BUS_SOURCE".split()
)


def test_exact_contract_and_human_parity(block_contract):
    rule = block_contract.block("CABLE_OUTLET_BUS")
    assert rule.required_definition_attributes == TAGS
    assert rule.allowed_groups == {"BUS"}
    assert rule.device_type == "CABLE_OUTLET"
    assert rule.bus_link_kind == "CABLE"
    assert rule.cable_link_kind is None
    text = (
        Path(__file__).parents[2] / "docs/autocad/AUTOCAD_BLOCK_ATTRIBUTE_REFERENCE.md"
    ).read_text(encoding="utf-8")
    section = text.split("#### `CABLE_OUTLET_BUS`", 1)[1].split("####", 1)[0]
    assert set(section.split("```text\n", 1)[1].split("```", 1)[0].split()) == TAGS


@pytest.mark.parametrize("kind", ["RS485", "DALI", "KNX"])
def test_project_kind_and_no_ordinary_cable(block_contract, make_observation, kind):
    row = make_observation(
        "CABLE_OUTLET_BUS",
        attributes={
            "BUS_POINT_ID": "920.001",
            "BUS_SOURCE": "" if kind == "RS485" else "920.000",
            "BUS_CABLE_TYPE": "FTP 5e",
            "BUS_MOUNT_WAY": "По полу",
            "BUS_GOFRA_TYPE": "ППЛ20",
            "BUS_GOFRA_COLOR": "Синий",
            "BUS_GOFRA_ID": "",
        },
    )
    result = CadContractValidator(block_contract, project_bus_kinds={"920": kind}).validate(
        CadObservationBatch("doc", (row,))
    )
    assert result.is_acceptable, result.issues
    payload = result.observations[0].read_payload
    assert payload.bus_type == kind
    assert payload.cable_identity is None
    assert payload.cable_link_kind is None


@pytest.mark.parametrize("kinds", [{}, {"920": "UNKNOWN"}])
def test_no_protocol_guess(block_contract, make_observation, kinds):
    row = make_observation(
        "CABLE_OUTLET_BUS", attributes={"BUS_POINT_ID": "920.001", "BUS_SOURCE": "920.000"}
    )
    result = CadContractValidator(block_contract, project_bus_kinds=kinds).validate(
        CadObservationBatch("doc", (row,))
    )
    assert "BUS_TYPE_REQUIRED" in issue_codes(result.issues)
    assert result.observations[0].read_payload.bus_type is None


@pytest.mark.parametrize("kind", ["DALI", "KNX"])
@pytest.mark.parametrize(
    ("sources", "code"),
    [
        (("920.000", "920.001", "920.001"), None),
        (("920.000", "920.000", "920.000"), None),
        (("920.002", "920.001", "920.002"), "BUS_SOURCE_CYCLE"),
        (("920.999", "920.001", "920.002"), "BUS_SOURCE_NOT_FOUND"),
        (("921.000", "920.001", "920.002"), "BUS_SOURCE_CROSS_BUS"),
        (("", "920.001", "920.002"), "BUS_SOURCE_FORMAT"),
    ],
)
def test_tree_rules(block_contract, make_observation, kind, sources, code):
    rows = tuple(
        make_observation(
            "CABLE_OUTLET_BUS",
            handle=str(i),
            attributes={"BUS_POINT_ID": f"920.{i:03d}", "BUS_SOURCE": source},
        )
        for i, source in enumerate(sources, 1)
    )
    result = CadContractValidator(block_contract, project_bus_kinds={"920": kind}).validate(
        CadObservationBatch("doc", rows)
    )
    if code:
        assert code in issue_codes(result.issues)
        assert "BUS_POINT_UNREACHABLE" in issue_codes(result.issues)
    else:
        assert result.is_acceptable, result.issues


def test_rs485_source_and_specialized_conflict(block_contract, make_observation):
    rows = (
        make_observation(
            "CABLE_OUTLET_BUS",
            handle="A",
            attributes={"BUS_POINT_ID": "920.001", "BUS_SOURCE": "920.000"},
        ),
        make_observation("SENSOR_MSW", handle="B", attributes={"BUS_POINT_ID": "921.001"}),
    )
    result = CadContractValidator(
        block_contract, project_bus_kinds={"920": "RS485", "921": "KNX"}
    ).validate(CadObservationBatch("doc", rows))
    assert {"RS485_BUS_SOURCE_FORBIDDEN", "BUS_TYPE_CONFLICT"} <= issue_codes(result.issues)


@pytest.mark.parametrize(
    ("values", "code"),
    [
        ({"BUS_POINT_ID": "920.000"}, "BUS_ROOT_RESERVED"),
        ({"BUS_POINT_ID": "920.01"}, "BUS_POINT_ID_FORMAT"),
        ({"BUS_MOUNT_WAY": "invalid"}, "BUS_MOUNT_WAY_NOT_ALLOWED"),
        ({"BUS_GOFRA_TYPE": "invalid"}, "BUS_GOFRA_TYPE_FORMAT"),
    ],
)
def test_invalid_facts(block_contract, make_observation, values, code):
    row = make_observation(
        "CABLE_OUTLET_BUS", attributes={"BUS_POINT_ID": "920.001", "BUS_SOURCE": "", **values}
    )
    result = CadContractValidator(block_contract, project_bus_kinds={"920": "RS485"}).validate(
        CadObservationBatch("doc", (row,))
    )
    assert code in issue_codes(result.issues)


def test_duplicate_parent_and_exact_definition(block_contract, make_observation):
    rows = tuple(
        make_observation(
            "CABLE_OUTLET_BUS",
            handle=str(i),
            attributes={"BUS_POINT_ID": "920.001", "BUS_SOURCE": source},
            definition_tags=tuple(TAGS | {"CALC_POWER"}),
        )
        for i, source in enumerate(("920.000", "920.003"))
    )
    result = CadContractValidator(block_contract, project_bus_kinds={"920": "KNX"}).validate(
        CadObservationBatch("doc", rows)
    )
    assert {"DUPLICATE_BUS_POINT_ID", "BUS_SOURCE_DOUBLE_PARENT"} <= issue_codes(result.issues)
    assert not result.is_acceptable
