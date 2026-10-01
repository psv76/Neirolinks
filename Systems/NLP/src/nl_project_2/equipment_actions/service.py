"""Transactional P1_002 equipment actions over canonical Project facts."""

from __future__ import annotations

import base64
import hashlib
import json
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import Engine, or_, select, update
from sqlalchemy.exc import IntegrityError

from nl_project_2.catalog.equipment import _product_count, _snapshot
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    bus,
    bus_endpoint,
    cable_line_assignment,
    cable_topology_endpoint,
    control_key_input_assignment,
    functional_relation,
    instance_resource,
    operation_journal,
    panel_placement,
    passport_definition,
    passport_resource_definition,
    product_definition,
    project,
    project_instance,
    resource_reservation,
    user_reserve,
)
from nl_project_2.persistence.uow import UnitOfWork
from nl_project_2.resource_labels import resource_user_label

from .domain import (
    ConfirmationRequired,
    DesignationPlan,
    DesignationPlanItem,
    DuplicatePreview,
    DuplicateReceipt,
    EmptyInstanceIssue,
    EquipmentActionError,
    ReserveState,
    StaleEquipmentPreview,
)

_COPIED_FACTS = (
    "тот же exact passport version",
    "тот же exact product version, если выбран",
    "та же область поставки",
    "новый полный набор ресурсов из canonical contract",
)

_EXCLUDED_FACTS = (
    "связи и назначения",
    "техническая занятость и reservations",
    "пользовательский РЕЗЕРВ",
    "щит, помещение и размещение DIN",
    "заметки, история и результаты проверок",
    "DWG binding/Handle",
)


class EquipmentActionService:
    EMPTY_INSTANCE_CODE = "EQUIPMENT_EMPTY_INSTANCE_ACTION_REQUIRED"

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def plan_designations(
        self, *, project_id: str, proposed_designations: Iterable[str]
    ) -> DesignationPlan:
        proposed = tuple(str(value).strip() for value in proposed_designations)
        with self._engine.connect() as connection:
            revision = self._project_revision(connection, project_id)
            existing = tuple(
                connection.execute(
                    select(project_instance.c.designation)
                    .where(
                        project_instance.c.project_id == project_id,
                        project_instance.c.lifecycle == "ACTIVE",
                    )
                    .order_by(project_instance.c.designation)
                ).scalars()
            )
        existing_set = set(existing)
        counts = Counter(proposed)
        items = []
        for designation in proposed:
            conflicts: list[str] = []
            if not designation:
                conflicts.append("DESIGNATION_REQUIRED")
            if designation in existing_set:
                conflicts.append("COLLISION_WITH_EXISTING")
            if designation and counts[designation] > 1:
                conflicts.append("COLLISION_WITH_PROPOSED")
            items.append(DesignationPlanItem(designation, tuple(conflicts)))
        payload = {
            "version": 1,
            "project_id": project_id,
            "project_revision": revision,
            "existing": existing,
            "proposed": proposed,
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return DesignationPlan(revision, existing, tuple(items), fingerprint)

    def preview_duplicate(
        self, *, project_id: str, source_instance_id: str, proposed_designation: str
    ) -> DuplicatePreview:
        plan = self.plan_designations(
            project_id=project_id, proposed_designations=(proposed_designation,)
        )
        with self._engine.connect() as connection:
            source = (
                connection.execute(
                    select(
                        project_instance,
                        passport_definition.c.name.label("passport_name"),
                        product_definition.c.name.label("product_name"),
                    )
                    .join(
                        passport_definition,
                        passport_definition.c.id == project_instance.c.passport_definition_id,
                    )
                    .outerjoin(
                        product_definition,
                        product_definition.c.id == project_instance.c.product_definition_id,
                    )
                    .where(
                        project_instance.c.id == source_instance_id,
                        project_instance.c.project_id == project_id,
                        project_instance.c.lifecycle == "ACTIVE",
                    )
                )
                .mappings()
                .one_or_none()
            )
        if source is None:
            raise EquipmentActionError("Source ProjectInstance not found or inactive")
        payload = {
            "version": 1,
            "project_id": project_id,
            "source_instance_id": source_instance_id,
            "source_row_version": int(source["row_version"]),
            "project_revision": plan.project_revision,
            "proposed_designation": plan.proposed[0].proposed_designation,
        }
        token = base64.urlsafe_b64encode(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).decode("ascii")
        fingerprint = hashlib.sha256(token.encode("ascii")).hexdigest()
        return DuplicatePreview(
            source_instance_id,
            source["designation"],
            source["passport_name"],
            source["passport_name"],
            source["product_name"],
            plan.proposed[0].proposed_designation,
            _COPIED_FACTS,
            _EXCLUDED_FACTS,
            plan.proposed[0].conflict_codes,
            plan.project_revision,
            int(source["row_version"]),
            fingerprint,
            token,
        )

    def confirm_duplicate(self, preview: DuplicatePreview, *, confirmed: bool) -> DuplicateReceipt:
        if not confirmed:
            raise ConfirmationRequired("Duplicate requires explicit confirmation")
        if (
            preview.fingerprint
            != hashlib.sha256(preview.confirmation_token.encode("ascii")).hexdigest()
        ):
            raise EquipmentActionError("DUPLICATE_PREVIEW_FINGERPRINT_INVALID")
        payload = self._decode_token(preview.confirmation_token)
        if payload["source_instance_id"] != preview.source_instance_id:
            raise EquipmentActionError("DUPLICATE_PREVIEW_SOURCE_MISMATCH")
        if preview.conflicts:
            raise EquipmentActionError("Duplicate designation plan contains conflicts")
        now = datetime.now(UTC)
        try:
            with UnitOfWork(self._engine) as uow:
                revision = self._project_revision(uow, payload["project_id"])
                if revision != payload["project_revision"]:
                    raise StaleEquipmentPreview("STALE_PROJECT_REVISION")
                source = (
                    uow.execute(
                        select(
                            project_instance,
                            passport_definition.c.passport_key,
                            product_definition.c.product_key,
                            product_definition.c.project_parameters_json,
                        )
                        .join(
                            passport_definition,
                            passport_definition.c.id == project_instance.c.passport_definition_id,
                        )
                        .outerjoin(
                            product_definition,
                            product_definition.c.id == project_instance.c.product_definition_id,
                        )
                        .where(
                            project_instance.c.id == payload["source_instance_id"],
                            project_instance.c.project_id == payload["project_id"],
                            project_instance.c.lifecycle == "ACTIVE",
                            project_instance.c.row_version == payload["source_row_version"],
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if source is None:
                    raise StaleEquipmentPreview("STALE_SOURCE_INSTANCE")
                templates = [
                    dict(row)
                    for row in uow.execute(
                        select(passport_resource_definition)
                        .where(
                            passport_resource_definition.c.passport_definition_id
                            == source["passport_definition_id"]
                        )
                        .order_by(
                            passport_resource_definition.c.resource_key,
                            passport_resource_definition.c.ordinal,
                        )
                    ).mappings()
                ]
                product = None
                if source["product_definition_id"] is not None:
                    product = {
                        "product_key": source["product_key"],
                        "project_parameters_json": dict(source["project_parameters_json"] or {}),
                    }
                new_instance_id = new_id()
                uow.execute(
                    project_instance.insert().values(
                        id=new_instance_id,
                        project_id=payload["project_id"],
                        designation=payload["proposed_designation"],
                        board_id=None,
                        room_id=None,
                        passport_definition_id=source["passport_definition_id"],
                        product_definition_id=source["product_definition_id"],
                        supply_scope=source["supply_scope"],
                        lifecycle="ACTIVE",
                        notes=None,
                        parameters_json={
                            "passport_key": source["passport_key"],
                            "product_key": source["product_key"],
                        },
                    )
                )
                resource_count = 0
                for template in templates:
                    count = _product_count(template, product)
                    ordinals = (
                        range(count)
                        if (template["display_json"] or {}).get("materialization")
                        == "PRODUCT_DEFINED"
                        else (template["ordinal"],)
                    )
                    for ordinal in ordinals:
                        uow.execute(
                            instance_resource.insert().values(
                                id=new_id(),
                                project_id=payload["project_id"],
                                project_instance_id=new_instance_id,
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
                        resource_count += 1
                self._touch_project(
                    uow,
                    payload["project_id"],
                    expected_revision=payload["project_revision"],
                    now=now,
                )
                command_id = new_id()
                uow.execute(
                    operation_journal.insert().values(
                        id=new_id(),
                        project_id=payload["project_id"],
                        command_id=command_id,
                        command_type="EQUIPMENT_DUPLICATE",
                        project_revision_before=payload["project_revision"],
                        project_revision_after=payload["project_revision"] + 1,
                        correlation_id=command_id,
                        status="SUCCEEDED",
                        started_at_utc=now,
                        completed_at_utc=now,
                        summary_json={
                            "human_summary": "Создана безопасная копия оборудования",
                            "context_label": payload["proposed_designation"],
                            "canonical_fact_count": resource_count + 1,
                        },
                    )
                )
                uow.commit()
        except IntegrityError as exc:
            raise EquipmentActionError("Duplicate designation is no longer unique") from exc
        return DuplicateReceipt(
            new_instance_id,
            payload["proposed_designation"],
            resource_count,
            payload["project_revision"],
            payload["project_revision"] + 1,
        )

    def reserve_state(self, *, project_id: str, target_kind: str, target_id: str) -> ReserveState:
        kind = self._target_kind(target_kind)
        with self._engine.connect() as connection:
            revision = self._project_revision(connection, project_id)
            target_label, instance_id = self._target_label(connection, project_id, kind, target_id)
            direct = self._active_reserve(connection, project_id, kind, target_id)
            inherited = None
            if kind == "INSTANCE_RESOURCE" and instance_id is not None:
                inherited = self._active_reserve(
                    connection, project_id, "PROJECT_INSTANCE", instance_id
                )
        effective = direct is not None or inherited is not None
        note = None if direct is None else direct["note"]
        if direct is not None:
            reason = "РЕЗЕРВ установлен пользователем для выбранной цели"
        elif inherited is not None:
            reason = "Ресурс исключён из кандидатов резервом всего экземпляра"
        else:
            reason = "РЕЗЕРВ не установлен"
        return ReserveState(
            kind,
            target_label,
            target_id,
            effective,
            direct is not None,
            inherited is not None,
            note,
            reason,
            revision,
        )

    def set_reserve(
        self,
        *,
        project_id: str,
        target_kind: str,
        target_id: str,
        actor: str,
        expected_project_revision: int,
        note: str = "",
    ) -> ReserveState:
        kind = self._target_kind(target_kind)
        clean_actor = str(actor).strip()
        if not clean_actor:
            raise EquipmentActionError("Reserve actor is required")
        now = datetime.now(UTC)
        with UnitOfWork(self._engine) as uow:
            revision = self._project_revision(uow, project_id)
            if revision != expected_project_revision:
                raise StaleEquipmentPreview("STALE_PROJECT_REVISION")
            target_label, _instance_id = self._target_label(uow, project_id, kind, target_id)
            existing = self._active_reserve(uow, project_id, kind, target_id)
            if existing is not None:
                uow.commit()
                return self.reserve_state(
                    project_id=project_id, target_kind=kind, target_id=target_id
                )
            if self._target_is_occupied(uow, project_id, kind, target_id):
                raise EquipmentActionError(
                    "TARGET_OCCUPIED: reserve cannot mask an existing assignment or placement"
                )
            uow.execute(
                user_reserve.insert().values(
                    id=new_id(),
                    project_id=project_id,
                    target_kind=kind,
                    project_instance_id=target_id if kind == "PROJECT_INSTANCE" else None,
                    instance_resource_id=target_id if kind == "INSTANCE_RESOURCE" else None,
                    actor=clean_actor,
                    note=str(note).strip() or None,
                    lifecycle="ACTIVE",
                )
            )
            self._touch_project(
                uow, project_id, expected_revision=expected_project_revision, now=now
            )
            command_id = new_id()
            uow.execute(
                operation_journal.insert().values(
                    id=new_id(),
                    project_id=project_id,
                    command_id=command_id,
                    command_type="EQUIPMENT_RESERVE_SET",
                    project_revision_before=expected_project_revision,
                    project_revision_after=expected_project_revision + 1,
                    correlation_id=command_id,
                    status="SUCCEEDED",
                    started_at_utc=now,
                    completed_at_utc=now,
                    summary_json={
                        "human_summary": "Установлен пользовательский РЕЗЕРВ",
                        "context_label": target_label,
                        "target_kind": kind,
                    },
                )
            )
            uow.commit()
        return self.reserve_state(project_id=project_id, target_kind=kind, target_id=target_id)

    def remove_reserve(
        self,
        *,
        project_id: str,
        target_kind: str,
        target_id: str,
        actor: str,
        expected_project_revision: int,
    ) -> ReserveState:
        kind = self._target_kind(target_kind)
        clean_actor = str(actor).strip()
        if not clean_actor:
            raise EquipmentActionError("Reserve actor is required")
        now = datetime.now(UTC)
        with UnitOfWork(self._engine) as uow:
            revision = self._project_revision(uow, project_id)
            if revision != expected_project_revision:
                raise StaleEquipmentPreview("STALE_PROJECT_REVISION")
            target_label, _instance_id = self._target_label(uow, project_id, kind, target_id)
            existing = self._active_reserve(uow, project_id, kind, target_id)
            if existing is not None:
                uow.execute(
                    update(user_reserve)
                    .where(user_reserve.c.id == existing["id"])
                    .values(
                        lifecycle="RETIRED",
                        actor=clean_actor,
                        row_version=user_reserve.c.row_version + 1,
                        updated_at_utc=now,
                    )
                )
                self._touch_project(
                    uow,
                    project_id,
                    expected_revision=expected_project_revision,
                    now=now,
                )
                command_id = new_id()
                uow.execute(
                    operation_journal.insert().values(
                        id=new_id(),
                        project_id=project_id,
                        command_id=command_id,
                        command_type="EQUIPMENT_RESERVE_REMOVED",
                        project_revision_before=expected_project_revision,
                        project_revision_after=expected_project_revision + 1,
                        correlation_id=command_id,
                        status="SUCCEEDED",
                        started_at_utc=now,
                        completed_at_utc=now,
                        summary_json={
                            "human_summary": "Снят пользовательский РЕЗЕРВ",
                            "context_label": target_label,
                            "target_kind": kind,
                        },
                    )
                )
            uow.commit()
        return self.reserve_state(project_id=project_id, target_kind=kind, target_id=target_id)

    def empty_instance_issues(self, *, project_id: str) -> tuple[EmptyInstanceIssue, ...]:
        with self._engine.connect() as connection:
            self._project_revision(connection, project_id)
            instances = list(
                connection.execute(
                    select(
                        project_instance.c.id,
                        project_instance.c.designation,
                        passport_definition.c.name.label("passport_name"),
                    )
                    .join(
                        passport_definition,
                        passport_definition.c.id == project_instance.c.passport_definition_id,
                    )
                    .where(
                        project_instance.c.project_id == project_id,
                        project_instance.c.lifecycle == "ACTIVE",
                    )
                    .order_by(project_instance.c.designation, project_instance.c.id)
                ).mappings()
            )
            issues = []
            for instance in instances:
                if (
                    self._active_reserve(connection, project_id, "PROJECT_INSTANCE", instance["id"])
                    is not None
                ):
                    continue
                if self._target_is_occupied(
                    connection, project_id, "PROJECT_INSTANCE", instance["id"]
                ):
                    continue
                label = f"{instance['designation']} — {instance['passport_name']}"
                issues.append(
                    EmptyInstanceIssue(
                        self.EMPTY_INSTANCE_CODE,
                        "Требуется действие",
                        instance["id"],
                        label,
                        "Требуется действие: назначить / резерв / удалить",
                        ("назначить", "резерв", "удалить"),
                    )
                )
        return tuple(issues)

    @staticmethod
    def _target_kind(value: str) -> str:
        kind = str(value).strip().upper()
        if kind not in {"PROJECT_INSTANCE", "INSTANCE_RESOURCE"}:
            raise EquipmentActionError("Reserve target must be instance or resource")
        return kind

    @staticmethod
    def _project_revision(connection, project_id: str) -> int:
        revision = connection.execute(
            select(project.c.project_revision).where(
                project.c.id == project_id, project.c.lifecycle == "ACTIVE"
            )
        ).scalar_one_or_none()
        if revision is None:
            raise EquipmentActionError("Project not found or inactive")
        return int(revision)

    @staticmethod
    def _target_label(connection, project_id, kind, target_id):
        if kind == "PROJECT_INSTANCE":
            row = (
                connection.execute(
                    select(
                        project_instance.c.designation,
                        passport_definition.c.name.label("passport_name"),
                    )
                    .join(
                        passport_definition,
                        passport_definition.c.id == project_instance.c.passport_definition_id,
                    )
                    .where(
                        project_instance.c.id == target_id,
                        project_instance.c.project_id == project_id,
                        project_instance.c.lifecycle == "ACTIVE",
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise EquipmentActionError("Reserve target not found or inactive")
            return f"{row['designation']} — {row['passport_name']}", target_id
        row = (
            connection.execute(
                select(
                    instance_resource,
                    project_instance.c.designation.label("instance_designation"),
                    passport_resource_definition.c.display_json,
                )
                .join(
                    project_instance,
                    project_instance.c.id == instance_resource.c.project_instance_id,
                )
                .join(
                    passport_resource_definition,
                    passport_resource_definition.c.id
                    == instance_resource.c.passport_resource_definition_id,
                )
                .where(
                    instance_resource.c.id == target_id,
                    instance_resource.c.project_id == project_id,
                    instance_resource.c.active.is_(True),
                    project_instance.c.lifecycle == "ACTIVE",
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise EquipmentActionError("Reserve target not found or inactive")
        return resource_user_label(row), row["project_instance_id"]

    @staticmethod
    def _active_reserve(connection, project_id, kind, target_id):
        target_column = (
            user_reserve.c.project_instance_id
            if kind == "PROJECT_INSTANCE"
            else user_reserve.c.instance_resource_id
        )
        return (
            connection.execute(
                select(user_reserve).where(
                    user_reserve.c.project_id == project_id,
                    user_reserve.c.target_kind == kind,
                    target_column == target_id,
                    user_reserve.c.lifecycle == "ACTIVE",
                )
            )
            .mappings()
            .one_or_none()
        )

    @classmethod
    def _target_is_occupied(cls, connection, project_id, kind, target_id) -> bool:
        if kind == "PROJECT_INSTANCE":
            resource_ids = tuple(
                connection.execute(
                    select(instance_resource.c.id).where(
                        instance_resource.c.project_id == project_id,
                        instance_resource.c.project_instance_id == target_id,
                        instance_resource.c.active.is_(True),
                    )
                ).scalars()
            )
            if connection.execute(
                select(panel_placement.c.id).where(
                    panel_placement.c.project_id == project_id,
                    panel_placement.c.project_instance_id == target_id,
                )
            ).first():
                return True
        else:
            resource_ids = (target_id,)
        if not resource_ids:
            return False
        checks = (
            select(functional_relation.c.id).where(
                functional_relation.c.project_id == project_id,
                or_(
                    functional_relation.c.source_resource_id.in_(resource_ids),
                    functional_relation.c.target_resource_id.in_(resource_ids),
                ),
            ),
            select(resource_reservation.c.id).where(
                resource_reservation.c.project_id == project_id,
                resource_reservation.c.resource_id.in_(resource_ids),
            ),
            select(cable_line_assignment.c.id)
            .join(
                cable_topology_endpoint,
                cable_topology_endpoint.c.id == cable_line_assignment.c.endpoint_id,
            )
            .where(
                cable_line_assignment.c.project_id == project_id,
                cable_topology_endpoint.c.instance_resource_id.in_(resource_ids),
            ),
            select(control_key_input_assignment.c.id).where(
                control_key_input_assignment.c.project_id == project_id,
                control_key_input_assignment.c.input_resource_id.in_(resource_ids),
            ),
            select(bus.c.id).where(
                bus.c.project_id == project_id,
                bus.c.root_resource_id.in_(resource_ids),
                bus.c.lifecycle == "ACTIVE",
            ),
            select(bus_endpoint.c.id).where(
                bus_endpoint.c.project_id == project_id,
                bus_endpoint.c.resource_id.in_(resource_ids),
            ),
        )
        return any(connection.execute(statement).first() is not None for statement in checks)

    @staticmethod
    def _touch_project(uow, project_id, *, expected_revision: int, now: datetime) -> None:
        result = uow.execute(
            update(project)
            .where(
                project.c.id == project_id,
                project.c.lifecycle == "ACTIVE",
                project.c.project_revision == expected_revision,
            )
            .values(
                project_revision=project.c.project_revision + 1,
                row_version=project.c.row_version + 1,
                updated_at_utc=now,
            )
        )
        if result.rowcount != 1:
            raise StaleEquipmentPreview("STALE_PROJECT_REVISION")

    @staticmethod
    def _decode_token(token: str) -> dict:
        try:
            payload = json.loads(base64.urlsafe_b64decode(token.encode("ascii")))
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise EquipmentActionError("DUPLICATE_PREVIEW_TOKEN_INVALID") from exc
        if payload.get("version") != 1:
            raise EquipmentActionError("DUPLICATE_PREVIEW_TOKEN_VERSION_UNSUPPORTED")
        return payload
