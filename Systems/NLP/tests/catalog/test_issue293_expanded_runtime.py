"""Real Constructor fixture acceptance for the additive WB catalog, isolated SQLite only."""
from pathlib import Path

from nl_project_2.catalog.payload import load_payload
from nl_project_2.catalog.installer import CatalogInstaller
from nl_project_2.constructor import ConstructorService
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import project


CATALOG = Path(__file__).resolve().parents[2] / "resources/catalogs"
PREDECESSOR = "nlp3.equipment.2026-10-27.wbe2-rs485-iso"


def create_test_project(database):
    release = CatalogInstaller(database.engine).install(load_payload(CATALOG))
    project_id = new_id()
    with database.engine.begin() as connection:
        connection.execute(project.insert().values(
            id=project_id, project_code="ISSUE293-EXPANDED", name="Issue 293 fixture",
            card_fields_json={}, active_catalog_release_id=release.release_id,
            lifecycle="ACTIVE",
        ))
    return project_id


def test_all_new_products_create_complete_disposable_instances(database):
    project_id = create_test_project(database)
    payload = load_payload(CATALOG)
    delta = payload.manifest["additive_predecessors"][PREDECESSOR]
    products = {p["id"]: p for p in payload.products["products"]}
    instance_service = ConstructorService(database.engine)
    installed = []
    for index, key in enumerate(delta["products"]):
        product = products[key]
        receipt = instance_service.create_instance(
            project_id=project_id,
            designation=f"ISSUE293-{index:02d}",
            passport_key=product["passport_id"],
            product_key=key,
            supply_scope="NEIROLINKS",
        )
        installed.append(receipt.instance_id)
    all_instances = instance_service.list_instances(project_id)
    all_resources = instance_service.list_resources(project_id)
    assert len(installed) == len(delta["products"]) == 32
    assert {row["id"] for row in all_instances} >= set(installed)
    assert {row["project_instance_id"] for row in all_resources} >= set(installed)


def test_wb85_zigbee_installation_has_no_rs485_bus_resource(database):
    project_id = create_test_project(database)
    service = ConstructorService(database.engine)
    controller = service.create_instance(
        project_id=project_id,
        designation="WB8.5-TEST",
        passport_key="controller.wiren_board_8_5",
        product_key="product.wirenboard.wb8_4g_64g_ind",
        supply_scope="NEIROLINKS",
    )
    radio = service.create_instance(
        project_id=project_id,
        designation="ZB-TEST",
        passport_key="module.wirenboard.wbe2r_r_zigbee_sh",
        product_key="product.wirenboard.wbe2r_r_zigbee_sh",
        supply_scope="NEIROLINKS",
    )
    resources = service.list_resources(project_id)
    slot = next(r for r in resources if r["project_instance_id"] == controller.instance_id
                and r["resource_kind"] == "INTERNAL_EXPANSION_SLOT" and r["ordinal"] == 2)
    attachment = next(r for r in resources if r["project_instance_id"] == radio.instance_id
                      and r["resource_kind"] == "INTERNAL_EXPANSION_MODULE_ATTACHMENT")
    service.create_relation(
        project_id=project_id,
        relation_kind="MODULE_INSTALLATION",
        source_resource_id=slot["id"],
        target_resource_id=attachment["id"],
    )
    assert any(r["relation_kind"] == "MODULE_INSTALLATION"
               for r in service.list_relations(project_id))
    assert not any(r["resource_kind"] == "RS485_INTERFACE"
                   for r in resources if r["project_instance_id"] == radio.instance_id)
