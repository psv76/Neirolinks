#!/usr/bin/env python3
"""Report, without modifying runtime, the approved #255 layer release blockers."""
from __future__ import annotations

import json
from pathlib import Path

CONTRACT = Path(__file__).resolve().parents[1] / "resources/autocad/block_contract.json"


def main() -> None:
    c = json.loads(CONTRACT.read_text(encoding="utf-8"))
    groups = c["functional_groups"]
    assert c["contract_version"] == "3.2.0", "Unexpected candidate: review #255 again"
    assert "HEATING" in groups and "VENTILATION" in groups, "HVAC migration status changed"
    assert "HVAC" not in groups, "HVAC candidate status changed: verify actual implementation"
    assert groups["AV"]["layers"] == ["AV"], "AV layer model changed: verify against #255"
    catalog = (
        Path(__file__).resolve().parents[1]
        / "src/nl_project_2/cad_contract/catalog.py"
    ).read_text(encoding="utf-8")
    assert "if layer in rule.layers" in catalog, "Layer resolution changed; re-audit #255"
    print("VERIFIED: candidate still has explicit legacy layer allow-lists")
    print("BLOCKED: Issue #255 dynamic layers/HVAC/AV/scan gate NOT IMPLEMENTED")
    print("This observation is NOT a release acceptance.")


if __name__ == "__main__":
    main()
