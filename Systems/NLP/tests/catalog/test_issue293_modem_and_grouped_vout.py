"""Issue 293: optional WBC2 modem and shared Vout on disposable SQLite."""
from pathlib import Path
import pytest
from nl_project_2.catalog.installer import CatalogInstaller
from nl_project_2.catalog.payload import load_payload
from nl_project_2.constructor import BlockingViolation, ConstructorService
from nl_project_2.persistence.database import DatabaseManager
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import project

CATALOG = Path(__file__).resolve().parents[2] / "resources/catalogs"

def setup(database):
    receipt=CatalogInstaller(database.engine).install(load_payload(CATALOG))
    pid=new_id()
    with database.engine.begin() as conn:
        conn.execute(project.insert().values(
            id=pid, project_code="ISSUE293-MODEM", name="Modem fixture",
            lifecycle="ACTIVE", card_fields_json={}, active_catalog_release_id=receipt.release_id))
    return pid,ConstructorService(database.engine)

def create(s,pid,name,passport,product):
    return s.create_instance(project_id=pid,designation=name,passport_key=passport,
                             product_key=product,supply_scope="NEIROLINKS")

def test_wb85_modem_separate_from_four_mod_slots_and_persists(database):
    pid,s=setup(database)
    host=create(s,pid,"WB85","controller.wiren_board_8_5_modular_cellular",
                "product.wirenboard.wb8_4g_64g_ind_modular_cellular")
    modem=create(s,pid,"WBC2","module.wirenboard.wbc2_4g","product.wirenboard.wbc2_4g")
    rr=s.list_resources(pid)
    hr=[r for r in rr if r["project_instance_id"]==host.instance_id]
    mr=[r for r in rr if r["project_instance_id"]==modem.instance_id]
    assert sum(r["resource_kind"]=="INTERNAL_EXPANSION_SLOT" for r in hr)==4
    assert not any(r["resource_kind"]=="CELLULAR_INTERFACE" for r in hr)
    assert not any(r["resource_key"]=="NANOSIM" for r in hr)
    slot=next(r for r in hr if r["resource_key"]=="INTERNAL_MODEM_SLOT")
    mod3=next(r for r in hr if r["resource_key"]=="INTERNAL_MODULE_SLOT" and r["ordinal"]==2)
    att=next(r for r in mr if r["resource_kind"]=="INTERNAL_MODEM_SLOT_ATTACHMENT")
    assert not s.preview_relation(project_id=pid,relation_kind="MODEM_INSTALLATION",
                                  source_resource_id=mod3["id"],target_resource_id=att["id"]).allowed
    rel=s.create_relation(project_id=pid,relation_kind="MODEM_INSTALLATION",
                          source_resource_id=slot["id"],target_resource_id=att["id"])
    with pytest.raises(BlockingViolation):
        s.create_relation(project_id=pid,relation_kind="MODEM_INSTALLATION",
                          source_resource_id=slot["id"],target_resource_id=att["id"])
    path=database.path;database.close()
    reopened=DatabaseManager().open_existing(path)
    try:
        assert any(r["id"]==rel.relation_id and r["relation_kind"]=="MODEM_INSTALLATION"
                   for r in ConstructorService(reopened.engine).list_relations(pid))
    finally:
        reopened.close()

def test_mge_shared_vout_preserves_two_physical_terminals(database):
    pid,s=setup(database)
    m=create(s,pid,"MGE","gateway.wirenboard.wb_mge_v3_shared_vout",
             "product.wirenboard.wb_mge_v3_shared_vout")
    vv=[r for r in s.list_resources(pid) if
        r["project_instance_id"]==m.instance_id and r["resource_key"]=="VOUT"]
    assert len(vv)==2 and len({r["id"] for r in vv})==2
    assert {r["group_key"] for r in vv}=={"VOUT_SHARED_SWITCH"}
    assert all(r["properties"]["independently_switchable"] is False for r in vv)
    assert all(r["properties"]["both_terminals_change_state_together"] is True for r in vv)

def test_old_passports_unchanged_and_product_variants_no_invented_sku():
    a=load_payload(CATALOG)
    ps={p["id"]:p for p in a.passports["passports"]}
    ts={p["id"]:p for p in a.products["products"]}
    assert (len(ps),len(ts))==(51,67)
    assert "CELLULAR_MODEM" in {r["resource_id"] for r in
        ps["controller.wiren_board_8_5"]["resources"]}
    assert "CELLULAR_MODEM" not in {r["resource_id"] for r in
        ps["controller.wiren_board_8_5_modular_cellular"]["resources"]}
    old=next(r for r in ps["gateway.wirenboard.wb_mge_v3"]["resources"] if r["resource_id"]=="VOUT")
    new=next(r for r in ps["gateway.wirenboard.wb_mge_v3_shared_vout"]["resources"] if r["resource_id"]=="VOUT")
    assert "groups" not in old and new["groups"]=={"VOUT_SHARED_SWITCH":["Vout-1","Vout-2"]}
    assert ts["product.wirenboard.wb8_4g_64g_ind_modular_cellular"]["article"] is None
    assert ts["product.wirenboard.wb8_4g_64g_ind_modular_cellular"]["official_source"]["reference_article"]=="WB8-4G-64G-IND"
