"""Full validator synthetic batches. No Project DB, CAD, or generated edges."""

from dataclasses import replace

import pytest

from nl_project_2.cad_contract import CadContractValidator, CadObservationBatch, issue_codes
from nl_project_2.cad_contract.models import CadAttribute


@pytest.fixture
def node(make_observation):
    def build(identity, source="905.000", bus="905", handle=None, name=None):
        attrs = {"BUS_SOURCE": source}
        if identity.startswith("BOX"):
            name = name or "EL_BOX_OUT_100x100"
            attrs.update(
                BOX_ID=identity, BUS_ID=bus, CABLE_ID="", CABLE_SOURCE="", CABLE_TYPE="", BOARD=""
            )
        elif identity.startswith("TRACK"):
            name = name or "TRACK_DALI"
            attrs.update(TRACK_ID=identity, BUS_ID=bus, CABLE_ID="401", LENGTH="1000")
        else:
            name = name or "LIGHT_OUT_DALI_230V"
            attrs.update(BUS_POINT_ID=identity)
        return make_observation(
            name,
            handle=handle or identity,
            attributes=attrs,
            layer=(
                "BUS"
                if name == "EL_BOX_OUT_100x100"
                else "TRACK_DALI"
                if name == "TRACK_DALI"
                else None
            ),
        )

    return build


def validate(contract, *nodes, roots=("905.000",), kinds=None):
    return CadContractValidator(
        contract,
        project_bus_roots=roots,
        project_bus_kinds=kinds,
    ).validate(CadObservationBatch("synthetic-237", tuple(nodes)))


def graph_issues(result):
    return [i for i in result.issues if i.code.startswith(("BUS_", "PASSIVE_"))]


def test_branched_two_box_two_track_ten_lights(block_contract, node):
    nodes = [
        node("BOX.001"),
        node("BOX.002", "BOX.001"),
        node("TRACK.001", "BOX.001"),
        node("TRACK.002", "BOX.002"),
    ]
    nodes += [
        node(f"905.{i:03d}", f"TRACK.{1 + i % 2:03d}", name="LIGHT_TRACK_DALI_48V")
        for i in range(1, 11)
    ]
    result = validate(block_contract, *nodes)
    assert graph_issues(result) == []
    for item in result.observations[:4]:
        assert (
            item.read_payload.bus_id,
            item.read_payload.bus_type,
            item.read_payload.bus_point_id,
        ) == ("905", "DALI", None)
    for item in result.observations[4:]:
        assert item.read_payload.bus_link_kind == "TRACK"
        assert item.read_payload.bus_point_id.startswith("905.")
    # #238 layer selection and ordinary TRACK source support are separate gates.
    assert "LAYER_FUNCTION_GROUP_MISMATCH" in issue_codes(result.issues)


def test_box_and_addressable_chain_is_fully_acceptable(block_contract, node):
    result = validate(block_contract, node("BOX.001"), node("905.001", "BOX.001"))
    assert result.is_acceptable, result.issues


@pytest.mark.parametrize(
    "source,code",
    [
        ("", "BUS_SOURCE_REQUIRED"),
        ("BOX.999", "BUS_SOURCE_NOT_FOUND"),
        ("TRACK.999", "BUS_SOURCE_NOT_FOUND"),
        ("905.099", "BUS_SOURCE_NOT_FOUND"),
        ("906.000", "BUS_SOURCE_CROSS_BUS"),
        ("906.001", "BUS_SOURCE_CROSS_BUS"),
        ("BOX.001;BOX.002", "BUS_SOURCE_FORMAT"),
        ("905.000;905.001", "BUS_SOURCE_FORMAT"),
    ],
)
@pytest.mark.parametrize("identity", ["BOX.003", "905.003"])
def test_invalid_parent_blocks_acceptance(block_contract, node, source, code, identity):
    result = validate(block_contract, node(identity, source))
    assert code in issue_codes(result.issues)
    assert not result.is_acceptable
    assert all(i.blocks_acceptance for i in graph_issues(result))


@pytest.mark.parametrize("identity", ["BOX.001", "TRACK.001", "905.001"])
def test_self_and_mixed_cycles(block_contract, node, identity):
    result = validate(block_contract, node(identity, identity))
    assert {"BUS_SOURCE_CYCLE", "BUS_SOURCE_UNREACHABLE"} <= issue_codes(result.issues)
    mixed = validate(
        block_contract,
        node("BOX.001", "905.001"),
        node("TRACK.001", "BOX.001"),
        node("905.001", "TRACK.001"),
    )
    assert len([i for i in mixed.issues if i.code == "BUS_SOURCE_CYCLE"]) == 3


@pytest.mark.parametrize("parent", ["BOX.001", "TRACK.001"])
@pytest.mark.parametrize("bus", ["906", ""])
def test_physical_source_membership_is_checked(block_contract, node, parent, bus):
    result = validate(
        block_contract, node(parent, "906.000" if bus else "", bus=bus), node("905.001", parent)
    )
    assert "BUS_SOURCE_CROSS_BUS" in issue_codes(result.issues)


@pytest.mark.parametrize("identity", ["BOX.001", "TRACK.001", "905.001"])
def test_duplicate_and_double_parent_never_selects_one(block_contract, node, identity):
    entries = (
        node(identity, handle="A"),
        node(identity, "BOX.002", handle="B"),
        node("BOX.002"),
        node("905.002", identity),
    )
    result = validate(block_contract, *entries)
    assert {
        "BUS_NODE_DUPLICATE",
        "BUS_SOURCE_DOUBLE_PARENT",
        "BUS_SOURCE_AMBIGUOUS",
        "BUS_SOURCE_UNREACHABLE",
    } <= issue_codes(result.issues)
    reverse = validate(block_contract, *reversed(entries))
    assert graph_issues(result) == graph_issues(reverse)


def test_duplicate_with_identical_parent_still_blocks(block_contract, node):
    result = validate(
        block_contract,
        node("BOX.001", handle="A"),
        node("BOX.001", handle="B"),
        node("905.001", "BOX.001"),
    )
    assert "BUS_NODE_DUPLICATE" in issue_codes(result.issues)
    assert "BUS_SOURCE_DOUBLE_PARENT" not in issue_codes(result.issues)


def test_duplicate_track_against_non_dali_insert(block_contract, node):
    result = validate(
        block_contract,
        node("TRACK.001", handle="A"),
        node("TRACK.001", "", bus="", handle="B", name="TRACK_48V"),
        node("905.001", "TRACK.001"),
    )
    assert "BUS_SOURCE_AMBIGUOUS" in issue_codes(result.issues)


@pytest.mark.parametrize(
    "roots,code",
    [
        (None, "BUS_ROOT_UNVERIFIED"),
        ((), "BUS_ROOT_NOT_FOUND"),
        (("906.000",), "BUS_ROOT_NOT_FOUND"),
    ],
)
def test_physical_graph_requires_project_root(block_contract, node, roots, code):
    result = validate(block_contract, node("BOX.001"), node("905.001", "BOX.001"), roots=roots)
    assert code in issue_codes(result.issues)
    assert len([i for i in result.issues if i.code == "BUS_SOURCE_UNREACHABLE"]) == 2


def test_missing_upstream_propagates_but_valid_branch_is_independent(block_contract, node):
    result = validate(
        block_contract, node("BOX.001", "BOX.999"), node("905.001", "BOX.001"), node("905.002")
    )
    assert {i.handle for i in result.issues if i.code == "BUS_SOURCE_UNREACHABLE"} == {
        "BOX.001",
        "905.001",
    }


def test_legacy_passive_address_is_not_used_or_migrated(block_contract, node):
    box = node("BOX.001")
    box = replace(
        box, raw_attributes=box.raw_attributes + (CadAttribute("BUS_POINT_ID", "905.010"),)
    )
    result = validate(block_contract, box, node("905.001", "905.010"))
    assert "PASSIVE_BUS_POINT_ID_FORBIDDEN" in issue_codes(result.issues)
    assert "BUS_SOURCE_NOT_FOUND" in issue_codes(result.issues)
    assert result.observations[0].read_payload.bus_point_id is None
    assert result.observations[0].read_payload.bus_id == "905"


@pytest.mark.parametrize("kind,source", [("DALI", "BOX.001"), ("RS485", ""), ("KNX", "905.000")])
def test_universal_outlet_remains_project_typed_addressable(block_contract, node, kind, source):
    outlet = node("905.001", source, name="CABLE_OUTLET_BUS")
    nodes = [outlet] + ([node("BOX.001")] if kind == "DALI" else [])
    result = validate(block_contract, *nodes, kinds={"905": kind})
    assert graph_issues(result) == []
    assert result.observations[0].read_payload.bus_type == kind
    assert result.observations[0].read_payload.bus_point_id == "905.001"


def test_universal_outlet_never_infers_type_from_source(block_contract, node):
    result = validate(block_contract, node("905.001", name="CABLE_OUTLET_BUS"))
    assert "BUS_TYPE_REQUIRED" in issue_codes(result.issues)
    assert result.observations[0].read_payload.bus_type is None


def test_rs485_cannot_be_dali_parent(block_contract, node):
    result = validate(
        block_contract, node("905.001", "", name="SENSOR_MSW"), node("BOX.001", "905.001")
    )
    assert "BUS_SOURCE_TYPE_CONFLICT" in issue_codes(result.issues)


def test_long_chain_does_not_recurse(block_contract, node):
    nodes = [node(f"BOX.{i:03d}", "905.000" if i == 0 else f"BOX.{i - 1:03d}") for i in range(999)]
    nodes += [
        node(f"905.{i:03d}", "BOX.998" if i == 1 else f"905.{i - 1:03d}") for i in range(1, 999)
    ]
    assert graph_issues(validate(block_contract, *reversed(nodes))) == []


def test_missing_physical_identity_is_blocking(block_contract, node):
    box = node("BOX.001")
    box = replace(
        box,
        raw_attributes=tuple(
            CadAttribute(a.tag, "") if a.tag == "BOX_ID" else a for a in box.raw_attributes
        ),
    )
    result = validate(block_contract, box)
    assert "BUS_PHYSICAL_ID_REQUIRED" in issue_codes(result.issues)
    assert not result.is_acceptable


def test_repeated_parent_attribute_is_not_accepted(block_contract, node):
    box = node("BOX.001")
    box = replace(box, raw_attributes=box.raw_attributes + (CadAttribute("BUS_SOURCE", "BOX.002"),))
    result = validate(block_contract, box, node("BOX.002"))
    assert not result.is_acceptable
    assert any("DUPLICATE" in i.code and i.field == "BUS_SOURCE" for i in result.issues)


def test_numeric_addressable_order_does_not_invent_edges(block_contract, node):
    result = validate(block_contract, node("905.009"), node("905.002", "905.009"))
    assert graph_issues(result) == []
    missing = validate(block_contract, node("905.001", ""), node("905.002", "905.001"))
    assert "BUS_SOURCE_REQUIRED" in issue_codes(missing.issues)
    assert len([i for i in missing.issues if i.code == "BUS_SOURCE_UNREACHABLE"]) == 2


def test_passive_bus_conflicting_with_project_type_is_rejected(block_contract, node):
    result = validate(block_contract, node("BOX.001"), kinds={"905": "KNX"})
    assert "BUS_TYPE_CONFLICT" in issue_codes(result.issues)
    assert not result.is_acceptable
