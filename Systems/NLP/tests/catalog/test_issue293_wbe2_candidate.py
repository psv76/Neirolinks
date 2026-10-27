import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CANDIDATE = ROOT / "docs/legacy/issue293/candidates/wbe2_i_rs485_iso_candidate.json"


def test_wbe2_rs485_iso_draft_has_separate_installation_and_bus_resources():
    candidate = json.loads(CANDIDATE.read_text(encoding="utf-8"))
    assert candidate["status"] == "DRAFT_NOT_RUNTIME_RELEASE"
    passport, product = candidate["passport"], candidate["product"]
    assert passport["id"] == product["passport_id"]
    assert passport["id"] == passport["passport_id"]
    assert product["id"] == product["product_id"]
    assert product["article"] == "WBE2-I-RS485-ISO"
    resources = passport["resources"]
    assert len(resources) == 2
    attachment, interface = resources
    assert attachment["kind"] == "INTERNAL_EXPANSION_MODULE_ATTACHMENT"
    assert attachment["direction"] == "IN"
    assert attachment["exclusive"] is True
    assert attachment["constraints"]["compatible_slot_labels"] == ["MOD1", "MOD2", "MOD3", "MOD4"]
    assert interface["kind"] == "RS485_INTERFACE"
    assert interface["resource_id"] == "RS485"
    assert interface["quantity"] == 1
    assert interface["constraints"]["isolated"] is True
    assert passport["compatibility"]["root_requires_valid_installation"] is True
    assert product["dimensions_mm"] == {"width": None, "height": None, "depth": None}


def test_wbe2_release_matches_verified_candidate_without_drift():
    candidate = json.loads(CANDIDATE.read_text(encoding="utf-8"))
    catalog = ROOT / "resources/catalogs"
    passports = json.loads((catalog / "equipment_passports.json").read_text(encoding="utf-8"))["passports"]
    products = json.loads((catalog / "products.json").read_text(encoding="utf-8"))["products"]
    assert [x for x in passports if x["id"] == candidate["passport"]["id"]] == [
        candidate["passport"]
    ]
    assert [x for x in products if x["id"] == candidate["product"]["id"]] == [
        candidate["product"]
    ]
