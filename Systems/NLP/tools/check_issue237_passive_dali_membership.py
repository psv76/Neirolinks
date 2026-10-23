"""Focused #237 D1 smoke: passive DALI membership in pure CAD validator.

Only checks typed BUS_ID and field-level validation, not graph resolution,
owner-aware Project sync, legacy migration, real DWG or Windows/AutoCAD.
"""

from __future__ import annotations

from pathlib import Path

from nl_project_2.cad_contract import (
    BlockDefinitionMetadata,
    CadContractValidator,
    CadObservation,
    CadObservationBatch,
    issue_codes,
    load_contract,
)

ROOT = Path(__file__).resolve().parents[1]
CATALOG = load_contract(ROOT / "resources/autocad/block_contract.json")
VALIDATOR = CadContractValidator(CATALOG)


def validate(name: str, layer: str, values: dict[str, str]):
    rule = CATALOG.block(name)
    assert rule is not None
    attrs = {tag: "" for tag in rule.required_definition_attributes}
    attrs.update(values)
    obs = CadObservation.from_mapping(
        effective_name=name,
        layer=layer,
        handle="D1",
        x=0,
        y=0,
        raw_attributes=attrs,
        definition=BlockDefinitionMetadata(tuple(attrs)),
    )
    result = VALIDATOR.validate(CadObservationBatch("synthetic-only", (obs,)))
    assert len(result.observations) == 1
    payload = result.observations[0].read_payload
    assert payload is not None
    return payload, issue_codes(result.issues)


def check() -> None:
    box = "EL_BOX_OUT_100x100"
    good, codes = validate(
        box, "BUS", {"BOX_ID": "BOX.023", "BUS_ID": "905", "BUS_SOURCE": "905.000"}
    )
    assert good.box_id == "BOX.023"
    assert (good.bus_id, good.bus_type, good.bus_point_id) == ("905", "DALI", None)
    assert not (codes & {
        "BUS_ID_FORMAT", "BUS_ID_REQUIRED", "BUS_SOURCE_REQUIRED",
        "BUS_SOURCE_FORMAT", "BUS_SOURCE_CROSS_BUS",
    }), codes

    track, codes = validate(
        "TRACK_DALI", "TRACK_DALI",
        {"TRACK_ID": "TRACK.001", "BUS_ID": "905", "BUS_SOURCE": "BOX.023"},
    )
    assert (track.bus_id, track.bus_type, track.bus_point_id) == ("905", "DALI", None)
    # The independent 3YY/4YY group fix is in stacked #238, not this PR.
    assert "LAYER_FUNCTION_GROUP_MISMATCH" in codes

    invalid, codes = validate(
        box, "BUS", {"BOX_ID": "BOX.023", "BUS_ID": "INVALID", "BUS_SOURCE": "905.000"}
    )
    assert "BUS_ID_FORMAT" in codes
    assert (invalid.bus_id, invalid.bus_type) == (None, None)

    _, codes = validate(
        box, "BUS", {"BOX_ID": "BOX.023", "BUS_ID": "905", "BUS_SOURCE": "906.000"}
    )
    assert "BUS_SOURCE_CROSS_BUS" in codes

    _, codes = validate(
        box, "BUS", {"BOX_ID": "BOX.023", "BUS_ID": "905", "BUS_SOURCE": "not-an-id"}
    )
    assert "BUS_SOURCE_FORMAT" in codes

    _, codes = validate(box, "BUS", {"BOX_ID": "BOX.023", "BUS_SOURCE": "905.000"})
    assert "BUS_ID_REQUIRED" in codes

    _, codes = validate(box, "BUS", {"BOX_ID": "BOX.023", "BUS_ID": "905"})
    assert "BUS_SOURCE_REQUIRED" in codes

    unlinked, codes = validate(box, "BUS", {"BOX_ID": "BOX.023"})
    assert unlinked.bus_id is None
    assert not (codes & {"BUS_ID_REQUIRED", "BUS_SOURCE_REQUIRED"})

    addressable, codes = validate(
        "LIGHT_OUT_DALI_230V", "LIGHTING_230V",
        {"BUS_POINT_ID": "905.001", "BUS_SOURCE": "905.000"},
    )
    assert (addressable.bus_id, addressable.bus_point_id) == ("905", "905.001")
    assert "BUS_ID_FORMAT" not in codes

    bus_outlet, codes = validate(
        "CABLE_OUTLET_BUS", "BUS",
        {"BUS_POINT_ID": "905.007", "BUS_SOURCE": "905.000"},
    )
    assert bus_outlet.bus_point_id == "905.007"
    assert bus_outlet.bus_id == "905"
    assert "BUS_ID_FORMAT" not in codes

    rs485, codes = validate("SENSOR_MSW", "BUS", {"BUS_POINT_ID": "902.001"})
    assert (rs485.bus_id, rs485.bus_type) == ("902", "RS485")
    assert not (codes & {"BUS_ID_FORMAT", "BUS_SOURCE_REQUIRED"})

    print("PASS 11 focused passive DALI/other bus typed membership and format cases")
    print("NOT TESTED: BOX/TRACK graph, #238 voltage, owner sync, legacy, Windows/DWG")


if __name__ == "__main__":
    check()
