"""Issue #293: manufacturer-verified invariants for previously published WB passports.

READY means the passport's identity/resources were audited; it never implies
real-hardware or UI-workflow acceptance.
"""
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
COVERAGE = ROOT / "docs/legacy/issue293/CURRENT_COVERAGE_2026-10-27.json"


@pytest.fixture(scope="module")
def equipment():
    data = json.loads((ROOT / "resources/catalogs/equipment_passports.json").read_text(encoding="utf-8"))
    return {e["id"]: e for e in data["passports"]}


@pytest.fixture(scope="module")
def records():
    data = json.loads(COVERAGE.read_text(encoding="utf-8"))
    return {e["article"]: e for e in data["rows"]}


@pytest.mark.parametrize("article", [
    "WB-UPS v.3", "WBE2-I-KNX", "WB-MR6C v.2", "WB-DALI3", "WB-MCM8",
])
def test_audited_existing_passports_are_not_missing_or_unnamed(records, equipment, article):
    r = records[article]
    assert r["status"] == "READY"
    assert r["source"].startswith("https://")
    assert r["passport_id"] in equipment
    assert r["product_id"]


def resources(equipment, key):
    return {r["resource_id"]: r for r in equipment[key]["resources"]}


def test_ups_is_single_backed_output_with_a_real_modbus_port(equipment):
    r=resources(equipment,"power.wb_ups_v3")
    assert r["VIN"]["constraints"]["range_v"] == [10,27]
    assert r["VOUT"]["constraints"]["rated_power_w"] == 15
    assert r["VOUT"]["constraints"]["peak_power_w"] == 20
    assert r["RS485"]["constraints"]["protocol"] == "MODBUS_RTU"
    assert r["INTERNAL_BATTERY"]["constraints"]["rated_energy_wh"] == 15


def test_knx_expansion_is_never_an_rs485_interface(equipment):
    r=resources(equipment,"module.wirenboard.wbe2_i_knx")
    assert set(r) == {"HOST_SLOT_ATTACHMENT", "KNX_PORT"}
    assert r["HOST_SLOT_ATTACHMENT"]["kind"] == "INTERNAL_EXPANSION_MODULE_ATTACHMENT"
    assert r["KNX_PORT"]["kind"] == "KNX_BUS_PORT"
    assert r["KNX_PORT"]["constraints"]["isolation_kv"] == 4
    assert r["KNX_PORT"]["constraints"]["external_bus_power_required"] is True


def test_mr6c_v2_relays_com_groups_and_seven_inputs(equipment):
    r=resources(equipment,"controller.wb_mr6c_v2")
    assert r["RELAY_OUTPUT"]["quantity"] == 6
    assert r["INPUT"]["quantity"] == 7
    assert r["COM"]["quantity"] == 2
    assert r["COM"]["constraints"]["group_nominal_current_a_at_230vac"] == 30
    assert r["RELAY_OUTPUT"]["constraints"]["rated_current_a_at_230vac"] == 10
    assert r["RELAY_OUTPUT"]["constraints"]["maximum_inrush_current_a_20ms_at_230vac"] == 80


def test_dali3_ports_are_separate_from_upstream_modbus(equipment):
    r=resources(equipment,"gateway.wirenboard.wb_dali3")
    assert r["DALI_PORT"]["kind"] == "DALI_BUS_PORT"
    assert r["DALI_PORT"]["quantity"] == 3
    assert r["DALI_PORT"]["constraints"]["output_current_ma_by_label"] == {
        "DA1": 200, "DA2": 100, "DA3": 100
    }
    assert r["RS485"]["kind"] == "RS485_INTERFACE"
    assert r["INPUT"]["quantity"] == 7
    assert r["AC_DALI_POWER"]["constraints"]["nominal_voltage_v"] == 230
    assert r["DC_ELECTRONICS_POWER"]["constraints"]["range_v"] == [9,28]


def test_mcm8_all_eight_inputs_are_discrete_not_relays(equipment):
    r=resources(equipment,"module.wirenboard.wb_mcm8")
    assert {k for k in r} == {"ELECTRONICS_POWER","RS485","INPUT"}
    assert r["INPUT"]["kind"] == "DRY_CONTACT_INPUT"
    assert r["INPUT"]["quantity"] == 8
    assert r["RS485"]["kind"] == "RS485_INTERFACE"


@pytest.mark.parametrize("article",[
    "WB-LED", "WB-MRM2-mini v.3", "WB-MDIO8"
])
def test_blocked_hardware_is_not_implicitly_certified(records, article):
    r=records[article]
    assert r["status"] == "NEEDS_VERIFICATION"
    assert r["source"].startswith("https://")
    assert r["rationale"]


def test_all_legacy_skus_have_a_reviewed_state(records):
    assert len(records)==43
    assert sum(x["status"]=="READY" for x in records.values())==40
    assert sum(x["status"]=="NEEDS_VERIFICATION" for x in records.values())==3
    assert sum(x["status"]=="MISSING" for x in records.values())==0
