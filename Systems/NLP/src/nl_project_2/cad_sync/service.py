"""Three-way DWG preview and explicit transactional synchronization commands."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, delete, func, select, update

from nl_project_2.cables.domain import (
    ConduitContractError,
    format_conduit_id,
    parse_conduit_id,
    validate_line_conduit_fields,
)
from nl_project_2.cables.recalculation import RecalculationError, recalculate_segments
from nl_project_2.cad_contract import (
    CadContractValidator,
    CadObservationBatch,
    CadReadRequest,
    ValidatedObservation,
    load_contract,
)
from nl_project_2.field_model.domain import canonical_port, normalize_led_type
from nl_project_2.objects.room_rules import RoomIdentity, normalize_room_name, resolve_room
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    board,
    building,
    bus,
    bus_endpoint,
    bus_segment,
    bus_segment_conduit_assignment,
    cable_line,
    cable_point,
    cable_point_field_device,
    cable_segment,
    cable_topology_endpoint,
    conduit,
    conduit_segment_assignment,
    dali_group,
    dwg_baseline,
    dwg_document_binding,
    dwg_observation,
    dwg_scan,
    dwg_sync_change,
    dwg_sync_operation,
    dwg_write_receipt,
    field_control_key,
    field_device,
    field_port,
    led_line_profile,
    project,
    room,
    topology_migration_review,
)
from nl_project_2.persistence.uow import UnitOfWork

from .models import (
    ChangeClass,
    DwgScanProgress,
    DwgWritePlan,
    DwgWriteTarget,
    ScanProposal,
    SyncChange,
    SyncOwnerKind,
    SyncSummary,
    WriteExecutionReceipt,
    WriteResult,
)
from .reconciliation import (
    ROUTE_FIELDS,
    NormalizedCadSnapshot,
    normalize_validated_snapshot,
    reconcile_snapshot_edge_projections,
)
from .selection import atomic_line_import_groups

PROJECT_TO_DWG_ALLOW_LIST = frozenset(
    {
        "DEVICE_NAME",
        "BUILDING",
        "ROOM",
        "MOUNT_HEIGHT",
        "CABLE_ID",
        "CABLE_TYPE",
        "BOARD",
        "CABLE_SOURCE",
        "BOX_ID",
        "BUS_POINT_ID",
        "BUS_SOURCE",
        "BUS_CABLE_TYPE",
        "BUS_MOUNT_WAY",
        "BUS_GOFRA_TYPE",
        "BUS_GOFRA_COLOR",
        "BUS_GOFRA_ID",
        "LOAD_TYPE",
        "LOAD_NAME",
        "CALC_POWER",
        "LENGTH",
        "LED_TYPE",
        "PHASE",
        "BOARD_ID",
        "KEY_1",
        "KEY_2",
        "KEY_3",
        "KEY_4",
        "DALI_GROUP_ID",
        "COMMENT_1",
        "COMMENT_2",
        "MOUNT_WAY",
        "GOFRA_TYPE",
        "GOFRA_COLOR",
        "GOFRA_ID",
        "W1",
        "W2",
        "COM1",
        "COM2",
        "K1",
        "K2",
        "IN_1",
        "IN_2",
    }
)
CAD_SCAN_DEADLINE_SECONDS = 120.0
LINE_WIDE_FIELDS = frozenset({"CABLE_TYPE", "BOARD", "LED_TYPE", "LOAD_NAME"})
SEGMENT_OWNED_FIELDS = frozenset(ROUTE_FIELDS)
OBSERVED_FIELDS = ("BLOCK_NAME", "LAYER", "X", "Y")


class DwgSyncError(RuntimeError):
    pass


class StaleProposalError(DwgSyncError):
    pass


class DwgSyncService:
    def __init__(self, engine: Engine, cad_port=None) -> None:
        self._engine = engine
        self._cad_port = cad_port
        self._contract = load_contract()
        self._validator = CadContractValidator(self._contract)

    def scan_active(
        self,
        *,
        project_id: str,
        expected_identity: str = "",
        progress: Callable[[DwgScanProgress], None] | None = None,
    ) -> ScanProposal:
        if self._cad_port is None:
            raise DwgSyncError("CAD adapter is not configured")
        if not expected_identity.strip():
            raise DwgSyncError("Target DWG identity must be confirmed before scanning")
        emit = progress or (lambda _event: None)
        emit(DwgScanProgress("CONNECTING"))
        emit(DwgScanProgress("SCANNING"))
        batch = self._cad_port.read_observations(
            CadReadRequest(
                expected_identity,
                deadline_seconds=CAD_SCAN_DEADLINE_SECONDS,
                definition_names=tuple(self._contract.blocks),
            )
        )
        emit(DwgScanProgress("VALIDATING"))
        return self.preview(project_id=project_id, batch=batch, progress=emit)

    def inspect_active_document(self):
        if self._cad_port is None:
            raise DwgSyncError("CAD adapter is not configured")
        return self._cad_port.inspect_active_document(deadline_seconds=15.0)

    def preview(
        self,
        *,
        project_id: str,
        batch: CadObservationBatch,
        progress: Callable[[DwgScanProgress], None] | None = None,
    ) -> ScanProposal:
        validation = self._validator.validate(batch)
        if progress is not None:
            progress(DwgScanProgress("FORMING_CHANGES"))
        snapshot = normalize_validated_snapshot(validation.observations)
        with self._engine.connect() as connection:
            revision = connection.scalar(
                select(project.c.project_revision).where(project.c.id == project_id)
            )
            if revision is None:
                raise DwgSyncError("Project not found")
            binding_row = (
                connection.execute(
                    select(dwg_document_binding).where(
                        dwg_document_binding.c.project_id == project_id,
                        dwg_document_binding.c.application_uuid
                        == _application_uuid(batch.document_identity),
                    )
                )
                .mappings()
                .one_or_none()
            )
            binding_id = None if binding_row is None else binding_row["id"]
            devices: dict[str, dict[str, Any]] = {}
            baselines: dict[str, Any] = {}
            if binding_id:
                devices = {
                    row["entity_handle"]: dict(row["normalized_fields_json"] or {})
                    for row in connection.execute(
                        select(
                            field_device.c.entity_handle,
                            field_device.c.normalized_fields_json,
                        ).where(
                            field_device.c.project_id == project_id,
                            field_device.c.dwg_document_binding_id == binding_id,
                            field_device.c.lifecycle == "ACTIVE",
                        )
                    ).mappings()
                }
                baselines = {
                    row["field_path"]: row["accepted_value_json"]
                    for row in connection.execute(
                        select(
                            dwg_baseline.c.field_path,
                            dwg_baseline.c.accepted_value_json,
                        ).where(
                            dwg_baseline.c.project_id == project_id,
                            dwg_baseline.c.dwg_document_binding_id == binding_id,
                        )
                    ).mappings()
                }
            for fact in snapshot.facts:
                legacy_path = _legacy_box_owner_path(
                    fact.owner_key, fact.field, devices.get(fact.primary_handle, {})
                )
                if legacy_path in baselines and fact.owner_path not in baselines:
                    baselines[fact.owner_path] = baselines[legacy_path]
            project_owner_values = _load_project_owner_values(
                connection,
                project_id=project_id,
                snapshot=snapshot,
                devices=devices,
                baselines=baselines,
            )
            snapshot = reconcile_snapshot_edge_projections(snapshot, baselines)
            display_contexts = _preview_display_contexts(
                connection,
                project_id=project_id,
                binding_id=binding_id,
                observations=validation.observations,
            )

        valid_by_handle = {
            item.observation.handle: item
            for item in validation.observations
            if not item.ignored_project_data
        }
        changes: list[SyncChange] = []
        issues_by_handle: dict[str, list] = defaultdict(list)
        for issue in validation.issues:
            if issue.handle:
                issues_by_handle[issue.handle].append(issue)
        invalid_handles = {
            issue.handle for issue in validation.issues if issue.blocks_acceptance and issue.handle
        }
        for handle in sorted(invalid_handles):
            changes.append(
                SyncChange(
                    f"{handle}:$",
                    handle,
                    "$",
                    None,
                    devices.get(handle),
                    _fields(valid_by_handle[handle]) if handle in valid_by_handle else None,
                    ChangeClass.INVALID_DWG_DATA,
                    _validation_reason(issues_by_handle[handle]),
                    SyncOwnerKind.INSERTION,
                    handle,
                    f"insertion:{handle}:$",
                    (handle,),
                )
            )
        new_handles: set[str] = set()
        for handle, item in sorted(valid_by_handle.items()):
            if handle in invalid_handles:
                continue
            if handle not in devices:
                new_handles.add(handle)
                dwg_fields = _fields(item)
                changes.append(
                    SyncChange(
                        f"{handle}:$",
                        handle,
                        "$",
                        None,
                        None,
                        dwg_fields,
                        ChangeClass.NEW_DWG_INSERTION,
                        "DWG Handle has no confirmed Project counterpart",
                        SyncOwnerKind.INSERTION,
                        handle,
                        f"insertion:{handle}:$",
                        (handle,),
                        structural=True,
                    )
                )
        for fact in snapshot.facts:
            if fact.primary_handle in invalid_handles:
                continue
            all_handles_are_new = bool(fact.affected_handles) and all(
                handle in new_handles for handle in fact.affected_handles
            )
            existing_line_load_name = (
                fact.field == "LOAD_NAME"
                and fact.owner_kind is SyncOwnerKind.BASE_LINE
                and fact.owner_path in project_owner_values
            )
            if all_handles_are_new and not existing_line_load_name:
                continue
            project_value = project_owner_values.get(fact.owner_path)
            baseline = baselines.get(fact.owner_path)
            if baseline is None:
                baseline = baselines.get(f"{fact.primary_handle}:{fact.field}")
            if (
                all_handles_are_new
                and existing_line_load_name
                and baseline is None
                and project_value == ""
            ):
                baseline = ""
            status, reason = _classify(baseline, project_value, fact.value)
            detail_status = (
                "BOTH_CHANGED_SAME"
                if reason == "Both sides changed to the same normalized value"
                else ""
            )
            if fact.structural and status not in {
                ChangeClass.EQUAL,
            }:
                status = ChangeClass.IDENTITY_COLLISION
                detail_status = "STRUCTURAL_IDENTITY_REVIEW"
                reason = "Structural identity/topology change requires explicit structural apply"
            changes.append(
                SyncChange(
                    f"{fact.primary_handle}:{fact.field}",
                    fact.primary_handle,
                    fact.field,
                    baseline,
                    project_value,
                    fact.value,
                    status,
                    reason,
                    fact.owner_kind,
                    fact.owner_key,
                    fact.owner_path,
                    fact.affected_handles,
                    fact.structural,
                    detail_status,
                )
            )
        for review in snapshot.structural_reviews:
            base = review.split(":", 1)[0]
            dual_projection = ":DUAL_PROJECTION_CONFLICT:" in review
            handles = tuple(
                sorted(
                    item.observation.handle
                    for item in validation.observations
                    if item.read_payload is not None
                    and item.read_payload.cable_identity is not None
                    and item.read_payload.cable_identity.base == base
                )
            )
            changes.append(
                SyncChange(
                    f"structural:{review}",
                    handles[0] if handles else "",
                    "$STRUCTURE",
                    None,
                    None,
                    review,
                    ChangeClass.IDENTITY_COLLISION,
                    (
                        "Port field and downstream CABLE_SOURCE describe "
                        "incompatible physical edges"
                        if dual_projection
                        else "Topology adjacency cannot be inferred from explicit planning facts"
                    ),
                    SyncOwnerKind.BASE_LINE,
                    base,
                    f"structure:{review}",
                    handles,
                    True,
                    (
                        "DUAL_PROJECTION_REQUIRES_ATTENTION"
                        if dual_projection
                        else "STRUCTURAL_IDENTITY_REVIEW"
                    ),
                )
            )
        for handle, values in sorted(devices.items()):
            if handle not in valid_by_handle:
                changes.append(
                    SyncChange(
                        f"{handle}:$",
                        handle,
                        "$",
                        None,
                        values,
                        None,
                        ChangeClass.MISSING_DWG_INSERTION,
                        "A previously confirmed Handle is absent; Project data is preserved",
                        SyncOwnerKind.INSERTION,
                        handle,
                        f"insertion:{handle}:$",
                        (handle,),
                        True,
                    )
                )
        missing_by_identity: dict[tuple[str, str], list[str]] = defaultdict(list)
        for handle, values in devices.items():
            if handle in valid_by_handle:
                continue
            identity = str(values.get("CABLE_ID", ""))
            block_name = str(values.get("BLOCK_NAME", ""))
            if identity:
                missing_by_identity[(identity, block_name)].append(handle)
        for handle in sorted(new_handles):
            item = valid_by_handle[handle]
            identity = item.normalized_attributes.get("CABLE_ID", "")
            candidates = missing_by_identity.get((identity, item.observation.effective_name), [])
            if len(candidates) == 1:
                old_handle = candidates[0]
                changes.append(
                    SyncChange(
                        f"remap:{old_handle}->{handle}",
                        handle,
                        "$HANDLE_REMAP",
                        old_handle,
                        old_handle,
                        handle,
                        ChangeClass.IDENTITY_COLLISION,
                        "A strong unique subject candidate exists; remap is never automatic",
                        SyncOwnerKind.INSERTION,
                        f"{old_handle}->{handle}",
                        f"remap:{old_handle}->{handle}",
                        (old_handle, handle),
                        True,
                        "STRUCTURAL_IDENTITY_REVIEW",
                    )
                )

        counts = Counter(change.change_class for change in changes)
        summary = SyncSummary(
            new=counts[ChangeClass.NEW_DWG_INSERTION],
            changed=counts[ChangeClass.DWG_CHANGED] + counts[ChangeClass.PROJECT_CHANGED],
            missing=counts[ChangeClass.MISSING_DWG_INSERTION],
            invalid=counts[ChangeClass.INVALID_DWG_DATA],
            conflicts=counts[ChangeClass.BOTH_CHANGED_CONFLICT],
        )
        return ScanProposal(
            project_id=project_id,
            batch=batch,
            changes=tuple(
                replace(
                    change,
                    display_context=display_contexts.get(change.handle, {}),
                )
                for change in changes
            ),
            issues=validation.issues,
            summary=summary,
            project_revision=int(revision),
            binding_id=binding_id,
        )

    def apply_dwg_to_project(
        self,
        proposal: ScanProposal,
        *,
        selected_paths: Iterable[str],
        confirmed: bool,
        allow_structural: bool = False,
        failure_hook: Callable[[], None] | None = None,
    ) -> str:
        if not confirmed:
            raise DwgSyncError("Explicit user confirmation is required")
        selected = set(selected_paths)
        if not selected:
            raise DwgSyncError("At least one preview item must be selected")
        applicable = {
            change.field_path
            for change in proposal.changes
            if change.change_class
            in {
                ChangeClass.NEW_DWG_INSERTION,
                ChangeClass.DWG_CHANGED,
                ChangeClass.BOTH_CHANGED_CONFLICT,
                ChangeClass.IDENTITY_COLLISION,
            }
            and (change.change_class is not ChangeClass.IDENTITY_COLLISION or change.structural)
            and (
                change.change_class is ChangeClass.NEW_DWG_INSERTION
                or not change.field.startswith("$")
            )
        }
        if not selected <= applicable:
            raise DwgSyncError("Selection contains a non-applicable or implicit change")
        selected_handles = {
            handle
            for change in proposal.changes
            if change.field_path in selected
            for handle in (change.affected_handles or (change.handle,))
        }
        if any(
            change.detail_status == "DUAL_PROJECTION_REQUIRES_ATTENTION"
            and selected_handles.intersection(change.affected_handles)
            for change in proposal.changes
        ):
            raise DwgSyncError(
                "Conflicting port/CABLE_SOURCE projections require attention; no silent winner"
            )
        if not allow_structural and any(
            change.field_path in selected and change.detail_status == "STRUCTURAL_IDENTITY_REVIEW"
            for change in proposal.changes
        ):
            raise DwgSyncError("Structural identity changes require explicit structural apply")
        self._check_selected_validation(proposal, selected)
        self._check_project_selection(proposal, selected)

        validated = {
            item.observation.handle: item
            for item in self._validator.validate(proposal.batch).observations
            if not item.ignored_project_data
        }
        snapshot = normalize_validated_snapshot(tuple(validated.values()))
        snapshot = reconcile_snapshot_edge_projections(
            snapshot,
            {
                change.owner_path: change.baseline_value
                for change in proposal.changes
                if change.owner_path
            },
        )
        by_path = {change.field_path: change for change in proposal.changes}
        expanded_selected = set(selected)
        active_handles: set[str] = set()
        for path in selected:
            change = by_path[path]
            active_handles.update(change.affected_handles or (change.handle,))
            if change.field != "$":
                expanded_selected.update(
                    f"{handle}:{change.field}"
                    for handle in (change.affected_handles or (change.handle,))
                )
            if change.owner_kind is SyncOwnerKind.FIELD_PORT:
                port = next(
                    (
                        item
                        for item in snapshot.ports
                        if item.handle == change.handle and item.tag == change.field
                    ),
                    None,
                )
                related_identities = {
                    str(value)
                    for value in (
                        None if port is None else port.value,
                        change.baseline_value,
                        change.project_value,
                    )
                    if value
                }
                for point in snapshot.points:
                    if point.logical_identity in related_identities:
                        active_handles.update(point.handles)
        load_name_only = all(
            by_path[path].field == "LOAD_NAME"
            and by_path[path].owner_kind is SyncOwnerKind.BASE_LINE
            for path in selected
        )
        now = datetime.now(UTC)
        with UnitOfWork(self._engine) as uow:
            current_revision = uow.execute(
                select(project.c.project_revision).where(project.c.id == proposal.project_id)
            ).scalar_one()
            if current_revision != proposal.project_revision:
                raise StaleProposalError("Project changed after preview")
            self._check_baseline_preconditions(uow, proposal, selected)
            binding_id = self._ensure_binding(uow, proposal, now)
            scan_id, observations = self._persist_scan(uow, proposal, binding_id, now)
            if load_name_only:
                self._apply_load_name_only(
                    uow,
                    project_id=proposal.project_id,
                    binding_id=binding_id,
                    changes=(by_path[path] for path in selected),
                    now=now,
                )
                active_handles.clear()
            board_ids = self._upsert_boards(uow, proposal.project_id, validated, active_handles)
            line_ids = self._upsert_lines(
                uow,
                proposal.project_id,
                validated,
                board_ids,
                expanded_selected,
                active_handles,
            )
            self._materialize_led_profiles(
                uow,
                project_id=proposal.project_id,
                snapshot=snapshot,
                line_ids=line_ids,
                active_handles=active_handles,
            )
            device_ids = self._upsert_devices(
                uow,
                proposal.project_id,
                binding_id,
                validated,
                expanded_selected,
                active_handles,
            )
            all_snapshot_handles = {item.observation.handle for item in validated.values()}
            for row in uow.execute(
                select(field_device.c.id, field_device.c.entity_handle).where(
                    field_device.c.project_id == proposal.project_id,
                    field_device.c.dwg_document_binding_id == binding_id,
                    field_device.c.entity_handle.in_(all_snapshot_handles),
                    field_device.c.lifecycle == "ACTIVE",
                )
            ).mappings():
                device_ids.setdefault(row["entity_handle"], row["id"])
            if not load_name_only:
                self._materialize_snapshot(
                    uow,
                    proposal.project_id,
                    snapshot,
                    line_ids,
                    device_ids,
                    observations,
                    active_handles,
                )
            operation_id = new_id()
            correlation_id = new_id()
            uow.execute(
                dwg_sync_operation.insert().values(
                    id=operation_id,
                    project_id=proposal.project_id,
                    dwg_document_binding_id=binding_id,
                    direction="DWG_TO_PROJECT",
                    selection_json=sorted(selected),
                    result_json={"status": "APPLIED", "scan_id": scan_id},
                    correlation_id=correlation_id,
                    created_at_utc=now,
                )
            )
            for change in proposal.changes:
                if change.field_path not in selected:
                    continue
                self._record_change(uow, proposal.project_id, operation_id, change, "ACCEPT_DWG")
            if failure_hook:
                failure_hook()
            uow.execute(
                update(project)
                .where(project.c.id == proposal.project_id)
                .values(
                    project_revision=project.c.project_revision + 1,
                    updated_at_utc=now,
                )
            )
            new_revision = proposal.project_revision + 1
            self._replace_baselines(
                uow,
                proposal,
                binding_id,
                scan_id,
                new_revision,
                selected,
                validated,
                snapshot,
            )
            uow.execute(
                update(dwg_scan)
                .where(dwg_scan.c.id == scan_id)
                .values(completed_at_utc=now, status="ACCEPTED")
            )
            uow.commit()
        return operation_id

    def write_project_to_dwg(
        self,
        proposal: ScanProposal,
        *,
        selected_paths: Iterable[str],
        confirmed: bool,
        bridge=None,
    ) -> WriteResult:
        plan = self.plan_project_to_dwg(proposal, selected_paths=selected_paths)
        receipt = self.execute_write_plan(
            plan,
            confirmed=confirmed,
            bridge=bridge,
        )
        if receipt.result is None:
            return WriteResult(
                document_identity=plan.document_identity,
                readback=tuple(
                    {
                        "handle": handle,
                        "tag": tag,
                        "value": next(
                            target.new_value
                            for target in plan.targets
                            if target.handle == handle and target.tag == tag
                        ),
                    }
                    for handle, tag in receipt.completed_targets
                ),
                no_save_confirmed=receipt.no_save_confirmed,
                document_saved=receipt.document_saved,
                status=receipt.status,
                failures=receipt.failed_targets,
            )
        return receipt.result

    def plan_project_to_dwg(
        self,
        proposal: ScanProposal,
        *,
        selected_paths: Iterable[str],
    ) -> DwgWritePlan:
        selected = set(selected_paths)
        by_path = {change.field_path: change for change in proposal.changes}
        if not selected or not selected <= set(by_path):
            raise DwgSyncError("Unknown write selection")
        if proposal.binding_id is None:
            raise DwgSyncError("A confirmed DWG binding/baseline is required before write-back")
        self._validate_project_write_snapshot(
            proposal,
            tuple(by_path[path] for path in sorted(selected)),
        )
        observations = {item.handle: item for item in proposal.batch.observations if item.handle}
        targets: list[DwgWriteTarget] = []
        for path in sorted(selected):
            change = by_path[path]
            if change.field not in PROJECT_TO_DWG_ALLOW_LIST:
                raise DwgSyncError(f"Project to DWG is forbidden for {change.field}")
            if change.change_class not in {
                ChangeClass.PROJECT_CHANGED,
                ChangeClass.BOTH_CHANGED_CONFLICT,
                ChangeClass.IDENTITY_COLLISION,
            }:
                raise DwgSyncError(f"{path} is not a Project-originated change")
            handles = change.affected_handles or (change.handle,)
            for handle in handles:
                observation = observations.get(handle)
                if observation is None:
                    raise DwgSyncError(f"Write target Handle {handle} is absent from the scan")
                attributes = {item.tag: item.value for item in observation.raw_attributes}
                if change.field not in attributes:
                    raise DwgSyncError(f"Handle {handle} has no canonical {change.field} attribute")
                targets.append(
                    DwgWriteTarget(
                        proposal.batch.document_identity,
                        handle,
                        change.field,
                        attributes[change.field],
                        "" if change.project_value is None else str(change.project_value),
                        observation.effective_name,
                        observation.layer,
                        change.owner_kind,
                        change.owner_key,
                        change.owner_path or change.field_path,
                        change.reason,
                    )
                )
        unique: dict[tuple[str, str], DwgWriteTarget] = {}
        for target in targets:
            key = (target.handle, target.tag)
            if key in unique and unique[key] != target:
                raise DwgSyncError(f"Conflicting write targets for {target.handle}/{target.tag}")
            unique[key] = target
        ordered = tuple(sorted(unique.values(), key=lambda item: (item.handle, item.tag)))
        self._check_line_wide_selection(
            [target.bridge_command() for target in ordered], observations
        )
        plan_id = new_id()
        correlation_id = new_id()
        fingerprint = _write_plan_fingerprint(
            project_id=proposal.project_id,
            binding_id=proposal.binding_id,
            document_identity=proposal.batch.document_identity,
            project_revision=proposal.project_revision,
            selected=selected,
            targets=ordered,
        )
        return DwgWritePlan(
            plan_id,
            correlation_id,
            proposal.project_id,
            proposal.binding_id,
            proposal.batch.document_identity,
            proposal.project_revision,
            tuple(sorted(selected)),
            ordered,
            fingerprint,
        )

    def _validate_project_write_snapshot(
        self, proposal: ScanProposal, changes: tuple[SyncChange, ...]
    ) -> None:
        overrides: dict[tuple[str, str], str] = {}
        selected_handles: set[str] = set()
        for change in changes:
            for handle in change.affected_handles or (change.handle,):
                overrides[(handle, change.field)] = (
                    "" if change.project_value is None else str(change.project_value)
                )
                selected_handles.add(handle)
        rewritten = []
        for observation in proposal.batch.observations:
            attributes = {
                item.tag: overrides.get((observation.handle, item.tag), item.value)
                for item in observation.raw_attributes
            }
            rewritten.append(
                type(observation).from_mapping(
                    effective_name=observation.effective_name,
                    layer=observation.layer,
                    raw_attributes=attributes,
                    x=observation.x,
                    y=observation.y,
                    handle=observation.handle,
                    definition=observation.definition,
                )
            )
        validation = self._validator.validate(
            CadObservationBatch(
                proposal.batch.document_identity,
                tuple(rewritten),
                proposal.batch.source_metadata,
            )
        )
        blocking = [
            issue
            for issue in validation.issues
            if issue.blocks_acceptance
            and (
                issue.handle is None
                or issue.handle in selected_handles
                or bool(set(issue.related_handles) & selected_handles)
            )
        ]
        if blocking:
            raise DwgSyncError(
                "Planned Project values failed full CAD contract validation: "
                + _validation_reason(blocking)
            )

    def execute_write_plan(
        self,
        plan: DwgWritePlan,
        *,
        confirmed: bool,
        bridge=None,
    ) -> WriteExecutionReceipt:
        if not confirmed:
            raise DwgSyncError("Explicit user confirmation is required")
        expected_fingerprint = _write_plan_fingerprint(
            project_id=plan.project_id,
            binding_id=plan.binding_id,
            document_identity=plan.document_identity,
            project_revision=plan.project_revision,
            selected=set(plan.selected_paths),
            targets=plan.targets,
        )
        if expected_fingerprint != plan.fingerprint:
            raise DwgSyncError("Closed write plan fingerprint mismatch")
        adapter = bridge or self._cad_port
        if adapter is None or not hasattr(adapter, "write_attributes"):
            raise DwgSyncError("Writable CAD adapter is not configured")
        with self._engine.connect() as connection:
            current_revision = connection.scalar(
                select(project.c.project_revision).where(project.c.id == plan.project_id)
            )
            current_binding = connection.scalar(
                select(dwg_document_binding.c.id).where(
                    dwg_document_binding.c.id == plan.binding_id,
                    dwg_document_binding.c.project_id == plan.project_id,
                    dwg_document_binding.c.application_uuid
                    == _application_uuid(plan.document_identity),
                )
            )
        if current_revision != plan.project_revision or current_binding != plan.binding_id:
            raise StaleProposalError("Write plan preconditions are stale")
        previous = self._write_attempts(plan)
        completed = {
            tuple(item) for attempt in previous for item in attempt.get("completed_targets", [])
        }
        remaining = [
            target for target in plan.targets if (target.handle, target.tag) not in completed
        ]
        if not remaining:
            return WriteExecutionReceipt(
                plan.plan_id,
                plan.correlation_id,
                "READ_BACK_OK",
                tuple(sorted(completed)),
                (),
                all(attempt.get("no_save_confirmed", False) for attempt in previous),
                any(attempt.get("document_saved", False) for attempt in previous),
                None,
            )
        result = adapter.write_attributes(
            document_identity=plan.document_identity,
            changes=[target.bridge_command() for target in remaining],
            deadline_seconds=15.0,
        )
        if result.document_identity != plan.document_identity:
            raise DwgSyncError("Bridge returned a different DWG document identity")
        readback = {
            (str(item["handle"]), str(item["tag"])): str(item["value"]) for item in result.readback
        }
        newly_completed: set[tuple[str, str]] = set()
        failures = list(result.failures)
        for target in remaining:
            actual = readback.get((target.handle, target.tag))
            if actual == target.new_value:
                newly_completed.add((target.handle, target.tag))
            else:
                failures.append(
                    {
                        "handle": target.handle,
                        "tag": target.tag,
                        "reason": "READBACK_MISSING" if actual is None else "READBACK_MISMATCH",
                        "expected": target.new_value,
                        "actual": "" if actual is None else actual,
                    }
                )
        completed.update(newly_completed)
        status = (
            "READ_BACK_OK"
            if len(completed) == len(plan.targets)
            and result.no_save_confirmed
            and not result.document_saved
            and not failures
            else "PARTIAL"
        )
        attempt_number = len(previous) + 1
        correlation_id = (
            plan.correlation_id
            if attempt_number == 1
            else str(uuid.uuid5(uuid.NAMESPACE_URL, f"{plan.correlation_id}:{attempt_number}"))
        )
        self._record_write_plan_attempt(
            plan,
            correlation_id=correlation_id,
            attempted=remaining,
            newly_completed=newly_completed,
            all_completed=completed,
            failures=tuple(failures),
            result=result,
            status=status,
        )
        return WriteExecutionReceipt(
            plan.plan_id,
            correlation_id,
            status,
            tuple(sorted(completed)),
            tuple(failures),
            result.no_save_confirmed,
            result.document_saved,
            result,
        )

    def _ensure_binding(self, uow, proposal: ScanProposal, now: datetime) -> str:
        if proposal.binding_id:
            return proposal.binding_id
        binding_id = new_id()
        identity = proposal.batch.document_identity
        uow.execute(
            dwg_document_binding.insert().values(
                id=binding_id,
                project_id=proposal.project_id,
                application_uuid=_application_uuid(identity),
                normalized_last_path=identity.casefold(),
                document_signature=identity,
                fingerprint=_fingerprint(identity),
                confirmed_at_utc=now,
                status="CONFIRMED",
            )
        )
        return binding_id

    def _persist_scan(self, uow, proposal, binding_id, now):
        scan_id = new_id()
        payload = _batch_payload(proposal.batch)
        metadata = dict(proposal.batch.source_metadata)
        uow.execute(
            dwg_scan.insert().values(
                id=scan_id,
                project_id=proposal.project_id,
                dwg_document_binding_id=binding_id,
                adapter_version=str(metadata.get("adapter_version", "UNKNOWN")),
                protocol_version=str(metadata.get("protocol_version", "UNKNOWN")),
                contract_version=self._contract.contract_version,
                started_at_utc=now,
                document_facts_json=metadata,
                content_sha256=hashlib.sha256(payload).hexdigest(),
                status="PENDING",
            )
        )
        ids: dict[str, str] = {}
        issues_by_handle: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
        for issue in proposal.issues:
            issues_by_handle[issue.handle].append(
                {
                    "code": issue.code,
                    "message": issue.message,
                    "severity": issue.severity,
                    "blocks_acceptance": issue.blocks_acceptance,
                    "field": issue.field,
                }
            )
        for observation in proposal.batch.observations:
            if observation.effective_name == "ROOM_NAME":
                continue
            observation_id = new_id()
            ids[observation.handle] = observation_id
            uow.execute(
                dwg_observation.insert().values(
                    id=observation_id,
                    project_id=proposal.project_id,
                    dwg_scan_id=scan_id,
                    entity_handle=observation.handle,
                    effective_block_name=observation.effective_name,
                    layer_name=observation.layer,
                    space_name="MODEL",
                    geometry_json={"x": observation.x, "y": observation.y},
                    raw_attributes_json={
                        item.tag: item.value for item in observation.raw_attributes
                    },
                    diagnostics_json=issues_by_handle.get(observation.handle, []),
                )
            )
        return scan_id, ids

    def _upsert_boards(self, uow, project_id, validated, active_handles):
        result: dict[str, str] = {}
        for handle, item in validated.items():
            if handle not in active_handles:
                continue
            if item.device_type != "BOARD":
                continue
            designation = item.normalized_attributes.get("BOARD_ID", "")
            existing = uow.execute(
                select(board.c.id).where(
                    board.c.project_id == project_id,
                    board.c.designation == designation,
                    board.c.lifecycle == "ACTIVE",
                )
            ).scalar_one_or_none()
            if existing is None:
                existing = new_id()
                uow.execute(
                    board.insert().values(
                        id=existing,
                        project_id=project_id,
                        designation=designation,
                        board_kind=item.normalized_attributes.get("LOAD_TYPE", "BOARD"),
                        title=item.normalized_attributes.get("DEVICE_NAME"),
                    )
                )
            result[designation] = existing
        return result

    def _upsert_lines(self, uow, project_id, validated, board_ids, selected, active_handles):
        grouped: dict[str, list[ValidatedObservation]] = defaultdict(list)
        for handle, item in validated.items():
            if handle not in active_handles:
                continue
            cable_id = item.normalized_attributes.get("CABLE_ID", "")
            if cable_id:
                grouped[cable_id.split(".", 1)[0]].append(item)
        result: dict[str, str] = {}
        for designation, items in grouped.items():
            existing = (
                uow.execute(
                    select(cable_line).where(
                        cable_line.c.project_id == project_id,
                        cable_line.c.designation == designation,
                        cable_line.c.lifecycle == "ACTIVE",
                    )
                )
                .mappings()
                .one_or_none()
            )
            sample = items[0]
            facts = dict(existing["cable_facts_json"] or {}) if existing else {}
            for field in SEGMENT_OWNED_FIELDS:
                facts.pop(field, None)
            for field in LINE_WIDE_FIELDS:
                if field == "LED_TYPE":
                    continue
                if existing is None or any(
                    f"{item.observation.handle}:{field}" in selected
                    or f"{item.observation.handle}:$" in selected
                    for item in items
                ):
                    facts[field] = sample.normalized_attributes.get(field)
            facts["FUNCTION_GROUP"] = sample.function_group
            board_id = board_ids.get(
                sample.normalized_attributes.get("BOARD", ""),
                existing["board_id"] if existing else None,
            )
            if existing:
                identifier = existing["id"]
                uow.execute(
                    update(cable_line)
                    .where(cable_line.c.id == identifier)
                    .values(cable_facts_json=facts, board_id=board_id)
                )
            else:
                identifier = new_id()
                uow.execute(
                    cable_line.insert().values(
                        id=identifier,
                        project_id=project_id,
                        designation=designation,
                        system_kind=sample.function_group or "UNKNOWN",
                        board_id=board_id,
                        cable_facts_json=facts,
                    )
                )
            result[designation] = identifier
        return result

    def _apply_load_name_only(
        self,
        uow,
        *,
        project_id: str,
        binding_id: str,
        changes: Iterable[SyncChange],
        now: datetime,
    ) -> None:
        """Update only the accepted line name and its existing insertion evidence."""

        for change in changes:
            line_row = (
                uow.execute(
                    select(cable_line).where(
                        cable_line.c.project_id == project_id,
                        cable_line.c.designation == change.owner_key,
                        cable_line.c.lifecycle == "ACTIVE",
                    )
                )
                .mappings()
                .one_or_none()
            )
            if line_row is None:
                raise DwgSyncError(
                    f"LOAD_NAME-only apply requires existing line {change.owner_key}"
                )
            facts = dict(line_row["cable_facts_json"] or {})
            facts["LOAD_NAME"] = change.dwg_value
            uow.execute(
                update(cable_line)
                .where(cable_line.c.id == line_row["id"])
                .values(
                    cable_facts_json=facts,
                    updated_at_utc=now,
                    row_version=cable_line.c.row_version + 1,
                )
            )
            for device_row in uow.execute(
                select(field_device).where(
                    field_device.c.project_id == project_id,
                    field_device.c.dwg_document_binding_id == binding_id,
                    field_device.c.entity_handle.in_(change.affected_handles),
                    field_device.c.lifecycle == "ACTIVE",
                )
            ).mappings():
                fields = dict(device_row["normalized_fields_json"] or {})
                fields["LOAD_NAME"] = change.dwg_value
                uow.execute(
                    update(field_device)
                    .where(field_device.c.id == device_row["id"])
                    .values(
                        normalized_fields_json=fields,
                        updated_at_utc=now,
                        row_version=field_device.c.row_version + 1,
                    )
                )

    def _materialize_led_profiles(
        self, uow, *, project_id, snapshot, line_ids, active_handles
    ) -> None:
        for fact in snapshot.facts:
            if (
                fact.owner_kind is not SyncOwnerKind.BASE_LINE
                or fact.field != "LED_TYPE"
                or fact.owner_key not in line_ids
                or not (set(fact.affected_handles) & active_handles)
            ):
                continue
            led_kind, channels, _conductors = normalize_led_type(str(fact.value))
            existing = (
                uow.execute(
                    select(led_line_profile).where(
                        led_line_profile.c.project_id == project_id,
                        led_line_profile.c.cable_line_id == line_ids[fact.owner_key],
                    )
                )
                .mappings()
                .one_or_none()
            )
            values = {
                "led_kind": led_kind,
                "channels": channels,
                "led_type_origin": "DWG",
                "sync_baseline_json": {"LED_TYPE": led_kind},
                "sync_state": "IN_SYNC",
                "updated_at_utc": datetime.now(UTC),
            }
            if existing is None:
                uow.execute(
                    led_line_profile.insert().values(
                        id=new_id(),
                        project_id=project_id,
                        cable_line_id=line_ids[fact.owner_key],
                        **values,
                    )
                )
            else:
                uow.execute(
                    update(led_line_profile)
                    .where(led_line_profile.c.id == existing["id"])
                    .values(**values, row_version=led_line_profile.c.row_version + 1)
                )

    def _upsert_devices(self, uow, project_id, binding_id, validated, selected, active_handles):
        result: dict[str, str] = {}
        for handle, item in validated.items():
            if handle not in active_handles:
                continue
            existing = (
                uow.execute(
                    select(field_device).where(
                        field_device.c.project_id == project_id,
                        field_device.c.dwg_document_binding_id == binding_id,
                        field_device.c.entity_handle == handle,
                        field_device.c.lifecycle == "ACTIVE",
                    )
                )
                .mappings()
                .one_or_none()
            )
            dwg_fields = _fields(item)
            values = dict(existing["normalized_fields_json"] or {}) if existing else {}
            if existing is None or f"{handle}:$" in selected:
                values.update(dwg_fields)
            else:
                for field, value in dwg_fields.items():
                    if f"{handle}:{field}" in selected:
                        values[field] = value
            room_fields_selected = (
                existing is None
                or f"{handle}:$" in selected
                or f"{handle}:ROOM" in selected
                or f"{handle}:BUILDING" in selected
            )
            room_id = (
                self._ensure_room(uow, project_id, values)
                if room_fields_selected
                else existing["room_id"]
            )
            if existing:
                identifier = existing["id"]
                uow.execute(
                    update(field_device)
                    .where(field_device.c.id == identifier)
                    .values(
                        block_kind=item.observation.effective_name,
                        room_id=room_id,
                        normalized_fields_json=values,
                        row_version=field_device.c.row_version + 1,
                        updated_at_utc=datetime.now(UTC),
                    )
                )
            else:
                identifier = new_id()
                uow.execute(
                    field_device.insert().values(
                        id=identifier,
                        project_id=project_id,
                        block_kind=item.observation.effective_name,
                        room_id=room_id,
                        normalized_fields_json=values,
                        dwg_document_binding_id=binding_id,
                        entity_handle=handle,
                    )
                )
            result[handle] = identifier
        return result

    def _ensure_room(self, uow, project_id, values):
        building_name = str(values.get("BUILDING", "")).strip()
        room_name = str(values.get("ROOM", "")).strip()
        if not building_name or not room_name:
            return None
        building_rows = list(
            uow.execute(
                select(building.c.id, building.c.name).where(building.c.project_id == project_id)
            ).mappings()
        )
        building_matches = [
            item
            for item in building_rows
            if normalize_room_name(item["name"]) == normalize_room_name(building_name)
        ]
        if len(building_matches) != 1:
            return None
        building_id = building_matches[0]["id"]
        room_rows = list(
            uow.execute(
                select(room.c.id, room.c.name).where(
                    room.c.project_id == project_id,
                    room.c.building_id == building_id,
                )
            ).mappings()
        )
        resolution = resolve_room(
            (RoomIdentity(item["id"], item["name"]) for item in room_rows),
            room_name,
        )
        return resolution.room_id

    def _materialize_snapshot(
        self,
        uow,
        project_id: str,
        snapshot: NormalizedCadSnapshot,
        line_ids: dict[str, str],
        device_ids: dict[str, str],
        observations: dict[str, str],
        active_handles: set[str],
    ) -> None:
        """Materialize validated points/edges/keys/ports from one immutable snapshot."""

        self._materialize_bus_snapshot(
            uow,
            project_id=project_id,
            snapshot=snapshot,
            device_ids=device_ids,
            active_handles=active_handles,
        )

        endpoint_ids: dict[str, str] = {}
        points_by_base: dict[str, list] = defaultdict(list)
        for point in snapshot.points:
            if set(point.handles) & active_handles:
                points_by_base[point.base].append(point)
        for base, plans in sorted(points_by_base.items()):
            line_id = line_ids[base]
            for plan in sorted(plans, key=lambda item: item.logical_identity):
                point_id = self._find_snapshot_point(uow, project_id, line_id, plan, adopt=True)
                if point_id is None:
                    point_id = new_id()
                    maximum = uow.execute(
                        select(func.max(cable_point.c.ordinal)).where(
                            cable_point.c.cable_line_id == line_id
                        )
                    ).scalar_one()
                    uow.execute(
                        cable_point.insert().values(
                            id=point_id,
                            project_id=project_id,
                            cable_line_id=line_id,
                            field_device_id=None,
                            point_kind=plan.point_kind,
                            ordinal=0 if maximum is None else maximum + 1,
                            logical_identity=plan.logical_identity,
                            origin_kind="PROJECT",
                            migration_state="CONFIRMED",
                            location_json={"x": plan.x, "y": plan.y},
                            dwg_observation_id=observations[plan.handles[0]],
                        )
                    )
                else:
                    uow.execute(
                        update(cable_point)
                        .where(cable_point.c.id == point_id)
                        .values(
                            point_kind=plan.point_kind,
                            location_json={"x": plan.x, "y": plan.y},
                            dwg_observation_id=observations[plan.handles[0]],
                            migration_state="CONFIRMED",
                            row_version=cable_point.c.row_version + 1,
                            updated_at_utc=datetime.now(UTC),
                        )
                    )
                endpoint_id = uow.execute(
                    select(cable_topology_endpoint.c.id).where(
                        cable_topology_endpoint.c.project_id == project_id,
                        cable_topology_endpoint.c.cable_line_id == line_id,
                        cable_topology_endpoint.c.cable_point_id == point_id,
                    )
                ).scalar_one_or_none()
                if endpoint_id is None:
                    endpoint_id = new_id()
                    uow.execute(
                        cable_topology_endpoint.insert().values(
                            id=endpoint_id,
                            project_id=project_id,
                            cable_line_id=line_id,
                            endpoint_kind="TOPOLOGY_POINT",
                            cable_point_id=point_id,
                        )
                    )
                endpoint_ids[plan.key] = endpoint_id
                for handle in plan.handles:
                    if handle not in device_ids:
                        continue
                    membership = (
                        uow.execute(
                            select(
                                cable_point_field_device.c.id,
                                cable_point_field_device.c.cable_point_id,
                            ).where(
                                cable_point_field_device.c.project_id == project_id,
                                cable_point_field_device.c.field_device_id == device_ids[handle],
                            )
                        )
                        .mappings()
                        .one_or_none()
                    )
                    if membership is None:
                        uow.execute(
                            cable_point_field_device.insert().values(
                                id=new_id(),
                                project_id=project_id,
                                cable_point_id=point_id,
                                field_device_id=device_ids[handle],
                            )
                        )
                    elif membership["cable_point_id"] != point_id:
                        uow.execute(
                            update(cable_point_field_device)
                            .where(cable_point_field_device.c.id == membership["id"])
                            .values(cable_point_id=point_id, updated_at_utc=datetime.now(UTC))
                        )

        self._materialize_keys_and_ports(
            uow,
            project_id=project_id,
            snapshot=snapshot,
            device_ids=device_ids,
            line_ids=line_ids,
            active_handles=active_handles,
        )
        source_endpoints: dict[str, str] = {}
        segment_ids: dict[str, str] = {}
        active_segments = [
            plan
            for plan in snapshot.segments
            if plan.target_point_key in endpoint_ids and plan.base in line_ids
        ]
        points_by_key = {point.key: point for point in snapshot.points}
        for plan in active_segments:
            line_id = line_ids[plan.base]
            if plan.source_point_key is None:
                if plan.source_reference and "/" in plan.source_reference:
                    source_endpoint = self._ensure_field_port_endpoint(
                        uow, project_id, line_id, plan.source_reference
                    )
                else:
                    source_endpoint = source_endpoints.get(plan.base)
                    if source_endpoint is None:
                        source_endpoint = self._ensure_internal_source_endpoint(
                            uow, project_id, line_id, plan.base
                        )
                        source_endpoints[plan.base] = source_endpoint
            else:
                source_plan = points_by_key.get(plan.source_point_key)
                if source_plan is None:
                    raise DwgSyncError("Источник участка отсутствует в проверенном снимке DWG.")
                if source_plan.base != plan.base:
                    raise DwgSyncError(
                        f"Источник {plan.source_reference} принадлежит линии {source_plan.base}, "
                        f"а участок — линии {plan.base}. Независимая линия должна выходить "
                        "из щита или физического порта устройства."
                    )
                source_endpoint = endpoint_ids.get(plan.source_point_key)
                if source_endpoint is None:
                    source_point_id = self._find_snapshot_point(
                        uow, project_id, line_id, source_plan, adopt=False
                    )
                    if source_point_id is not None:
                        source_endpoint = uow.execute(
                            select(cable_topology_endpoint.c.id).where(
                                cable_topology_endpoint.c.project_id == project_id,
                                cable_topology_endpoint.c.cable_line_id == line_id,
                                cable_topology_endpoint.c.cable_point_id == source_point_id,
                            )
                        ).scalar_one_or_none()
                    if source_endpoint is None:
                        raise DwgSyncError(
                            f"Источник {plan.source_reference or source_plan.logical_identity} "
                            "ещё не принят в Project. Примите его вместе с выбранной точкой "
                            "или отдельно, затем повторите импорт."
                        )
            target_endpoint = endpoint_ids[plan.target_point_key]
            route = dict(plan.route)
            segment_id = uow.execute(
                select(cable_segment.c.id).where(
                    cable_segment.c.project_id == project_id,
                    cable_segment.c.cable_line_id == line_id,
                    cable_segment.c.target_endpoint_id == target_endpoint,
                )
            ).scalar_one_or_none()
            values = {
                "source_endpoint_id": source_endpoint,
                "mount_way": route.get("MOUNT_WAY") or None,
                "gofra_type": route.get("GOFRA_TYPE") or None,
                "gofra_color": route.get("GOFRA_COLOR") or None,
                "migration_state": "CONFIRMED",
                "updated_at_utc": datetime.now(UTC),
            }
            if segment_id is None:
                segment_id = new_id()
                uow.execute(
                    cable_segment.insert().values(
                        id=segment_id,
                        project_id=project_id,
                        cable_line_id=line_id,
                        target_endpoint_id=target_endpoint,
                        origin_kind="PROJECT",
                        **values,
                    )
                )
            else:
                uow.execute(
                    update(cable_segment)
                    .where(cable_segment.c.id == segment_id)
                    .values(**values, row_version=cable_segment.c.row_version + 1)
                )
            segment_ids[plan.key] = segment_id

        point_identity_by_key = {point.key: point.logical_identity for point in snapshot.points}
        bus_point_by_handle = {point.handle: point.point_id for point in snapshot.bus_points}
        for plan in active_segments:
            target_identity = point_identity_by_key[plan.target_point_key]
            canonical_port_reference = (
                plan.source_reference
                if plan.source_reference and "/" in plan.source_reference
                else None
            )
            for port in snapshot.ports:
                if port.tag not in {"K1", "K2"} or port.handle not in device_ids:
                    continue
                bus_point_id = bus_point_by_handle.get(port.handle)
                if not bus_point_id:
                    continue
                port_reference = f"{bus_point_id}/{port.tag}"
                if port.value != target_identity and port_reference != canonical_port_reference:
                    continue
                desired_value = (
                    target_identity if port_reference == canonical_port_reference else ""
                )
                fields = dict(
                    uow.execute(
                        select(field_device.c.normalized_fields_json).where(
                            field_device.c.id == device_ids[port.handle]
                        )
                    ).scalar_one()
                    or {}
                )
                if fields.get(port.tag, "") == desired_value:
                    continue
                fields[port.tag] = desired_value
                uow.execute(
                    update(field_device)
                    .where(field_device.c.id == device_ids[port.handle])
                    .values(normalized_fields_json=fields)
                )

        self._materialize_segment_conduits(
            uow,
            project_id=project_id,
            plans=active_segments,
            segment_ids=segment_ids,
            device_ids=device_ids,
        )
        try:
            recalculate_segments(
                uow,
                project_id,
                segment_ids=set(segment_ids.values()),
            )
        except RecalculationError as exc:
            raise DwgSyncError(str(exc)) from exc
        review_bases = {review.split(":", 1)[0] for review in snapshot.structural_reviews}
        for base in sorted(review_bases):
            if base not in line_ids:
                continue
            line_id = line_ids[base]
            existing = uow.execute(
                select(topology_migration_review.c.id).where(
                    topology_migration_review.c.project_id == project_id,
                    topology_migration_review.c.cable_line_id == line_id,
                    topology_migration_review.c.review_kind == "DWG_POINT_ORDER",
                )
            ).scalar_one_or_none()
            if existing is None:
                uow.execute(
                    topology_migration_review.insert().values(
                        id=new_id(),
                        project_id=project_id,
                        cable_line_id=line_id,
                        review_kind="DWG_POINT_ORDER",
                        legacy_source_id=line_id,
                        reason="DWG contract source topology requires attention",
                        legacy_payload_json={
                            "review": next(
                                value
                                for value in snapshot.structural_reviews
                                if value.startswith(f"{base}:")
                            )
                        },
                        review_state="MIGRATION_REVIEW_REQUIRED",
                    )
                )

    def _find_snapshot_point(self, uow, project_id, line_id, plan, *, adopt):
        row = (
            uow.execute(
                select(cable_point.c.id, cable_point.c.cable_line_id).where(
                    cable_point.c.project_id == project_id,
                    cable_point.c.logical_identity == plan.logical_identity,
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is not None:
            if row["cable_line_id"] != line_id:
                raise DwgSyncError(
                    f"Точка {plan.logical_identity} уже принадлежит другой линии Project."
                )
            return row["id"]
        if plan.point_kind != "EL_BOX" or not plan.logical_identity.startswith("BOX."):
            return None
        # Reuse an unambiguous pre-repair box point without changing schema or
        # importing its owning insertion as a dependency. Never split a collapsed
        # persisted point by guessing which existing edges belong to which box.
        point_ids = set(
            uow.execute(
                select(cable_point_field_device.c.cable_point_id)
                .join(field_device, field_device.c.id == cable_point_field_device.c.field_device_id)
                .where(
                    cable_point_field_device.c.project_id == project_id,
                    field_device.c.lifecycle == "ACTIVE",
                    field_device.c.normalized_fields_json["BOX_ID"].as_string()
                    == plan.logical_identity,
                )
            ).scalars()
        )
        if not point_ids:
            return None
        if len(point_ids) != 1:
            raise DwgSyncError(f"Топология коробки {plan.logical_identity} неоднозначна в Project.")
        point_id = point_ids.pop()
        fields = list(
            uow.execute(
                select(field_device.c.normalized_fields_json)
                .join(
                    cable_point_field_device,
                    cable_point_field_device.c.field_device_id == field_device.c.id,
                )
                .where(cable_point_field_device.c.cable_point_id == point_id)
            ).scalars()
        )
        owner_line = uow.execute(
            select(cable_point.c.cable_line_id).where(cable_point.c.id == point_id)
        ).scalar_one()
        if owner_line != line_id or any(
            (values or {}).get("BOX_ID") != plan.logical_identity for values in fields
        ):
            raise DwgSyncError(
                f"Существующая точка коробки {plan.logical_identity} объединяет разные "
                "физические объекты или принадлежит другой линии. Требуется восстановление "
                "топологии Project; изменения не применены."
            )
        if adopt:
            uow.execute(
                update(cable_point)
                .where(cable_point.c.id == point_id)
                .values(logical_identity=plan.logical_identity)
            )
        return point_id

    def _materialize_bus_snapshot(
        self, uow, *, project_id, snapshot, device_ids, active_handles
    ) -> None:
        grouped: dict[str, list] = defaultdict(list)
        for plan in snapshot.bus_points:
            if plan.handle in active_handles and plan.handle in device_ids:
                grouped[plan.bus_id].append(plan)
        for designation, plans in sorted(grouped.items()):
            bus_row = (
                uow.execute(
                    select(bus).where(
                        bus.c.project_id == project_id,
                        bus.c.designation == designation,
                        bus.c.lifecycle == "ACTIVE",
                    )
                )
                .mappings()
                .one_or_none()
            )
            if bus_row is None:
                raise DwgSyncError(
                    f"BUS_ROOT_BINDING_REQUIRED:{designation}; "
                    "create/bind the Project bus root first"
                )
            kinds = {plan.bus_kind for plan in plans}
            if kinds != {bus_row["bus_kind"]}:
                raise DwgSyncError(
                    f"BUS_TYPE_CONFLICT:{designation}:{sorted(kinds)} != {bus_row['bus_kind']}"
                )
            cable_types = {plan.cable_type for plan in plans if plan.connection_kind == "CABLE"}
            if len(cable_types) > 1:
                raise DwgSyncError(
                    f"BUS_CABLE_TYPE_INCONSISTENT:{designation}:{sorted(cable_types)}"
                )
            cable_type = next(iter(cable_types), "")
            if bus_row.get("cable_type") and cable_type and bus_row["cable_type"] != cable_type:
                raise DwgSyncError(
                    f"BUS_CABLE_TYPE_CONFLICT:{designation}:{bus_row['cable_type']} != {cable_type}"
                )
            if cable_type and not bus_row.get("cable_type"):
                uow.execute(
                    update(bus).where(bus.c.id == bus_row["id"]).values(cable_type=cable_type)
                )

            endpoint_by_address = {
                row["address"]: row["id"]
                for row in uow.execute(
                    select(bus_endpoint).where(
                        bus_endpoint.c.project_id == project_id,
                        bus_endpoint.c.bus_id == bus_row["id"],
                    )
                ).mappings()
            }
            for plan in plans:
                endpoint_id = endpoint_by_address.get(plan.point_id)
                if endpoint_id is None:
                    endpoint_id = new_id()
                    uow.execute(
                        bus_endpoint.insert().values(
                            id=endpoint_id,
                            project_id=project_id,
                            bus_id=bus_row["id"],
                            endpoint_kind="FIELD_DEVICE",
                            field_device_id=device_ids[plan.handle],
                            endpoint_role="DEVICE",
                            address=plan.point_id,
                            endpoint_order=int(plan.point_id.rsplit(".", 1)[1]),
                        )
                    )
                    endpoint_by_address[plan.point_id] = endpoint_id

            ordered = sorted(plans, key=lambda plan: int(plan.point_id.rsplit(".", 1)[1]))
            previous_rs485 = None
            for plan in ordered:
                target_endpoint = endpoint_by_address[plan.point_id]
                if plan.bus_kind == "RS485":
                    source_endpoint = previous_rs485
                    previous_rs485 = target_endpoint
                elif plan.source == f"{designation}.000":
                    source_endpoint = None
                else:
                    source_endpoint = endpoint_by_address.get(plan.source)
                    if source_endpoint is None:
                        raise DwgSyncError(f"BUS_SOURCE_NOT_FOUND:{plan.source}")
                route = dict(plan.route)
                if plan.connection_kind == "TRACK" and any(route.values()):
                    raise DwgSyncError(f"TRACK_BUS_ROUTE_FORBIDDEN:{plan.point_id}")
                existing = uow.execute(
                    select(bus_segment.c.id).where(
                        bus_segment.c.project_id == project_id,
                        bus_segment.c.bus_id == bus_row["id"],
                        bus_segment.c.target_endpoint_id == target_endpoint,
                    )
                ).scalar_one_or_none()
                values = {
                    "source_endpoint_id": source_endpoint,
                    "connection_kind": plan.connection_kind,
                    "mount_way": route.get("BUS_MOUNT_WAY") or None,
                    "gofra_type": route.get("BUS_GOFRA_TYPE") or None,
                    "gofra_color": route.get("BUS_GOFRA_COLOR") or None,
                    "gofra_id": route.get("BUS_GOFRA_ID") or None,
                    "origin_kind": "PROJECT",
                    "migration_state": "CONFIRMED",
                }
                if existing is None:
                    segment_id = new_id()
                    uow.execute(
                        bus_segment.insert().values(
                            id=segment_id,
                            project_id=project_id,
                            bus_id=bus_row["id"],
                            target_endpoint_id=target_endpoint,
                            **values,
                        )
                    )
                else:
                    segment_id = existing
                    uow.execute(
                        update(bus_segment).where(bus_segment.c.id == segment_id).values(**values)
                    )
                self._materialize_bus_segment_conduit(
                    uow,
                    project_id=project_id,
                    segment_id=segment_id,
                    connection_kind=plan.connection_kind,
                    route=route,
                )

    def _materialize_bus_segment_conduit(
        self, uow, *, project_id, segment_id, connection_kind, route
    ) -> None:
        if connection_kind == "TRACK":
            self._replace_bus_segment_conduit_assignment(uow, project_id, segment_id, None)
            return
        try:
            present = validate_line_conduit_fields(
                mount_way=route.get("BUS_MOUNT_WAY", ""),
                conduit_type=route.get("BUS_GOFRA_TYPE", ""),
                conduit_color=route.get("BUS_GOFRA_COLOR", ""),
                conduit_id=route.get("BUS_GOFRA_ID", ""),
            )
        except ConduitContractError as exc:
            raise DwgSyncError(str(exc)) from exc
        if not present:
            self._replace_bus_segment_conduit_assignment(uow, project_id, segment_id, None)
            return
        designation = route.get("BUS_GOFRA_ID", "")
        if not designation:
            next_number = (
                uow.execute(
                    select(func.max(conduit.c.conduit_number)).where(
                        conduit.c.project_id == project_id
                    )
                ).scalar_one()
                or 0
            ) + 1
            if next_number > 999:
                raise DwgSyncError("No automatic conduit number remains in NNN format")
            designation = format_conduit_id(next_number, route["BUS_GOFRA_TYPE"])
        existing = (
            uow.execute(
                select(conduit).where(
                    conduit.c.project_id == project_id,
                    conduit.c.designation == designation,
                    conduit.c.lifecycle == "ACTIVE",
                )
            )
            .mappings()
            .one_or_none()
        )
        if existing is None:
            conduit_id = new_id()
            uow.execute(
                conduit.insert().values(
                    id=conduit_id,
                    project_id=project_id,
                    designation=designation,
                    conduit_number=parse_conduit_id(designation, route["BUS_GOFRA_TYPE"]),
                    conduit_type=route["BUS_GOFRA_TYPE"],
                    color=route.get("BUS_GOFRA_COLOR") or None,
                    length_m_decimal=None,
                    path_json={
                        "origin": "AUTO_BUS_SEGMENT",
                        "initial_length_status": "PENDING_SEGMENT_LENGTH",
                    },
                )
            )
        else:
            conduit_id = existing["id"]
            if existing["conduit_type"] != route["BUS_GOFRA_TYPE"] or (
                existing["color"] or ""
            ) != route.get("BUS_GOFRA_COLOR", ""):
                raise DwgSyncError(f"Shared conduit {designation} has conflicting type/color")
        self._replace_bus_segment_conduit_assignment(uow, project_id, segment_id, conduit_id)

    def _ensure_internal_source_endpoint(self, uow, project_id, line_id, base):
        point_id = uow.execute(
            select(cable_point.c.id).where(
                cable_point.c.project_id == project_id,
                cable_point.c.cable_line_id == line_id,
                cable_point.c.point_kind == "INTERNAL_SOURCE",
            )
        ).scalar_one_or_none()
        if point_id is None:
            point_id = new_id()
            ordinal = uow.execute(
                select(func.max(cable_point.c.ordinal)).where(
                    cable_point.c.cable_line_id == line_id
                )
            ).scalar_one()
            uow.execute(
                cable_point.insert().values(
                    id=point_id,
                    project_id=project_id,
                    cable_line_id=line_id,
                    field_device_id=None,
                    point_kind="INTERNAL_SOURCE",
                    ordinal=(ordinal or 0) + 1,
                    logical_identity=f"internal:{base}:source",
                    origin_kind="PROJECT",
                    migration_state="CONFIRMED",
                )
            )
        endpoint_id = uow.execute(
            select(cable_topology_endpoint.c.id).where(
                cable_topology_endpoint.c.project_id == project_id,
                cable_topology_endpoint.c.cable_line_id == line_id,
                cable_topology_endpoint.c.cable_point_id == point_id,
            )
        ).scalar_one_or_none()
        if endpoint_id is None:
            endpoint_id = new_id()
            uow.execute(
                cable_topology_endpoint.insert().values(
                    id=endpoint_id,
                    project_id=project_id,
                    cable_line_id=line_id,
                    endpoint_kind="TOPOLOGY_POINT",
                    cable_point_id=point_id,
                )
            )
        return endpoint_id

    def _ensure_field_port_endpoint(self, uow, project_id, line_id, reference):
        bus_point_id, port_tag = reference.rsplit("/", 1)
        rows = list(
            uow.execute(
                select(field_port.c.id)
                .select_from(
                    field_port.join(field_device, field_port.c.field_device_id == field_device.c.id)
                )
                .where(
                    field_port.c.project_id == project_id,
                    field_port.c.port_tag == port_tag,
                    field_device.c.normalized_fields_json["BUS_POINT_ID"].as_string()
                    == bus_point_id,
                    field_device.c.lifecycle == "ACTIVE",
                )
            ).scalars()
        )
        if len(rows) != 1:
            raise DwgSyncError(
                f"Источник {reference} не разрешается в один физический порт Project. "
                "Примите устройство-источник и его порт, затем повторите импорт."
            )
        endpoint_id = uow.execute(
            select(cable_topology_endpoint.c.id).where(
                cable_topology_endpoint.c.project_id == project_id,
                cable_topology_endpoint.c.cable_line_id == line_id,
                cable_topology_endpoint.c.field_port_id == rows[0],
            )
        ).scalar_one_or_none()
        if endpoint_id is None:
            endpoint_id = new_id()
            uow.execute(
                cable_topology_endpoint.insert().values(
                    id=endpoint_id,
                    project_id=project_id,
                    cable_line_id=line_id,
                    endpoint_kind="FIELD_PORT",
                    field_port_id=rows[0],
                )
            )
        return endpoint_id

    def _materialize_segment_conduits(
        self, uow, *, project_id, plans, segment_ids, device_ids
    ) -> None:
        designation_counts = Counter(
            dict(plan.route).get("GOFRA_ID", "")
            for plan in plans
            if dict(plan.route).get("GOFRA_ID", "")
        )
        next_number = (
            uow.execute(
                select(func.max(conduit.c.conduit_number)).where(conduit.c.project_id == project_id)
            ).scalar_one()
            or 0
        ) + 1
        conduit_ids: dict[str, str] = {}
        for plan in sorted(plans, key=lambda item: item.key):
            route = dict(plan.route)
            try:
                present = validate_line_conduit_fields(
                    mount_way=route.get("MOUNT_WAY", ""),
                    conduit_type=route.get("GOFRA_TYPE", ""),
                    conduit_color=route.get("GOFRA_COLOR", ""),
                    conduit_id=route.get("GOFRA_ID", ""),
                )
            except ConduitContractError as exc:
                raise DwgSyncError(str(exc)) from exc
            segment_id = segment_ids[plan.key]
            if not present:
                self._replace_segment_conduit_assignment(uow, project_id, segment_id, None)
                continue
            designation = route.get("GOFRA_ID", "")
            generated = not designation
            if generated:
                if next_number > 999:
                    raise DwgSyncError("No automatic conduit number remains in NNN format")
                designation = format_conduit_id(next_number, route["GOFRA_TYPE"])
                next_number += 1
            if designation not in conduit_ids:
                existing = (
                    uow.execute(
                        select(conduit).where(
                            conduit.c.project_id == project_id,
                            conduit.c.designation == designation,
                            conduit.c.lifecycle == "ACTIVE",
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if existing is None:
                    conduit_id = new_id()
                    number = parse_conduit_id(designation, route["GOFRA_TYPE"])
                    uow.execute(
                        conduit.insert().values(
                            id=conduit_id,
                            project_id=project_id,
                            designation=designation,
                            conduit_number=number,
                            conduit_type=route["GOFRA_TYPE"],
                            color=route.get("GOFRA_COLOR") or None,
                            length_m_decimal=None,
                            path_json={
                                "origin": "AUTO_SEGMENT" if generated else "DWG_PREEXISTING",
                                "initial_length_status": (
                                    "INCOMPLETE_SHARED"
                                    if designation_counts.get(designation, 0) > 1
                                    else "PENDING_SEGMENT_LENGTH"
                                ),
                            },
                        )
                    )
                else:
                    conduit_id = existing["id"]
                    if existing["conduit_type"] != route["GOFRA_TYPE"] or (
                        existing["color"] or ""
                    ) != route.get("GOFRA_COLOR", ""):
                        raise DwgSyncError(
                            f"Shared conduit {designation} has conflicting type/color"
                        )
                conduit_ids[designation] = conduit_id
            self._replace_segment_conduit_assignment(
                uow, project_id, segment_id, conduit_ids[designation]
            )
            if generated:
                for handle in plan.target_handles:
                    if handle not in device_ids:
                        continue
                    fields = dict(
                        uow.execute(
                            select(field_device.c.normalized_fields_json).where(
                                field_device.c.id == device_ids[handle]
                            )
                        ).scalar_one()
                        or {}
                    )
                    fields["GOFRA_ID"] = designation
                    uow.execute(
                        update(field_device)
                        .where(field_device.c.id == device_ids[handle])
                        .values(normalized_fields_json=fields)
                    )

    def _materialize_keys_and_ports(
        self, uow, *, project_id, snapshot, device_ids, line_ids, active_handles
    ) -> None:
        for plan in snapshot.ports:
            if plan.handle not in active_handles or plan.handle not in device_ids:
                continue
            kind, direction = canonical_port(plan.block_name, plan.tag)
            existing = uow.execute(
                select(field_port.c.id).where(
                    field_port.c.project_id == project_id,
                    field_port.c.field_device_id == device_ids[plan.handle],
                    field_port.c.port_tag == plan.tag,
                )
            ).scalar_one_or_none()
            if existing is None:
                uow.execute(
                    field_port.insert().values(
                        id=new_id(),
                        project_id=project_id,
                        field_device_id=device_ids[plan.handle],
                        port_tag=plan.tag,
                        port_kind=kind,
                        direction=direction,
                        contract_version=1,
                    )
                )
        for plan in snapshot.keys:
            if plan.handle not in active_handles or plan.handle not in device_ids:
                continue
            target_kind = "UNRESOLVED"
            target_line_id = None
            target_dali_id = None
            if plan.value in line_ids:
                target_kind = "CABLE_LINE"
                target_line_id = line_ids[plan.value]
            elif plan.value:
                target_line_id = uow.execute(
                    select(cable_line.c.id).where(
                        cable_line.c.project_id == project_id,
                        cable_line.c.designation == plan.value,
                    )
                ).scalar_one_or_none()
                if target_line_id is not None:
                    target_kind = "CABLE_LINE"
            if target_line_id is None and plan.value.startswith("D."):
                target_dali_id = uow.execute(
                    select(dali_group.c.id).where(
                        dali_group.c.project_id == project_id,
                        dali_group.c.group_key == plan.value,
                    )
                ).scalar_one_or_none()
                if target_dali_id is not None:
                    target_kind = "DALI_GROUP"
            existing = (
                uow.execute(
                    select(field_control_key).where(
                        field_control_key.c.project_id == project_id,
                        field_control_key.c.field_device_id == device_ids[plan.handle],
                        field_control_key.c.key_tag == plan.tag,
                    )
                )
                .mappings()
                .one_or_none()
            )
            values = {
                "functional_target_text": plan.value or None,
                "target_kind": target_kind,
                "target_cable_line_id": target_line_id,
                "target_dali_group_id": target_dali_id,
                "origin_json": {
                    "source": "DWG",
                    "handle": plan.handle,
                    "tag": plan.tag,
                    "contract_version": self._contract.contract_version,
                },
                "baseline_json": {"value": plan.value},
                "lifecycle": "ACTIVE",
                "updated_at_utc": datetime.now(UTC),
            }
            if existing is None:
                uow.execute(
                    field_control_key.insert().values(
                        id=new_id(),
                        project_id=project_id,
                        field_device_id=device_ids[plan.handle],
                        key_tag=plan.tag,
                        **values,
                    )
                )
            else:
                uow.execute(
                    update(field_control_key)
                    .where(field_control_key.c.id == existing["id"])
                    .values(**values, row_version=field_control_key.c.row_version + 1)
                )

    def _record_change(self, uow, project_id, operation_id, change, decision):
        uow.execute(
            dwg_sync_change.insert().values(
                id=new_id(),
                project_id=project_id,
                dwg_sync_operation_id=operation_id,
                field_path=change.owner_path or change.field_path,
                baseline_value_json=change.baseline_value,
                project_value_json=change.project_value,
                dwg_value_json=change.dwg_value,
                change_class=change.change_class,
                decision=decision,
                apply_result_json={"status": "APPLIED"},
            )
        )

    def _replace_baselines(
        self,
        uow,
        proposal,
        binding_id,
        scan_id,
        revision,
        selected,
        validated,
        snapshot,
    ):
        by_path = {change.field_path: change for change in proposal.changes}
        selected_new_handles = {
            by_path[path].handle
            for path in selected
            if by_path[path].change_class is ChangeClass.NEW_DWG_INSERTION
        }
        owner_values: dict[str, Any] = {}
        for path in selected:
            change = by_path[path]
            if change.field != "$" and change.owner_path:
                owner_values[change.owner_path] = change.dwg_value
        for fact in snapshot.facts:
            if fact.affected_handles and set(fact.affected_handles) <= selected_new_handles:
                owner_values[fact.owner_path] = fact.value
        for field_path, value in sorted(owner_values.items()):
            existing = uow.execute(
                select(dwg_baseline.c.id).where(
                    dwg_baseline.c.project_id == proposal.project_id,
                    dwg_baseline.c.dwg_document_binding_id == binding_id,
                    dwg_baseline.c.field_path == field_path,
                )
            ).scalar_one_or_none()
            values = {
                "accepted_value_json": value,
                "dwg_scan_id": scan_id,
                "project_revision": revision,
                "updated_at_utc": datetime.now(UTC),
            }
            if existing:
                uow.execute(
                    update(dwg_baseline).where(dwg_baseline.c.id == existing).values(**values)
                )
            else:
                uow.execute(
                    dwg_baseline.insert().values(
                        id=new_id(),
                        project_id=proposal.project_id,
                        dwg_document_binding_id=binding_id,
                        field_path=field_path,
                        **values,
                    )
                )

    def _check_baseline_preconditions(self, uow, proposal, selected: set[str]) -> None:
        if not proposal.binding_id:
            return
        by_path = {change.field_path: change for change in proposal.changes}
        for path in selected:
            change = by_path[path]
            if change.change_class is ChangeClass.NEW_DWG_INSERTION:
                continue
            owner_path = change.owner_path or change.field_path
            current = uow.execute(
                select(dwg_baseline.c.accepted_value_json).where(
                    dwg_baseline.c.project_id == proposal.project_id,
                    dwg_baseline.c.dwg_document_binding_id == proposal.binding_id,
                    dwg_baseline.c.field_path == owner_path,
                )
            ).scalar_one_or_none()
            if current is None:
                fields = uow.execute(
                    select(field_device.c.normalized_fields_json).where(
                        field_device.c.project_id == proposal.project_id,
                        field_device.c.dwg_document_binding_id == proposal.binding_id,
                        field_device.c.entity_handle == change.handle,
                        field_device.c.lifecycle == "ACTIVE",
                    )
                ).scalar_one_or_none()
                legacy_path = _legacy_box_owner_path(change.owner_key, change.field, fields or {})
                if legacy_path:
                    current = uow.execute(
                        select(dwg_baseline.c.accepted_value_json).where(
                            dwg_baseline.c.project_id == proposal.project_id,
                            dwg_baseline.c.dwg_document_binding_id == proposal.binding_id,
                            dwg_baseline.c.field_path == legacy_path,
                        )
                    ).scalar_one_or_none()
            if current is None:
                current = uow.execute(
                    select(dwg_baseline.c.accepted_value_json).where(
                        dwg_baseline.c.project_id == proposal.project_id,
                        dwg_baseline.c.dwg_document_binding_id == proposal.binding_id,
                        dwg_baseline.c.field_path == change.field_path,
                    )
                ).scalar_one_or_none()
            if current != change.baseline_value:
                raise StaleProposalError(f"Baseline changed after preview for {owner_path}")

    def _check_line_wide_selection(self, commands, observations):
        by_line: dict[tuple[str, str], set[str]] = defaultdict(set)
        expected: dict[tuple[str, str], set[str]] = defaultdict(set)
        for observation in observations.values():
            attrs = {item.tag: item.value for item in observation.raw_attributes}
            cable_id = attrs.get("CABLE_ID", "")
            if cable_id:
                base = cable_id.split(".", 1)[0]
                for field in LINE_WIDE_FIELDS:
                    if field in attrs:
                        expected[(base, field)].add(observation.handle)
        for command in commands:
            if command["tag"] in LINE_WIDE_FIELDS:
                observation = observations[command["handle"]]
                attrs = {item.tag: item.value for item in observation.raw_attributes}
                base = attrs["CABLE_ID"].split(".", 1)[0]
                by_line[(base, command["tag"])].add(command["handle"])
        for key, selected_handles in by_line.items():
            if selected_handles != expected[key]:
                raise DwgSyncError(f"Partial line-wide write is forbidden for {key[0]}/{key[1]}")
        cable_commands = [item for item in commands if item["tag"] == "CABLE_ID"]
        for command in cable_commands:
            old_base = command["old_value"].split(".", 1)[0]
            new_base = command["new_value"].split(".", 1)[0]
            if old_base == new_base:
                continue
            expected_handles = {
                observation.handle
                for observation in observations.values()
                if {item.tag: item.value for item in observation.raw_attributes}.get(
                    "CABLE_ID", ""
                ).split(".", 1)[0]
                == old_base
            }
            selected_handles = {
                item["handle"]
                for item in cable_commands
                if item["old_value"].split(".", 1)[0] == old_base
                and item["new_value"].split(".", 1)[0] == new_base
            }
            if selected_handles != expected_handles:
                raise DwgSyncError(f"Partial base CABLE_ID write is forbidden for {old_base}")

    def _check_project_selection(self, proposal: ScanProposal, selected: set[str]) -> None:
        observations = {item.handle: item for item in proposal.batch.observations if item.handle}
        line_handles: dict[str, set[str]] = defaultdict(set)
        for observation in observations.values():
            attributes = {item.tag: item.value for item in observation.raw_attributes}
            cable_id = attributes.get("CABLE_ID", "")
            if cable_id:
                line_handles[cable_id.split(".", 1)[0]].add(observation.handle)
        by_path = {change.field_path: change for change in proposal.changes}
        for group in atomic_line_import_groups(proposal):
            selected_group = selected & set(group.required_paths)
            if selected_group and selected_group != set(group.required_paths):
                raise DwgSyncError(f"Partial line import is forbidden for {group.line_number}")
        for base, handles in line_handles.items():
            line_changes = [
                by_path[path]
                for path in selected
                if path in by_path
                and by_path[path].owner_kind is SyncOwnerKind.BASE_LINE
                and by_path[path].owner_key == base
            ]
            for change in line_changes:
                if change.field in LINE_WIDE_FIELDS and set(change.affected_handles) != handles:
                    raise DwgSyncError(
                        f"Incomplete owner set for line-wide import {base}/{change.field}"
                    )
            cable_changes = [
                by_path[path]
                for path in selected
                if path in by_path
                and by_path[path].field == "CABLE_ID"
                and bool(set(by_path[path].affected_handles or (by_path[path].handle,)) & handles)
            ]
            base_changed = any(
                str(change.project_value).split(".", 1)[0] != str(change.dwg_value).split(".", 1)[0]
                for change in cable_changes
                if change.project_value is not None
            )
            affected = {
                handle
                for change in cable_changes
                for handle in (change.affected_handles or (change.handle,))
            }
            if base_changed and affected != handles:
                raise DwgSyncError(f"Partial base CABLE_ID import is forbidden for {base}")

    def _check_selected_validation(self, proposal: ScanProposal, selected: set[str]) -> None:
        selected_handles = {path.split(":", 1)[0] for path in selected}
        blocking = [
            issue
            for issue in proposal.issues
            if issue.blocks_acceptance
            and (
                issue.handle is None
                or issue.handle in selected_handles
                or selected_handles.intersection(issue.related_handles)
            )
        ]
        if blocking:
            raise DwgSyncError(
                "Selected DWG data failed validation: " + _validation_reason(blocking)
            )

    def _replace_segment_conduit_assignment(
        self, uow, project_id: str, segment_id: str, target_conduit_id: str | None
    ) -> None:
        old_ids = list(
            uow.execute(
                select(conduit_segment_assignment.c.conduit_id).where(
                    conduit_segment_assignment.c.project_id == project_id,
                    conduit_segment_assignment.c.cable_segment_id == segment_id,
                )
            ).scalars()
        )
        if old_ids == ([target_conduit_id] if target_conduit_id else []):
            return
        uow.execute(
            delete(conduit_segment_assignment).where(
                conduit_segment_assignment.c.project_id == project_id,
                conduit_segment_assignment.c.cable_segment_id == segment_id,
            )
        )
        if target_conduit_id:
            uow.execute(
                conduit_segment_assignment.insert().values(
                    id=new_id(),
                    project_id=project_id,
                    conduit_id=target_conduit_id,
                    cable_segment_id=segment_id,
                )
            )
        for old_id in old_ids:
            if old_id == target_conduit_id:
                continue
            ordinary_count = uow.execute(
                select(func.count())
                .select_from(conduit_segment_assignment)
                .where(conduit_segment_assignment.c.conduit_id == old_id)
            ).scalar_one()
            bus_count = uow.execute(
                select(func.count())
                .select_from(bus_segment_conduit_assignment)
                .where(bus_segment_conduit_assignment.c.conduit_id == old_id)
            ).scalar_one()
            origin = uow.execute(
                select(conduit.c.path_json).where(conduit.c.id == old_id)
            ).scalar_one_or_none()
            if ordinary_count + bus_count == 0 and (origin or {}).get("origin") in {
                "AUTO_LINE",
                "AUTO_SEGMENT",
                "AUTO_BUS_SEGMENT",
            }:
                uow.execute(delete(conduit).where(conduit.c.id == old_id))

    def _replace_bus_segment_conduit_assignment(
        self, uow, project_id: str, segment_id: str, target_conduit_id: str | None
    ) -> None:
        old_ids = list(
            uow.execute(
                select(bus_segment_conduit_assignment.c.conduit_id).where(
                    bus_segment_conduit_assignment.c.project_id == project_id,
                    bus_segment_conduit_assignment.c.bus_segment_id == segment_id,
                )
            ).scalars()
        )
        if old_ids == ([target_conduit_id] if target_conduit_id else []):
            return
        uow.execute(
            delete(bus_segment_conduit_assignment).where(
                bus_segment_conduit_assignment.c.project_id == project_id,
                bus_segment_conduit_assignment.c.bus_segment_id == segment_id,
            )
        )
        if target_conduit_id:
            uow.execute(
                bus_segment_conduit_assignment.insert().values(
                    id=new_id(),
                    project_id=project_id,
                    bus_segment_id=segment_id,
                    conduit_id=target_conduit_id,
                )
            )
        for old_id in old_ids:
            if old_id == target_conduit_id:
                continue
            bus_count = uow.execute(
                select(func.count())
                .select_from(bus_segment_conduit_assignment)
                .where(bus_segment_conduit_assignment.c.conduit_id == old_id)
            ).scalar_one()
            ordinary_count = uow.execute(
                select(func.count())
                .select_from(conduit_segment_assignment)
                .where(conduit_segment_assignment.c.conduit_id == old_id)
            ).scalar_one()
            origin = uow.execute(
                select(conduit.c.path_json).where(conduit.c.id == old_id)
            ).scalar_one_or_none()
            if ordinary_count + bus_count == 0 and (origin or {}).get("origin") in {
                "AUTO_LINE",
                "AUTO_SEGMENT",
                "AUTO_BUS_SEGMENT",
            }:
                uow.execute(delete(conduit).where(conduit.c.id == old_id))

    def _write_attempts(self, plan: DwgWritePlan) -> list[dict[str, Any]]:
        with self._engine.connect() as connection:
            rows = list(
                connection.execute(
                    select(
                        dwg_sync_operation.c.selection_json,
                        dwg_sync_operation.c.result_json,
                    ).where(
                        dwg_sync_operation.c.project_id == plan.project_id,
                        dwg_sync_operation.c.dwg_document_binding_id == plan.binding_id,
                        dwg_sync_operation.c.direction == "PROJECT_TO_DWG",
                    )
                ).mappings()
            )
        return [
            dict(row["result_json"] or {})
            for row in rows
            if isinstance(row["selection_json"], dict)
            and row["selection_json"].get("plan_id") == plan.plan_id
        ]

    def _record_write_plan_attempt(
        self,
        plan: DwgWritePlan,
        *,
        correlation_id: str,
        attempted: list[DwgWriteTarget],
        newly_completed: set[tuple[str, str]],
        all_completed: set[tuple[str, str]],
        failures: tuple[dict[str, str], ...],
        result: WriteResult,
        status: str,
    ) -> None:
        now = datetime.now(UTC)
        readback = {
            (str(item["handle"]), str(item["tag"])): str(item["value"]) for item in result.readback
        }
        with UnitOfWork(self._engine) as uow:
            revision = uow.execute(
                select(project.c.project_revision).where(project.c.id == plan.project_id)
            ).scalar_one()
            if revision != plan.project_revision:
                raise StaleProposalError("Project changed after write plan was built")
            binding = uow.execute(
                select(dwg_document_binding.c.id).where(
                    dwg_document_binding.c.id == plan.binding_id,
                    dwg_document_binding.c.project_id == plan.project_id,
                    dwg_document_binding.c.application_uuid
                    == _application_uuid(plan.document_identity),
                )
            ).scalar_one_or_none()
            if binding is None:
                raise StaleProposalError("DWG binding changed after write plan was built")
            operation_id = new_id()
            uow.execute(
                dwg_sync_operation.insert().values(
                    id=operation_id,
                    project_id=plan.project_id,
                    dwg_document_binding_id=plan.binding_id,
                    direction="PROJECT_TO_DWG",
                    selection_json={
                        "plan_id": plan.plan_id,
                        "fingerprint": plan.fingerprint,
                        "selected_paths": list(plan.selected_paths),
                        "attempted_targets": [[target.handle, target.tag] for target in attempted],
                    },
                    result_json={
                        "status": status,
                        "completed_targets": [list(item) for item in sorted(all_completed)],
                        "failed_targets": list(failures),
                        "no_save_confirmed": result.no_save_confirmed,
                        "document_saved": result.document_saved,
                    },
                    correlation_id=correlation_id,
                    created_at_utc=now,
                )
            )
            for target in attempted:
                key = (target.handle, target.tag)
                baseline_row = (
                    uow.execute(
                        select(dwg_baseline).where(
                            dwg_baseline.c.project_id == plan.project_id,
                            dwg_baseline.c.dwg_document_binding_id == plan.binding_id,
                            dwg_baseline.c.field_path == target.owner_path,
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                change_id = new_id()
                actual = readback.get(key)
                uow.execute(
                    dwg_sync_change.insert().values(
                        id=change_id,
                        project_id=plan.project_id,
                        dwg_sync_operation_id=operation_id,
                        field_path=f"{target.owner_path}@{target.handle}:{target.tag}",
                        baseline_value_json=(
                            None if baseline_row is None else baseline_row["accepted_value_json"]
                        ),
                        project_value_json=target.new_value,
                        dwg_value_json=target.expected_old_value,
                        change_class="PROJECT_CHANGED",
                        decision="WRITE_PROJECT",
                        apply_result_json={
                            "status": "WRITTEN" if key in newly_completed else "UNCONFIRMED"
                        },
                        readback_result_json={
                            "status": "MATCH" if key in newly_completed else "MISMATCH",
                            "value": actual,
                        },
                    )
                )
                uow.execute(
                    dwg_write_receipt.insert().values(
                        id=new_id(),
                        project_id=plan.project_id,
                        dwg_sync_change_id=change_id,
                        target_preconditions_json={
                            **target.bridge_command(),
                            "document_identity": target.document_identity,
                            "owner_kind": target.owner_kind,
                            "owner_key": target.owner_key,
                            "owner_path": target.owner_path,
                            "plan_id": plan.plan_id,
                            "correlation_id": correlation_id,
                        },
                        written_value_json=target.new_value,
                        readback_value_json=actual,
                        no_save_confirmed=result.no_save_confirmed,
                        created_at_utc=now,
                    )
                )

            targets_by_owner: dict[str, list[DwgWriteTarget]] = defaultdict(list)
            for target in plan.targets:
                targets_by_owner[target.owner_path].append(target)
            for owner_path, owner_targets in targets_by_owner.items():
                owner_keys = {(target.handle, target.tag) for target in owner_targets}
                if not owner_keys <= all_completed:
                    continue
                values = {target.new_value for target in owner_targets}
                if len(values) != 1:
                    raise DwgSyncError(f"Owner {owner_path} has inconsistent planned values")
                baseline = (
                    uow.execute(
                        select(dwg_baseline).where(
                            dwg_baseline.c.project_id == plan.project_id,
                            dwg_baseline.c.dwg_document_binding_id == plan.binding_id,
                            dwg_baseline.c.field_path == owner_path,
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if baseline is None:
                    raise StaleProposalError(f"No confirmed baseline exists for {owner_path}")
                uow.execute(
                    update(dwg_baseline)
                    .where(dwg_baseline.c.id == baseline["id"])
                    .values(
                        accepted_value_json=next(iter(values)),
                        project_revision=revision,
                        updated_at_utc=now,
                    )
                )
                if owner_path.startswith("base_line:") and owner_path.endswith(":LED_TYPE"):
                    base = owner_path.split(":", 2)[1]
                    line_id = uow.execute(
                        select(cable_line.c.id).where(
                            cable_line.c.project_id == plan.project_id,
                            cable_line.c.designation == base,
                            cable_line.c.lifecycle == "ACTIVE",
                        )
                    ).scalar_one_or_none()
                    if line_id is not None:
                        uow.execute(
                            update(led_line_profile)
                            .where(
                                led_line_profile.c.project_id == plan.project_id,
                                led_line_profile.c.cable_line_id == line_id,
                            )
                            .values(
                                sync_baseline_json={"LED_TYPE": next(iter(values))},
                                sync_state="IN_SYNC",
                                row_version=led_line_profile.c.row_version + 1,
                                updated_at_utc=now,
                            )
                        )
            uow.commit()


def _validation_reason(issues) -> str:
    return " | ".join(f"{issue.code} [{issue.field or '-'}]: {issue.message}" for issue in issues)


def _preview_display_contexts(
    connection,
    *,
    project_id: str,
    binding_id: str | None,
    observations: tuple[ValidatedObservation, ...],
) -> dict[str, dict[str, str]]:
    """Resolve preview rooms against current Project identity without mutating data."""

    building_rows = list(
        connection.execute(
            select(building.c.id, building.c.name).where(building.c.project_id == project_id)
        ).mappings()
    )
    room_rows = list(
        connection.execute(
            select(room.c.id, room.c.name, room.c.building_id).where(
                room.c.project_id == project_id
            )
        ).mappings()
    )
    canonical_by_id = {row["id"]: row["name"] for row in room_rows}
    stable_by_handle: dict[str, str] = {}
    stable_query = select(field_device.c.entity_handle, field_device.c.room_id).where(
        field_device.c.project_id == project_id,
        field_device.c.lifecycle == "ACTIVE",
        field_device.c.entity_handle.is_not(None),
    )
    if binding_id is not None:
        stable_query = stable_query.where(field_device.c.dwg_document_binding_id == binding_id)
    for row in connection.execute(stable_query).mappings():
        room_name = canonical_by_id.get(row["room_id"])
        if room_name:
            stable_by_handle[row["entity_handle"]] = room_name

    contexts: dict[str, dict[str, str]] = {}
    for item in observations:
        if item.ignored_project_data or not item.observation.handle:
            continue
        raw_room = str(item.normalized_attributes.get("ROOM", "")).strip()
        canonical = stable_by_handle.get(item.observation.handle)
        if canonical is None and raw_room:
            raw_building = str(item.normalized_attributes.get("BUILDING", "")).strip()
            candidates = room_rows
            if raw_building:
                matched_buildings = [
                    row
                    for row in building_rows
                    if normalize_room_name(row["name"]) == normalize_room_name(raw_building)
                ]
                candidates = (
                    [row for row in room_rows if row["building_id"] == matched_buildings[0]["id"]]
                    if len(matched_buildings) == 1
                    else []
                )
            resolution = resolve_room(
                (RoomIdentity(row["id"], row["name"]) for row in candidates),
                raw_room,
            )
            canonical = canonical_by_id.get(resolution.room_id)
        display = canonical or (f"Не разрешено: {raw_room}" if raw_room else "Не разрешено")
        contexts[item.observation.handle] = {
            "room_name": display,
            "raw_room": raw_room,
        }
    return contexts


def _fields(item: ValidatedObservation) -> dict[str, Any]:
    observation = item.observation
    values = {
        "BLOCK_NAME": observation.effective_name,
        "LAYER": observation.layer,
        "X": observation.x,
        "Y": observation.y,
        "DWG_HANDLE": observation.handle,
        "FUNCTION_GROUP": item.function_group,
        **dict(item.normalized_attributes),
    }
    values["DEVICE_TYPE"] = item.device_type
    payload = item.read_payload
    if payload is not None:
        if payload.derived_phase is not None:
            values["PHASE"] = payload.derived_phase
        if payload.cable_link_kind and payload.cable_identity is not None:
            values["CABLE_LINK"] = payload.cable_link_kind
        if payload.bus_link_kind and payload.bus_point_id:
            values["BUS_LINK"] = payload.bus_link_kind
        if payload.bus_id:
            values["BUS_ID"] = payload.bus_id
            values["BUS_TYPE"] = payload.bus_type
    return values


def _legacy_box_owner_path(owner_key: str, field: str, fields: dict) -> str | None:
    base, _, identity = owner_key.partition("/")
    if not identity.startswith("BOX.") or fields.get("BOX_ID") != identity:
        return None
    if fields.get("CABLE_ID") != base:
        return None
    if field == "CABLE_SOURCE":
        return f"edge:{base}:CABLE_SOURCE"
    if field in SEGMENT_OWNED_FIELDS:
        return f"segment:{base}/{base}:{field}"
    return None


def _load_project_owner_values(
    connection,
    *,
    project_id: str,
    snapshot: NormalizedCadSnapshot,
    devices: dict[str, dict[str, Any]],
    baselines: dict[str, Any],
) -> dict[str, Any]:
    """Read each Project value from its schema-7 authoritative owner."""

    result: dict[str, Any] = {}
    device_locations = {
        row["entity_handle"]: {
            "ROOM": row["room_name"],
            "BUILDING": row["building_name"],
        }
        for row in connection.execute(
            select(
                field_device.c.entity_handle,
                room.c.name.label("room_name"),
                building.c.name.label("building_name"),
            )
            .select_from(field_device)
            .outerjoin(room, room.c.id == field_device.c.room_id)
            .outerjoin(building, building.c.id == room.c.building_id)
            .where(
                field_device.c.project_id == project_id,
                field_device.c.lifecycle == "ACTIVE",
                field_device.c.entity_handle.is_not(None),
            )
        ).mappings()
    }
    line_rows = {
        row["designation"]: row
        for row in connection.execute(
            select(
                cable_line.c.id,
                cable_line.c.designation,
                cable_line.c.system_kind,
                cable_line.c.cable_facts_json,
            ).where(
                cable_line.c.project_id == project_id,
                cable_line.c.lifecycle == "ACTIVE",
            )
        ).mappings()
    }
    line_by_id = {row["id"]: designation for designation, row in line_rows.items()}
    led_by_line_id = {
        row["cable_line_id"]: row["led_kind"]
        for row in connection.execute(
            select(led_line_profile.c.cable_line_id, led_line_profile.c.led_kind).where(
                led_line_profile.c.project_id == project_id
            )
        ).mappings()
    }
    segment_rows: dict[str, dict[str, Any]] = {}
    for row in connection.execute(
        select(
            cable_point.c.cable_line_id,
            cable_point.c.logical_identity,
            cable_segment.c.mount_way,
            cable_segment.c.gofra_type,
            cable_segment.c.gofra_color,
            conduit.c.designation.label("gofra_id"),
        )
        .select_from(cable_point)
        .join(
            cable_topology_endpoint,
            cable_topology_endpoint.c.cable_point_id == cable_point.c.id,
        )
        .join(
            cable_segment,
            cable_segment.c.target_endpoint_id == cable_topology_endpoint.c.id,
        )
        .outerjoin(
            conduit_segment_assignment,
            conduit_segment_assignment.c.cable_segment_id == cable_segment.c.id,
        )
        .outerjoin(conduit, conduit.c.id == conduit_segment_assignment.c.conduit_id)
        .where(cable_point.c.project_id == project_id)
    ).mappings():
        line_designation = line_by_id.get(row["cable_line_id"])
        if line_designation is not None and row["logical_identity"]:
            segment_rows[f"{line_designation}/{row['logical_identity']}"] = dict(row)

    source_endpoint = cable_topology_endpoint.alias("source_endpoint_read")
    target_endpoint = cable_topology_endpoint.alias("target_endpoint_read")
    source_point = cable_point.alias("source_point_read")
    target_point = cable_point.alias("target_point_read")
    source_port = field_port.alias("source_port_read")
    source_device = field_device.alias("source_device_read")
    box_by_point_id = {
        row["cable_point_id"]: str((row["normalized_fields_json"] or {}).get("BOX_ID", ""))
        for row in connection.execute(
            select(
                cable_point_field_device.c.cable_point_id,
                field_device.c.normalized_fields_json,
            )
            .select_from(
                cable_point_field_device.join(
                    field_device,
                    field_device.c.id == cable_point_field_device.c.field_device_id,
                )
            )
            .where(cable_point_field_device.c.project_id == project_id)
        ).mappings()
        if (row["normalized_fields_json"] or {}).get("BOX_ID")
    }
    canonical_sources: dict[str, str] = {}
    for row in connection.execute(
        select(
            cable_segment.c.cable_line_id,
            target_point.c.logical_identity.label("target_identity"),
            source_endpoint.c.endpoint_kind.label("source_kind"),
            source_point.c.id.label("source_point_id"),
            source_point.c.point_kind.label("source_point_kind"),
            source_point.c.logical_identity.label("source_identity"),
            source_port.c.port_tag,
            source_device.c.entity_handle.label("source_handle"),
            source_device.c.normalized_fields_json.label("source_fields"),
        )
        .select_from(cable_segment)
        .join(target_endpoint, target_endpoint.c.id == cable_segment.c.target_endpoint_id)
        .join(target_point, target_point.c.id == target_endpoint.c.cable_point_id)
        .join(source_endpoint, source_endpoint.c.id == cable_segment.c.source_endpoint_id)
        .outerjoin(source_point, source_point.c.id == source_endpoint.c.cable_point_id)
        .outerjoin(source_port, source_port.c.id == source_endpoint.c.field_port_id)
        .outerjoin(source_device, source_device.c.id == source_port.c.field_device_id)
        .where(cable_segment.c.project_id == project_id)
    ).mappings():
        line_designation = line_by_id.get(row["cable_line_id"])
        target_identity = row["target_identity"]
        if not line_designation or not target_identity:
            continue
        if row["source_kind"] == "FIELD_PORT":
            bus_point_id = str((row["source_fields"] or {}).get("BUS_POINT_ID", ""))
            source_value = f"{bus_point_id}/{row['port_tag']}"
        elif row["source_point_kind"] == "INTERNAL_SOURCE":
            source_value = ""
        elif row["source_point_kind"] == "EL_BOX":
            source_value = box_by_point_id.get(row["source_point_id"], "")
        else:
            source_value = row["source_identity"] or ""
        canonical_sources[f"edge:{target_identity}:CABLE_SOURCE"] = source_value

    key_values = {
        (row["entity_handle"], row["key_tag"]): row["functional_target_text"] or ""
        for row in connection.execute(
            select(
                field_device.c.entity_handle,
                field_control_key.c.key_tag,
                field_control_key.c.functional_target_text,
            )
            .select_from(field_control_key)
            .join(field_device, field_device.c.id == field_control_key.c.field_device_id)
            .where(
                field_control_key.c.project_id == project_id,
                field_control_key.c.lifecycle == "ACTIVE",
            )
        ).mappings()
    }
    for fact in snapshot.facts:
        if fact.owner_kind is SyncOwnerKind.BASE_LINE:
            row = line_rows.get(fact.owner_key)
            if row is None:
                continue
            if fact.field == "FUNCTION_GROUP":
                result[fact.owner_path] = row["system_kind"]
            elif fact.field == "CABLE_ID":
                result[fact.owner_path] = row["designation"]
            elif fact.field == "LED_TYPE":
                result[fact.owner_path] = led_by_line_id.get(row["id"])
            else:
                result[fact.owner_path] = dict(row["cable_facts_json"] or {}).get(fact.field)
        elif fact.owner_kind is SyncOwnerKind.SEGMENT:
            legacy_path = _legacy_box_owner_path(
                fact.owner_key, fact.field, devices.get(fact.primary_handle, {})
            )
            if fact.field == "CABLE_SOURCE":
                if fact.owner_path in canonical_sources:
                    result[fact.owner_path] = canonical_sources[fact.owner_path]
                elif legacy_path in canonical_sources:
                    result[fact.owner_path] = canonical_sources[legacy_path]
                continue
            row = segment_rows.get(fact.owner_key)
            if row is None and legacy_path:
                row = segment_rows.get(legacy_path.split(":")[1])
            if row is None:
                continue
            column = {
                "MOUNT_WAY": "mount_way",
                "GOFRA_TYPE": "gofra_type",
                "GOFRA_COLOR": "gofra_color",
                "GOFRA_ID": "gofra_id",
            }[fact.field]
            result[fact.owner_path] = row[column] or ""
        elif fact.owner_kind is SyncOwnerKind.CONTROL_KEY:
            value = key_values.get((fact.primary_handle, fact.field))
            if value is not None:
                result[fact.owner_path] = value
        else:
            fields = devices.get(fact.primary_handle)
            if fields is not None:
                if fact.field in {"ROOM", "BUILDING"}:
                    canonical_value = device_locations.get(fact.primary_handle, {}).get(fact.field)
                    result[fact.owner_path] = (
                        canonical_value if canonical_value is not None else fields.get(fact.field)
                    )
                else:
                    result[fact.owner_path] = fields.get(fact.field)
    return result


def _classify(baseline: Any, project_value: Any, dwg_value: Any):
    if baseline is None and project_value == dwg_value:
        return ChangeClass.EQUAL, "Both sides are equal; no earlier baseline is required"
    project_changed = project_value != baseline
    dwg_changed = dwg_value != baseline
    if project_value == dwg_value and project_changed and dwg_changed:
        return ChangeClass.EQUAL, "Both sides changed to the same normalized value"
    if project_value == dwg_value:
        return ChangeClass.EQUAL, "Project and DWG values are equal"
    if dwg_changed and not project_changed:
        return ChangeClass.DWG_CHANGED, "Only DWG differs from the confirmed baseline"
    if project_changed and not dwg_changed:
        return ChangeClass.PROJECT_CHANGED, "Only Project differs from the confirmed baseline"
    return ChangeClass.BOTH_CHANGED_CONFLICT, "Both sides differ from baseline and each other"


def _application_uuid(identity: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"nlp2-dwg:{identity.casefold()}"))


def _fingerprint(identity: str) -> str:
    path = Path(identity)
    if path.is_file():
        stat = path.stat()
        source = f"{identity.casefold()}|{stat.st_size}|{stat.st_mtime_ns}"
    else:
        source = identity.casefold()
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _batch_payload(batch: CadObservationBatch) -> bytes:
    payload = [
        {
            "name": item.effective_name,
            "layer": item.layer,
            "handle": item.handle,
            "x": item.x,
            "y": item.y,
            "attributes": [(attribute.tag, attribute.value) for attribute in item.raw_attributes],
        }
        for item in batch.observations
        if item.effective_name != "ROOM_NAME"
    ]
    return json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")


def _write_plan_fingerprint(
    *,
    project_id: str,
    binding_id: str,
    document_identity: str,
    project_revision: int,
    selected: set[str],
    targets: tuple[DwgWriteTarget, ...],
) -> str:
    payload = {
        "project_id": project_id,
        "binding_id": binding_id,
        "document_identity": document_identity,
        "project_revision": project_revision,
        "selected_paths": sorted(selected),
        "targets": [
            {
                "handle": target.handle,
                "tag": target.tag,
                "expected_old_value": target.expected_old_value,
                "new_value": target.new_value,
                "expected_block_name": target.expected_block_name,
                "expected_layer": target.expected_layer,
                "owner_kind": target.owner_kind,
                "owner_key": target.owner_key,
                "owner_path": target.owner_path,
                "reason": target.reason,
            }
            for target in targets
        ],
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
