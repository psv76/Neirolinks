from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import func, select

from nl_project_2.bulk_actions import (
    BulkActionError,
    BulkActionService,
    BulkConfirmationRequired,
    BulkPlanBlocked,
    StaleBulkPreview,
)
from nl_project_2.catalog.equipment import EquipmentService
from nl_project_2.constructor import ConstructorService
from nl_project_2.field_model import TopologyPersistenceService
from nl_project_2.guided_actions import GuidedAction
from nl_project_2.operations import LocalApplicationProfile
from nl_project_2.persistence.database import DatabaseManager
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    bulk_operation_receipt,
    cable_line,
    cable_line_assignment,
    control_key_input_assignment,
    field_device,
    field_port,
    functional_relation,
    instance_resource,
    operation_journal,
    project,
    project_instance,
    user_reserve,
)


def _instance(database, designation, passport, product):
    return EquipmentService(database.engine).create_instance(
        project_id=database.test_project_id,
        designation=designation,
        passport_key=passport,
        product_key=product,
        supply_scope="NEIROLINKS",
    )


def _resource(database, instance_id, key, ordinal=0):
    return next(
        row
        for row in ConstructorService(database.engine).list_resources(
            database.test_project_id
        )
        if row["project_instance_id"] == instance_id
        and row["resource_key"] == key
        and row["ordinal"] == ordinal
    )


def _line(database, designation, system_kind="SWITCHES"):
    identifier = new_id()
    with database.engine.begin() as connection:
        connection.execute(
            cable_line.insert().values(
                id=identifier,
                project_id=database.test_project_id,
                designation=designation,
                system_kind=system_kind,
                cable_facts_json={"LOAD_NAME": f"Нагрузка {designation}"},
            )
        )
    return identifier


def _keys(database, count):
    line = _line(database, "201")
    field = TopologyPersistenceService(database.engine)
    keys = []
    for index in range(count):
        device_number = index // 4 + 1
        key_number = index % 4 + 1
        device_id = f"device-{device_number}"
        if key_number == 1:
            device_id = new_id()
            database.test_key_devices = getattr(database, "test_key_devices", {})
            database.test_key_devices[device_number] = device_id
            with database.engine.begin() as connection:
                connection.execute(
                    field_device.insert().values(
                        id=device_id,
                        project_id=database.test_project_id,
                        block_kind="SWITCH",
                        normalized_fields_json={"CABLE_ID": f"201.{device_number:02d}"},
                        entity_handle=f"KEYS-{device_number}",
                    )
                )
        else:
            device_id = database.test_key_devices[device_number]
        keys.append(
            field.create_control_key(
                project_id=database.test_project_id,
                field_device_id=device_id,
                key_tag=f"KEY_{key_number}",
                target_kind="CABLE_LINE",
                target_id=line,
                target_text="Свет",
            )
        )
    return tuple(keys)


def _revision(database):
    with database.engine.connect() as connection:
        return connection.scalar(
            select(project.c.project_revision).where(
                project.c.id == database.test_project_id
            )
        )


def _catalog_variant(query, contains):
    return next(
        item
        for item in query.variants
        if item.selectable
        and item.stable_identity.startswith("catalog:")
        and contains in item.label
    )


def test_selection_and_variant_queries_are_deterministic_and_read_only(database):
    module = _instance(
        database,
        "MCM8.1",
        "module.wirenboard.wb_mcm8",
        "product.wirenboard.wb_mcm8",
    )
    keys = _keys(database, 2)
    service = BulkActionService(database.engine)
    before_revision = _revision(database)
    before_hash = hashlib.sha256(database.path.read_bytes()).hexdigest()

    first = service.selection_snapshot(
        GuidedAction.INPUT,
        project_id=database.test_project_id,
        owner_ids=(keys[1], keys[0]),
    )
    second = service.selection_snapshot(
        GuidedAction.INPUT,
        project_id=database.test_project_id,
        owner_ids=(keys[0], keys[1]),
    )
    assert first == second
    assert first.valid
    variants = service.candidate_variants(first)
    chosen = _catalog_variant(variants, "WB-MCM8")
    assert chosen.existing_resource_count >= 8
    assert chosen.auto_creatable
    assert module.instance_id not in chosen.label
    assert _revision(database) == before_revision
    assert hashlib.sha256(database.path.read_bytes()).hexdigest() == before_hash

    mixed = service.selection_snapshot(
        GuidedAction.INPUT,
        project_id=database.test_project_id,
        owner_ids=(keys[0], keys[0]),
    )
    assert not mixed.valid
    assert "DUPLICATE_OWNER" in mixed.owners[0].reason_codes


def test_bulk_power_reuses_one_branching_source_and_is_idempotent(database, tmp_path):
    psu = _instance(
        database,
        "PSU.1",
        "power.acdc.24v.din",
        "product.meanwell.hdr_60_24",
    )
    targets = tuple(
        _resource(
            database,
            _instance(
                database,
                f"MCM8.{index}",
                "module.wirenboard.wb_mcm8",
                "product.wirenboard.wb_mcm8",
            ).instance_id,
            "ELECTRONICS_POWER",
        )["id"]
        for index in range(1, 4)
    )
    profile = LocalApplicationProfile(tmp_path / "profile")
    service = BulkActionService(database.engine, profile)
    snapshot = service.selection_snapshot(
        GuidedAction.POWER,
        project_id=database.test_project_id,
        owner_ids=targets,
    )
    variant = _catalog_variant(service.candidate_variants(snapshot), "HDR-60-24")
    preview = service.preview(snapshot, chosen_variant_identity=variant.stable_identity)
    assert preview.confirmable
    assert preview.new_instance_count == 0
    assert len({item.instance_designation for item in preview.mappings}) == 1
    with pytest.raises(BulkConfirmationRequired):
        service.confirm(preview, confirmed=False)
    before = _revision(database)
    receipt = service.confirm(preview, confirmed=True)
    repeated = service.confirm(preview, confirmed=True)
    assert repeated.command_id == receipt.command_id
    assert receipt.project_revision_after == before + 1
    assert profile.preference("POWER").stable_identity == variant.stable_identity
    output = _resource(database, psu.instance_id, "DC24_OUTPUT")
    with database.engine.connect() as connection:
        assert (
            connection.scalar(
                select(func.count())
                .select_from(functional_relation)
                .where(functional_relation.c.source_resource_id == output["id"])
            )
            == 3
        )
        assert (
            connection.scalar(select(func.count()).select_from(bulk_operation_receipt))
            == 1
        )
        assert (
            connection.scalar(select(func.count()).select_from(operation_journal)) == 1
        )


def test_wb_mcm8_shortage_uses_eight_inputs_and_explicit_new_designation(database):
    _instance(
        database,
        "MCM8.1",
        "module.wirenboard.wb_mcm8",
        "product.wirenboard.wb_mcm8",
    )
    keys = _keys(database, 10)
    service = BulkActionService(database.engine)
    snapshot = service.selection_snapshot(
        GuidedAction.INPUT,
        project_id=database.test_project_id,
        owner_ids=keys,
    )
    variant = _catalog_variant(service.candidate_variants(snapshot), "WB-MCM8")
    blocked = service.preview(snapshot, chosen_variant_identity=variant.stable_identity)
    assert "DESIGNATION_INPUT_REQUIRED" in blocked.conflicts
    assert blocked.new_instance_count == 1
    assert blocked.shortage_owner_count == 2
    with pytest.raises(BulkPlanBlocked):
        service.confirm(blocked, confirmed=True)

    preview = service.preview(
        snapshot,
        chosen_variant_identity=variant.stable_identity,
        proposed_designations=("MCM8.10",),
    )
    assert preview.confirmable
    assert preview.new_designations == ("MCM8.10",)
    assert any("Input 1" in item.resource_labels for item in preview.mappings)
    receipt = service.confirm(preview, confirmed=True)
    assert receipt.canonical_fact_count == 10
    with database.engine.connect() as connection:
        assert (
            connection.scalar(
                select(func.count()).select_from(control_key_input_assignment)
            )
            == 10
        )
        new_instance = connection.scalar(
            select(project_instance.c.id).where(
                project_instance.c.project_id == database.test_project_id,
                project_instance.c.designation == "MCM8.10",
            )
        )
        assert (
            connection.scalar(
                select(func.count())
                .select_from(instance_resource)
                .where(
                    instance_resource.c.project_instance_id == new_instance,
                    instance_resource.c.resource_key == "INPUT",
                )
            )
            == 8
        )


def test_bulk_protection_reuses_existing_then_creates_exact_shortage(database):
    _instance(
        database,
        "QF.1",
        "protection.circuit_breaker.1p",
        "product.schneider.a9f84116",
    )
    targets = tuple(
        _resource(
            database,
            _instance(
                database,
                f"PSU.{index}",
                "power.acdc.24v.din",
                "product.meanwell.hdr_60_24",
            ).instance_id,
            "AC_INPUT",
        )["id"]
        for index in range(1, 3)
    )
    service = BulkActionService(database.engine)
    snapshot = service.selection_snapshot(
        GuidedAction.PROTECTION,
        project_id=database.test_project_id,
        owner_ids=targets,
    )
    variant = next(
        item
        for item in service.candidate_variants(snapshot).variants
        if item.selectable and "product.schneider.a9f84116" in item.stable_identity
    )
    preview = service.preview(
        snapshot,
        chosen_variant_identity=variant.stable_identity,
        proposed_designations=("QF.10",),
    )
    assert preview.confirmable
    assert preview.new_instance_count == 1
    assert preview.mappings[0].instance_designation == "QF.1"
    service.confirm(preview, confirmed=True)
    with database.engine.connect() as connection:
        assert (
            connection.scalar(select(func.count()).select_from(functional_relation))
            == 2
        )
        assert (
            connection.scalar(
                select(func.count())
                .select_from(project_instance)
                .where(project_instance.c.designation == "QF.1")
            )
            == 1
        )


def test_bulk_ordinary_output_shortage_preserves_existing_designations(database):
    _instance(
        database,
        "MR6C.1",
        "controller.wb_mr6c_v2",
        "product.wirenboard.wb_mr6c_v2",
    )
    lines = tuple(
        _line(database, f"30{index}", "LIGHTING_230V") for index in range(1, 8)
    )
    service = BulkActionService(database.engine)
    snapshot = service.selection_snapshot(
        GuidedAction.OUTPUT,
        project_id=database.test_project_id,
        owner_ids=tuple(reversed(lines)),
    )
    variant = _catalog_variant(service.candidate_variants(snapshot), "WB-MR6C")
    blocked = service.preview(snapshot, chosen_variant_identity=variant.stable_identity)
    assert blocked.new_instance_count == 1
    assert "DESIGNATION_INPUT_REQUIRED" in blocked.conflicts
    preview = service.preview(
        snapshot,
        chosen_variant_identity=variant.stable_identity,
        proposed_designations=("MR6C.10",),
    )
    assert preview.confirmable
    service.confirm(preview, confirmed=True)
    with database.engine.connect() as connection:
        designations = tuple(
            connection.execute(
                select(project_instance.c.designation)
                .where(project_instance.c.project_id == database.test_project_id)
                .order_by(project_instance.c.designation)
            ).scalars()
        )
        assert designations == ("MR6C.1", "MR6C.10")
        assert (
            connection.scalar(select(func.count()).select_from(cable_line_assignment))
            == 7
        )


@pytest.mark.parametrize(
    ("led_kind", "tape_product", "channels", "line_count"),
    (
        ("MONO", "product.arlight.048822", 1, 5),
        ("CCT", "product.arlight.045179", 2, 3),
        ("RGB", "product.arlight.046937", 3, 2),
        ("RGBW", "product.arlight.046937", 4, 2),
    ),
)
def test_bulk_led_bundles_use_canonical_channel_counts_and_shortage(
    database, led_kind, tape_product, channels, line_count
):
    _instance(
        database,
        "PWM.1",
        "controller.wb_led_v1",
        "product.wirenboard.wb_led_v1",
    )
    service = BulkActionService(database.engine)
    lines = []
    for index in range(line_count):
        line = _line(database, f"LED-{led_kind}-{index}", "LED")
        service.guided.automation.create_led_profile(
            project_id=database.test_project_id,
            cable_line_id=line,
            led_kind=led_kind,
            tape_product_key=tape_product,
            supply_scope="NEIROLINKS",
            segments=({"design_length_mm": 1000},),
        )
        lines.append(line)
    snapshot = service.selection_snapshot(
        GuidedAction.OUTPUT,
        project_id=database.test_project_id,
        owner_ids=tuple(lines),
    )
    variant = _catalog_variant(service.candidate_variants(snapshot), "WB-LED")
    preview = service.preview(
        snapshot,
        chosen_variant_identity=variant.stable_identity,
        proposed_designations=("PWM.10",),
    )
    assert preview.confirmable
    assert preview.new_instance_count == 1
    assert all(len(item.resource_labels) == channels for item in preview.mappings)
    receipt = service.confirm(preview, confirmed=True)
    assert receipt.canonical_fact_count == line_count * channels


def test_mixed_led_channel_shapes_are_blocked_without_hidden_subgroups(database):
    _instance(
        database,
        "PWM.1",
        "controller.wb_led_v1",
        "product.wirenboard.wb_led_v1",
    )
    service = BulkActionService(database.engine)
    lines = []
    for kind, product_key in (
        ("MONO", "product.arlight.048822"),
        ("CCT", "product.arlight.045179"),
    ):
        line = _line(database, f"LED-{kind}", "LED")
        service.guided.automation.create_led_profile(
            project_id=database.test_project_id,
            cable_line_id=line,
            led_kind=kind,
            tape_product_key=product_key,
            supply_scope="NEIROLINKS",
            segments=({"design_length_mm": 1000},),
        )
        lines.append(line)
    snapshot = service.selection_snapshot(
        GuidedAction.OUTPUT,
        project_id=database.test_project_id,
        owner_ids=tuple(lines),
    )
    variant = _catalog_variant(service.candidate_variants(snapshot), "WB-LED")
    preview = service.preview(snapshot, chosen_variant_identity=variant.stable_identity)
    assert "MIXED_SELECTION" in preview.conflicts
    assert not preview.confirmable


def test_existing_field_output_and_input_paths_never_auto_create_field_devices(
    database,
):
    output_lines = (
        _line(database, "501", "LIGHTING_230V"),
        _line(database, "502", "LIGHTING_230V"),
    )
    device_id = new_id()
    with database.engine.begin() as connection:
        connection.execute(
            field_device.insert().values(
                id=device_id,
                project_id=database.test_project_id,
                block_kind="WB_MRM2_MINI",
                normalized_fields_json={"CABLE_ID": "901.01"},
                entity_handle="FIELD-1",
            )
        )
    field = TopologyPersistenceService(database.engine)
    for tag in ("K1", "K2", "IN_1", "IN_2"):
        field.create_field_port(
            project_id=database.test_project_id,
            field_device_id=device_id,
            port_tag=tag,
        )
    service = BulkActionService(database.engine)
    output_snapshot = service.selection_snapshot(
        GuidedAction.OUTPUT,
        project_id=database.test_project_id,
        owner_ids=output_lines,
    )
    field_variant = next(
        item
        for item in service.candidate_variants(output_snapshot).variants
        if item.selectable and item.stable_identity.startswith("field:")
    )
    assert not field_variant.auto_creatable
    output_preview = service.preview(
        output_snapshot, chosen_variant_identity=field_variant.stable_identity
    )
    assert output_preview.confirmable
    service.confirm(output_preview, confirmed=True)

    keys = _keys(database, 2)
    input_snapshot = service.selection_snapshot(
        GuidedAction.INPUT,
        project_id=database.test_project_id,
        owner_ids=keys,
    )
    input_variant = next(
        item
        for item in service.candidate_variants(input_snapshot).variants
        if item.selectable and item.stable_identity.startswith("field:")
    )
    input_preview = service.preview(
        input_snapshot, chosen_variant_identity=input_variant.stable_identity
    )
    assert input_preview.confirmable
    service.confirm(input_preview, confirmed=True)
    with database.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(field_device)) == 2
        assert connection.scalar(select(func.count()).select_from(field_port)) == 4


def test_failure_on_nth_write_rolls_back_new_instances_prior_assignments_and_receipt(
    database,
):
    _instance(
        database,
        "MCM8.1",
        "module.wirenboard.wb_mcm8",
        "product.wirenboard.wb_mcm8",
    )
    keys = _keys(database, 10)

    class FailingBulkService(BulkActionService):
        def _execute_mapping(
            self, uow, preview, mapping, new_ids, command_id, index, now
        ):
            if index == 9:
                raise BulkActionError("INJECTED_NINTH_WRITE_FAILURE")
            return super()._execute_mapping(
                uow, preview, mapping, new_ids, command_id, index, now
            )

    service = FailingBulkService(database.engine)
    snapshot = service.selection_snapshot(
        GuidedAction.INPUT,
        project_id=database.test_project_id,
        owner_ids=keys,
    )
    variant = _catalog_variant(service.candidate_variants(snapshot), "WB-MCM8")
    preview = service.preview(
        snapshot,
        chosen_variant_identity=variant.stable_identity,
        proposed_designations=("MCM8.10",),
    )
    before_revision = _revision(database)
    with pytest.raises(BulkActionError, match="INJECTED_NINTH"):
        service.confirm(preview, confirmed=True)
    with database.engine.connect() as connection:
        assert (
            connection.scalar(
                select(func.count()).select_from(control_key_input_assignment)
            )
            == 0
        )
        assert (
            connection.scalar(select(func.count()).select_from(bulk_operation_receipt))
            == 0
        )

    with database.engine.connect() as connection:
        assert (
            connection.scalar(
                select(func.count())
                .select_from(project_instance)
                .where(project_instance.c.designation == "MCM8.10")
            )
            == 0
        )
        assert (
            connection.scalar(select(func.count()).select_from(bulk_operation_receipt))
            == 0
        )
    assert _revision(database) == before_revision


def test_stale_reserve_and_designation_collision_leave_no_partial_changes(database):
    first = _instance(
        database,
        "MCM8.1",
        "module.wirenboard.wb_mcm8",
        "product.wirenboard.wb_mcm8",
    )
    keys = _keys(database, 10)
    service = BulkActionService(database.engine)
    snapshot = service.selection_snapshot(
        GuidedAction.INPUT,
        project_id=database.test_project_id,
        owner_ids=keys,
    )
    variant = _catalog_variant(service.candidate_variants(snapshot), "WB-MCM8")
    preview = service.preview(
        snapshot,
        chosen_variant_identity=variant.stable_identity,
        proposed_designations=("MCM8.10",),
    )
    EquipmentService(database.engine).create_instance(
        project_id=database.test_project_id,
        designation="MCM8.10",
        passport_key="module.wirenboard.wb_mcm8",
        product_key="product.wirenboard.wb_mcm8",
        supply_scope="NEIROLINKS",
    )
    with pytest.raises(StaleBulkPreview):
        service.confirm(preview, confirmed=True)
    with database.engine.connect() as connection:
        assert (
            connection.scalar(
                select(func.count()).select_from(control_key_input_assignment)
            )
            == 0
        )
        assert (
            connection.scalar(select(func.count()).select_from(bulk_operation_receipt))
            == 0
        )

    fresh = service.selection_snapshot(
        GuidedAction.INPUT,
        project_id=database.test_project_id,
        owner_ids=keys[:2],
    )
    fresh_variant = _catalog_variant(service.candidate_variants(fresh), "WB-MCM8")
    fresh_preview = service.preview(
        fresh, chosen_variant_identity=fresh_variant.stable_identity
    )
    resource_id = _resource(database, first.instance_id, "INPUT")["id"]
    TopologyPersistenceService(database.engine).set_user_reserve(
        project_id=database.test_project_id,
        target_kind="INSTANCE_RESOURCE",
        target_id=resource_id,
        actor="test",
    )
    with pytest.raises(StaleBulkPreview):
        service.confirm(fresh_preview, confirmed=True)
    with database.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(user_reserve)) == 1
        assert (
            connection.scalar(
                select(func.count()).select_from(control_key_input_assignment)
            )
            == 0
        )


def test_reopen_preserves_mapping_receipt_and_obsolete_confirm_is_idempotent(database):
    _instance(
        database,
        "MCM8.1",
        "module.wirenboard.wb_mcm8",
        "product.wirenboard.wb_mcm8",
    )
    keys = _keys(database, 2)
    service = BulkActionService(database.engine)
    snapshot = service.selection_snapshot(
        GuidedAction.INPUT,
        project_id=database.test_project_id,
        owner_ids=keys,
    )
    variant = _catalog_variant(service.candidate_variants(snapshot), "WB-MCM8")
    preview = service.preview(snapshot, chosen_variant_identity=variant.stable_identity)
    receipt = service.confirm(preview, confirmed=True)
    path = database.path
    project_id = database.test_project_id
    database.close()
    reopened = DatabaseManager().open_existing(path)
    try:
        reopened_service = BulkActionService(reopened.engine)
        restored = reopened_service.list_receipts(project_id)
        assert len(restored) == 1
        assert restored[0].command_id == receipt.command_id
        assert (
            reopened_service.confirm(preview, confirmed=True).command_id
            == receipt.command_id
        )
        with reopened.engine.connect() as connection:
            assert (
                connection.scalar(
                    select(func.count()).select_from(control_key_input_assignment)
                )
                == 2
            )
    finally:
        reopened.close()


def test_local_preference_failure_does_not_rollback_successful_project_commit(
    database, tmp_path
):
    class FailingProfile(LocalApplicationProfile):
        def update(self, action_type, stable_identity):
            raise OSError("profile unavailable")

    _instance(
        database,
        "MR6C.1",
        "controller.wb_mr6c_v2",
        "product.wirenboard.wb_mr6c_v2",
    )
    line = _line(database, "601", "LIGHTING_230V")
    service = BulkActionService(database.engine, FailingProfile(tmp_path / "profile"))
    snapshot = service.selection_snapshot(
        GuidedAction.OUTPUT,
        project_id=database.test_project_id,
        owner_ids=(line,),
    )
    variant = _catalog_variant(service.candidate_variants(snapshot), "WB-MR6C")
    preview = service.preview(snapshot, chosen_variant_identity=variant.stable_identity)
    receipt = service.confirm(preview, confirmed=True)
    assert not receipt.preference_updated
    assert receipt.preference_diagnostic == "LOCAL_PREFERENCE_UPDATE_FAILED:OSError"
    with database.engine.connect() as connection:
        assert (
            connection.scalar(select(func.count()).select_from(cable_line_assignment))
            == 1
        )
        assert (
            connection.scalar(select(func.count()).select_from(bulk_operation_receipt))
            == 1
        )
