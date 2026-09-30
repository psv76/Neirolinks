from __future__ import annotations

from dataclasses import replace

import pytest
from sqlalchemy import func, select, update

from nl_project_2.cad_contract import (
    BlockDefinitionMetadata,
    CadObservation,
    CadObservationBatch,
    load_contract,
)
from nl_project_2.cad_sync import ChangeClass, DwgSyncError, DwgSyncService, WriteResult
from nl_project_2.objects.models import ProjectCard
from nl_project_2.objects.service import ObjectService
from nl_project_2.persistence.database import DatabaseManager
from nl_project_2.persistence.schema import (
    cable_line,
    cable_point,
    cable_point_field_device,
    conduit,
    conduit_segment_assignment,
    dwg_baseline,
    dwg_observation,
    dwg_scan,
    dwg_write_receipt,
    field_device,
    topology_migration_review,
)
from nl_project_2.persistence.uow import UnitOfWork


def _socket(
    *,
    handle: str = "A1",
    cable_id: str = "101.01",
    cable_type: str = "NYM",
    device_name: str = "Socket",
    mount_way: str = "По полу",
    gofra_type: str = "ПНД25",
    gofra_color: str = "Черный",
    gofra_id: str = "001.PND25",
) -> CadObservation:
    rule = load_contract().block("SOCKET_IN")
    assert rule is not None
    attributes = {tag: "" for tag in rule.required_definition_attributes}
    attributes.update(
        {
            "DEVICE_NAME": device_name,
            "BUILDING": "Building",
            "ROOM": "Room",
            "MOUNT_HEIGHT": "300",
            "CABLE_ID": cable_id,
            "CABLE_TYPE": cable_type,
            "BOARD": "B.01",
            "LOAD_TYPE": "SOCKET_LIVING_LOW",
            "LOAD_NAME": "General sockets",
            "MOUNT_WAY": mount_way,
            "GOFRA_TYPE": gofra_type,
            "GOFRA_COLOR": gofra_color,
            "GOFRA_ID": gofra_id,
        }
    )
    return CadObservation.from_mapping(
        effective_name="SOCKET_IN",
        layer="POWER",
        raw_attributes=attributes,
        x=10,
        y=20,
        handle=handle,
        definition=BlockDefinitionMetadata(tuple(attributes), False),
    )


def _batch(*observations: CadObservation) -> CadObservationBatch:
    return CadObservationBatch(
        document_identity="C:/fixture/sync-test.dwg",
        observations=observations,
        source_metadata={"adapter_version": "test", "protocol_version": "1.0"},
    )


def _project(database) -> str:
    return ObjectService(database.engine).create_project(
        ProjectCard(name="CAD test", project_code="CAD-T")
    )


def _applicable(proposal) -> set[str]:
    return {
        item.field_path
        for item in proposal.changes
        if item.change_class in {ChangeClass.NEW_DWG_INSERTION, ChangeClass.DWG_CHANGED}
    }


def _unmanaged(name: str, handle: str, attributes=None) -> CadObservation:
    values = dict(attributes or {})
    return CadObservation.from_mapping(
        effective_name=name,
        layer="INTERIOR",
        raw_attributes=values,
        x=10,
        y=20,
        handle=handle,
        definition=BlockDefinitionMetadata(tuple(values), False),
    )


def test_preview_excludes_unmanaged_blocks_but_keeps_nl_claimant_error(database):
    project_id = _project(database)
    service = DwgSyncService(database.engine)

    furniture = service.preview(
        project_id=project_id,
        batch=_batch(
            _unmanaged("Chair 01", "F1"),
            _unmanaged("DOOR-modern", "F2"),
            _unmanaged("TABLE_round", "F3"),
        ),
    )
    assert furniture.issues == ()
    assert furniture.changes == ()
    assert furniture.summary.invalid == 0
    assert furniture.summary.new == 0

    claimant = service.preview(
        project_id=project_id,
        batch=_batch(_unmanaged("CUSTOM_UNKNOWN", "N1", {"CABLE_ID": "101.01"})),
    )
    assert claimant.summary.invalid == 1
    assert {issue.code for issue in claimant.issues} == {"UNKNOWN_BLOCK_NAME"}
    assert claimant.changes[0].change_class == ChangeClass.INVALID_DWG_DATA


def test_preview_is_read_only_initial_apply_is_atomic_and_rescan_is_idempotent(database):
    project_id = _project(database)
    service = DwgSyncService(database.engine)
    proposal = service.preview(project_id=project_id, batch=_batch(_socket()))
    assert proposal.can_apply
    assert proposal.summary.new == 1
    with database.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(dwg_scan)) == 0

    service.apply_dwg_to_project(
        proposal,
        selected_paths=_applicable(proposal),
        confirmed=True,
    )
    with database.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(field_device)) == 1
        assert connection.scalar(select(func.count()).select_from(cable_line)) == 1
        assert connection.scalar(select(func.count()).select_from(dwg_observation)) == 1
        assert connection.scalar(select(func.count()).select_from(dwg_baseline)) > 1
        tube = connection.execute(select(conduit)).mappings().one()
        assert tube["designation"] == "001.PND25"
        assert tube["conduit_number"] == 1
        assert tube["color"] == "Черный"

    repeated = service.preview(project_id=project_id, batch=_batch(_socket()))
    assert {item.change_class for item in repeated.changes} == {ChangeClass.EQUAL}
    assert repeated.summary == replace(repeated.summary)


def test_four_new_insertions_create_one_persisted_line_and_normal_baseline(database):
    project_id = _project(database)
    service = DwgSyncService(database.engine)
    source = _socket(handle="S102", cable_id="102.01", gofra_id="002.PND25")
    source_proposal = service.preview(project_id=project_id, batch=_batch(source))
    service.apply_dwg_to_project(
        source_proposal,
        selected_paths=_applicable(source_proposal),
        confirmed=True,
    )
    with database.engine.connect() as connection:
        source_before = (
            connection.execute(select(cable_line).where(cable_line.c.designation == "102"))
            .mappings()
            .one()
        )

    new_items = tuple(
        _socket(
            handle=f"N120{i}",
            cable_id=f"120.{i:02d}",
            device_name=f"Line 120 socket {i}",
            gofra_id=f"{10 + i:03d}.PND25",
        )
        for i in range(1, 5)
    )
    batch = _batch(source, *new_items)
    proposal = service.preview(project_id=project_id, batch=batch)
    new_paths = {
        change.field_path
        for change in proposal.changes
        if change.change_class is ChangeClass.NEW_DWG_INSERTION
    }
    assert new_paths == {f"N120{i}:$" for i in range(1, 5)}
    service.apply_dwg_to_project(
        proposal,
        selected_paths=new_paths,
        confirmed=True,
    )

    with database.engine.connect() as connection:
        lines = list(
            connection.execute(select(cable_line).order_by(cable_line.c.designation)).mappings()
        )
        target = next(row for row in lines if row["designation"] == "120")
        source_after = next(row for row in lines if row["designation"] == "102")
        memberships = list(
            connection.execute(
                select(field_device.c.entity_handle, cable_point.c.logical_identity)
                .select_from(cable_point_field_device)
                .join(
                    field_device,
                    field_device.c.id == cable_point_field_device.c.field_device_id,
                )
                .join(
                    cable_point,
                    cable_point.c.id == cable_point_field_device.c.cable_point_id,
                )
                .where(cable_point.c.cable_line_id == target["id"])
            ).mappings()
        )
        baseline_count = connection.scalar(
            select(func.count())
            .select_from(dwg_baseline)
            .where(dwg_baseline.c.field_path.like("base_line:120:%"))
        )
    assert [row["designation"] for row in lines] == ["102", "120"]
    assert source_after == source_before
    assert {row["entity_handle"] for row in memberships} == {
        "N1201",
        "N1202",
        "N1203",
        "N1204",
    }
    assert {row["logical_identity"] for row in memberships} == {
        "120.01",
        "120.02",
        "120.03",
        "120.04",
    }
    assert baseline_count and baseline_count > 0

    repeated = service.preview(project_id=project_id, batch=batch)
    assert ChangeClass.NEW_DWG_INSERTION not in {change.change_class for change in repeated.changes}
    with database.engine.connect() as connection:
        assert (
            connection.scalar(
                select(func.count())
                .select_from(cable_line)
                .where(cable_line.c.designation == "120")
            )
            == 1
        )


def test_dwg_change_conflict_and_missing_keep_project_only_data(database):
    project_id = _project(database)
    service = DwgSyncService(database.engine)
    first = service.preview(project_id=project_id, batch=_batch(_socket()))
    service.apply_dwg_to_project(first, selected_paths=_applicable(first), confirmed=True)

    changed = service.preview(
        project_id=project_id,
        batch=_batch(_socket(device_name="Changed in DWG")),
    )
    device_name = next(item for item in changed.changes if item.field == "DEVICE_NAME")
    assert device_name.change_class == ChangeClass.DWG_CHANGED
    service.apply_dwg_to_project(
        changed,
        selected_paths={device_name.field_path},
        confirmed=True,
    )
    with UnitOfWork(database.engine) as uow:
        row = uow.execute(select(field_device)).mappings().one()
        fields = dict(row["normalized_fields_json"])
        fields["DEVICE_NAME"] = "Changed in Project"
        fields["PROJECT_ONLY_NOTE"] = "must survive"
        uow.execute(
            update(field_device)
            .where(field_device.c.id == row["id"])
            .values(normalized_fields_json=fields)
        )
        uow.commit()
    conflict = service.preview(
        project_id=project_id,
        batch=_batch(_socket(device_name="Changed again in DWG")),
    )
    item = next(change for change in conflict.changes if change.field == "DEVICE_NAME")
    assert item.change_class == ChangeClass.BOTH_CHANGED_CONFLICT

    missing = service.preview(project_id=project_id, batch=_batch())
    assert missing.summary.missing == 1
    with database.engine.connect() as connection:
        fields = connection.execute(select(field_device.c.normalized_fields_json)).scalar_one()
    assert fields["PROJECT_ONLY_NOTE"] == "must survive"
    assert fields["DEVICE_NAME"] == "Changed in Project"


def test_inconsistent_line_is_rejected_without_partial_scan(database):
    project_id = _project(database)
    service = DwgSyncService(database.engine)
    invalid = service.preview(
        project_id=project_id,
        batch=_batch(
            _socket(handle="A1", cable_id="101.01", cable_type="NYM"),
            _socket(handle="A2", cable_id="101.02", cable_type="VVG"),
        ),
    )
    assert not invalid.can_apply
    assert "LINE_CABLE_TYPE_INCONSISTENT" in {issue.code for issue in invalid.issues}
    with pytest.raises(DwgSyncError):
        service.apply_dwg_to_project(
            invalid,
            selected_paths={item.field_path for item in invalid.changes},
            confirmed=True,
        )
    with database.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(dwg_scan)) == 0
        assert connection.scalar(select(func.count()).select_from(field_device)) == 0


def test_invalid_preview_exposes_existing_validator_code_field_and_message(database):
    project_id = _project(database)
    service = DwgSyncService(database.engine)

    proposal = service.preview(
        project_id=project_id,
        batch=_batch(replace(_socket(), layer="100")),
    )

    change = next(
        item for item in proposal.changes if item.change_class == ChangeClass.INVALID_DWG_DATA
    )
    assert "LAYER_FUNCTION_GROUP_MISMATCH [LAYER]" in change.reason
    assert "layer '100' is not an approved unique group for SOCKET_IN" in change.reason
    assert "The insertion failed mandatory contract validation" not in change.reason


def test_partial_new_line_import_is_rejected(database):
    project_id = _project(database)
    service = DwgSyncService(database.engine)
    proposal = service.preview(
        project_id=project_id,
        batch=_batch(
            _socket(handle="A1", cable_id="101.01"),
            _socket(handle="A2", cable_id="101.02"),
        ),
    )
    with pytest.raises(DwgSyncError, match="Partial line import"):
        service.apply_dwg_to_project(
            proposal,
            selected_paths={"A1:$"},
            confirmed=True,
        )
    with database.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(field_device)) == 0


def test_failure_injection_rolls_back_whole_import(database):
    project_id = _project(database)
    service = DwgSyncService(database.engine)
    proposal = service.preview(project_id=project_id, batch=_batch(_socket()))

    def fail() -> None:
        raise RuntimeError("injected")

    with pytest.raises(RuntimeError, match="injected"):
        service.apply_dwg_to_project(
            proposal,
            selected_paths=_applicable(proposal),
            confirmed=True,
            failure_hook=fail,
        )
    with database.engine.connect() as connection:
        for table in (dwg_scan, dwg_observation, field_device, cable_line):
            assert connection.scalar(select(func.count()).select_from(table)) == 0


class _WriteBridge:
    def __init__(self) -> None:
        self.commands = None

    def write_attributes(self, *, document_identity, changes, deadline_seconds):
        self.commands = changes
        return WriteResult(
            document_identity=document_identity,
            readback=tuple(
                {"handle": item["handle"], "tag": item["tag"], "value": item["new_value"]}
                for item in changes
            ),
            no_save_confirmed=True,
            document_saved=False,
        )


def test_project_to_dwg_uses_allow_list_preconditions_readback_and_no_save(database):
    project_id = _project(database)
    service = DwgSyncService(database.engine)
    first = service.preview(project_id=project_id, batch=_batch(_socket()))
    service.apply_dwg_to_project(first, selected_paths=_applicable(first), confirmed=True)
    with UnitOfWork(database.engine) as uow:
        row = uow.execute(select(field_device)).mappings().one()
        fields = dict(row["normalized_fields_json"])
        fields["DEVICE_NAME"] = "Project value"
        uow.execute(
            update(field_device)
            .where(field_device.c.id == row["id"])
            .values(normalized_fields_json=fields)
        )
        uow.commit()
    proposal = service.preview(project_id=project_id, batch=_batch(_socket()))
    item = next(change for change in proposal.changes if change.field == "DEVICE_NAME")
    assert item.change_class == ChangeClass.PROJECT_CHANGED
    bridge = _WriteBridge()
    result = service.write_project_to_dwg(
        proposal,
        selected_paths={item.field_path},
        confirmed=True,
        bridge=bridge,
    )
    assert bridge.commands == [
        {
            "handle": "A1",
            "tag": "DEVICE_NAME",
            "old_value": "Socket",
            "new_value": "Project value",
            "expected_block_name": "SOCKET_IN",
            "expected_layer": "POWER",
        }
    ]
    assert result.no_save_confirmed and not result.document_saved
    with database.engine.connect() as connection:
        receipt = connection.execute(select(dwg_write_receipt)).mappings().one()
    assert receipt["readback_value_json"] == "Project value"


def test_empty_gofra_id_gets_max_plus_one_and_remains_project_change_until_writeback(database):
    project_id = _project(database)
    service = DwgSyncService(database.engine)
    first = service.preview(
        project_id=project_id,
        batch=_batch(_socket(handle="A1", cable_id="101.01", gofra_id="")),
    )
    service.apply_dwg_to_project(first, selected_paths={"A1:$"}, confirmed=True)
    with database.engine.connect() as connection:
        tube = connection.execute(select(conduit)).mappings().one()
        fields = connection.execute(select(field_device.c.normalized_fields_json)).scalar_one()
    assert tube["designation"] == "001.PND25"
    assert tube["conduit_number"] == 1
    assert fields["GOFRA_ID"] == "001.PND25"

    repeated = service.preview(
        project_id=project_id,
        batch=_batch(_socket(handle="A1", cable_id="101.01", gofra_id="")),
    )
    generated = next(change for change in repeated.changes if change.field == "GOFRA_ID")
    assert generated.change_class == ChangeClass.PROJECT_CHANGED
    assert generated.baseline_value == ""
    assert generated.project_value == "001.PND25"


def test_multi_point_dwg_line_uses_explicit_cable_source_roots(database):
    project_id = _project(database)
    service = DwgSyncService(database.engine)
    initial_batch = _batch(
        _socket(handle="A1", cable_id="101.01"),
        _socket(handle="A2", cable_id="101.02"),
    )
    first = service.preview(project_id=project_id, batch=initial_batch)
    service.apply_dwg_to_project(first, selected_paths={"A1:$", "A2:$"}, confirmed=True)
    with database.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(conduit)) == 1
        assert connection.scalar(select(func.count()).select_from(conduit_segment_assignment)) == 2
        assert connection.scalar(select(func.count()).select_from(topology_migration_review)) == 0


def test_preexisting_shared_gofra_id_creates_one_incomplete_conduit(database):
    project_id = _project(database)
    service = DwgSyncService(database.engine)
    proposal = service.preview(
        project_id=project_id,
        batch=_batch(
            _socket(handle="A1", cable_id="101.01", gofra_id="003.PND25"),
            _socket(handle="A2", cable_id="102.01", gofra_id="003.PND25"),
        ),
    )
    service.apply_dwg_to_project(
        proposal,
        selected_paths={"A1:$", "A2:$"},
        confirmed=True,
    )
    with database.engine.connect() as connection:
        tube = connection.execute(select(conduit)).mappings().one()
        assignments = connection.scalar(
            select(func.count()).select_from(conduit_segment_assignment)
        )
    assert tube["designation"] == "003.PND25"
    assert tube["length_m_decimal"] is None
    assert tube["path_json"]["initial_length_status"] == "INCOMPLETE_SHARED"
    assert assignments == 2


def test_multi_point_preexisting_conduit_uses_explicit_sources_and_reopens(database):
    project_id = _project(database)
    sync = DwgSyncService(database.engine)
    proposal = sync.preview(
        project_id=project_id,
        batch=_batch(
            _socket(handle="A1", cable_id="101.01", gofra_id="003.PND25"),
            replace(
                _socket(handle="A2", cable_id="101.02", gofra_id="003.PND25"),
                x=1010,
            ),
        ),
    )
    sync.apply_dwg_to_project(
        proposal,
        selected_paths={"A1:$", "A2:$"},
        confirmed=True,
    )
    with database.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(conduit)) == 1
        assert connection.scalar(select(func.count()).select_from(conduit_segment_assignment)) == 2
        assert connection.scalar(select(func.count()).select_from(topology_migration_review)) == 0

    path = database.path
    database.close()
    reopened = DatabaseManager().open_existing(path)
    try:
        with reopened.engine.connect() as connection:
            assert connection.scalar(select(func.count()).select_from(conduit)) == 1
            assert (
                connection.scalar(select(func.count()).select_from(conduit_segment_assignment)) == 2
            )
            assert (
                connection.scalar(select(func.count()).select_from(topology_migration_review)) == 0
            )
    finally:
        reopened.close()


def test_two_explicit_lines_can_share_one_segment_owned_conduit(database):
    project_id = _project(database)
    sync = DwgSyncService(database.engine)
    proposal = sync.preview(
        project_id=project_id,
        batch=_batch(
            _socket(handle="A1", cable_id="101.01", gofra_id="003.PND25"),
            replace(
                _socket(handle="A2", cable_id="101.02", gofra_id="003.PND25"),
                x=1010,
            ),
            _socket(handle="B1", cable_id="102.01", gofra_id="003.PND25"),
            replace(
                _socket(handle="B2", cable_id="102.02", gofra_id="003.PND25"),
                x=2010,
            ),
        ),
    )
    sync.apply_dwg_to_project(
        proposal,
        selected_paths={"A1:$", "A2:$", "B1:$", "B2:$"},
        confirmed=True,
    )
    with database.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(conduit)) == 1
        assert connection.scalar(select(func.count()).select_from(conduit_segment_assignment)) == 4
        assert connection.scalar(select(func.count()).select_from(topology_migration_review)) == 0


def test_unrelated_invalid_legacy_row_does_not_block_selected_valid_line(database):
    project_id = _project(database)
    service = DwgSyncService(database.engine)
    invalid = replace(_socket(handle="BAD", cable_id="102.01"), layer="0")
    proposal = service.preview(
        project_id=project_id,
        batch=_batch(_socket(handle="GOOD", cable_id="101.01"), invalid),
    )
    assert not proposal.can_apply
    assert proposal.summary.invalid == 1
    service.apply_dwg_to_project(
        proposal,
        selected_paths={"GOOD:$"},
        confirmed=True,
    )
    with database.engine.connect() as connection:
        handles = set(connection.execute(select(field_device.c.entity_handle)).scalars())
    assert handles == {"GOOD"}


def test_646_unselected_invalid_rows_do_not_block_three_selected_insertions(database):
    project_id = _project(database)
    service = DwgSyncService(database.engine)
    valid = tuple(_socket(handle=handle, cable_id="101") for handle in ("5FF12", "60B36", "60B61"))
    invalid = tuple(
        replace(
            _socket(handle=f"BAD{index:03d}", cable_id=f"{200 + index}.01"),
            layer="0",
        )
        for index in range(646)
    )
    proposal = service.preview(project_id=project_id, batch=_batch(*valid, *invalid))
    selected = {"5FF12:$", "60B36:$", "60B61:$"}
    assert proposal.summary.new == 3
    assert proposal.summary.invalid == 646

    service.apply_dwg_to_project(proposal, selected_paths=selected, confirmed=True)

    with database.engine.connect() as connection:
        line_designations = set(connection.execute(select(cable_line.c.designation)).scalars())
        handles = set(connection.execute(select(field_device.c.entity_handle)).scalars())
        points = connection.scalar(select(func.count()).select_from(cable_point))
        memberships = connection.scalar(select(func.count()).select_from(cable_point_field_device))
    assert line_designations == {"101"}
    assert handles == {"5FF12", "60B36", "60B61"}
    assert points == 2
    assert memberships == 3
