"""In-memory schema compatibility with pinned #227; not runtime integration."""

from __future__ import annotations

import json
import subprocess
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
OUTLET_SHA = "2c7dcebabbd37b4ac821d256978642b9cacef1f0"
BEFORE_SHA = "337fcb41c334204d008c98043e7a5dfc3130ce3f"
PATH = "Systems/NLP/resources/autocad/"


def historical(sha: str, name: str) -> dict:
    return json.loads(subprocess.check_output(["git", "show", f"{sha}:{PATH}{name}"], cwd=REPO))


def check() -> None:
    candidate = json.loads(
        (ROOT / "resources/autocad/block_contract.json").read_text(encoding="utf-8")
    )
    schema = json.loads(
        (ROOT / "resources/autocad/block_contract.schema.json").read_text(encoding="utf-8")
    )
    outlet = historical(OUTLET_SHA, "block_contract.json")
    prior_schema = historical(BEFORE_SHA, "block_contract.schema.json")
    assert candidate["contract_version"] == outlet["contract_version"] == "3.1.0"
    assert len(candidate["approved_block_names"]) == 71
    assert len(outlet["approved_block_names"]) == 72
    assert set(outlet["approved_block_names"]) - set(candidate["approved_block_names"]) == {
        "CABLE_OUTLET_BUS"
    }

    # Diagnostic composition in memory only: retain all #236 profiles, overlay
    # only #227 family metadata and its one additional exact block/profile.
    combined = deepcopy(candidate)
    combined["approved_block_names"].append("CABLE_OUTLET_BUS")
    combined["attribute_profiles"]["BUS_OUTLET"] = deepcopy(
        outlet["attribute_profiles"]["BUS_OUTLET"]
    )
    if "CABLE_OUTLET" not in combined["functional_groups"]["BUS"]["device_types"]:
        combined["functional_groups"]["BUS"]["device_types"].append("CABLE_OUTLET")
    by_names = {tuple(f["names"]): f for f in combined["block_families"]}
    for family in outlet["block_families"]:
        if family["names"] == ["CABLE_OUTLET_BUS"]:
            combined["block_families"].append(deepcopy(family))
        else:
            target = by_names[tuple(family["names"])]
            for key in ("bus_kind", "allowed_groups"):
                if key in family:
                    target[key] = deepcopy(family[key])

    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    validator.validate(candidate)
    old_errors = list(Draft202012Validator(prior_schema).iter_errors(combined))
    assert old_errors and all(error.validator == "additionalProperties" for error in old_errors), [
        (list(error.path), error.message) for error in old_errors
    ]
    validator.validate(combined)
    assert set(
        schema["properties"]["block_families"]["items"]["properties"]["allowed_groups"]["items"][
            "enum"
        ]
    ) == set(candidate["functional_groups"])
    assert "BUS_ID" not in combined["forbidden_attributes"]
    for name in ("EL_BOX", "TRACK", "TRACK_DALI"):
        assert combined["attribute_profiles"][name] == candidate["attribute_profiles"][name]
    assert "BUS_POINT_ID" in combined["attribute_profiles"]["BUS_OUTLET"]["definition_required"]
    assert "BUS_ID" not in combined["attribute_profiles"]["BUS_OUTLET"]["definition_required"]
    negative = 0
    for key, value in (
        ("bus_kind", "GUESS"),
        ("allowed_groups", ["UNKNOWN"]),
        ("allowed_groups", []),
        ("allowed_groups", ["BUS", "BUS"]),
    ):
        invalid = deepcopy(combined)
        invalid["block_families"][-1][key] = value
        assert not validator.is_valid(invalid)
        negative += 1
    print(
        "PASS schema-only: prior rejection reproduced; "
        f"in-memory 72 definitions; {negative} negatives"
    )
    print("UNCHANGED: actual candidate remains 71 definitions; no merged runtime or release")
    print(
        "OPEN: two distinct draft payloads use 3.1.0; "
        "pin SHA, integrate parser/owners/tests separately"
    )


if __name__ == "__main__":
    check()
