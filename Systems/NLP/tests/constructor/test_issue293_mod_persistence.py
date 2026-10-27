from __future__ import annotations

import pytest

from nl_project_2.constructor import BlockingViolation, ConstructorService
from nl_project_2.persistence.database import DatabaseManager


def _instance(service, project, designation, passport, product):
    return service.create_instance(
        project_id=project,
        designation=designation,
        passport_key=passport,
        product_key=product,
        supply_scope="NEIROLINKS",
    )


def _parts(service, project):
    resources = service.list_resources(project)
    slots = [r for r in resources if r["resource_kind"] == "INTERNAL_EXPANSION_SLOT"]
    attachment = next(r for r in resources if r["resource_kind"] == "INTERNAL_EXPANSION_MODULE_ATTACHMENT")
    return slots, attachment


def test_wb85_mod_slot_installation_is_persisted_and_exclusive(database):
    p = database.test_project_id
    service = ConstructorService(database.engine)
    _instance(service, p, "WB.MAIN", "controller.wiren_board_8_5", "product.wirenboard.wb8_4g_64g_ind")
    _instance(service, p, "KNX.MOD1", "module.wirenboard.wbe2_i_knx", "product.wirenboard.wbe2_i_knx")
    slots, attachment = _parts(service, p)
    assert len(slots) == 4
    assert sorted(r["ordinal"] for r in slots) == [0, 1, 2, 3]
    receipt = service.create_relation(
        project_id=p,
        relation_kind="MODULE_INSTALLATION",
        source_resource_id=slots[0]["id"],
        target_resource_id=attachment["id"],
    )
    assert receipt.relation_id
    with pytest.raises(BlockingViolation):
        service.create_relation(
            project_id=p,
            relation_kind="MODULE_INSTALLATION",
            source_resource_id=slots[0]["id"],
            target_resource_id=attachment["id"],
        )
    assert any(r["id"] == receipt.relation_id for r in service.list_relations(p))
    path = database.path
    database.close()
    reopened = DatabaseManager().open_existing(path)
    try:
        assert any(r["id"] == receipt.relation_id for r in ConstructorService(reopened.engine).list_relations(p))
    finally:
        reopened.close()
