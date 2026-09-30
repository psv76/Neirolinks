from __future__ import annotations

import pytest
from sqlalchemy import select, text

from nl_project_2.catalog.installer import CatalogInstaller
from nl_project_2.catalog.payload import load_packaged_payload
from nl_project_2.field_model import FieldModelError, RouteFacts, TopologyPersistenceService
from nl_project_2.persistence.database import DatabaseManager
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    building,
    cable_line,
    conduit,
    control_key_input_assignment,
    field_device,
    instance_resource,
    passport_resource_definition,
    product_definition,
    project,
    project_instance,
    room,
)


def _seed(database) -> dict[str, str]:
    release = CatalogInstaller(database.engine).install(load_packaged_payload())
    ids = {name: new_id() for name in ("project", "building", "room", "line", "device1", "device2")}
    with database.engine.begin() as connection:
        product = connection.execute(
            select(product_definition).where(
                product_definition.c.catalog_release_id == release.release_id,
                product_definition.c.product_key == "product.wirenboard.wb_mcm8",
            )
        ).mappings().first()
        resource = connection.execute(
            select(passport_resource_definition).where(
                passport_resource_definition.c.passport_definition_id
                == product["passport_definition_id"],
                passport_resource_definition.c.resource_kind == "DRY_CONTACT_INPUT",
                passport_resource_definition.c.direction.in_(("IN", "BIDIRECTIONAL")),
            )
        ).mappings().first()
        assert product is not None and resource is not None
        ids.update(product=product["id"], passport=product["passport_definition_id"])
        ids.update(instance=new_id(), input1=new_id(), input2=new_id(), input3=new_id())
        connection.execute(
            project.insert().values(
                id=ids["project"],
                project_code="P0-TOPOLOGY",
                name="P0 topology",
                card_fields_json={},
                active_catalog_release_id=release.release_id,
            )
        )
        connection.execute(
            building.insert().values(
                id=ids["building"],
                project_id=ids["project"],
                code="B1",
                normalized_code="b1",
                name="Building",
                display_order=0,
            )
        )
        connection.execute(
            room.insert().values(
                id=ids["room"],
                project_id=ids["project"],
                building_id=ids["building"],
                name="Room",
                normalized_name="room",
            )
        )
        connection.execute(
            cable_line.insert().values(
                id=ids["line"],
                project_id=ids["project"],
                designation="L.1",
                system_kind="POWER",
                cable_facts_json={},
            )
        )
        connection.execute(
            field_device.insert(),
            [
                {
                    "id": ids["device1"],
                    "project_id": ids["project"],
                    "block_kind": "WB_MRM2_MINI",
                    "room_id": ids["room"],
                    "normalized_fields_json": {},
                },
                {
                    "id": ids["device2"],
                    "project_id": ids["project"],
                    "block_kind": "WB_MRM2_MINI",
                    "room_id": ids["room"],
                    "normalized_fields_json": {},
                },
            ],
        )
        connection.execute(
            project_instance.insert().values(
                id=ids["instance"],
                project_id=ids["project"],
                designation="CONTROLLER.1",
                passport_definition_id=ids["passport"],
                product_definition_id=ids["product"],
                parameters_json={},
            )
        )
        for ordinal, input_id in enumerate(
            (ids["input1"], ids["input2"], ids["input3"])
        ):
            connection.execute(
                instance_resource.insert().values(
                    id=input_id,
                    project_id=ids["project"],
                    project_instance_id=ids["instance"],
                    resource_key=f"TEST_INPUT_{ordinal}",
                    ordinal=ordinal,
                    passport_resource_definition_id=resource["id"],
                    resource_kind=resource["resource_kind"],
                    direction="IN",
                    medium=resource["medium"],
                    snapshot_json={},
                )
            )
    return ids


def test_shared_point_branching_segment_routes_ports_and_product_roundtrip(database) -> None:
    ids = _seed(database)
    service = TopologyPersistenceService(database.engine)
    source = service.create_topology_point(
        project_id=ids["project"],
        cable_line_id=ids["line"],
        point_kind="INTERNAL_SOURCE",
        logical_identity="L.1:SOURCE",
    )
    shared = service.create_topology_point(
        project_id=ids["project"],
        cable_line_id=ids["line"],
        point_kind="INSTALLATION_GROUP",
        logical_identity="GROUP.1",
    )
    branch = service.create_topology_point(
        project_id=ids["project"],
        cable_line_id=ids["line"],
        point_kind="DEVICE_POINT",
        logical_identity="L.1:BRANCH",
    )
    service.add_field_device_to_point(
        project_id=ids["project"], cable_point_id=shared, field_device_id=ids["device1"]
    )
    service.add_field_device_to_point(
        project_id=ids["project"], cable_point_id=shared, field_device_id=ids["device2"]
    )
    source_endpoint = service.endpoint_for_point(
        project_id=ids["project"], cable_line_id=ids["line"], cable_point_id=source
    )
    shared_endpoint = service.endpoint_for_point(
        project_id=ids["project"], cable_line_id=ids["line"], cable_point_id=shared
    )
    branch_endpoint = service.endpoint_for_point(
        project_id=ids["project"], cable_line_id=ids["line"], cable_point_id=branch
    )
    first_segment = service.create_segment(
        project_id=ids["project"],
        cable_line_id=ids["line"],
        source_endpoint_id=source_endpoint,
        target_endpoint_id=shared_endpoint,
        route=RouteFacts("По полу", "ПВХ 16", "серый"),
    )
    second_segment = service.create_segment(
        project_id=ids["project"],
        cable_line_id=ids["line"],
        source_endpoint_id=shared_endpoint,
        target_endpoint_id=branch_endpoint,
        route=RouteFacts("По потолку", "ПНД 20", "чёрный"),
    )
    with pytest.raises(FieldModelError, match="Duplicate physical edge"):
        service.create_segment(
            project_id=ids["project"],
            cable_line_id=ids["line"],
            source_endpoint_id=source_endpoint,
            target_endpoint_id=shared_endpoint,
        )
    conduit_ids = (new_id(), new_id())
    with database.engine.begin() as connection:
        connection.execute(
            conduit.insert(),
            [
                {
                    "id": conduit_ids[0],
                    "project_id": ids["project"],
                    "designation": "ГФ001.ПВХ16",
                    "conduit_number": 1,
                    "conduit_type": "ПВХ16",
                },
                {
                    "id": conduit_ids[1],
                    "project_id": ids["project"],
                    "designation": "ГФ002.ПНД20",
                    "conduit_number": 2,
                    "conduit_type": "ПНД20",
                },
            ],
        )
    service.assign_segment_conduit(
        project_id=ids["project"], cable_segment_id=first_segment, conduit_id=conduit_ids[0]
    )
    service.assign_segment_conduit(
        project_id=ids["project"], cable_segment_id=second_segment, conduit_id=conduit_ids[1]
    )
    port = service.create_field_port(
        project_id=ids["project"], field_device_id=ids["device1"], port_tag="K1"
    )
    service.assign_line_to_field_port(
        project_id=ids["project"],
        cable_line_id=ids["line"],
        field_port_id=port,
        assignment_role="CONTROL_OUTPUT",
    )
    service.select_field_device_product(
        project_id=ids["project"],
        field_device_id=ids["device1"],
        product_definition_id=ids["product"],
        configuration_schema_version=1,
        configuration={"channels": {"K1": "LIGHT.1"}},
        supply_scope="NEIROLINKS",
    )

    snapshot = service.topology_snapshot(ids["project"])
    assert len(snapshot["memberships"]) == 2
    assert {row["mount_way"] for row in snapshot["segments"]} == {"По полу", "По потолку"}
    assert {row["cable_segment_id"] for row in snapshot["segment_conduits"]} == {
        first_segment,
        second_segment,
    }
    assert snapshot["ports"][0]["port_kind"] == "RELAY_OUTPUT"
    assert snapshot["field_product_selections"][0]["configuration_json"] == {
        "channels": {"K1": "LIGHT.1"}
    }


def test_control_key_input_exclusivity_user_reserve_and_led_enum(database) -> None:
    ids = _seed(database)
    service = TopologyPersistenceService(database.engine)
    key1 = service.create_control_key(
        project_id=ids["project"],
        field_device_id=ids["device1"],
        key_tag="KEY_1",
        target_kind="CABLE_LINE",
        target_id=ids["line"],
        target_text="Light",
    )
    key2 = service.create_control_key(
        project_id=ids["project"],
        field_device_id=ids["device1"],
        key_tag="KEY_2",
        target_kind="CABLE_LINE",
        target_id=ids["line"],
        target_text="Light",
    )
    service.assign_control_key_input(
        project_id=ids["project"], field_control_key_id=key1, input_resource_id=ids["input1"]
    )
    with pytest.raises(FieldModelError, match="already assigned"):
        service.assign_control_key_input(
            project_id=ids["project"],
            field_control_key_id=key2,
            input_resource_id=ids["input1"],
        )
    service.assign_control_key_input(
        project_id=ids["project"], field_control_key_id=key2, input_resource_id=ids["input2"]
    )
    service.set_user_reserve(
        project_id=ids["project"],
        target_kind="PROJECT_INSTANCE",
        target_id=ids["instance"],
        actor="test",
    )
    service.set_user_reserve(
        project_id=ids["project"],
        target_kind="INSTANCE_RESOURCE",
        target_id=ids["input3"],
        actor="test",
    )
    service.set_led_sync_fact(
        project_id=ids["project"],
        cable_line_id=ids["line"],
        led_type="RGB",
        origin="DWG",
        baseline={"LED_TYPE": "RGB"},
        sync_state="IN_SYNC",
    )
    with pytest.raises(FieldModelError, match="LED_TYPE"):
        service.set_led_sync_fact(
            project_id=ids["project"],
            cable_line_id=ids["line"],
            led_type="MIX",
            origin="DWG",
            baseline=None,
            sync_state="UNCONFIRMED",
        )
    with database.engine.connect() as connection:
        assignment_count = connection.scalar(
            select(text("count(*)")).select_from(control_key_input_assignment)
        )
        assert assignment_count == 2
        assert connection.execute(text("PRAGMA integrity_check")).scalar_one() == "ok"
        assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
    snapshot = service.topology_snapshot(ids["project"])
    assert {row["target_kind"] for row in snapshot["user_reserves"]} == {
        "PROJECT_INSTANCE",
        "INSTANCE_RESOURCE",
    }
    path = database.path
    database.close()
    reopened = DatabaseManager().open_existing(path)
    reopened.close()
