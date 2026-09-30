from __future__ import annotations

import json
from pathlib import Path

import pytest

from nl_project_2.cad_contract import ContractCatalogError, default_contract_path, load_contract


def test_machine_contract_has_exact_approved_shape(block_contract):
    assert block_contract.contract_version == "3.0.0"
    assert set(block_contract.blocks) == set(block_contract.approved_block_names)
    assert len(block_contract.functional_groups) == 10
    assert set(block_contract.source_documents) == {
        "01_CURRENT_TOPOLOGY_ARCHITECTURE_2026-08-30.md",
        "02_AUTOCAD_BLOCK_ATTRIBUTE_REFERENCE_2026-08-30.md",
    }
    assert {
        "DALI_GROUP",
        "ROOM_NAME",
        "SOCKET_ETHERNET",
        "FRAME_5",
        "EL_BOX_OUT_100x100",
        "WB_MRM2_MINI",
    } <= set(block_contract.blocks)
    assert block_contract.block("SOCKET_1_ETH") is None
    assert "LENGTH" in block_contract.block("LIGHT_LED").optional_attributes
    assert "LENGTH" not in block_contract.block("SOCKET_IN").optional_attributes
    assert {"MOUNT_WAY", "GOFRA_TYPE", "GOFRA_COLOR", "GOFRA_ID"} <= set(
        block_contract.block("SOCKET_IN").optional_attributes
    )
    assert "LED_TYPE" in block_contract.block("LIGHT_LED").required_definition_attributes
    assert not {"OUT_1", "OUT_2", "OUT_3", "OUT_4", "OUT_5"} & set(
        block_contract.block("EL_BOX_OUT_100x100").required_definition_attributes
    )
    assert {"COM1", "COM2", "K1", "K2", "IN_1", "IN_2"} <= set(
        block_contract.block("WB_MRM2_MINI").optional_attributes
    )
    assert {"W1", "W2"} <= set(block_contract.block("WB_M1W2").optional_attributes)


def test_every_physical_name_has_device_type_profile_and_group(block_contract):
    for rule in block_contract.blocks.values():
        if rule.block_class == "LOGICAL":
            assert rule.device_type is None
            continue
        assert rule.device_type
        assert rule.attribute_profile
        assert rule.required_definition_attributes
        assert rule.allowed_groups


def test_contract_directory_contains_no_graphical_cad_library():
    directory = default_contract_path().parent
    assert {path.suffix.casefold() for path in directory.iterdir()} <= {".json", ".md"}
    assert not any(
        path.suffix.casefold() in {".dwg", ".dxf", ".dwt", ".dws"} for path in directory.rglob("*")
    )


def test_schema_and_payload_are_json_objects():
    contract_path = default_contract_path()
    schema_path = contract_path.with_name("block_contract.schema.json")
    assert isinstance(json.loads(contract_path.read_text(encoding="utf-8")), dict)
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema["additionalProperties"] is False
    assert "block_families" in schema["required"]
    assert "approved_block_names" in schema["required"]


def test_loader_rejects_duplicate_or_incomplete_catalog(tmp_path: Path):
    data = json.loads(default_contract_path().read_text(encoding="utf-8"))
    data["block_families"][1]["names"].append("FRAME_1")
    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ContractCatalogError, match="duplicate block name"):
        load_contract(broken)


def test_loader_rejects_family_set_drift_without_magic_count(tmp_path: Path):
    data = json.loads(default_contract_path().read_text(encoding="utf-8"))
    data["approved_block_names"].remove("WB_MRM2_MINI")
    broken = tmp_path / "broken-set.json"
    broken.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ContractCatalogError, match="approved_block_names"):
        load_contract(broken)
