from __future__ import annotations

import pytest

from nl_project_2.buses import BusError, BusService
from nl_project_2.constructor import BlockingViolation, ConstructorService
from nl_project_2.persistence.database import DatabaseManager


def test_wbe2_rs485_install_bus903_reopen_and_safe_uninstall(database):
    project_id = database.test_project_id
    constructor = ConstructorService(database.engine)
    controller = constructor.create_instance(
        project_id=project_id,
        designation="WB85.TEST",
        passport_key="controller.wiren_board_8_5",
        product_key="product.wirenboard.wb8_4g_64g_ind",
        supply_scope="NEIROLINKS",
    )
    module = constructor.create_instance(
        project_id=project_id,
        designation="WBE2.MOD1",
        passport_key="module.wirenboard.wbe2_i_rs485_iso",
        product_key="product.wirenboard.wbe2_i_rs485_iso",
        supply_scope="NEIROLINKS",
    )
    resources = constructor.list_resources(project_id)
    slots = sorted(
        (
            resource for resource in resources
            if resource["project_instance_id"] == controller.instance_id
            and resource["resource_kind"] == "INTERNAL_EXPANSION_SLOT"
        ),
        key=lambda resource: resource["ordinal"],
    )
    module_resources = {
        resource["resource_kind"]: resource["id"]
        for resource in resources
        if resource["project_instance_id"] == module.instance_id
    }
    assert len(slots) == 4
    assert set(module_resources) == {
        "INTERNAL_EXPANSION_MODULE_ATTACHMENT", "RS485_INTERFACE"
    }
    rs485 = module_resources["RS485_INTERFACE"]
    attachment = module_resources["INTERNAL_EXPANSION_MODULE_ATTACHMENT"]
    buses = BusService(database.engine)
    def candidate():
        return next(
            row for row in buses.list_rs485_resource_candidates(project_id)
            if row["id"] == rs485
        )
    assert not candidate()["source_available"]
    with pytest.raises(BusError, match="must be installed"):
        buses.create_rs485_bus(
            project_id=project_id, designation="903",
            root_resource_id=rs485, points=()
        )
    installation = constructor.create_relation(
        project_id=project_id,
        relation_kind="MODULE_INSTALLATION",
        source_resource_id=slots[0]["id"],
        target_resource_id=attachment,
    )
    assert candidate()["source_available"]
    with pytest.raises(BlockingViolation):
        constructor.create_relation(
            project_id=project_id,
            relation_kind="MODULE_INSTALLATION",
            source_resource_id=slots[0]["id"],
            target_resource_id=attachment,
        )
    receipt = buses.create_rs485_bus(
        project_id=project_id, designation="903",
        root_resource_id=rs485, points=()
    )
    assert buses.get_bus(project_id, receipt.bus_id)["root_resource_id"] == rs485

    path = database.path
    database.close()
    reopened = DatabaseManager().open_existing(path)
    try:
        buses = BusService(reopened.engine)
        constructor = ConstructorService(reopened.engine)
        assert buses.get_bus(project_id, receipt.bus_id)["designation"] == "903"
        assert any(
            row["id"] == installation.relation_id
            for row in constructor.list_relations(project_id)
        )
        with pytest.raises(BlockingViolation, match="корнем активной шины"):
            constructor.delete_relation(
                project_id=project_id, relation_id=installation.relation_id
            )
        buses.delete_rs485_bus(project_id=project_id, bus_id=receipt.bus_id)
        constructor.delete_relation(
            project_id=project_id, relation_id=installation.relation_id
        )
        assert not next(
            row["source_available"]
            for row in buses.list_rs485_resource_candidates(project_id)
            if row["id"] == rs485
        )
    finally:
        reopened.close()
