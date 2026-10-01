"""Homogeneous selection -> deterministic preview -> one atomic Project commit."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, or_, select, update
from sqlalchemy.exc import IntegrityError

from nl_project_2.catalog.equipment import _product_count, _snapshot
from nl_project_2.constructor import ConstructorService
from nl_project_2.constructor.domain import find_cycle, validate_relation
from nl_project_2.equipment_actions import EquipmentActionService
from nl_project_2.guided_actions import GuidedAction, GuidedActionService
from nl_project_2.operations import LocalApplicationProfile
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    bulk_operation_receipt,
    cable_line,
    cable_line_assignment,
    cable_topology_endpoint,
    control_key_input_assignment,
    field_control_key,
    field_port,
    functional_relation,
    instance_resource,
    led_line_profile,
    operation_journal,
    passport_definition,
    passport_resource_definition,
    product_definition,
    project,
    project_instance,
    resource_reservation,
    user_reserve,
)
from nl_project_2.persistence.uow import UnitOfWork
from nl_project_2.resource_labels import resource_display_name

from .domain import (
    BulkActionError,
    BulkActionPreview,
    BulkActionReceipt,
    BulkConfirmationRequired,
    BulkMapping,
    BulkOwner,
    BulkPlanBlocked,
    BulkSelectionSnapshot,
    BulkVariant,
    BulkVariantQuery,
    StaleBulkPreview,
)

_AVAILABILITY_REASONS = frozenset({"OCCUPIED", "USER_RESERVE"})


@dataclass(frozen=True, slots=True)
class _Contract:
    stable_identity: str
    passport_id: str
    passport_key: str
    passport_name: str
    product_id: str | None
    product_key: str | None
    product_name: str | None
    product_parameters: dict[str, Any]
    resource_key: str
    supply_scope: str
    templates: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class _Unit:
    key: str
    command_kind: str
    instance_id: str
    instance_designation: str
    resource_refs: tuple[str, ...]
    resource_labels: tuple[str, ...]
    new_index: int | None
    source_facts: Any = None


@dataclass(frozen=True, slots=True)
class _PlannedMapping:
    owner: BulkOwner
    unit: _Unit
    command: dict[str, Any]
    fact_kind: str
    fact_count: int


@dataclass(frozen=True, slots=True)
class _Plan:
    preview: BulkActionPreview
    mappings: tuple[_PlannedMapping, ...]
    contract: _Contract | None


class BulkActionService:
    """One reusable application service for all four approved bulk actions."""

    def __init__(
        self,
        engine: Engine,
        preference_profile: LocalApplicationProfile | None = None,
    ) -> None:
        self._engine = engine
        self._profile = preference_profile
        self.guided = GuidedActionService(engine, preference_profile)
        self.equipment = EquipmentActionService(engine)
        self.constructor = ConstructorService(engine)

    def selection_snapshot(
        self,
        action: GuidedAction | str,
        *,
        project_id: str,
        owner_ids: tuple[str, ...] | list[str],
    ) -> BulkSelectionSnapshot:
        action = GuidedAction(action)
        revision = self._project_revision(project_id)
        requested = tuple(str(value) for value in owner_ids)
        duplicate_ids = {value for value in requested if requested.count(value) > 1}
        owners: list[BulkOwner] = []
        for owner_id in dict.fromkeys(requested):
            reasons = ("DUPLICATE_OWNER",) if owner_id in duplicate_ids else ()
            try:
                owner, _records = self.guided._records(action, project_id, owner_id)
                label = owner.label
                context = self._context_kind(action, project_id, owner_id)
            except Exception:
                label = f"Недоступный owner {owner_id}"
                context = "UNKNOWN"
                reasons = tuple(dict.fromkeys((*reasons, "OWNER_NOT_FOUND_OR_INACTIVE")))
            owners.append(BulkOwner(owner_id, label, context, reasons))
        owners.sort(key=lambda item: (_natural_key(item.label), item.owner_id))
        if not owners:
            owners.append(BulkOwner("", "Selection пуст", "UNKNOWN", ("SELECTION_REQUIRED",)))
        contexts = {item.context_kind for item in owners if item.valid}
        if len(contexts) > 1:
            owners = [
                replace(
                    item,
                    reason_codes=tuple(dict.fromkeys((*item.reason_codes, "MIXED_SELECTION"))),
                )
                for item in owners
            ]
        payload = {
            "version": 1,
            "project_id": project_id,
            "project_revision": revision,
            "action": action.value,
            "owners": [(item.owner_id, item.context_kind, item.reason_codes) for item in owners],
        }
        return BulkSelectionSnapshot(
            project_id,
            revision,
            action,
            action.label,
            tuple(owners),
            _hash(payload),
        )

    def candidate_variants(self, snapshot: BulkSelectionSnapshot) -> BulkVariantQuery:
        self._require_snapshot_current(snapshot)
        if not snapshot.valid:
            return BulkVariantQuery(
                snapshot.action,
                snapshot.action_label,
                snapshot.fingerprint,
                snapshot.project_revision,
                (),
                "SELECTION_BLOCKED",
            )
        records_by_owner = self._records_by_owner(snapshot)
        identities = sorted(
            {
                record.preference_identity
                for records in records_by_owner.values()
                for record in records
            }
        )
        preferred = None
        if self._profile is not None:
            try:
                preferred = self._profile.preference(snapshot.action.value).stable_identity
            except OSError:
                preferred = None
        variants = []
        for identity in identities:
            reasons: list[str] = []
            selectable_records = []
            sample = None
            for owner in snapshot.owners:
                matches = [
                    record
                    for record in records_by_owner[owner.owner_id]
                    if record.preference_identity == identity
                ]
                sample = sample or (matches[0] if matches else None)
                if not matches:
                    reasons.append("VARIANT_NOT_APPLICABLE")
                    continue
                engineering = {
                    reason
                    for record in matches
                    for reason in record.dto.reason_codes
                    if reason not in _AVAILABILITY_REASONS
                }
                if engineering:
                    reasons.extend(sorted(engineering))
                selectable_records.extend(record for record in matches if record.dto.selectable)
            contract = self._variant_contract(snapshot.project_id, identity)
            resource_key = identity.rsplit(":", 1)[-1]
            label = (
                self._contract_label(contract)
                if contract is not None
                else (sample.dto.target_label if sample is not None else identity)
            )
            unique_resources = {
                tuple(record.command.get(key) for key in ("id", "source_resource_id"))
                or (record.dto.candidate_id,)
                for record in selectable_records
            }
            variants.append(
                BulkVariant(
                    identity,
                    label,
                    None if contract is None else contract.passport_key,
                    None if contract is None else contract.product_key,
                    resource_key,
                    not reasons,
                    len(unique_resources),
                    contract is not None,
                    preferred == identity,
                    tuple(dict.fromkeys(reasons)),
                )
            )
        variants.sort(
            key=lambda item: (
                0 if item.selectable and item.preferred else 1 if item.selectable else 2,
                _natural_key(item.label),
                item.stable_identity,
            )
        )
        status = "READY" if any(item.selectable for item in variants) else "NO_COMMON_VARIANT"
        return BulkVariantQuery(
            snapshot.action,
            snapshot.action_label,
            snapshot.fingerprint,
            snapshot.project_revision,
            tuple(variants),
            status,
        )

    def preview(
        self,
        snapshot: BulkSelectionSnapshot,
        *,
        chosen_variant_identity: str,
        proposed_designations: tuple[str, ...] | list[str] = (),
    ) -> BulkActionPreview:
        return self._build_plan(
            snapshot,
            str(chosen_variant_identity),
            tuple(str(value).strip() for value in proposed_designations),
        ).preview

    def confirm(self, preview: BulkActionPreview, *, confirmed: bool) -> BulkActionReceipt:
        if not confirmed:
            raise BulkConfirmationRequired(
                "Массовая операция выполняется только после явного подтверждения"
            )
        payload = self._decode_token(preview.confirmation_token)
        if preview.fingerprint != payload.get("preview_fingerprint"):
            raise BulkActionError("BULK_PREVIEW_FINGERPRINT_INVALID")
        with self._engine.connect() as connection:
            existing = self._receipt_row(connection, preview.fingerprint)
        if existing is not None:
            return self._receipt_dto(existing)
        snapshot = self.selection_snapshot(
            payload["action"],
            project_id=payload["project_id"],
            owner_ids=tuple(payload["owner_ids"]),
        )
        if snapshot.fingerprint != payload["selection_fingerprint"]:
            raise StaleBulkPreview("SELECTION_SNAPSHOT_CHANGED")
        plan = self._build_plan(
            snapshot,
            payload["chosen_variant_identity"],
            tuple(payload["proposed_designations"]),
        )
        if plan.preview.fingerprint != preview.fingerprint:
            raise StaleBulkPreview("BULK_PLAN_CHANGED")
        if not preview.confirmable:
            raise BulkPlanBlocked("Bulk preview contains blocking rows or conflicts")
        now = datetime.now(UTC)
        command_id = _uuid_from_hash(f"command:{preview.fingerprint}")
        try:
            with UnitOfWork(self._engine) as uow:
                existing = self._receipt_row(uow, preview.fingerprint)
                if existing is not None:
                    uow.commit()
                    return self._receipt_dto(existing)
                revision = uow.execute(
                    select(project.c.project_revision).where(
                        project.c.id == preview.project_id,
                        project.c.lifecycle == "ACTIVE",
                    )
                ).scalar_one_or_none()
                if revision != preview.project_revision:
                    raise StaleBulkPreview("STALE_PROJECT_REVISION")
                resource_ids = self._materialize_new_instances(uow, plan)
                fact_count = 0
                for index, mapping in enumerate(plan.mappings, start=1):
                    fact_count += self._execute_mapping(
                        uow, preview, mapping, resource_ids, command_id, index, now
                    )
                after = preview.project_revision + 1
                result = uow.execute(
                    update(project)
                    .where(
                        project.c.id == preview.project_id,
                        project.c.lifecycle == "ACTIVE",
                        project.c.project_revision == preview.project_revision,
                    )
                    .values(
                        project_revision=after,
                        row_version=project.c.row_version + 1,
                        updated_at_utc=now,
                    )
                )
                if result.rowcount != 1:
                    raise StaleBulkPreview("STALE_PROJECT_REVISION")
                receipt_id = new_id()
                summary = {
                    "action_label": preview.action_label,
                    "selection_count": preview.selected_owner_count,
                    "chosen_variant": preview.chosen_variant_label,
                    "chosen_variant_identity": preview.chosen_variant_identity,
                    "new_designations": list(preview.new_designations),
                    "canonical_fact_count": fact_count,
                    "result": "SUCCEEDED",
                }
                uow.execute(
                    bulk_operation_receipt.insert().values(
                        id=receipt_id,
                        project_id=preview.project_id,
                        command_id=command_id,
                        action_type=preview.action.value,
                        selected_owner_ids_json=[item.owner.owner_id for item in plan.mappings],
                        preview_fingerprint=preview.fingerprint,
                        project_revision_before=preview.project_revision,
                        project_revision_after=after,
                        result_status="SUCCEEDED",
                        correlation_id=preview.correlation_id,
                        summary_json=summary,
                        created_at_utc=now,
                    )
                )
                uow.execute(
                    operation_journal.insert().values(
                        id=new_id(),
                        project_id=preview.project_id,
                        command_id=command_id,
                        command_type=f"BULK_{preview.action.value}",
                        project_revision_before=preview.project_revision,
                        project_revision_after=after,
                        correlation_id=preview.correlation_id,
                        status="SUCCEEDED",
                        started_at_utc=now,
                        completed_at_utc=now,
                        summary_json=summary,
                    )
                )
                uow.commit()
        except IntegrityError as exc:
            raise StaleBulkPreview("BULK_COMMIT_CONFLICT") from exc
        preference_updated = False
        diagnostic = None
        if self._profile is not None:
            try:
                self._profile.update(preview.action.value, preview.chosen_variant_identity)
                preference_updated = True
            except Exception as exc:
                diagnostic = f"LOCAL_PREFERENCE_UPDATE_FAILED:{type(exc).__name__}"
        return BulkActionReceipt(
            receipt_id,
            command_id,
            preview.action,
            preview.action_label,
            preview.selected_owner_count,
            preview.new_designations,
            fact_count,
            preview.project_revision,
            after,
            "SUCCEEDED",
            preview.correlation_id,
            preview.chosen_variant_identity,
            preference_updated,
            diagnostic,
        )

    def list_receipts(self, project_id: str) -> tuple[BulkActionReceipt, ...]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(bulk_operation_receipt)
                .where(bulk_operation_receipt.c.project_id == project_id)
                .order_by(bulk_operation_receipt.c.created_at_utc, bulk_operation_receipt.c.id)
            ).mappings()
            return tuple(self._receipt_dto(row) for row in rows)

    def _build_plan(
        self,
        snapshot: BulkSelectionSnapshot,
        identity: str,
        proposed_designations: tuple[str, ...],
    ) -> _Plan:
        self._require_snapshot_current(snapshot)
        conflicts: list[str] = []
        if not snapshot.valid:
            conflicts.append("SELECTION_BLOCKED")
        query = self.candidate_variants(snapshot) if snapshot.valid else None
        variant = (
            None
            if query is None
            else next(
                (item for item in query.variants if item.stable_identity == identity),
                None,
            )
        )
        if variant is None:
            conflicts.append("CHOSEN_VARIANT_NOT_FOUND")
        elif not variant.selectable:
            conflicts.extend(variant.reason_codes or ("CHOSEN_VARIANT_NOT_APPLICABLE",))
        contract = self._variant_contract(snapshot.project_id, identity)
        records_by_owner = self._records_by_owner(snapshot) if snapshot.valid else {}
        matches_by_owner: dict[str, list[Any]] = {}
        unavailable: list[BulkOwner] = []
        command_shapes = set()
        for owner in snapshot.owners:
            matches = [
                record
                for record in records_by_owner.get(owner.owner_id, ())
                if record.preference_identity == identity
            ]
            matches_by_owner[owner.owner_id] = matches
            engineering = tuple(
                dict.fromkeys(
                    reason
                    for record in matches
                    for reason in record.dto.reason_codes
                    if reason not in _AVAILABILITY_REASONS
                )
            )
            if not matches or engineering:
                reasons = engineering or ("VARIANT_NOT_APPLICABLE",)
                unavailable.append(replace(owner, reason_codes=reasons))
            for record in matches:
                shape = (
                    record.command["kind"],
                    len(record.command.get("channel_ordinals", ())),
                )
                command_shapes.add(shape)
        if len(command_shapes) > 1:
            conflicts.append("MIXED_SELECTION")
        planned: list[_PlannedMapping] = []
        used_refs: set[str] = set()
        relation_targets: dict[str, list[str]] = defaultdict(list)
        with self._engine.connect() as connection:
            for owner in snapshot.owners:
                if any(item.owner_id == owner.owner_id for item in unavailable):
                    continue
                chosen = self._allocate_existing(
                    connection,
                    snapshot,
                    owner,
                    matches_by_owner[owner.owner_id],
                    used_refs,
                    relation_targets,
                )
                if chosen is not None:
                    planned.append(chosen)
            shortage = [
                owner
                for owner in snapshot.owners
                if owner.valid
                and not any(item.owner.owner_id == owner.owner_id for item in planned)
                and not any(item.owner_id == owner.owner_id for item in unavailable)
            ]
            new_index = 0
            while shortage and contract is not None and new_index < len(snapshot.owners):
                new_index += 1
                units = self._new_units(
                    contract,
                    matches_by_owner[shortage[0].owner_id][0].command,
                    new_index,
                )
                progress = False
                for owner in tuple(shortage):
                    mapping = self._allocate_new(
                        connection,
                        snapshot,
                        owner,
                        matches_by_owner[owner.owner_id][0].command,
                        units,
                        used_refs,
                        relation_targets,
                    )
                    if mapping is not None:
                        planned.append(mapping)
                        shortage.remove(owner)
                        progress = True
                if not progress:
                    break
        if shortage:
            reason = (
                "FIELD_DEVICE_AUTO_CREATE_FORBIDDEN" if contract is None else "SHORTAGE_UNRESOLVED"
            )
            unavailable.extend(replace(owner, reason_codes=(reason,)) for owner in shortage)
        new_count = max(
            (item.unit.new_index or 0 for item in planned),
            default=0,
        )
        designations: tuple[str, ...] = ()
        if new_count:
            if len(proposed_designations) != new_count:
                conflicts.append(
                    "DESIGNATION_INPUT_REQUIRED"
                    if not proposed_designations
                    else "DESIGNATION_COUNT_MISMATCH"
                )
            else:
                designation_plan = self.equipment.plan_designations(
                    project_id=snapshot.project_id,
                    proposed_designations=proposed_designations,
                )
                designations = tuple(
                    item.proposed_designation for item in designation_plan.proposed
                )
                conflicts.extend(
                    code for item in designation_plan.proposed for code in item.conflict_codes
                )
        mapped = []
        public_mappings = []
        for item in sorted(planned, key=lambda value: _natural_key(value.owner.label)):
            unit = item.unit
            if unit.new_index is not None and len(designations) == new_count:
                designation = designations[unit.new_index - 1]
                labels = tuple(f"{designation} / {label}" for label in unit.resource_labels)
                unit = replace(unit, instance_designation=designation)
            else:
                designation = unit.instance_designation
                labels = unit.resource_labels
            mapped_item = replace(item, unit=unit)
            mapped.append(mapped_item)
            public_mappings.append(
                BulkMapping(
                    item.owner.owner_id,
                    item.owner.label,
                    designation,
                    "NEW"
                    if unit.new_index is not None
                    else (
                        "FIELD"
                        if unit.command_kind.startswith("KEY_FIELD")
                        or unit.command_kind == "FIELD_OUTPUT"
                        else "EXISTING"
                    ),
                    labels,
                    (
                        f"{snapshot.action_label}: {item.owner.label} → "
                        f"{designation} / {' + '.join(labels)}"
                    ),
                    item.fact_kind,
                    item.fact_count,
                    unit.resource_refs,
                )
            )
        plan_payload = {
            "version": 1,
            "selection_fingerprint": snapshot.fingerprint,
            "chosen_variant_identity": identity,
            "proposed_designations": designations or proposed_designations,
            "mappings": [
                (
                    item.owner.owner_id,
                    item.unit.key,
                    item.unit.instance_designation,
                    item.unit.resource_refs,
                    item.command["kind"],
                )
                for item in mapped
            ],
            "unavailable": [(item.owner_id, item.reason_codes) for item in unavailable],
            "conflicts": tuple(dict.fromkeys(conflicts)),
        }
        fingerprint = _hash(plan_payload)
        correlation_id = _uuid_from_hash(f"correlation:{fingerprint}")
        token_payload = {
            "version": 1,
            "project_id": snapshot.project_id,
            "action": snapshot.action.value,
            "owner_ids": [item.owner_id for item in snapshot.owners],
            "selection_fingerprint": snapshot.fingerprint,
            "chosen_variant_identity": identity,
            "proposed_designations": list(proposed_designations),
            "preview_fingerprint": fingerprint,
        }
        token = base64.urlsafe_b64encode(
            json.dumps(token_payload, sort_keys=True, separators=(",", ":")).encode()
        ).decode("ascii")
        warnings = tuple(
            dict.fromkeys(
                warning
                for records in matches_by_owner.values()
                for record in records
                for warning in record.dto.warnings
            )
        )
        preview = BulkActionPreview(
            snapshot.project_id,
            snapshot.project_revision,
            snapshot.action,
            snapshot.action_label,
            len(snapshot.owners),
            identity,
            identity if variant is None else variant.label,
            tuple(public_mappings),
            tuple(unavailable),
            designations,
            sum(item.unit.new_index is not None for item in mapped),
            new_count,
            sum(item.fact_count for item in mapped),
            warnings,
            tuple(dict.fromkeys(conflicts)),
            fingerprint,
            token,
            correlation_id,
        )
        return _Plan(preview, tuple(mapped), contract)

    def _allocate_existing(
        self, connection, snapshot, owner, records, used_refs, relation_targets
    ) -> _PlannedMapping | None:
        ordered = sorted(
            (record for record in records if record.dto.selectable),
            key=lambda record: (
                _natural_key(record.dto.target_label),
                record.dto.candidate_id,
            ),
        )
        for record in ordered:
            unit = self._unit_from_record(record)
            if unit.command_kind == "RELATION":
                source = unit.resource_refs[0]
                if not self._relation_available(
                    connection,
                    snapshot.project_id,
                    source,
                    owner.owner_id,
                    relation_targets[source],
                ):
                    continue
                relation_targets[source].append(owner.owner_id)
            elif used_refs.intersection(unit.resource_refs):
                continue
            else:
                used_refs.update(unit.resource_refs)
            return self._mapping(owner, unit, record.command)
        return None

    def _allocate_new(
        self,
        connection,
        snapshot,
        owner,
        owner_command,
        units,
        used_refs,
        relation_targets,
    ) -> _PlannedMapping | None:
        for unit in units:
            if unit.command_kind == "RELATION":
                source = unit.resource_refs[0]
                if not self._new_relation_available(
                    connection,
                    snapshot.project_id,
                    unit.source_facts,
                    owner.owner_id,
                    relation_targets[source],
                ):
                    continue
                relation_targets[source].append(owner.owner_id)
            elif used_refs.intersection(unit.resource_refs):
                continue
            else:
                used_refs.update(unit.resource_refs)
            return self._mapping(owner, unit, owner_command)
        return None

    @staticmethod
    def _mapping(owner, unit, command):
        kind = command["kind"]
        fact_kind = (
            "FUNCTIONAL_RELATION"
            if kind == "RELATION"
            else "CONTROL_KEY_INPUT_ASSIGNMENT"
            if kind.startswith("KEY_")
            else "CABLE_LINE_ASSIGNMENT"
        )
        count = len(unit.resource_refs) if kind == "LED_BUNDLE" else 1
        return _PlannedMapping(owner, unit, dict(command), fact_kind, count)

    def _unit_from_record(self, record) -> _Unit:
        command = record.command
        kind = command["kind"]
        if kind == "RELATION":
            refs = (command["source_resource_id"],)
        elif kind in {
            "RESOURCE_OUTPUT",
            "KEY_RESOURCE_INPUT",
            "FIELD_OUTPUT",
            "KEY_FIELD_INPUT",
        }:
            refs = (command["id"],)
        else:
            with self._engine.connect() as connection:
                refs = tuple(
                    connection.execute(
                        select(instance_resource.c.id)
                        .where(
                            instance_resource.c.project_instance_id
                            == command["module_instance_id"],
                            instance_resource.c.resource_key == "PWM_OUTPUT",
                            instance_resource.c.ordinal.in_(command["channel_ordinals"]),
                        )
                        .order_by(instance_resource.c.ordinal)
                    ).scalars()
                )
        labels = tuple(
            part.strip() for part in record.dto.target_label.split(" / ")[-1].split(" + ")
        )
        instance = record.dto.instance_label or "Полевое устройство"
        key = f"{kind}:{'|'.join(refs)}"
        return _Unit(key, kind, instance, instance, refs, labels, None)

    def _new_units(self, contract: _Contract, command, new_index: int) -> tuple[_Unit, ...]:
        resources: list[tuple[str, int, str, Any]] = []
        product = (
            {
                "product_key": contract.product_key,
                "project_parameters_json": contract.product_parameters,
            }
            if contract.product_id is not None
            else None
        )
        for template in contract.templates:
            if template["resource_key"] != contract.resource_key:
                continue
            count = _product_count(template, product)
            ordinals = (
                range(count)
                if (template["display_json"] or {}).get("materialization") == "PRODUCT_DEFINED"
                else (template["ordinal"],)
            )
            for ordinal in ordinals:
                ref = f"new:{new_index}:{contract.resource_key}:{ordinal}"
                row = {
                    "id": ref,
                    "project_instance_id": f"new:{new_index}",
                    "resource_key": contract.resource_key,
                    "ordinal": ordinal,
                    "resource_kind": template["resource_kind"],
                    "direction": template["direction"],
                    "medium": template["medium"],
                    "snapshot_json": _snapshot(template, product, ordinal),
                    "display_json": template["display_json"],
                    "exclusive": template["exclusive"],
                    "capacity_decimal": template["capacity_decimal"],
                    "group_key": template["group_key"],
                    "passport_key": contract.passport_key,
                    "passport_name": contract.passport_name,
                }
                label = resource_display_name(row)
                facts = self.constructor._facts(row)
                resources.append((ref, ordinal, label, facts))
        kind = command["kind"]
        if kind == "LED_BUNDLE":
            required = len(command["channel_ordinals"])
            chunks = [
                resources[index : index + required] for index in range(0, len(resources), required)
            ]
            chunks = [chunk for chunk in chunks if len(chunk) == required]
        else:
            chunks = [[item] for item in resources]
        return tuple(
            _Unit(
                f"new-unit:{new_index}:{index}",
                kind,
                f"new:{new_index}",
                f"Новый {new_index}",
                tuple(item[0] for item in chunk),
                tuple(item[2] for item in chunk),
                new_index,
                chunk[0][3] if kind == "RELATION" else None,
            )
            for index, chunk in enumerate(chunks)
        )

    def _relation_available(self, connection, project_id, source_id, target_id, planned):
        source = self.constructor._load_facts(connection, project_id, source_id)
        return self._relation_facts_available(
            connection, project_id, source, source_id, target_id, planned
        )

    def _new_relation_available(self, connection, project_id, source, target_id, planned):
        return self._relation_facts_available(
            connection,
            project_id,
            source,
            source.id,
            target_id,
            planned,
            new_source=True,
        )

    def _relation_facts_available(
        self,
        connection,
        project_id,
        source,
        source_id,
        target_id,
        planned,
        *,
        new_source=False,
    ):
        target = self.constructor._load_facts(connection, project_id, target_id)
        definition = self.constructor._definition("POWER_FLOW")
        current_targets = (
            []
            if new_source
            else list(
                connection.execute(
                    select(functional_relation.c.target_resource_id).where(
                        functional_relation.c.project_id == project_id,
                        functional_relation.c.source_resource_id == source_id,
                    )
                ).scalars()
            )
        )
        demands = []
        for current in (*current_targets, *planned):
            facts = self.constructor._load_facts(connection, project_id, current)
            demand = facts.properties.get("demand")
            if demand is not None:
                demands.append(demand)
        preview = validate_relation(
            definition,
            source,
            target,
            source_relation_count=len(current_targets) + len(planned),
            target_relation_count=0,
            existing_target_demands=tuple(demands),
        )
        if not preview.allowed:
            return False
        if new_source:
            return True
        edges = tuple(
            connection.execute(
                select(
                    functional_relation.c.source_resource_id,
                    functional_relation.c.target_resource_id,
                ).where(
                    functional_relation.c.project_id == project_id,
                    functional_relation.c.relation_kind == "POWER_FLOW",
                )
            )
        ) + tuple((source_id, item) for item in (*planned, target_id))
        return find_cycle(edges) is None

    def _materialize_new_instances(self, uow, plan: _Plan) -> dict[str, str]:
        if plan.preview.new_instance_count == 0:
            return {}
        contract = plan.contract
        if contract is None:
            raise BulkPlanBlocked("FIELD_DEVICE_AUTO_CREATE_FORBIDDEN")
        active_contract = self._variant_contract(
            plan.preview.project_id, contract.stable_identity, uow
        )
        if active_contract is None:
            raise StaleBulkPreview("CHOSEN_VARIANT_NO_LONGER_ACTIVE")
        resource_ids: dict[str, str] = {}
        product = (
            {
                "product_key": contract.product_key,
                "project_parameters_json": contract.product_parameters,
            }
            if contract.product_id is not None
            else None
        )
        for index, designation in enumerate(plan.preview.new_designations, start=1):
            collision = uow.execute(
                select(project_instance.c.id).where(
                    project_instance.c.project_id == plan.preview.project_id,
                    project_instance.c.designation == designation,
                    project_instance.c.lifecycle == "ACTIVE",
                )
            ).first()
            if collision:
                raise StaleBulkPreview("DESIGNATION_COLLISION_AFTER_PREVIEW")
            instance_id = new_id()
            uow.execute(
                project_instance.insert().values(
                    id=instance_id,
                    project_id=plan.preview.project_id,
                    designation=designation,
                    board_id=None,
                    room_id=None,
                    passport_definition_id=contract.passport_id,
                    product_definition_id=contract.product_id,
                    supply_scope=contract.supply_scope,
                    lifecycle="ACTIVE",
                    notes=None,
                    parameters_json={
                        "passport_key": contract.passport_key,
                        "product_key": contract.product_key,
                    },
                )
            )
            for template in contract.templates:
                count = _product_count(template, product)
                ordinals = (
                    range(count)
                    if (template["display_json"] or {}).get("materialization") == "PRODUCT_DEFINED"
                    else (template["ordinal"],)
                )
                for ordinal in ordinals:
                    identifier = new_id()
                    uow.execute(
                        instance_resource.insert().values(
                            id=identifier,
                            project_id=plan.preview.project_id,
                            project_instance_id=instance_id,
                            resource_key=template["resource_key"],
                            ordinal=ordinal,
                            passport_resource_definition_id=template["id"],
                            resource_kind=template["resource_kind"],
                            direction=template["direction"],
                            medium=template["medium"],
                            snapshot_json=_snapshot(template, product, ordinal),
                            active=True,
                        )
                    )
                    resource_ids[f"new:{index}:{template['resource_key']}:{ordinal}"] = identifier
        return resource_ids

    def _execute_mapping(self, uow, preview, mapping, new_ids, command_id, _index, now) -> int:
        refs = tuple(new_ids.get(item, item) for item in mapping.unit.resource_refs)
        kind = mapping.command["kind"]
        if kind == "RELATION":
            return self._execute_relation(
                uow,
                preview.project_id,
                refs[0],
                mapping.owner.owner_id,
                command_id,
                now,
            )
        if kind in {"RESOURCE_OUTPUT", "LED_BUNDLE"}:
            return self._execute_resource_output(
                uow,
                preview.project_id,
                mapping.owner.owner_id,
                refs,
                led=kind == "LED_BUNDLE",
            )
        if kind == "FIELD_OUTPUT":
            return self._execute_field_output(
                uow, preview.project_id, mapping.owner.owner_id, refs[0]
            )
        if kind == "KEY_RESOURCE_INPUT":
            return self._execute_key_resource(
                uow, preview.project_id, mapping.owner.owner_id, refs[0]
            )
        if kind == "KEY_FIELD_INPUT":
            return self._execute_key_field(uow, preview.project_id, mapping.owner.owner_id, refs[0])
        raise BulkActionError(f"Unsupported bulk command: {kind}")

    def _execute_relation(self, uow, project_id, source_id, target_id, command_id, now):
        self._require_not_reserved(uow, project_id, source_id)
        definition = self.constructor._definition("POWER_FLOW")
        preview = self.constructor._preview_with_connection(
            uow, project_id, definition, source_id, target_id
        )
        if not preview.allowed:
            raise StaleBulkPreview("RELATION_NO_LONGER_ALLOWED")
        cycle = self.constructor._cycle_result(uow, project_id, definition, source_id, target_id)
        if cycle and cycle.outcome == "ERROR":
            raise StaleBulkPreview("POWER_CYCLE_AFTER_PREVIEW")
        relation_id = new_id()
        uow.execute(
            functional_relation.insert().values(
                id=relation_id,
                project_id=project_id,
                relation_kind="POWER_FLOW",
                source_resource_id=source_id,
                target_resource_id=target_id,
                parameters_json={},
                command_id=command_id,
            )
        )
        for resource in (preview.source, preview.target):
            if resource.exclusive:
                uow.execute(
                    resource_reservation.insert().values(
                        id=new_id(),
                        project_id=project_id,
                        resource_id=resource.id,
                        reservation_kind="EXCLUSIVE_RELATION",
                        slot_key="EXCLUSIVE",
                        owner_relation_id=relation_id,
                    )
                )
        demand = preview.target.properties.get("demand")
        if demand is not None:
            uow.execute(
                resource_reservation.insert().values(
                    id=new_id(),
                    project_id=project_id,
                    resource_id=source_id,
                    reservation_kind="CAPACITY",
                    slot_key=relation_id,
                    quantity_decimal=str(demand),
                    owner_relation_id=relation_id,
                )
            )
        self.constructor._save_trace(
            uow,
            project_id,
            command_id,
            preview.results + ((cycle,) if cycle else ()),
            now,
        )
        return 1

    def _execute_resource_output(self, uow, project_id, line_id, refs, *, led):
        line = uow.execute(
            select(cable_line.c.id).where(
                cable_line.c.id == line_id,
                cable_line.c.project_id == project_id,
                cable_line.c.lifecycle == "ACTIVE",
            )
        ).scalar_one_or_none()
        rows = list(
            uow.execute(
                select(instance_resource).where(
                    instance_resource.c.project_id == project_id,
                    instance_resource.c.id.in_(refs),
                    instance_resource.c.active.is_(True),
                )
            ).mappings()
        )
        if line is None or len(rows) != len(refs):
            raise StaleBulkPreview("OWNER_OR_RESOURCE_RETIRED")
        if any(row["direction"] not in {"OUT", "BIDIRECTIONAL"} for row in rows):
            raise StaleBulkPreview("OUTPUT_RESOURCE_INCOMPATIBLE")
        if led and any(row["resource_kind"] != "OPEN_COLLECTOR_PWM_OUTPUT" for row in rows):
            raise StaleBulkPreview("PWM_CHANNEL_INCOMPATIBLE_RESOURCE_KIND")
        for ref in refs:
            self._require_not_reserved(uow, project_id, ref)
        conflict = uow.execute(
            select(cable_line_assignment.c.id)
            .join(
                cable_topology_endpoint,
                cable_topology_endpoint.c.id == cable_line_assignment.c.endpoint_id,
            )
            .where(
                cable_line_assignment.c.project_id == project_id,
                or_(
                    cable_line_assignment.c.cable_line_id == line_id,
                    cable_topology_endpoint.c.instance_resource_id.in_(refs),
                ),
            )
        ).first()
        if conflict:
            raise StaleBulkPreview("OUTPUT_RESOURCE_OCCUPIED_AFTER_PREVIEW")
        for index, ref in enumerate(refs, start=1):
            endpoint_id = new_id()
            assignment_id = new_id()
            reservation_id = new_id()
            uow.execute(
                cable_topology_endpoint.insert().values(
                    id=endpoint_id,
                    project_id=project_id,
                    cable_line_id=line_id,
                    endpoint_kind="INSTANCE_RESOURCE",
                    instance_resource_id=ref,
                )
            )
            uow.execute(
                resource_reservation.insert().values(
                    id=reservation_id,
                    project_id=project_id,
                    resource_id=ref,
                    reservation_kind="CABLE_LINE_ASSIGNMENT",
                    slot_key="EXCLUSIVE",
                    owner_assignment_kind="CABLE_LINE_ASSIGNMENT",
                    owner_assignment_id=assignment_id,
                )
            )
            role = f"PWM_CHANNEL_{index}" if led else f"CONTROLLED_LOAD_{index}"
            uow.execute(
                cable_line_assignment.insert().values(
                    id=assignment_id,
                    project_id=project_id,
                    cable_line_id=line_id,
                    endpoint_id=endpoint_id,
                    assignment_role=role,
                    reservation_id=reservation_id,
                )
            )
        return len(refs)

    @staticmethod
    def _execute_field_output(uow, project_id, line_id, port_id):
        line = uow.execute(
            select(cable_line.c.id).where(
                cable_line.c.id == line_id,
                cable_line.c.project_id == project_id,
                cable_line.c.lifecycle == "ACTIVE",
            )
        ).first()
        port = uow.execute(
            select(field_port.c.direction).where(
                field_port.c.id == port_id,
                field_port.c.project_id == project_id,
                field_port.c.lifecycle == "ACTIVE",
            )
        ).scalar_one_or_none()
        conflict = uow.execute(
            select(cable_line_assignment.c.id)
            .join(
                cable_topology_endpoint,
                cable_topology_endpoint.c.id == cable_line_assignment.c.endpoint_id,
            )
            .where(
                cable_line_assignment.c.project_id == project_id,
                or_(
                    cable_line_assignment.c.cable_line_id == line_id,
                    cable_topology_endpoint.c.field_port_id == port_id,
                ),
            )
        ).first()
        if line is None or port not in {"OUT", "BIDIRECTIONAL"} or conflict:
            raise StaleBulkPreview("FIELD_OUTPUT_UNAVAILABLE_AFTER_PREVIEW")
        endpoint_id = new_id()
        uow.execute(
            cable_topology_endpoint.insert().values(
                id=endpoint_id,
                project_id=project_id,
                cable_line_id=line_id,
                endpoint_kind="FIELD_PORT",
                field_port_id=port_id,
            )
        )
        uow.execute(
            cable_line_assignment.insert().values(
                id=new_id(),
                project_id=project_id,
                cable_line_id=line_id,
                endpoint_id=endpoint_id,
                assignment_role="PHYSICAL_SOURCE",
                reservation_id=None,
            )
        )
        return 1

    def _execute_key_resource(self, uow, project_id, key_id, resource_id):
        key = uow.execute(
            select(field_control_key.c.id).where(
                field_control_key.c.id == key_id,
                field_control_key.c.project_id == project_id,
                field_control_key.c.lifecycle == "ACTIVE",
            )
        ).first()
        resource = uow.execute(
            select(instance_resource.c.direction, instance_resource.c.resource_kind).where(
                instance_resource.c.id == resource_id,
                instance_resource.c.project_id == project_id,
                instance_resource.c.active.is_(True),
            )
        ).one_or_none()
        self._require_not_reserved(uow, project_id, resource_id)
        conflict = uow.execute(
            select(control_key_input_assignment.c.id).where(
                control_key_input_assignment.c.project_id == project_id,
                or_(
                    control_key_input_assignment.c.field_control_key_id == key_id,
                    control_key_input_assignment.c.input_resource_id == resource_id,
                ),
            )
        ).first()
        if (
            key is None
            or resource is None
            or resource.direction not in {"IN", "BIDIRECTIONAL"}
            or resource.resource_kind not in {"DRY_CONTACT_INPUT", "DIGITAL_INPUT"}
            or conflict
        ):
            raise StaleBulkPreview("KEY_INPUT_UNAVAILABLE_AFTER_PREVIEW")
        assignment_id = new_id()
        reservation_id = new_id()
        uow.execute(
            resource_reservation.insert().values(
                id=reservation_id,
                project_id=project_id,
                resource_id=resource_id,
                reservation_kind="CONTROL_KEY_INPUT",
                slot_key="EXCLUSIVE",
                owner_assignment_kind="CONTROL_KEY_INPUT",
                owner_assignment_id=assignment_id,
            )
        )
        uow.execute(
            control_key_input_assignment.insert().values(
                id=assignment_id,
                project_id=project_id,
                field_control_key_id=key_id,
                input_kind="INSTANCE_RESOURCE",
                input_resource_id=resource_id,
                field_port_id=None,
                reservation_id=reservation_id,
            )
        )
        return 1

    @staticmethod
    def _execute_key_field(uow, project_id, key_id, port_id):
        key = uow.execute(
            select(field_control_key.c.id).where(
                field_control_key.c.id == key_id,
                field_control_key.c.project_id == project_id,
                field_control_key.c.lifecycle == "ACTIVE",
            )
        ).first()
        port = uow.execute(
            select(field_port.c.port_kind, field_port.c.direction).where(
                field_port.c.id == port_id,
                field_port.c.project_id == project_id,
                field_port.c.lifecycle == "ACTIVE",
            )
        ).one_or_none()
        conflict = uow.execute(
            select(control_key_input_assignment.c.id).where(
                control_key_input_assignment.c.project_id == project_id,
                or_(
                    control_key_input_assignment.c.field_control_key_id == key_id,
                    control_key_input_assignment.c.field_port_id == port_id,
                ),
            )
        ).first()
        if (
            key is None
            or port is None
            or port.port_kind != "DIGITAL_INPUT"
            or port.direction != "IN"
            or conflict
        ):
            raise StaleBulkPreview("KEY_FIELD_INPUT_UNAVAILABLE_AFTER_PREVIEW")
        uow.execute(
            control_key_input_assignment.insert().values(
                id=new_id(),
                project_id=project_id,
                field_control_key_id=key_id,
                input_kind="FIELD_PORT",
                input_resource_id=None,
                field_port_id=port_id,
                reservation_id=None,
            )
        )
        return 1

    @staticmethod
    def _require_not_reserved(connection, project_id, resource_id):
        row = connection.execute(
            select(user_reserve.c.id)
            .outerjoin(
                instance_resource,
                instance_resource.c.id == resource_id,
            )
            .where(
                user_reserve.c.project_id == project_id,
                user_reserve.c.lifecycle == "ACTIVE",
                or_(
                    user_reserve.c.instance_resource_id == resource_id,
                    user_reserve.c.project_instance_id == instance_resource.c.project_instance_id,
                ),
            )
        ).first()
        if row:
            raise StaleBulkPreview("USER_RESERVE_ADDED_AFTER_PREVIEW")

    def _variant_contract(self, project_id, identity, connection=None) -> _Contract | None:
        if not identity.startswith("catalog:"):
            return None
        _prefix, variant_key, resource_key = identity.split(":", 2)
        close = connection is None
        connection = self._engine.connect() if close else connection
        try:
            product_row = (
                connection.execute(
                    select(
                        passport_definition.c.id.label("passport_id"),
                        passport_definition.c.passport_key,
                        passport_definition.c.name.label("passport_name"),
                        product_definition.c.id.label("product_id"),
                        product_definition.c.product_key,
                        product_definition.c.name.label("product_name"),
                        product_definition.c.project_parameters_json,
                    )
                    .join(
                        product_definition,
                        product_definition.c.passport_definition_id == passport_definition.c.id,
                    )
                    .join(
                        project,
                        project.c.active_catalog_release_id
                        == passport_definition.c.catalog_release_id,
                    )
                    .where(
                        project.c.id == project_id,
                        passport_definition.c.lifecycle == "ACTIVE",
                        product_definition.c.lifecycle == "ACTIVE",
                        product_definition.c.product_key == variant_key,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if product_row is None:
                product_row = (
                    connection.execute(
                        select(
                            passport_definition.c.id.label("passport_id"),
                            passport_definition.c.passport_key,
                            passport_definition.c.name.label("passport_name"),
                        )
                        .join(
                            project,
                            project.c.active_catalog_release_id
                            == passport_definition.c.catalog_release_id,
                        )
                        .where(
                            project.c.id == project_id,
                            passport_definition.c.lifecycle == "ACTIVE",
                            passport_definition.c.passport_key == variant_key,
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
            if product_row is None:
                return None
            templates = tuple(
                dict(row)
                for row in connection.execute(
                    select(passport_resource_definition)
                    .where(
                        passport_resource_definition.c.passport_definition_id
                        == product_row["passport_id"]
                    )
                    .order_by(
                        passport_resource_definition.c.resource_key,
                        passport_resource_definition.c.ordinal,
                    )
                ).mappings()
            )
            if not any(row["resource_key"] == resource_key for row in templates):
                return None
            reference = (
                connection.execute(
                    select(project_instance.c.supply_scope)
                    .join(
                        instance_resource,
                        instance_resource.c.project_instance_id == project_instance.c.id,
                    )
                    .where(
                        project_instance.c.project_id == project_id,
                        project_instance.c.lifecycle == "ACTIVE",
                        project_instance.c.passport_definition_id == product_row["passport_id"],
                        project_instance.c.product_definition_id == product_row.get("product_id"),
                        instance_resource.c.resource_key == resource_key,
                    )
                    .order_by(project_instance.c.designation)
                )
                .scalars()
                .first()
            )
            if reference is None:
                return None
            return _Contract(
                identity,
                product_row["passport_id"],
                product_row["passport_key"],
                product_row["passport_name"],
                product_row.get("product_id"),
                product_row.get("product_key"),
                product_row.get("product_name"),
                dict(product_row.get("project_parameters_json") or {}),
                resource_key,
                reference,
                templates,
            )
        finally:
            if close:
                connection.close()

    @staticmethod
    def _contract_label(contract):
        return f"{contract.product_name or contract.passport_name} / {contract.resource_key}"

    def _records_by_owner(self, snapshot):
        return {
            owner.owner_id: self.guided._records(
                snapshot.action, snapshot.project_id, owner.owner_id
            )[1]
            for owner in snapshot.owners
            if owner.valid
        }

    def _require_snapshot_current(self, snapshot):
        if self._project_revision(snapshot.project_id) != snapshot.project_revision:
            raise StaleBulkPreview("STALE_PROJECT_REVISION")

    def _project_revision(self, project_id):
        with self._engine.connect() as connection:
            revision = connection.scalar(
                select(project.c.project_revision).where(
                    project.c.id == project_id,
                    project.c.lifecycle == "ACTIVE",
                )
            )
        if revision is None:
            raise BulkActionError("Project not found or inactive")
        return int(revision)

    def _context_kind(self, action, project_id, owner_id):
        if action in {GuidedAction.PROTECTION, GuidedAction.POWER}:
            return "RELATION_TARGET"
        if action == GuidedAction.INPUT:
            return "PHYSICAL_KEY"
        with self._engine.connect() as connection:
            led = connection.scalar(
                select(led_line_profile.c.id).where(
                    led_line_profile.c.project_id == project_id,
                    led_line_profile.c.cable_line_id == owner_id,
                )
            )
        return "LED_LINE" if led is not None else "CABLE_LINE"

    @staticmethod
    def _decode_token(token):
        try:
            payload = json.loads(base64.urlsafe_b64decode(token.encode("ascii")))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BulkActionError("BULK_PREVIEW_TOKEN_INVALID") from exc
        if payload.get("version") != 1:
            raise BulkActionError("BULK_PREVIEW_TOKEN_VERSION_UNSUPPORTED")
        return payload

    @staticmethod
    def _receipt_row(connection, fingerprint):
        return (
            connection.execute(
                select(bulk_operation_receipt).where(
                    bulk_operation_receipt.c.preview_fingerprint == fingerprint
                )
            )
            .mappings()
            .one_or_none()
        )

    @staticmethod
    def _receipt_dto(row):
        summary = dict(row["summary_json"] or {})
        identity = str(summary.get("chosen_variant_identity") or "persisted")
        return BulkActionReceipt(
            row["id"],
            row["command_id"],
            GuidedAction(row["action_type"]),
            str(summary.get("action_label") or GuidedAction(row["action_type"]).label),
            len(row["selected_owner_ids_json"]),
            tuple(summary.get("new_designations") or ()),
            int(summary.get("canonical_fact_count") or 0),
            int(row["project_revision_before"]),
            int(row["project_revision_after"]),
            row["result_status"],
            row["correlation_id"],
            identity,
        )


def _hash(value) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _uuid_from_hash(value: str) -> str:
    return str(uuid.UUID(hashlib.sha256(value.encode()).hexdigest()[:32]))


def _natural_key(value: str):
    return tuple(
        int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", str(value))
    )
