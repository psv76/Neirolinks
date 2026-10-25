"""Synthetic pure-validator diagnostic, not startup/sync/Windows acceptance.

Loads inspected source modules without package __init__ service imports.
No application startup, database, CAD adapter, migrations or writes.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
SRC = ROOT / "src/nl_project_2"
BASE = "8f566f7a1eddb2c7eb4242dd275cdd775ca79a89"


def isolated_modules():
    sys.dont_write_bytecode = True
    # Empty namespaces bypass __init__ exports of persistence/services. The
    # validator, DTOs, catalog and arithmetic themselves are the actual source.
    for name, path in (
        ("nl_project_2", SRC),
        ("nl_project_2.cables", SRC / "cables"),
        ("nl_project_2.cad_contract", SRC / "cad_contract"),
    ):
        assert name not in sys.modules, "Run this probe in a fresh interpreter"
        package = types.ModuleType(name)
        package.__path__ = [str(path)]
        sys.modules[name] = package
    result = {}
    for relative in (
        "runtime_resources.py",
        "cables/domain.py",
        "cad_contract/models.py",
        "cad_contract/catalog.py",
        "cad_contract/validator.py",
    ):
        path = SRC / relative
        original = subprocess.check_output(
            ["git", "show", f"{BASE}:Systems/NLP/src/nl_project_2/{relative}"], cwd=REPO
        ).decode("utf-8")
        assert path.read_text(encoding="utf-8") == original.replace("\r\n", "\n"), relative
        name = "nl_project_2." + relative[:-3].replace("/", ".")
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        result[relative] = module
    return result


def check() -> None:
    modules = isolated_modules()
    dto = modules["cad_contract/models.py"]
    catalog = modules["cad_contract/catalog.py"].load_contract(
        ROOT / "resources/autocad/block_contract.json"
    )
    validator = modules["cad_contract/validator.py"].CadContractValidator(catalog)

    def observe(name, layer, handle, values):
        rule = catalog.blocks[name]
        attrs = {tag: "" for tag in rule.required_definition_attributes}
        attrs.update(values)
        return dto.CadObservation.from_mapping(
            effective_name=name,
            layer=layer,
            handle=handle,
            raw_attributes=attrs,
            x=0,
            y=0,
            definition=dto.BlockDefinitionMetadata(tuple(attrs)),
        )

    cases = {
        "passive_box": observe(
            "EL_BOX_OUT_100x100",
            "BUS",
            "A1",
            {
                "BOX_ID": "BOX.023",
                "BUS_ID": "905",
                "BUS_SOURCE": "905.000",
            },
        ),
        "passive_track": observe(
            "TRACK_DALI",
            "TRACK_DALI",
            "A2",
            {
                "TRACK_ID": "TRACK.001",
                "CABLE_ID": "301",
                "MOUNT_WAY": "По потолку",
                "BUS_ID": "905",
                "BUS_SOURCE": "BOX.023",
            },
        ),
        "addressable_physical_source": observe(
            "LIGHT_TRACK_DALI_48V",
            "LIGHTING_230V",
            "A3",
            {
                "BUS_POINT_ID": "905.001",
                "BUS_SOURCE": "TRACK.001",
                "CABLE_SOURCE": "TRACK.001",
                "CABLE_ID": "301.01",
            },
        ),
        "addressable_root_control": observe(
            "LIGHT_TRACK_DALI_48V",
            "LIGHTING_230V",
            "A4",
            {
                "BUS_POINT_ID": "905.001",
                "BUS_SOURCE": "905.000",
            },
        ),
    }
    cases["passive_invalid_bus"] = observe(
        "EL_BOX_OUT_100x100",
        "BUS",
        "A5",
        {"BOX_ID": "BOX.023", "BUS_ID": "INVALID", "BUS_SOURCE": "905.000"},
    )
    cases["passive_cross_bus"] = observe(
        "EL_BOX_OUT_100x100",
        "BUS",
        "A6",
        {"BOX_ID": "BOX.023", "BUS_ID": "905", "BUS_SOURCE": "906.000"},
    )
    evidence = {}
    for label, observation in cases.items():
        result = validator.validate(dto.CadObservationBatch("synthetic-only", (observation,)))
        assert len(result.observations) == 1
        item = result.observations[0]
        payload = item.read_payload
        assert payload is not None
        evidence[label] = {
            "codes": sorted({issue.code for issue in result.issues}),
            "normalized_bus_id": item.normalized_attributes.get("BUS_ID"),
            "payload_bus_id": payload.bus_id,
            "payload_bus_type": payload.bus_type,
            "payload_bus_point_id": payload.bus_point_id,
            "payload_bus_source": payload.bus_source,
        }
    for label in ("passive_box", "passive_track"):
        assert evidence[label]["normalized_bus_id"] == "905"
        assert evidence[label]["payload_bus_id"] is None
        assert evidence[label]["payload_bus_type"] is None
    for label in ("passive_box", "passive_invalid_bus", "passive_cross_bus"):
        assert evidence[label]["codes"] == [], label
    assert "BUS_SOURCE_FORMAT" in evidence["addressable_physical_source"]["codes"]
    assert evidence["addressable_root_control"]["payload_bus_id"] == "905"
    assert evidence["addressable_root_control"]["payload_bus_type"] == "DALI"
    assert "BUS_SOURCE_FORMAT" not in evidence["addressable_root_control"]["codes"]
    assert not any(name.startswith(("sqlalchemy", "sqlite3", "pythoncom")) for name in sys.modules)
    print(
        json.dumps(
            {"status": "GAPS_REPRODUCED_NOT_ACCEPTANCE", "source_sha": BASE, "cases": evidence},
            indent=2,
        )
    )


if __name__ == "__main__":
    check()
