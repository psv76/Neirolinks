"""Project-backed DALI root/type acceptance for #237; isolated temporary SQLite.

No real DWG, production database or migration is touched.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select, update

from nl_project_2.automation import AutomationService
from nl_project_2.cad_contract import (
    BlockDefinitionMetadata,
    CadObservation,
    CadObservationBatch,
    issue_codes,
)
from nl_project_2.cad_sync import DwgSyncError, DwgSyncService
from nl_project_2.objects.models import ProjectCard
from nl_project_2.objects.service import ObjectService
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import bus, instance_resource, project_instance


def _project(database, code="ROOT-A"):
    return ObjectService(database.engine).create_project(
        ProjectCard(name=f"DALI root {code}", project_code=code)
    )


def _insert_root(database, project_id, *, designation="905", kind="DALI"):
    automation = AutomationService(database.engine)
    source = automation.constructor.create_instance(
        project_id=project_id,
        designation=f"DALI-GATE-{designation}",
        passport_key="gateway.wirenboard.wb_dali3",
        product_key="product.wirenboard.wb_dali3",
        supply_scope="NEIROLINKS",
    )
    with database.engine.connect() as connection:
        root_id = connection.scalar(
            select(instance_resource.c.id).where(
                instance_resource.c.project_id == project_id,
                instance_resource.c.project_instance_id == source.instance_id,
                instance_resource.c.resource_key == "DALI_PORT",
                instance_resource.c.active.is_(True),
            )
        )
    assert root_id
    with database.engine.begin() as connection:
        row_id = new_id()
        connection.execute(
            bus.insert().values(
                id=row_id,
                project_id=project_id,
                bus_kind=kind,
                designation=designation,
                root_resource_id=root_id,
                topology_policy="ORDERED_BRANCHES",
                lifecycle="ACTIVE",
            )
        )
    return row_id, root_id, source.instance_id


def _observation():
    from nl_project_2.cad_contract import load_contract

    rule = load_contract().block("EL_BOX_OUT_100x100")
    assert rule is not None
    attrs = {tag: "" for tag in rule.required_definition_attributes}
    attrs.update(
        BOX_ID="BOX.023",
        BUS_ID="905",
        BUS_SOURCE="905.000",
        DEVICE_NAME="DALI box",
        BUILDING="House",
        ROOM="Hall",
        MOUNT_HEIGHT="2500",
    )
    return CadObservation.from_mapping(
        effective_name=rule.name,
        layer="BUS",
        raw_attributes=attrs,
        x=0,
        y=0,
        handle="DALI-BOX",
        definition=BlockDefinitionMetadata(tuple(attrs)),
    )


def _batch():
    return CadObservationBatch("synthetic-root-only.dwg", (_observation(),))


def _codes(proposal):
    return issue_codes(proposal.issues)


def test_preview_requires_persisted_project_root(database):
    pid = _project(database)
    preview = DwgSyncService(database.engine).preview(project_id=pid, batch=_batch())
    assert "BUS_ROOT_NOT_FOUND" in _codes(preview)
    assert "BUS_ROOT_UNVERIFIED" not in _codes(preview)
    assert not preview.can_apply


def test_preview_verifies_own_active_project_root(database):
    pid = _project(database)
    _insert_root(database, pid)
    service = DwgSyncService(database.engine)
    preview = service.preview(project_id=pid, batch=_batch())
    assert not (
        {"BUS_ROOT_NOT_FOUND", "BUS_ROOT_UNVERIFIED", "BUS_TYPE_CONFLICT"} & _codes(preview)
    )
    assert preview.can_apply


def test_root_in_another_project_is_not_visible(database):
    owner = _project(database, "ROOT-OWNER")
    other = _project(database, "ROOT-OTHER")
    _insert_root(database, owner)
    preview = DwgSyncService(database.engine).preview(project_id=other, batch=_batch())
    assert "BUS_ROOT_NOT_FOUND" in _codes(preview)


def test_root_kind_knx_is_not_accepted_for_passive_dali(database):
    pid = _project(database)
    _insert_root(database, pid, kind="KNX")
    preview = DwgSyncService(database.engine).preview(project_id=pid, batch=_batch())
    assert "BUS_TYPE_CONFLICT" in _codes(preview)
    assert "BUS_ROOT_NOT_FOUND" in _codes(preview)


@pytest.mark.parametrize("disable", ["resource", "owner", "bus"])
def test_only_active_project_root_is_verified(database, disable):
    pid = _project(database)
    bus_id, resource_id, instance_id = _insert_root(database, pid)
    with database.engine.begin() as connection:
        if disable == "resource":
            connection.execute(
                update(instance_resource)
                .where(instance_resource.c.id == resource_id)
                .values(active=False)
            )
        elif disable == "owner":
            connection.execute(
                update(project_instance)
                .where(project_instance.c.id == instance_id)
                .values(lifecycle="RETIRED")
            )
        else:
            connection.execute(update(bus).where(bus.c.id == bus_id).values(lifecycle="RETIRED"))
    preview = DwgSyncService(database.engine).preview(project_id=pid, batch=_batch())
    assert "BUS_ROOT_NOT_FOUND" in _codes(preview)


def test_apply_requires_rescan_if_project_root_changes_after_preview(database):
    pid = _project(database)
    bus_id, _resource_id, _instance_id = _insert_root(database, pid)
    sync = DwgSyncService(database.engine)
    proposal = sync.preview(project_id=pid, batch=_batch())
    assert proposal.can_apply
    applicable = {
        change.field_path
        for change in proposal.changes
        if change.change_class.value == "NEW_DWG_INSERTION"
    }
    assert applicable
    with database.engine.begin() as connection:
        connection.execute(update(bus).where(bus.c.id == bus_id).values(lifecycle="RETIRED"))
    with pytest.raises(DwgSyncError, match="rescan"):
        sync.apply_dwg_to_project(proposal, selected_paths=applicable, confirmed=True)


def test_no_type_inference_from_dwg_source_with_foreign_kind(database):
    pid = _project(database)
    _insert_root(database, pid, kind="RS485")
    validation = DwgSyncService(database.engine)._validator_for_project(pid).validate(_batch())
    assert "BUS_TYPE_CONFLICT" in issue_codes(validation.issues)
    assert "BUS_ROOT_NOT_FOUND" in issue_codes(validation.issues)


@pytest.mark.parametrize(
    ("feeder", "group"),
    [("301", "LIGHTING_230V"), ("401", "LIGHTING_LED")],
)
def test_project_preview_validates_dali_box_track_with_feeder_group(database, feeder, group):
    from nl_project_2.cad_contract import load_contract

    pid = _project(database)
    _insert_root(database, pid)
    rule = load_contract().block("TRACK_DALI")
    assert rule is not None
    attrs = {tag: "" for tag in rule.required_definition_attributes}
    attrs.update(
        DEVICE_NAME="DALI track",
        BUILDING="House",
        ROOM="Hall",
        MOUNT_HEIGHT="2500",
        TRACK_ID="TRACK.003",
        BUS_ID="905",
        BUS_SOURCE="BOX.023",
        CABLE_ID=feeder,
        CABLE_TYPE="TEST CABLE",
        BOARD="B.01",
        LENGTH="1500",
    )
    track = CadObservation.from_mapping(
        effective_name="TRACK_DALI",
        layer="TRACK_DALI",
        raw_attributes=attrs,
        x=500,
        y=300,
        handle="DALI-TRACK",
        definition=BlockDefinitionMetadata(tuple(attrs)),
    )
    batch = CadObservationBatch("synthetic-root-only.dwg", (_observation(), track))
    sync = DwgSyncService(database.engine)
    validated = sync._validator_for_project(pid).validate(batch)
    assert validated.observations[1].function_group == group
    assert validated.observations[1].read_payload.bus_point_id is None
    codes = issue_codes(validated.issues)
    assert not (
        codes
        & {
            "TRACK_DALI_POWER_GROUP_UNRESOLVED",
            "LAYER_FUNCTION_GROUP_MISMATCH",
            "BUS_SOURCE_UNREACHABLE",
            "BUS_SOURCE_NOT_FOUND",
            "BUS_ROOT_NOT_FOUND",
            "BUS_ROOT_UNVERIFIED",
            "BUS_SOURCE_CROSS_BUS",
        }
    ), validated.issues
    proposal = sync.preview(project_id=pid, batch=batch)
    assert not (issue_codes(proposal.issues) & {"BUS_ROOT_NOT_FOUND", "BUS_SOURCE_UNREACHABLE"})
