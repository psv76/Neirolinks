"""Static parity checks for candidate CAD contract 3.1.0 (#235).

This is intentionally *not* a runtime validator/AutoCAD/SQLite acceptance test.
For production enablement, implement the code gates in Issue #237.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAD = ROOT / "resources" / "autocad"
REFERENCE = ROOT / "docs" / "autocad" / "AUTOCAD_BLOCK_ATTRIBUTE_REFERENCE.md"
TOPOLOGY = ROOT / "docs" / "autocad" / "CURRENT_TOPOLOGY_ARCHITECTURE.md"

TARGETS = {
    "EL_BOX_OUT_100x100": "EL_BOX",
    "TRACK_230V": "TRACK",
    "TRACK_48V": "TRACK",
    "TRACK_DALI": "TRACK_DALI",
}


def exact_tags(document: str, name: str) -> list[str]:
    heading = f"#### `{name}`"
    start = document.find(heading)
    if start < 0:
        raise AssertionError(f"Exact-reference block missing: {name}")
    next_heading = document.find("\n#### ", start + len(heading))
    if next_heading < 0:
        next_heading = len(document)
    section = document[start:next_heading]
    match = re.search(
        r"\*\*Exact ATTDEF set:\*\*\s*```text\s*(.*?)\s*```",
        section,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"Exact-reference ATTDEF block missing: {name}")
    return match.group(1).splitlines()


def check() -> None:
    data = json.loads((CAD / "block_contract.json").read_text(encoding="utf-8"))
    schema = json.loads((CAD / "block_contract.schema.json").read_text(encoding="utf-8"))
    reference = REFERENCE.read_text(encoding="utf-8")
    topology = TOPOLOGY.read_text(encoding="utf-8")

    assert data["contract_version"] == "3.1.0", data["contract_version"]
    assert len(data["approved_block_names"]) == 71
    assert len(set(data["approved_block_names"])) == 71
    assert len(data["functional_groups"]) == 10

    # Catch forbidden-vs-declared contradictions before runtime work begins.
    forbidden = set(data["forbidden_attributes"])
    assert "BUS_ID" not in forbidden
    assert schema["additionalProperties"] is False
    assert set(data).issubset(schema["properties"])
    assert set(schema["required"]).issubset(data)
    assert "conditional_attributes" not in schema["required"]
    assert set(schema["properties"]["block_families"]["items"]["properties"]).issuperset(
        {key for family in data["block_families"] for key in family}
    )

    families = {}
    for family in data["block_families"]:
        for name in family["names"]:
            assert name not in families, name
            families[name] = family
    assert set(families) == set(data["approved_block_names"])
    for name, profile_name in TARGETS.items():
        profile = data["attribute_profiles"][profile_name]
        actual = profile["definition_required"]
        assert actual == profile["optional"], name
        assert len(actual) == len(set(actual)), name
        assert not set(actual) & forbidden, name
        assert actual == exact_tags(reference, name), name
        assert families[name]["attribute_profile"] == profile_name

    box = set(data["attribute_profiles"]["EL_BOX"]["definition_required"])
    dali = set(data["attribute_profiles"]["TRACK_DALI"]["definition_required"])
    for tags in (box, dali):
        assert "BUS_ID" in tags
        assert "BUS_POINT_ID" not in tags
    assert "CABLE_TRANSIT" in box
    assert "CABLE_TRANSIT" not in dali

    pattern = re.compile(data["track_id_pattern"])
    assert pattern.fullmatch("TRACK.001")
    assert not pattern.fullmatch("T.001")
    assert not pattern.fullmatch("TRACK.1")
    assert data["track_mount_way_values"] == ["накладной", "встроенный", "подвесной"]
    for name in TARGETS:
        if name.startswith("TRACK"):
            assert "TRACK_ID" in data["attribute_profiles"][TARGETS[name]]["definition_required"]
            assert "TRACK_MOUNT_WAY" in data["attribute_profiles"][TARGETS[name]]["definition_required"]

    g3 = data["functional_groups"]["LIGHTING_230V"]
    g4 = data["functional_groups"]["LIGHTING_LED"]
    assert "TRACK_DALI" in g3["device_types"] and "TRACK_DALI" in g4["device_types"]
    assert "TRACK_DALI" in g3["layers"] and "TRACK_DALI" in g4["layers"]
    assert g3["cable_prefix"] == "3"
    assert g4["cable_prefix"] == "4"
    assert "неоднозначн" in topology.lower() and "Требует внимания" in topology
    assert "301-1" in topology and "301@1" not in data["track_id_pattern"]

    print(
        "PASS static CAD candidate 3.1.0 parity: 71 definitions; "
        "4 exact block profiles; BUS_ID/3YY/4YY/TRANSIT invariants"
    )
    print("NOT TESTED: runtime parser/DB migration, AutoCAD COM or DWG acceptance")


if __name__ == "__main__":
    check()
