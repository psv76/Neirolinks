"""Issue #293: no silent loss of legacy models, prevent false resource topology."""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[2]
LEGACY=ROOT/"docs/legacy/issue293"


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def current():
    ps=read(ROOT/"resources/catalogs/equipment_passports.json")["passports"]
    products=read(ROOT/"resources/catalogs/products.json")["products"]
    return {x["id"]:x for x in ps},{x["id"]:x for x in products}


def test_all_legacy_skus_have_explicit_coverage_status_and_no_duplicate():
    legacy={x["article"] for x in read(LEGACY/"wb_equipment_catalog.json")["items"]}
    rows=read(LEGACY/"CURRENT_COVERAGE_2026-10-27.json")["rows"]
    assert len(rows)==len(legacy)==43
    assert {x["article"] for x in rows}==legacy
    assert all(x["status"] in {"READY","NEEDS_VERIFICATION","MISSING","DEPRECATED"} for x in rows)
    passports,products=current()
    for x in rows:
        if x["passport_id"] is not None:
            assert x["passport_id"] in passports
            assert x["product_id"] in products
            assert products[x["product_id"]]["passport_id"]==x["passport_id"]
        if x["status"]=="READY":
            assert x["source"]
            assert x["resources"]


def test_wbe2_zigbee_not_an_rs485_bus_root():
    passports,_=current()
    mod=passports["module.wirenboard.wbe2r_r_zigbee_sh"]
    types={x["resource_id"]:x["kind"] for x in mod["resources"]}
    assert types=={
        "HOST_SLOT_ATTACHMENT":"INTERNAL_EXPANSION_MODULE_ATTACHMENT",
        "ZIGBEE_SERIAL":"ZIGBEE_SERIAL_INTERFACE",
    }
    assert mod["compatibility"]["not_rs485_bus_root"] is True


def test_distinct_host_interfaces_are_not_mod_slots():
    passports,_=current()
    for id in ("module.wirenboard.wbio_di_wd_14",
               "module.wirenboard.wbio_di_hvd_8",
               "module.wirenboard.wbio_di_hvd_16"):
        p=passports[id]
        assert p["compatibility"]["mount"]=="WBIO_SIDE"
        assert not any(x["resource_id"]=="RS485" for x in p["resources"])
    modem=passports["module.wirenboard.wbc2_4g"]
    assert modem["compatibility"]["host_mount"]=="MODEM_SLOT"
    assert modem["compatibility"]["not_mod_slot"] is True


def test_shared_ds18b20_passport_has_four_cable_products():
    _,products=current()
    found=[x for x in products.values() if x["passport_id"]=="module.wirenboard.ds18b20_probe"]
    assert {x["parameters_used_by_project"]["cable_length_m"] for x in found}=={1,3,5,10}


def test_mao4_current_outputs_and_four_discrete_inputs():
    passports,_=current()
    model=passports["module.wirenboard.wb_mao4_20ma"]
    byid={r["resource_id"]:r for r in model["resources"]}
    assert byid["ANALOG_OUTPUT"]["quantity"]==4
    assert byid["INPUT"]["quantity"]==4
    assert byid["RS485"]["kind"]=="RS485_INTERFACE"


def test_legacy_unverified_revisions_not_misrepresented_as_ready():
    rows={x["article"]:x for x in read(LEGACY/"CURRENT_COVERAGE_2026-10-27.json")["rows"]}
    for article in ("WB-MRM2-mini v.3","WB-MDIO8","WB-LED"):
        assert rows[article]["status"]=="NEEDS_VERIFICATION"
