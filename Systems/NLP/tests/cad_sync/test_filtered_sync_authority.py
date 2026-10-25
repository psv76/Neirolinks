from dataclasses import replace

import pytest
from sqlalchemy import select, update

from nl_project_2.cad_contract import (
    BlockDefinitionMetadata,
    CadObservation,
    CadObservationBatch,
    load_contract,
)
from nl_project_2.cad_sync import ChangeClass, DwgSyncError, DwgSyncService
from nl_project_2.cad_sync.bridge import LayerFilteredRead
from nl_project_2.cad_sync.service import StaleProposalError
from nl_project_2.objects.models import ProjectCard
from nl_project_2.objects.service import ObjectService
from nl_project_2.persistence.schema import (
    av_cable_profile,
    bus_endpoint,
    bus_segment,
    cable_line,
    cable_point,
    cable_segment,
    cable_topology_endpoint,
    conduit,
    conduit_segment_assignment,
    dwg_baseline,
    dwg_document_binding,
    dwg_scan,
    field_device,
    project,
)

DOC = "C:/fixture/c7e.dwg"


def socket(handle="A1", identifier="101.01"):
    attrs = dict.fromkeys(load_contract().block("SOCKET_IN").required_definition_attributes, "")
    attrs.update(
        DEVICE_NAME="Socket",
        BUILDING="Building",
        ROOM="Room",
        MOUNT_HEIGHT="300",
        CABLE_ID=identifier,
        CABLE_TYPE="NYM",
        BOARD="B.01",
        LOAD_TYPE="SOCKET_LIVING_LOW",
        LOAD_NAME="Sockets",
        MOUNT_WAY="По полу",
        GOFRA_TYPE="ПНД25",
        GOFRA_COLOR="Черный",
        GOFRA_ID="001.PND25",
    )
    return CadObservation.from_mapping(
        effective_name="SOCKET_IN",
        layer="100_Power",
        raw_attributes=attrs,
        x=10,
        y=20,
        handle=handle,
        definition=BlockDefinitionMetadata(tuple(attrs), False),
    )


def applicable(proposal):
    return {
        c.field_path
        for c in proposal.changes
        if c.change_class in {ChangeClass.NEW_DWG_INSERTION, ChangeClass.DWG_CHANGED}
    }


def state(database):
    tables = (
        project,
        field_device,
        cable_line,
        cable_point,
        cable_segment,
        cable_topology_endpoint,
        conduit,
        conduit_segment_assignment,
        bus_endpoint,
        bus_segment,
        av_cable_profile,
        dwg_scan,
        dwg_baseline,
    )
    with database.engine.connect() as connection:
        return {
            t.name: sorted(repr(tuple(r)) for r in connection.execute(select(t))) for t in tables
        }


@pytest.fixture
def seeded(database):
    project_id = ObjectService(database.engine).create_project(
        ProjectCard(name="C7E", project_code="C7E")
    )
    service = DwgSyncService(database.engine)
    batch = CadObservationBatch(DOC, (socket(), socket("A2", "101.02")))
    initial = service.preview(project_id=project_id, batch=batch)
    service.apply_dwg_to_project(initial, selected_paths=applicable(initial), confirmed=True)
    proposal = service.preview(project_id=project_id, batch=batch)
    return project_id, service, batch, proposal


class DiagnosticPort:
    def __init__(self, batch, census, *, during_read=None):
        self.batch = batch
        self.census = census
        self.during_read = during_read
        self.calls = []

    def read_layer_filtered_observations(self, request, *, tracked_handles):
        self.calls.append((request, tracked_handles))
        if self.during_read:
            self.during_read()
        return LayerFilteredRead(
            self.batch,
            self.census,
            tuple(h for h, layer in self.census if h in tracked_handles and layer == "ARCH"),
            tuple(sorted(set(tracked_handles) - {h for h, _ in self.census})),
        )


def partial(batch, mode="FILTERED_FINGERPRINT"):
    return replace(
        batch,
        source_metadata={
            "scan_mode": mode,
            "layer_filter_applied": True,
            "scan_is_complete_for_reconciliation": False,
            "skipped_block_references": 1,
        },
    )


@pytest.mark.parametrize("mode", ["FILTERED_FINGERPRINT", "FILTERED_COM_FALLBACK"])
def test_tracked_off_layer_remains_present_and_partial_cannot_remove_topology(
    database, seeded, mode
):
    project_id, _, batch, proposal = seeded
    moved = replace(
        batch, observations=(replace(batch.observations[0], layer="ARCH"), batch.observations[1])
    )
    port = DiagnosticPort(
        partial(moved, mode), (("A1", "ARCH"), ("A2", "100_Power"), ("F1", "ARCH"))
    )
    service = DwgSyncService(database.engine, port)
    before = state(database)
    review = service.review_filtered_sync(project_id=project_id, expected_identity=DOC)
    assert port.calls[0][1] == ("A1", "A2")  # Foreign excluded F1 is not a stored owner.
    assert review.present_excluded_handles == ("A1",)
    assert review.absent_unknown_handles == ()
    assert review.status == "REQUIRES_ATTENTION"
    with pytest.raises(DwgSyncError, match="SCAN_NOT_AUTHORITATIVE"):
        service.preview(project_id=project_id, batch=review.batch)
    with pytest.raises(DwgSyncError, match="SCAN_NOT_AUTHORITATIVE"):
        service.apply_dwg_to_project(
            replace(proposal, batch=review.batch), selected_paths={"A1:$"}, confirmed=True
        )
    assert state(database) == before
    # An independently supplied FULL snapshot shows invalid placement, not missing.
    full = service.preview(project_id=project_id, batch=moved)
    assert any(c.change_class is ChangeClass.INVALID_DWG_DATA for c in full.changes)
    assert not any(c.change_class is ChangeClass.MISSING_DWG_INSERTION for c in full.changes)


def test_deleted_handle_is_unknown_until_full_confirmation_and_not_auto_deleted(database, seeded):
    project_id, _, batch, proposal = seeded
    remaining = replace(batch, observations=batch.observations[1:])
    port = DiagnosticPort(partial(remaining), (("A2", "100_Power"),))
    service = DwgSyncService(database.engine, port)
    before = state(database)
    review = service.review_filtered_sync(project_id=project_id, expected_identity=DOC)
    assert review.absent_unknown_handles == ("A1",)
    with pytest.raises(DwgSyncError, match="SCAN_NOT_AUTHORITATIVE"):
        service.preview(project_id=project_id, batch=review.batch)
    with pytest.raises(DwgSyncError, match="SCAN_NOT_AUTHORITATIVE"):
        service.apply_dwg_to_project(
            replace(proposal, batch=review.batch), selected_paths={"A1:$"}, confirmed=True
        )
    full = service.preview(project_id=project_id, batch=remaining)
    missing = [c for c in full.changes if c.change_class is ChangeClass.MISSING_DWG_INSERTION]
    assert [c.handle for c in missing] == ["A1"]
    with pytest.raises(DwgSyncError, match="non-applicable"):
        service.apply_dwg_to_project(full, selected_paths={missing[0].field_path}, confirmed=True)
    assert state(database) == before


@pytest.mark.parametrize("mode", ["FILTERED_FINGERPRINT", "FILTERED_COM_FALLBACK"])
@pytest.mark.parametrize(
    "flags",
    [
        {},
        {
            "layer_filter_applied": False,
            "scan_is_complete_for_reconciliation": True,
            "skipped_block_references": 0,
        },
    ],
)
def test_filtered_provenance_cannot_be_promoted_by_flag_tampering(database, seeded, mode, flags):
    project_id, service, batch, proposal = seeded
    forged = replace(batch, observations=(), source_metadata={"scan_mode": mode, **flags})
    before = state(database)
    with pytest.raises(DwgSyncError, match="SCAN_NOT_AUTHORITATIVE"):
        service.preview(project_id=project_id, batch=forged)
    with pytest.raises(DwgSyncError, match="SCAN_NOT_AUTHORITATIVE"):
        service.apply_dwg_to_project(
            replace(proposal, batch=forged), selected_paths={"A1:$"}, confirmed=True
        )
    assert state(database) == before


@pytest.mark.parametrize("change", ["revision", "binding", "owners"])
def test_project_context_change_during_read_rejects_result(database, seeded, change):
    project_id, _, batch, proposal = seeded

    def mutate():
        with database.engine.begin() as connection:
            if change == "revision":
                connection.execute(
                    update(project)
                    .where(project.c.id == project_id)
                    .values(project_revision=project.c.project_revision + 1)
                )
            elif change == "binding":
                connection.execute(
                    update(dwg_document_binding)
                    .where(dwg_document_binding.c.id == proposal.binding_id)
                    .values(row_version=dwg_document_binding.c.row_version + 1)
                )
            else:
                connection.execute(
                    update(field_device)
                    .where(
                        field_device.c.project_id == project_id,
                        field_device.c.entity_handle == "A2",
                    )
                    .values(entity_handle="B2")
                )

    port = DiagnosticPort(
        partial(batch), (("A1", "100_Power"), ("A2", "100_Power")), during_read=mutate
    )
    with pytest.raises(StaleProposalError, match="changed during filtered read"):
        DwgSyncService(database.engine, port).review_filtered_sync(
            project_id=project_id, expected_identity=DOC
        )


def test_wrong_project_or_document_does_not_read_cad(database, seeded):
    project_id, _, batch, _ = seeded
    other = ObjectService(database.engine).create_project(
        ProjectCard(name="Other", project_code="OTHER")
    )
    port = DiagnosticPort(partial(batch), ())
    service = DwgSyncService(database.engine, port)
    for selected_project, doc in [(other, DOC), (project_id, "other.dwg")]:
        with pytest.raises(DwgSyncError, match="CONFIRMED_PROJECT_BINDING_REQUIRED"):
            service.review_filtered_sync(project_id=selected_project, expected_identity=doc)
    assert port.calls == []


@pytest.mark.parametrize("change", ["status", "path", "application", "wrong_project"])
def test_apply_rechecks_binding_inside_sqlite_transaction(database, seeded, change):
    project_id, service, batch, _ = seeded
    changed = replace(
        batch,
        observations=(socket(identifier="101.01"), socket("A2", "101.02"), socket("A3", "101.03")),
    )
    proposal = service.preview(project_id=project_id, batch=changed)
    if change == "wrong_project":
        other = ObjectService(database.engine).create_project(
            ProjectCard(name="Other", project_code="OTHER")
        )
        with database.engine.connect() as connection:
            revision = connection.scalar(
                select(project.c.project_revision).where(project.c.id == other)
            )
        proposal = replace(proposal, project_id=other, project_revision=revision)
    else:
        values = (
            {"status": "REVOKED"}
            if change == "status"
            else {"normalized_last_path": "other.dwg"}
            if change == "path"
            else {"application_uuid": "other"}
        )
        with database.engine.begin() as connection:
            connection.execute(
                update(dwg_document_binding)
                .where(dwg_document_binding.c.id == proposal.binding_id)
                .values(**values)
            )
    before = state(database)
    with pytest.raises(StaleProposalError, match="binding changed"):
        service.apply_dwg_to_project(proposal, selected_paths={"A3:$"}, confirmed=True)
    assert state(database) == before


def test_changed_dwg_after_diagnostic_read_still_has_no_apply_authority(database, seeded):
    project_id, _, batch, proposal = seeded
    port = DiagnosticPort(partial(batch), (("A1", "100_Power"), ("A2", "100_Power")))
    service = DwgSyncService(database.engine, port)
    review = service.review_filtered_sync(project_id=project_id, expected_identity=DOC)
    port.batch = partial(replace(batch, observations=()))  # DWG changed after review.
    before = state(database)
    with pytest.raises(DwgSyncError, match="SCAN_NOT_AUTHORITATIVE"):
        service.apply_dwg_to_project(
            replace(proposal, batch=review.batch), selected_paths={"A1:$"}, confirmed=True
        )
    assert state(database) == before


def test_full_numeric_av_and_dali_preview_apply_still_supported(database):
    project_id = ObjectService(database.engine).create_project(
        ProjectCard(name="Numeric", project_code="NUM")
    )

    def observation(name, layer, handle, values):
        rule = load_contract().block(name)
        attrs = dict.fromkeys(rule.required_definition_attributes, "")
        attrs.update(DEVICE_NAME=name, BUILDING="Building", ROOM="Room", MOUNT_HEIGHT="300")
        if "MOUNT_WAY" in attrs:
            attrs["MOUNT_WAY"] = "По потолку"
        if name == "DALI_GROUP":
            attrs = {}
        attrs.update(values)
        return CadObservation.from_mapping(
            effective_name=name,
            layer=layer,
            handle=handle,
            raw_attributes=attrs,
            x=0,
            y=0,
            definition=BlockDefinitionMetadata(tuple(attrs), name == "DALI_GROUP"),
        )

    batch = CadObservationBatch(
        DOC,
        (
            socket(),
            observation(
                "BOARD_IN", "700_AV board", "B1", {"BOARD_ID": "AV.01", "LOAD_TYPE": "BOARD_AV"}
            ),
            observation(
                "CABLE_OUTLET",
                "700_HDMI",
                "B2",
                {"BOARD": "AV.01", "LOAD_TYPE": "HDMI", "CABLE_TYPE": "HDMI", "CABLE_ID": "HDMI-1"},
            ),
            observation("DALI_GROUP", "300_DALI", "D1", {"DALI_GROUP_ID": "D.001"}),
            observation("DALI_GROUP", "400_DALI", "D2", {"DALI_GROUP_ID": "D.002"}),
        ),
    )
    service = DwgSyncService(database.engine)
    proposal = service.preview(project_id=project_id, batch=batch)
    assert proposal.can_apply, proposal.issues
    service.apply_dwg_to_project(proposal, selected_paths=applicable(proposal), confirmed=True)
    with database.engine.connect() as connection:
        handles = set(
            connection.scalars(
                select(field_device.c.entity_handle).where(field_device.c.project_id == project_id)
            )
        )
    assert {"A1", "B1", "B2"} <= handles
    port = DiagnosticPort(partial(batch), tuple((o.handle, o.layer) for o in batch.observations))
    review = DwgSyncService(database.engine, port).review_filtered_sync(
        project_id=project_id, expected_identity=DOC
    )
    assert {"D1", "D2"} <= set(review.context.tracked_handles)


@pytest.mark.parametrize("fault", ["document", "authority"])
def test_service_rejects_wrong_document_or_promoted_adapter_result(database, seeded, fault):
    project_id, _, batch, _ = seeded
    returned = partial(batch)
    if fault == "document":
        returned = replace(returned, document_identity="other.dwg")
    else:
        returned = replace(returned, source_metadata={})
    port = DiagnosticPort(returned, (("A1", "100_Power"), ("A2", "100_Power")))
    before = state(database)
    with pytest.raises(DwgSyncError, match="DOCUMENT_MISMATCH|AUTHORITY_PROMOTION_FORBIDDEN"):
        DwgSyncService(database.engine, port).review_filtered_sync(
            project_id=project_id, expected_identity=DOC
        )
    assert state(database) == before
