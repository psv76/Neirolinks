#!/usr/bin/env python3
"""Read-only cross-revision CAD contract compatibility inventory for D23.

Checks a narrow, known additive surface. This does not prove legacy runtime
or DWG acceptance and must not be treated as a release gate.
"""
import json
import subprocess
from pathlib import Path

RELATIVE = "Systems/NLP/resources/autocad/block_contract.json"


def main() -> None:
    old = json.loads(subprocess.check_output(["git", "show", f"origin/main:{RELATIVE}"], text=True))
    new = json.loads(Path(RELATIVE).read_text(encoding="utf-8"))
    assert old["contract_version"] == "3.0.0", "Unexpected production contract"
    assert new["contract_version"] == "3.2.0", "Unexpected candidate contract"
    before = set(old["approved_block_names"])
    after = set(new["approved_block_names"])
    assert len(before) == 71 and len(after) == 72
    assert after - before == {"CABLE_OUTLET_BUS"}
    assert not before - after, "Existing approved block was removed"
    old_profiles = set(old["attribute_profiles"])
    new_profiles = set(new["attribute_profiles"])
    assert new_profiles - old_profiles == {"BUS_OUTLET"}
    assert not old_profiles - new_profiles
    print("PASS: expected 3.0.0/71 -> 3.2.0/72 inventory delta")
    print("OPEN: attribute semantics, dynamic layer contract #255, existing DWG and runtime parity")


if __name__ == "__main__":
    main()
