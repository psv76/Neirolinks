from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from nl_project_2.buses import BusError, BusService
from nl_project_2.constructor import BlockingViolation, ConstructorService
from nl_project_2.persistence.database import DatabaseManager
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    instance_resource, passport_definition, passport_resource_definition,
    project, project_instance,
)


def _draft_module_in_test_database(database):
    # Import the candidate ONLY into this disposable fixture database.
    root = Path(__file__).resolve().parents[2]
    draft = json.loads((root / "docs/legacy/issue293/candidates/wbe2_i_rs485_iso_candidate.json").read_text(encoding="utf-8"))
    p = draft["passport"]
    project_id = database.test_project_id
    passport_id, module_id = new_id(), new_id()
    with database.engine.begin() as connection:
        release_id = connection.scalar(
            select(project.c.active_catalog_release_id).where(project.c.id == project_id)
        )
        connection.execute(passport_definition.insert().values(
            id=passport_id, catalog_release_id=release_id,
            passport_key=p["id"], version=1, name=p["name"],
            equipment_class=p["equipment_class"], functional_role=p["functional_role"],
            schema_version=1, source_reference="issue293-test-draft-only",
            content_sha256="0" * 64, lifecycle="ACTIVE",
        ))
        connection.execute(project_instance.insert().values(
            id=module_id, project_id=project_id, designation="WBE2.TEST",
            passport_definition_id=passport_id, product_definition_id=None,
            supply_scope="CUSTOMER", lifecycle="ACTIVE", parameters_json={},
        ))
        created = {}
        for resource in p["resources"]:
            definition_id, resource_id = new_id(), new_id()
            kind = resource["kind"]
            key = resource["resource_id"]
            connection.execute(passport_resource_definition.insert().values(
                id=definition_id, passport_definition_id=passport_id,
                resource_key=key, ordinal=0, resource_kind=kind,
                direction=resource["direction"], medium="INTERFACE",
                exclusive=True, display_json=resource,
            ))
            connection.execute(instance_resource.insert().values(
                id=resource_id, project_id=project_id, project_instance_id=module_id,
                resource_key=key, ordinal=0, passport_resource_definition_id=definition_id,
                resource_kind=kind, direction=resource["direction"], medium="INTERFACE",
                snapshot_json={"resource_definition": resource, "passport_resource": resource},
                active=True,
            ))
            created[key] = resource_id
    return created


def test_wbe2_rs485_requires_installation_to_source_903_and_reopens(database):
    project_id = database.test_project_id
    constructor = ConstructorService(database.engine)
    controller = constructor.create_instance(
        project_id=project_id, designation="WB85.TEST",
        passport_key="controller.wiren_board_8_5",
        product_key="product.wirenboard.wb8_4g_64g_ind",
        supply_scope="NEIROLINKS",
    )
    slots = sorted(
        (
            r for r in constructor.list_resources(project_id)
            if r["project_instance_id"] == controller.instance_id
            and r["resource_kind"] == "INTERNAL_EXPANSION_SLOT"
        ),
        key=lambda r: r["ordinal"],
    )
    assert len(slots) == 4
    module = _draft_module_in_test_database(database)
    service = BusService(database.engine)
    resource = module["RS485"]
    assert not next(
        r["source_available"]
        for r in service.list_rs485_resource_candidates(project_id)
        if r["id"] == resource
    )
    with pytest.raises(BusError, match="must be installed"):
        service.create_rs485_bus(
            project_id=project_id, designation="903",
            root_resource_id=resource, points=(),
        )
    installation = constructor.create_relation(
        project_id=project_id, relation_kind="MODULE_INSTALLATION",
        source_resource_id=slots[0]["id"],
        target_resource_id=module["HOST_SLOT_ATTACHMENT"],
    )
    assert next(
        r["source_available"]
        for r in service.list_rs485_resource_candidates(project_id)
        if r["id"] == resource
    )
    receipt = service.create_rs485_bus(
        project_id=project_id, designation="903",
        root_resource_id=resource, points=(),
    )
    assert service.get_bus(project_id, receipt.bus_id)["root_resource_id"] == resource

    path = database.path
    database.close()
    reopened = DatabaseManager().open_existing(path)
    try:
        buses = BusService(reopened.engine)
        assert buses.get_bus(project_id, receipt.bus_id)["designation"] == "903"
        assert not next(
            r["source_available"]
            for r in buses.list_rs485_resource_candidates(project_id)
            if r["id"] == resource
        )  # now occupied as source
        installed = ConstructorService(reopened.engine)
        assert any(
            r["relation_kind"] == "MODULE_INSTALLATION"
            for r in installed.list_relations(project_id)
        )
        with pytest.raises(BlockingViolation, match="корнем активной шины"):
            installed.delete_relation(
                project_id=project_id, relation_id=installation.relation_id
            )
        buses.delete_rs485_bus(project_id=project_id, bus_id=receipt.bus_id)
        installed.delete_relation(
            project_id=project_id, relation_id=installation.relation_id
        )
        assert not any(
            r["id"] == installation.relation_id
            for r in installed.list_relations(project_id)
        )
        assert not next(
            r["source_available"]
            for r in buses.list_rs485_resource_candidates(project_id)
            if r["id"] == resource
        )
    finally:
        reopened.close()
