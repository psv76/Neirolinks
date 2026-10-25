"""Focused regression smoke for NLP #237 D1: TRACK_DALI voltage-based group.

Does not prove passive DALI endpoint reconciliation or DWG compatibility.
"""

from __future__ import annotations

from types import SimpleNamespace

from nl_project_2.cad_contract import CadContractValidator, TaggedFact, issue_codes, load_contract


def observation(block: str, layer: str, cable_id: str, *, bus_id: str = ""):
    return SimpleNamespace(
        effective_name=block,
        handle="SMOKE-1",
        layer=layer,
        raw_attributes=(
            TaggedFact("CABLE_ID", cable_id),
            TaggedFact("BUS_ID", bus_id),
        ),
    )


def check() -> None:
    catalog = load_contract()
    validator = CadContractValidator(catalog)

    def evaluate(block: str, layer: str, cable_id: str, *, bus_id: str = ""):
        issues = []
        group = validator._function_group(  # focused contract-level check
            observation(block, layer, cable_id, bus_id=bus_id),
            catalog.block(block),
            {"CABLE_ID": cable_id, "BUS_ID": bus_id},
            issues,
        )
        return group, issue_codes(issues)

    assert evaluate("TRACK_DALI", "TRACK_DALI", "301", bus_id="905") == ("LIGHTING_230V", set())
    assert evaluate("TRACK_DALI", "TRACK_DALI", "401", bus_id="905") == ("LIGHTING_LED", set())
    assert evaluate("TRACK_DALI", "TRACK_DALI", "301.01", bus_id="905") == ("LIGHTING_230V", set())
    for bad in ("", "501", "foo", "301-1"):
        group, errors = evaluate("TRACK_DALI", "TRACK_DALI", bad, bus_id="905")
        assert group is None
        assert "TRACK_DALI_POWER_GROUP_UNRESOLVED" in errors

    # No change to the unambiguous layer policy of other physical blocks.
    assert evaluate("TRACK_230V", "TRACK_230V", "301") == ("LIGHTING_230V", set())
    assert evaluate("TRACK_48V", "TRACK_48V", "401") == ("LIGHTING_LED", set())
    group, issues = evaluate("TRACK_DALI", "TRACK_230V", "301", bus_id="905")
    # TRACK_230V layer still maps only to the 3YY context; this must not
    # cause a cross-family inference from DALI membership.
    assert group == "LIGHTING_230V" and not issues

    print("PASS TRACK_DALI 3YY/4YY feeder selection without changing other blocks")
    print("NOT TESTED: complete CAD validator, DALI graph or DWG import")


if __name__ == "__main__":
    check()
