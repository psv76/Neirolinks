from __future__ import annotations

import json

import pytest
from sqlalchemy import func, or_, select, update

from nl_project_2.automation import AutomationService
from nl_project_2.buses import BusService
from nl_project_2.catalog.equipment import EquipmentService
from nl_project_2.constructor import ConstructorService
from nl_project_2.equipment_actions import (
    ConfirmationRequired,
    EquipmentActionError,
    EquipmentActionService,
    StaleEquipmentPreview,
)
from nl_project_2.field_model import TopologyPersistenceService
from nl_project_2.guided_actions import (
    ConfirmationRequired as GuidedConfirmationRequired,
)
from nl_project_2.guided_actions import (
    GuidedAction,
    GuidedActionService,
    StalePreview,
)
from nl_project_2.operations import LastUsedPreference, LocalApplicationProfile
from nl_project_2.panels import PanelService
from nl_project_2.persistence.database import DatabaseManager
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    bus_endpoint,
    cable_line,
    cable_line_assignment,
    control_key_input_assignment,
    field_device,
    functional_relation,
    instance_resource,
    panel_placement,
    product_selection_history,
    project,
    project_instance,
    resource_reservation,
    user_reserve,
)


def _add_project(database, code):
    identifier = new_id()
    with database.engine.begin() as connection:
        connection.execute(
            project.insert().values(
                id=identifier,
                project_code=code,
                name=code,
                card_fields_json={},
                active_catalog_release_id=database.test_release_id,
                lifecycle="ACTIVE",
            )
        )
    return identifier


def _instance(database, designation, passport, product, *, project_id=None):
    return EquipmentService(database.engine).create_instance(
        project_id=project_id or database.test_project_id,
        designation=designation,
        passport_key=passport,
        product_key=product,
        supply_scope="NEIROLINKS",
    )


def _resources(database, instance_id, *, project_id=None):
    return [
        row
        for row in ConstructorService(database.engine).list_resources(
            project_id or database.test_project_id
        )
        if row["project_instance_id"] == instance_id
    ]


def _resource(database, instance_id, key, ordinal=0, *, project_id=None):
    return next(
        row
        for row in _resources(database, instance_id, project_id=project_id)
        if row["resource_key"] == key and row["ordinal"] == ordinal
    )


def _line(database, designation, *, project_id=None):
    identifier = new_id()
    with database.engine.begin() as connection:
        connection.execute(
            cable_line.insert().values(
                id=identifier,
                project_id=project_id or database.test_project_id,
                designation=designation,
                system_kind="LIGHTING_230V",
                cable_facts_json={"LOAD_NAME": designation},
            )
        )
    return identifier


def _revision(database, project_id=None):
    with database.engine.connect() as connection:
        return int(
            connection.scalar(
                select(project.c.project_revision).where(
                    project.c.id == (project_id or database.test_project_id)
                )
            )
        )


def _counts(database, project_id=None):
    owner = project_id or database.test_project_id
    with database.engine.connect() as connection:
        return {
            "instances": connection.scalar(
                select(func.count())
                .select_from(project_instance)
                .where(project_instance.c.project_id == owner)
            ),
            "resources": connection.scalar(
                select(func.count())
                .select_from(instance_resource)
                .where(instance_resource.c.project_id == owner)
            ),
        }


def _selectable(query, contains):
    return next(
        item for item in query.candidates if item.selectable and contains in item.target_label
    )


def test_duplicate_preview_confirm_is_independent_and_reopens(database):
    project_id = database.test_project_id
    source = _instance(
        database,
        "A01",
        "controller.wb_mr6c_v2",
        "product.wirenboard.wb_mr6c_v2",
    )
    psu = _instance(
        database,
        "PSU.1",
        "power.acdc.24v.din",
        "product.meanwell.hdr_60_24",
    )
    ConstructorService(database.engine).create_relation(
        project_id=project_id,
        relation_kind="POWER_FLOW",
        source_resource_id=_resource(database, psu.instance_id, "DC24_OUTPUT")["id"],
        target_resource_id=_resource(database, source.instance_id, "ELECTRONICS_POWER")["id"],
    )
    line = _line(database, "301")
    output = _resource(database, source.instance_id, "RELAY_OUTPUT", 0)
    AutomationService(database.engine).assign_output_line(
        project_id=project_id,
        cable_line_id=line,
        output_resource_id=output["id"],
    )
    reserve_target = _resource(database, source.instance_id, "RELAY_OUTPUT", 1)
    TopologyPersistenceService(database.engine).set_user_reserve(
        project_id=project_id,
        target_kind="INSTANCE_RESOURCE",
        target_id=reserve_target["id"],
        actor="pytest",
    )
    field = TopologyPersistenceService(database.engine)
    key_line = _line(database, "KEY-301")
    field_device_id = new_id()
    with database.engine.begin() as connection:
        connection.execute(
            field_device.insert().values(
                id=field_device_id,
                project_id=project_id,
                block_kind="SWITCH_1",
                normalized_fields_json={"CABLE_ID": "201.01"},
                entity_handle="P1002KEY",
            )
        )
    key_id = field.create_control_key(
        project_id=project_id,
        field_device_id=field_device_id,
        key_tag="KEY_1",
        target_kind="CABLE_LINE",
        target_id=key_line,
        target_text="Key target",
    )
    source_input = next(
        row["id"]
        for row in _resources(database, source.instance_id)
        if row["resource_kind"] == "DRY_CONTACT_INPUT"
    )
    field.assign_control_key_input(
        project_id=project_id,
        field_control_key_id=key_id,
        input_resource_id=source_input,
    )
    controller = _instance(
        database,
        "WB.1",
        "controller.wiren_board_8_5",
        "product.wirenboard.wb8_4g_64g_ind",
    )
    controller_rs485 = next(
        row["id"]
        for row in _resources(database, controller.instance_id)
        if row["resource_kind"] == "RS485_INTERFACE"
    )
    source_rs485 = next(
        row["id"]
        for row in _resources(database, source.instance_id)
        if row["resource_kind"] == "RS485_INTERFACE"
    )
    BusService(database.engine).create_rs485_bus(
        project_id=project_id,
        designation="901",
        root_resource_id=controller_rs485,
        points=(
            {
                "resource_id": source_rs485,
                "cable_id": "901.001",
                "x_mm": 0,
                "y_mm": 0,
            },
        ),
    )
    panels = PanelService(database.engine)
    board_id = panels.create_board(project_id=project_id, designation="BOARD.1")
    section_id = panels.create_section(
        project_id=project_id,
        board_id=board_id,
        section_key="MAIN",
        section_order=0,
    )
    rail_id = panels.create_rail(
        project_id=project_id,
        section_id=section_id,
        rail_order=0,
        usable_width_mm=500,
    )
    panels.assign_instance_to_board(
        project_id=project_id,
        instance_id=source.instance_id,
        board_id=board_id,
    )
    panels.place_instance(
        project_id=project_id,
        rail_id=rail_id,
        instance_id=source.instance_id,
        start_mm=0,
    )
    with database.engine.begin() as connection:
        connection.execute(
            update(project_instance)
            .where(project_instance.c.id == source.instance_id)
            .values(notes="must not be copied")
        )
    service = EquipmentActionService(database.engine)
    before = _counts(database)
    before_revision = _revision(database)

    preview = service.preview_duplicate(
        project_id=project_id,
        source_instance_id=source.instance_id,
        proposed_designation="A02",
    )
    assert preview.valid and preview.source_designation == "A01"
    assert "связи и назначения" in preview.excluded_facts
    assert _counts(database) == before and _revision(database) == before_revision
    with pytest.raises(ConfirmationRequired):
        service.confirm_duplicate(preview, confirmed=False)

    receipt = service.confirm_duplicate(preview, confirmed=True)
    assert receipt.project_revision_after == receipt.project_revision_before + 1
    source_resources = _resources(database, source.instance_id)
    copy_resources = _resources(database, receipt.new_instance_id)
    assert {(r["resource_key"], r["ordinal"]) for r in copy_resources} == {
        (r["resource_key"], r["ordinal"]) for r in source_resources
    }
    assert {r["id"] for r in copy_resources}.isdisjoint({r["id"] for r in source_resources})
    copy_ids = {row["id"] for row in copy_resources}
    with database.engine.connect() as connection:
        copied = (
            connection.execute(
                select(project_instance).where(project_instance.c.id == receipt.new_instance_id)
            )
            .mappings()
            .one()
        )
        assert copied["notes"] is None and copied["board_id"] is None and copied["room_id"] is None
        assert (
            connection.scalar(
                select(func.count())
                .select_from(cable_line_assignment)
                .where(cable_line_assignment.c.project_id == project_id)
            )
            == 1
        )
        assert (
            connection.scalar(
                select(func.count())
                .select_from(resource_reservation)
                .where(resource_reservation.c.resource_id.in_(copy_ids))
            )
            == 0
        )
        assert (
            connection.scalar(
                select(func.count())
                .select_from(functional_relation)
                .where(
                    or_(
                        functional_relation.c.source_resource_id.in_(copy_ids),
                        functional_relation.c.target_resource_id.in_(copy_ids),
                    )
                )
            )
            == 0
        )
        assert (
            connection.scalar(
                select(func.count())
                .select_from(control_key_input_assignment)
                .where(control_key_input_assignment.c.input_resource_id.in_(copy_ids))
            )
            == 0
        )
        assert (
            connection.scalar(
                select(func.count())
                .select_from(bus_endpoint)
                .where(bus_endpoint.c.resource_id.in_(copy_ids))
            )
            == 0
        )
        assert (
            connection.scalar(
                select(func.count())
                .select_from(panel_placement)
                .where(panel_placement.c.project_instance_id == receipt.new_instance_id)
            )
            == 0
        )
        assert (
            connection.scalar(
                select(func.count())
                .select_from(user_reserve)
                .where(
                    user_reserve.c.instance_resource_id.in_(copy_ids),
                    user_reserve.c.lifecycle == "ACTIVE",
                )
            )
            == 0
        )
        assert (
            connection.scalar(
                select(func.count())
                .select_from(product_selection_history)
                .where(product_selection_history.c.project_instance_id == receipt.new_instance_id)
            )
            == 0
        )

    path = database.path
    database.close()
    reopened = DatabaseManager().open_existing(path)
    try:
        assert (
            len(
                [
                    row
                    for row in ConstructorService(reopened.engine).list_resources(project_id)
                    if row["project_instance_id"] == receipt.new_instance_id
                ]
            )
            == receipt.resource_count
        )
    finally:
        reopened.close()


def test_duplicate_conflict_and_stale_preview_leave_no_partial_rows(database):
    source = _instance(
        database,
        "QF.01",
        "protection.circuit_breaker.1p",
        "product.schneider.a9f84116",
    )
    service = EquipmentActionService(database.engine)
    conflict = service.preview_duplicate(
        project_id=database.test_project_id,
        source_instance_id=source.instance_id,
        proposed_designation="QF.01",
    )
    assert conflict.conflicts == ("COLLISION_WITH_EXISTING",)
    before = _counts(database)
    with pytest.raises(EquipmentActionError, match="conflicts"):
        service.confirm_duplicate(conflict, confirmed=True)
    assert _counts(database) == before

    stale = service.preview_duplicate(
        project_id=database.test_project_id,
        source_instance_id=source.instance_id,
        proposed_designation="QF.02",
    )
    with database.engine.begin() as connection:
        connection.execute(
            update(project)
            .where(project.c.id == database.test_project_id)
            .values(project_revision=project.c.project_revision + 1)
        )
    with pytest.raises(StaleEquipmentPreview):
        service.confirm_duplicate(stale, confirmed=True)
    assert _counts(database) == before


def test_new_only_designation_planner_is_explicit_deterministic_and_never_fills_gaps(database):
    for designation in ("A01", "A03"):
        _instance(
            database,
            designation,
            "controller.wb_mr6c_v2",
            "product.wirenboard.wb_mr6c_v2",
        )
    service = EquipmentActionService(database.engine)
    first = service.plan_designations(
        project_id=database.test_project_id,
        proposed_designations=("A10", "A11"),
    )
    second = service.plan_designations(
        project_id=database.test_project_id,
        proposed_designations=("A10", "A11"),
    )
    assert first == second and first.valid
    assert first.formatter_path == "EXPLICIT_PROPOSED_SEQUENCE"
    assert [item.proposed_designation for item in first.proposed] == ["A10", "A11"]
    assert first.existing_designations == ("A01", "A03")
    collision = service.plan_designations(
        project_id=database.test_project_id,
        proposed_designations=("A03", "A20", "A20", ""),
    )
    assert collision.proposed[0].conflict_codes == ("COLLISION_WITH_EXISTING",)
    assert collision.proposed[1].conflict_codes == ("COLLISION_WITH_PROPOSED",)
    assert collision.proposed[3].conflict_codes == ("DESIGNATION_REQUIRED",)
    changed = service.plan_designations(
        project_id=database.test_project_id,
        proposed_designations=("A21", "A22"),
    )
    assert changed.fingerprint != first.fingerprint
    assert [
        row["designation"]
        for row in ConstructorService(database.engine).list_instances(database.test_project_id)
    ] == ["A01", "A03"]


def test_reserve_set_remove_effective_state_and_reopen_are_separate_from_occupancy(database):
    instance = _instance(
        database,
        "MCM.1",
        "module.wirenboard.wb_mcm8",
        "product.wirenboard.wb_mcm8",
    )
    resource = _resource(database, instance.instance_id, "INPUT", 0)
    service = EquipmentActionService(database.engine)
    start = service.reserve_state(
        project_id=database.test_project_id,
        target_kind="INSTANCE_RESOURCE",
        target_id=resource["id"],
    )
    assert not start.effective_reserved
    instance_state = service.set_reserve(
        project_id=database.test_project_id,
        target_kind="PROJECT_INSTANCE",
        target_id=instance.instance_id,
        actor="pytest",
        note="spare module",
        expected_project_revision=start.project_revision,
    )
    inherited = service.reserve_state(
        project_id=database.test_project_id,
        target_kind="INSTANCE_RESOURCE",
        target_id=resource["id"],
    )
    assert instance_state.direct_reserved
    assert inherited.effective_reserved and inherited.inherited_from_instance
    with database.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(resource_reservation)) == 0
        assert connection.scalar(select(func.count()).select_from(functional_relation)) == 0
        assert connection.scalar(select(func.count()).select_from(cable_line_assignment)) == 0
    removed = service.remove_reserve(
        project_id=database.test_project_id,
        target_kind="PROJECT_INSTANCE",
        target_id=instance.instance_id,
        actor="pytest-remove",
        expected_project_revision=inherited.project_revision,
    )
    assert not removed.effective_reserved
    direct = service.set_reserve(
        project_id=database.test_project_id,
        target_kind="INSTANCE_RESOURCE",
        target_id=resource["id"],
        actor="pytest",
        note="one input",
        expected_project_revision=removed.project_revision,
    )
    assert direct.direct_reserved and direct.note == "one input"
    path = database.path
    database.close()
    reopened = DatabaseManager().open_existing(path)
    try:
        state = EquipmentActionService(reopened.engine).reserve_state(
            project_id=database.test_project_id,
            target_kind="INSTANCE_RESOURCE",
            target_id=resource["id"],
        )
        assert state.direct_reserved and state.note == "one input"
    finally:
        reopened.close()


def test_reserve_blocks_guided_candidates_but_free_sibling_of_used_instance_is_normal(database):
    first = _instance(
        database,
        "MR.1",
        "controller.wb_mr6c_v2",
        "product.wirenboard.wb_mr6c_v2",
    )
    second = _instance(
        database,
        "MR.2",
        "controller.wb_mr6c_v2",
        "product.wirenboard.wb_mr6c_v2",
    )
    service = EquipmentActionService(database.engine)
    state = service.reserve_state(
        project_id=database.test_project_id,
        target_kind="PROJECT_INSTANCE",
        target_id=first.instance_id,
    )
    service.set_reserve(
        project_id=database.test_project_id,
        target_kind="PROJECT_INSTANCE",
        target_id=first.instance_id,
        actor="pytest",
        expected_project_revision=state.project_revision,
    )
    line = _line(database, "OUT-1")
    query = GuidedActionService(database.engine).output_candidates(
        project_id=database.test_project_id, cable_line_id=line
    )
    first_candidates = [item for item in query.candidates if item.instance_label == "MR.1"]
    assert first_candidates and all(
        "USER_RESERVE" in item.reason_codes for item in first_candidates
    )
    assert any(item.selectable and item.instance_label == "MR.2" for item in query.candidates)

    instance_reserve = service.reserve_state(
        project_id=database.test_project_id,
        target_kind="PROJECT_INSTANCE",
        target_id=first.instance_id,
    )
    service.remove_reserve(
        project_id=database.test_project_id,
        target_kind="PROJECT_INSTANCE",
        target_id=first.instance_id,
        actor="pytest",
        expected_project_revision=instance_reserve.project_revision,
    )
    unreserved = GuidedActionService(database.engine).output_candidates(
        project_id=database.test_project_id, cable_line_id=line
    )
    assert _selectable(unreserved, "MR.1 / K1")

    first_output = _resource(database, first.instance_id, "RELAY_OUTPUT", 0)
    resource_state = service.reserve_state(
        project_id=database.test_project_id,
        target_kind="INSTANCE_RESOURCE",
        target_id=first_output["id"],
    )
    service.set_reserve(
        project_id=database.test_project_id,
        target_kind="INSTANCE_RESOURCE",
        target_id=first_output["id"],
        actor="pytest",
        expected_project_revision=resource_state.project_revision,
    )
    one_reserved = GuidedActionService(database.engine).output_candidates(
        project_id=database.test_project_id, cable_line_id=line
    )
    k1 = next(item for item in one_reserved.candidates if item.target_label == "MR.1 / K1")
    assert not k1.selectable and "USER_RESERVE" in k1.reason_codes
    assert _selectable(one_reserved, "MR.1 / K2")
    direct = service.reserve_state(
        project_id=database.test_project_id,
        target_kind="INSTANCE_RESOURCE",
        target_id=first_output["id"],
    )
    service.remove_reserve(
        project_id=database.test_project_id,
        target_kind="INSTANCE_RESOURCE",
        target_id=first_output["id"],
        actor="pytest",
        expected_project_revision=direct.project_revision,
    )
    restored = GuidedActionService(database.engine).output_candidates(
        project_id=database.test_project_id, cable_line_id=line
    )
    assert _selectable(restored, "MR.1 / K1")

    line2 = _line(database, "OUT-2")
    free = _resource(database, second.instance_id, "RELAY_OUTPUT", 0)
    AutomationService(database.engine).assign_output_line(
        project_id=database.test_project_id,
        cable_line_id=line2,
        output_resource_id=free["id"],
    )
    after = GuidedActionService(database.engine).output_candidates(
        project_id=database.test_project_id, cable_line_id=_line(database, "OUT-3")
    )
    assert any(item.selectable and item.instance_label == "MR.2" for item in after.candidates)
    assert second.instance_id not in {
        issue.instance_id
        for issue in EquipmentActionService(database.engine).empty_instance_issues(
            project_id=database.test_project_id
        )
    }


def test_occupied_target_cannot_be_masked_as_user_reserve(database):
    relay = _instance(
        database,
        "MR.OCC",
        "controller.wb_mr6c_v2",
        "product.wirenboard.wb_mr6c_v2",
    )
    output = _resource(database, relay.instance_id, "RELAY_OUTPUT", 0)
    AutomationService(database.engine).assign_output_line(
        project_id=database.test_project_id,
        cable_line_id=_line(database, "OCC"),
        output_resource_id=output["id"],
    )
    service = EquipmentActionService(database.engine)
    state = service.reserve_state(
        project_id=database.test_project_id,
        target_kind="INSTANCE_RESOURCE",
        target_id=output["id"],
    )
    with pytest.raises(EquipmentActionError, match="TARGET_OCCUPIED"):
        service.set_reserve(
            project_id=database.test_project_id,
            target_kind="INSTANCE_RESOURCE",
            target_id=output["id"],
            actor="pytest",
            expected_project_revision=state.project_revision,
        )
    assert not service.reserve_state(
        project_id=database.test_project_id,
        target_kind="INSTANCE_RESOURCE",
        target_id=output["id"],
    ).effective_reserved


def test_empty_instance_issue_is_derived_and_tracks_instance_reserve_or_assignment(database):
    instance = _instance(
        database,
        "EMPTY.1",
        "controller.wb_mr6c_v2",
        "product.wirenboard.wb_mr6c_v2",
    )
    service = EquipmentActionService(database.engine)
    issue = next(
        item
        for item in service.empty_instance_issues(project_id=database.test_project_id)
        if item.instance_id == instance.instance_id
    )
    assert issue.status == "Требуется действие"
    assert issue.suggested_actions == ("назначить", "резерв", "удалить")
    resource = _resource(database, instance.instance_id, "RELAY_OUTPUT", 5)
    resource_state = service.reserve_state(
        project_id=database.test_project_id,
        target_kind="INSTANCE_RESOURCE",
        target_id=resource["id"],
    )
    service.set_reserve(
        project_id=database.test_project_id,
        target_kind="INSTANCE_RESOURCE",
        target_id=resource["id"],
        actor="pytest",
        expected_project_revision=resource_state.project_revision,
    )
    assert instance.instance_id in {
        item.instance_id
        for item in service.empty_instance_issues(project_id=database.test_project_id)
    }
    instance_state = service.reserve_state(
        project_id=database.test_project_id,
        target_kind="PROJECT_INSTANCE",
        target_id=instance.instance_id,
    )
    service.set_reserve(
        project_id=database.test_project_id,
        target_kind="PROJECT_INSTANCE",
        target_id=instance.instance_id,
        actor="pytest",
        expected_project_revision=instance_state.project_revision,
    )
    assert instance.instance_id not in {
        item.instance_id
        for item in service.empty_instance_issues(project_id=database.test_project_id)
    }
    current = service.reserve_state(
        project_id=database.test_project_id,
        target_kind="PROJECT_INSTANCE",
        target_id=instance.instance_id,
    )
    service.remove_reserve(
        project_id=database.test_project_id,
        target_kind="PROJECT_INSTANCE",
        target_id=instance.instance_id,
        actor="pytest",
        expected_project_revision=current.project_revision,
    )
    assert instance.instance_id in {
        item.instance_id
        for item in service.empty_instance_issues(project_id=database.test_project_id)
    }
    assignable = _resource(database, instance.instance_id, "RELAY_OUTPUT", 0)
    AutomationService(database.engine).assign_output_line(
        project_id=database.test_project_id,
        cable_line_id=_line(database, "USED"),
        output_resource_id=assignable["id"],
    )
    assert instance.instance_id not in {
        item.instance_id
        for item in service.empty_instance_issues(project_id=database.test_project_id)
    }


def test_local_profile_versions_reopens_and_clears_corrupt_or_stale_preferences(tmp_path):
    profile = LocalApplicationProfile(tmp_path)
    saved = profile.update("POWER", "catalog:product.example:POWER_OUTPUT")
    assert saved.resolved
    reopened = LocalApplicationProfile(tmp_path)
    assert reopened.preference("POWER").stable_identity == saved.stable_identity
    resolved = reopened.resolve("POWER", {saved.stable_identity})
    assert resolved.resolved
    stale = reopened.resolve("POWER", {"catalog:other:POWER_OUTPUT"})
    assert not stale.resolved and reopened.preference("POWER").stable_identity is None
    profile.path.write_text("{broken", encoding="utf-8")
    assert not profile.preference("POWER").resolved
    profile.path.write_text(json.dumps({"version": 999, "last_used": {}}), encoding="utf-8")
    assert not profile.preference("POWER").resolved


def test_successful_guided_commit_updates_cross_project_preference_and_ranks_only_selectable(
    database, tmp_path
):
    profile = LocalApplicationProfile(tmp_path)
    project1 = database.test_project_id
    psu30 = _instance(
        database,
        "PSU.30",
        "power.acdc.24v.din",
        "product.meanwell.hdr_30_24",
    )
    psu60 = _instance(
        database,
        "PSU.60",
        "power.acdc.24v.din",
        "product.meanwell.hdr_60_24",
    )
    target1 = _instance(
        database,
        "MCM.1",
        "module.wirenboard.wb_mcm8",
        "product.wirenboard.wb_mcm8",
    )
    target_resource1 = _resource(database, target1.instance_id, "ELECTRONICS_POWER")
    guided1 = GuidedActionService(database.engine, profile)
    query1 = guided1.power_candidates(
        project_id=project1, target_resource_id=target_resource1["id"]
    )
    candidate60 = _selectable(query1, "PSU.60")
    preview = guided1.preview(
        GuidedAction.POWER, project1, target_resource1["id"], candidate60.candidate_id
    )
    before_profile = profile.preference("POWER")
    assert not before_profile.resolved
    receipt = guided1.confirm(preview, confirmed=True)
    assert receipt.preference_updated and receipt.preference_identity
    assert profile.preference("POWER").stable_identity == receipt.preference_identity

    project2 = _add_project(database, "P1-002-B")
    for designation in ("PSU.60A", "PSU.60B"):
        _instance(
            database,
            designation,
            "power.acdc.24v.din",
            "product.meanwell.hdr_60_24",
            project_id=project2,
        )
    _instance(
        database,
        "PSU.30",
        "power.acdc.24v.din",
        "product.meanwell.hdr_30_24",
        project_id=project2,
    )
    target2 = _instance(
        database,
        "MCM.2",
        "module.wirenboard.wb_mcm8",
        "product.wirenboard.wb_mcm8",
        project_id=project2,
    )
    target_resource2 = _resource(
        database, target2.instance_id, "ELECTRONICS_POWER", project_id=project2
    )
    query2 = GuidedActionService(database.engine, profile).power_candidates(
        project_id=project2, target_resource_id=target_resource2["id"]
    )
    selectable_labels = [item.target_label for item in query2.candidates if item.selectable]
    assert selectable_labels[:2] == [
        _selectable(query2, "PSU.60A").target_label,
        _selectable(query2, "PSU.60B").target_label,
    ]
    preferred_output = _resource(
        database,
        next(
            row["id"]
            for row in ConstructorService(database.engine).list_instances(project2)
            if row["designation"] == "PSU.60A"
        ),
        "DC24_OUTPUT",
        project_id=project2,
    )
    TopologyPersistenceService(database.engine).set_user_reserve(
        project_id=project2,
        target_kind="INSTANCE_RESOURCE",
        target_id=preferred_output["id"],
        actor="pytest",
    )
    reserved_query = GuidedActionService(database.engine, profile).power_candidates(
        project_id=project2, target_resource_id=target_resource2["id"]
    )
    reserved = next(item for item in reserved_query.candidates if "PSU.60A" in item.target_label)
    assert not reserved.selectable and "USER_RESERVE" in reserved.reason_codes
    assert reserved_query.candidates[0].selectable
    assert psu30.instance_id != psu60.instance_id

    profile.update("POWER", "catalog:missing.product:DC24_OUTPUT")
    revision_before_stale_resolution = _revision(database, project2)
    GuidedActionService(database.engine, profile).power_candidates(
        project_id=project2, target_resource_id=target_resource2["id"]
    )
    assert profile.preference("POWER").stable_identity is None
    assert _revision(database, project2) == revision_before_stale_resolution


def test_preview_cancel_stale_and_failed_commits_do_not_update_preference(database, tmp_path):
    profile = LocalApplicationProfile(tmp_path)
    _instance(
        database,
        "PSU.1",
        "power.acdc.24v.din",
        "product.meanwell.hdr_60_24",
    )
    target = _instance(
        database,
        "MCM.1",
        "module.wirenboard.wb_mcm8",
        "product.wirenboard.wb_mcm8",
    )
    target_resource = _resource(database, target.instance_id, "ELECTRONICS_POWER")
    service = GuidedActionService(database.engine, profile)
    query = service.power_candidates(
        project_id=database.test_project_id, target_resource_id=target_resource["id"]
    )
    candidate = next(item for item in query.candidates if item.selectable)
    preview = service.preview(
        GuidedAction.POWER,
        database.test_project_id,
        target_resource["id"],
        candidate.candidate_id,
    )
    assert not profile.preference("POWER").resolved
    with pytest.raises(GuidedConfirmationRequired):
        service.confirm(preview, confirmed=False)
    assert not profile.preference("POWER").resolved
    with database.engine.begin() as connection:
        connection.execute(
            update(project)
            .where(project.c.id == database.test_project_id)
            .values(project_revision=project.c.project_revision + 1)
        )
    with pytest.raises(StalePreview):
        service.confirm(preview, confirmed=True)
    assert not profile.preference("POWER").resolved


class _FailingProfile:
    def resolve(self, action_type, available_identities):
        del available_identities
        return LastUsedPreference(str(action_type), None, False)

    def update(self, action_type, stable_identity):
        del action_type, stable_identity
        raise OSError("simulated profile write failure")


def test_local_profile_failure_is_separate_after_successful_project_commit(database):
    _instance(
        database,
        "PSU.1",
        "power.acdc.24v.din",
        "product.meanwell.hdr_60_24",
    )
    target = _instance(
        database,
        "MCM.1",
        "module.wirenboard.wb_mcm8",
        "product.wirenboard.wb_mcm8",
    )
    target_resource = _resource(database, target.instance_id, "ELECTRONICS_POWER")
    service = GuidedActionService(database.engine, _FailingProfile())
    query = service.power_candidates(
        project_id=database.test_project_id, target_resource_id=target_resource["id"]
    )
    candidate = next(item for item in query.candidates if item.selectable)
    receipt = service.confirm(
        service.preview(
            GuidedAction.POWER,
            database.test_project_id,
            target_resource["id"],
            candidate.candidate_id,
        ),
        confirmed=True,
    )
    assert not receipt.preference_updated
    assert receipt.preference_diagnostic == "LOCAL_PREFERENCE_UPDATE_FAILED:OSError"
    with database.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(functional_relation)) == 1
