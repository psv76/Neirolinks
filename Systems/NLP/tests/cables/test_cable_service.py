from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import func, select

from nl_project_2.cables import CableError, CableService, RouteMethod
from nl_project_2.objects.models import ProjectCard, ProjectSettings
from nl_project_2.objects.service import ObjectService
from nl_project_2.persistence.database import DatabaseManager
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    cable_line,
    cable_line_product_selection,
    cable_point,
    cable_point_field_device,
    cable_segment,
    cable_topology_endpoint,
    conduit,
    conduit_segment_assignment,
    field_device,
    passport_definition,
    product_definition,
)
from nl_project_2.persistence.uow import UnitOfWork


def _project(database):
    objects = ObjectService(database.engine)
    project_id = objects.create_project(ProjectCard(name="Cable", project_code="CB-1"))
    building_id = objects.add_building(project_id, "Building")
    first_room = objects.add_room(
        project_id=project_id,
        building_id=building_id,
        name="First",
        base_mark_mm=-250,
        height_m="2.8",
        marking_color="#FFFFFF",
    )
    second_room = objects.add_room(
        project_id=project_id,
        building_id=building_id,
        name="Second",
        base_mark_mm=-150,
        height_m="3.0",
        marking_color="#FFFFFF",
    )
    objects.save_settings(project_id, ProjectSettings(cable_reserve_at_board_m=Decimal("1.5")))
    return project_id, first_room, second_room


def _line_with_points(database, project_id, rooms, designation="101", *, line_id=None):
    line_id = line_id or new_id()
    with UnitOfWork(database.engine) as uow:
        existing_line = (
            uow.execute(select(cable_line).where(cable_line.c.id == line_id))
            .mappings()
            .one_or_none()
        )
        if existing_line is None:
            uow.execute(
                cable_line.insert().values(
                    id=line_id,
                    project_id=project_id,
                    designation=designation,
                    system_kind="POWER",
                    cable_facts_json={
                        "BOARD": "B.01",
                        "CABLE_TYPE": "NYM",
                    },
                )
            )
        point_ids = []
        for ordinal, (room_id, x, y) in enumerate(((rooms[0], 0, 0), (rooms[1], 1000, 2000))):
            device_id = new_id()
            point_id = new_id()
            point_ids.append(point_id)
            uow.execute(
                field_device.insert().values(
                    id=device_id,
                    project_id=project_id,
                    block_kind="SOCKET_IN",
                    room_id=room_id,
                    normalized_fields_json={"MOUNT_HEIGHT": "300"},
                )
            )
            uow.execute(
                cable_point.insert().values(
                    id=point_id,
                    project_id=project_id,
                    cable_line_id=line_id,
                    field_device_id=None,
                    point_kind="DEVICE_POINT",
                    ordinal=ordinal,
                    logical_identity=f"{line_id}:{ordinal}",
                    origin_kind="PROJECT",
                    migration_state="CONFIRMED",
                    location_json={"x": x, "y": y},
                )
            )
            uow.execute(
                cable_point_field_device.insert().values(
                    id=new_id(),
                    project_id=project_id,
                    cable_point_id=point_id,
                    field_device_id=device_id,
                )
            )
        endpoint_ids = []
        for point_id in point_ids:
            endpoint_id = new_id()
            endpoint_ids.append(endpoint_id)
            uow.execute(
                cable_topology_endpoint.insert().values(
                    id=endpoint_id,
                    project_id=project_id,
                    cable_line_id=line_id,
                    endpoint_kind="TOPOLOGY_POINT",
                    cable_point_id=point_id,
                )
            )
        is_av = existing_line is not None and existing_line["system_kind"] == "AV"
        uow.execute(
            cable_segment.insert().values(
                id=new_id(),
                project_id=project_id,
                cable_line_id=line_id,
                source_endpoint_id=endpoint_ids[0],
                target_endpoint_id=endpoint_ids[1],
                mount_way="В кабель-канале" if is_av else "По полу",
                gofra_type=None if is_av else "ПНД25",
                gofra_color=None if is_av else "Черный",
                origin_kind="PROJECT",
                migration_state="CONFIRMED",
            )
        )
        uow.commit()
    return line_id


def test_lengths_manual_priority_auto_conduit_and_reopen(database):
    project_id, *rooms = _project(database)
    line_id = _line_with_points(database, project_id, rooms)
    service = CableService(database.engine)
    result = service.calculate_and_save_length(
        project_id=project_id,
        cable_line_id=line_id,
        route_method=RouteMethod.FLOOR,
        additional_m="0.4",
    )
    assert result.automatic_m == Decimal("4.1")
    # A line label naming a board is not a physical board-owned source endpoint.
    assert result.effective_m == Decimal("4.5")
    with database.engine.connect() as connection:
        tube = connection.execute(select(conduit)).mappings().one()
    assert Decimal(tube["length_m_decimal"]) == Decimal("4.1")
    assert tube["path_json"]["origin"] == "AUTO_SEGMENT"

    manual = service.calculate_and_save_length(
        project_id=project_id,
        cable_line_id=line_id,
        route_method=RouteMethod.FLOOR,
        additional_m="99",
        manual_full_m="5",
    )
    assert manual.effective_m == Decimal("5")
    path = database.path
    database.close()
    reopened = DatabaseManager().open_existing(path)
    try:
        assert CableService(reopened.engine).effective_length(project_id, line_id).effective_m == 5
        with reopened.engine.connect() as connection:
            assert Decimal(connection.scalar(select(conduit.c.length_m_decimal))) == Decimal("4.1")
    finally:
        reopened.close()


def test_conduit_merge_user_empty_bulk_edit_and_rollback(database):
    project_id, *rooms = _project(database)
    service = CableService(database.engine)
    first = _line_with_points(database, project_id, rooms, "101")
    second = _line_with_points(database, project_id, rooms, "102")
    for line_id in (first, second):
        service.calculate_and_save_length(
            project_id=project_id,
            cable_line_id=line_id,
            route_method=RouteMethod.FLOOR,
        )
    with database.engine.connect() as connection:
        assignments = list(
            connection.execute(
                select(
                    conduit_segment_assignment.c.conduit_id,
                    cable_segment.c.cable_line_id,
                ).join(
                    cable_segment,
                    cable_segment.c.id == conduit_segment_assignment.c.cable_segment_id,
                )
            ).mappings()
        )
    first_tube = next(item["conduit_id"] for item in assignments if item["cable_line_id"] == first)
    service.move_line_to_conduit(
        project_id=project_id,
        cable_line_id=second,
        target_conduit_id=first_tube,
    )
    user_tube = service.create_empty_conduit(
        project_id=project_id,
        designation="050.PND32",
        conduit_type="ПНД32",
        length_m="12.5",
    )
    with database.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(conduit)) == 2
        assert (
            connection.scalar(
                select(func.count())
                .select_from(conduit_segment_assignment)
                .where(conduit_segment_assignment.c.conduit_id == first_tube)
            )
            == 2
        )
    route_rows = service.list_conduit_routes(project_id)
    shared_route = next(row for row in route_rows if row["id"] == first_tube)
    assert [row["designation"] for row in shared_route["lines"]] == ["101", "102"]
    assert shared_route["product_display"] == "Не выбран"
    service.bulk_edit_conduits(
        project_id=project_id,
        conduit_ids={first_tube, user_tube},
        conduit_type="ПНД32",
        diameter_mm="32",
    )
    service.bulk_edit_line_conduits(
        project_id=project_id,
        cable_line_ids={first, second},
        conduit_type="ПНД40",
        diameter_mm="40",
    )
    service.update_conduit_length(
        project_id=project_id,
        conduit_id=first_tube,
        length_m="18.75",
    )
    with database.engine.connect() as connection:
        assert {
            (row.conduit_type, row.diameter_mm_decimal)
            for row in connection.execute(select(conduit))
        } == {("ПНД40", "40"), ("ПНД32", "32")}
        assert Decimal(
            connection.scalar(select(conduit.c.length_m_decimal).where(conduit.c.id == first_tube))
        ) == Decimal("18.75")

    def fail():
        raise RuntimeError("injected")

    with pytest.raises(RuntimeError, match="injected"):
        service.bulk_edit_conduits(
            project_id=project_id,
            conduit_ids={first_tube, user_tube},
            conduit_type="ПВХ40",
            diameter_mm="40",
            failure_hook=fail,
        )
    with database.engine.connect() as connection:
        assert {row.conduit_type for row in connection.execute(select(conduit))} == {
            "ПНД40",
            "ПНД32",
        }


def test_route_edit_updates_shared_line_and_device_facts(database):
    project_id, *rooms = _project(database)
    service = CableService(database.engine)
    line_id = _line_with_points(database, project_id, rooms, "101")
    service.calculate_and_save_length(
        project_id=project_id,
        cable_line_id=line_id,
        route_method=RouteMethod.FLOOR,
    )
    with database.engine.connect() as connection:
        tube = connection.execute(select(conduit)).mappings().one()
    service.update_conduit_details(
        project_id=project_id,
        conduit_id=tube["id"],
        conduit_number=7,
        conduit_type="ПВХ20",
        color="Серый",
        length_m="8.5",
    )
    with database.engine.connect() as connection:
        updated = connection.execute(select(conduit)).mappings().one()
        segment_facts = connection.execute(
            select(cable_segment).where(cable_segment.c.cable_line_id == line_id)
        ).mappings().one()
        device_facts = list(
            connection.execute(select(field_device.c.normalized_fields_json)).scalars()
        )
    assert updated["designation"] == "007.PVH20"
    assert updated["conduit_number"] == 7
    assert updated["color"] == "Серый"
    assert Decimal(updated["length_m_decimal"]) == Decimal("8.5")
    assert segment_facts["gofra_type"] == "ПВХ20"
    assert segment_facts["gofra_color"] == "Серый"
    assert sum(row.get("GOFRA_ID") == "007.PVH20" for row in device_facts) == 1


def test_line_editor_contract_can_clear_optional_conduit(database):
    project_id, *rooms = _project(database)
    service = CableService(database.engine)
    line_id = _line_with_points(database, project_id, rooms, "101")
    service.calculate_and_save_length(
        project_id=project_id,
        cable_line_id=line_id,
        route_method=RouteMethod.FLOOR,
    )
    service.update_line_fields(
        project_id=project_id,
        cable_line_id=line_id,
        cable_type="NYM",
        board_designation="B.01",
        mount_way="В кабель-канале",
        gofra_type="",
        gofra_color="",
        gofra_id="",
    )
    service.calculate_and_save_length(
        project_id=project_id,
        cable_line_id=line_id,
        route_method=RouteMethod.CABLE_CHANNEL,
    )
    with database.engine.connect() as connection:
        segment_facts = connection.execute(
            select(cable_segment).where(cable_segment.c.cable_line_id == line_id)
        ).mappings().one()
        conduit_count = connection.scalar(select(func.count()).select_from(conduit))
    assert segment_facts["mount_way"] == "В кабель-канале"
    assert segment_facts["gofra_type"] is None
    assert conduit_count == 0


def test_pp25_dkc_11525_catalog_selection_and_legacy_conduit_ids(database):
    project_id, _first_room, _second_room = _project(database)
    service = CableService(database.engine)
    pp_id = service.create_empty_conduit(
        project_id=project_id,
        designation="001.PP25",
        conduit_type="ПП25",
        color="синий",
        diameter_mm=25,
        length_m=12,
    )
    candidates = service.conduit_product_candidates(
        project_id=project_id, conduit_id=pp_id
    )
    assert [(row["product_key"], row["article"]) for row in candidates] == [
        ("product.dkc.11525", "11525")
    ]
    service.select_conduit_product(
        project_id=project_id,
        conduit_id=pp_id,
        product_definition_id=candidates[0]["id"],
    )
    route = service.list_conduit_routes(project_id)[0]
    assert "11525" in route["product_display"]
    assert service.create_empty_conduit(
        project_id=project_id,
        designation="002.PND25",
        conduit_type="ПНД25",
    )
    assert service.create_empty_conduit(
        project_id=project_id,
        designation="003.PVH25",
        conduit_type="ПВХ25",
    )
    assert service.create_empty_conduit(
        project_id=project_id,
        designation="004.MR25",
        conduit_type="Металлорукав25",
    )


def test_av_identity_catalog_hdmi_selection_and_length_change(database):
    project_id, *rooms = _project(database)
    service = CableService(database.engine)
    board_one = service.create_board_av(project_id=project_id, designation="AV-A")
    board_two = service.create_board_av(project_id=project_id, designation="AV-B")
    hdmi_line = service.create_av_line(
        project_id=project_id,
        board_id=board_one,
        cable_id=" hdmi room ",
        load_type="HDMI",
        cable_type="HDMI 2.1",
    )
    service.create_av_line(
        project_id=project_id,
        board_id=board_two,
        cable_id="HDMI ROOM",
        load_type="HDMI",
        cable_type="HDMI 2.1",
    )
    with pytest.raises(CableError, match="already exists"):
        service.create_av_line(
            project_id=project_id,
            board_id=board_one,
            cable_id="hdmi room",
            load_type="HDMI",
            cable_type="HDMI 2.1",
        )
    _line_with_points(database, project_id, rooms, "ignored", line_id=hdmi_line)
    service.calculate_and_save_length(
        project_id=project_id,
        cable_line_id=hdmi_line,
        route_method=RouteMethod.CABLE_CHANNEL,
    )
    draft = service.start_catalog_draft("CABLES-1")
    product_ids = []
    for length in (2, 5, 10):
        product_ids.append(
            service.add_catalog_product(
                draft_release_id=draft,
                product_key=f"HDMI-{length}",
                category="HDMI",
                manufacturer="Test",
                model=f"Cable {length}",
                cable_type="HDMI 2.1",
                factory_length_m=length,
            )
        )
    service.publish_catalog(draft)
    selected = service.auto_select_hdmi(project_id=project_id, cable_line_id=hdmi_line)
    assert selected.required_length_m == Decimal("3")
    assert selected.factory_length_m == Decimal("5")
    assert selected.warning is None
    short = service.select_hdmi_manually(
        project_id=project_id,
        cable_line_id=hdmi_line,
        product_id=product_ids[0],
    )
    assert short.warning == "HDMI_SHORTER_THAN_REQUIRED"
    service.calculate_and_save_length(
        project_id=project_id,
        cable_line_id=hdmi_line,
        route_method=RouteMethod.CABLE_CHANNEL,
        manual_full_m=20,
    )
    insufficient = service.auto_select_hdmi(project_id=project_id, cable_line_id=hdmi_line)
    assert insufficient.factory_length_m == Decimal("10")
    assert insufficient.warning == "NO_SUFFICIENT_HDMI_LENGTH"
    service.calculate_and_save_length(
        project_id=project_id,
        cable_line_id=hdmi_line,
        route_method=RouteMethod.CABLE_CHANNEL,
        additional_m=1,
    )
    assert service.hdmi_selection_status(project_id, hdmi_line) == "RECONFIRM_REQUIRED"
    with database.engine.connect() as connection:
        selection = connection.execute(select(cable_line_product_selection)).mappings().one()
    assert selection["cable_product_definition_id"] == product_ids[2]


def test_speaker_product_versioned_catalog_and_equipment_catalog_is_unchanged(database):
    project_id, *_rooms = _project(database)
    service = CableService(database.engine)
    board_id = service.create_board_av(project_id=project_id, designation="AV-S")
    line_id = service.create_av_line(
        project_id=project_id,
        board_id=board_id,
        cable_id="spk-01",
        load_type="SPEAKER_CABLE",
        cable_type="2x2.5",
    )
    with database.engine.connect() as connection:
        equipment_counts = (
            connection.scalar(select(func.count()).select_from(passport_definition)),
            connection.scalar(select(func.count()).select_from(product_definition)),
        )
    draft = service.start_catalog_draft("SPEAKER-1")
    product_id = service.add_catalog_product(
        draft_release_id=draft,
        product_key="PREMIERA-CX-225",
        category="SPEAKER_CABLE",
        manufacturer="Premiera",
        model="CX-225",
        cable_type="2x2.5",
    )
    service.publish_catalog(draft)
    service.select_speaker_product(
        project_id=project_id,
        cable_line_id=line_id,
        product_id=product_id,
    )
    with database.engine.connect() as connection:
        assert (
            connection.scalar(
                select(cable_line_product_selection.c.cable_product_definition_id).where(
                    cable_line_product_selection.c.cable_line_id == line_id
                )
            )
            == product_id
        )
        assert equipment_counts == (
            connection.scalar(select(func.count()).select_from(passport_definition)),
            connection.scalar(select(func.count()).select_from(product_definition)),
        )

    second_draft = service.start_catalog_draft("SPEAKER-2")
    service.publish_catalog(second_draft)
    products = service.list_catalog_products()
    copied = [
        row
        for row in products
        if row["product_key"] == "PREMIERA-CX-225" and row["release_status"] == "ACTIVE"
    ]
    assert len(copied) == 1
    assert copied[0]["version"] == 2
