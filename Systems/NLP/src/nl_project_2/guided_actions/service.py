"""Shared candidate -> immutable preview -> explicit confirmation orchestration."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from itertools import combinations
from typing import Any

from sqlalchemy import Engine, select

from nl_project_2.automation import AutomationError, AutomationService
from nl_project_2.automation.domain import assess_pwm_capacity
from nl_project_2.constructor import BlockingViolation, ConstructorService
from nl_project_2.constructor.domain import find_cycle
from nl_project_2.field_model import FieldModelError, TopologyPersistenceService
from nl_project_2.operations import LocalApplicationProfile
from nl_project_2.persistence.schema import (
    cable_line,
    cable_line_assignment,
    led_line_profile,
    product_definition,
    project,
    project_instance,
    user_reserve,
)

from .domain import (
    CandidateQuery,
    CandidateState,
    CandidateUnavailable,
    ConfirmationRequired,
    GuidedAction,
    GuidedActionError,
    GuidedActionPreview,
    GuidedActionReceipt,
    GuidedCandidate,
    StalePreview,
)


@dataclass(frozen=True, slots=True)
class _CandidateRecord:
    dto: GuidedCandidate
    command: dict[str, Any]
    preference_identity: str


@dataclass(frozen=True, slots=True)
class _Owner:
    label: str
    existing_state: tuple[str, ...]


_REASON_TEXT = {
    "OCCUPIED": "ресурс уже занят",
    "OWNER_ALREADY_ASSIGNED": "для выбранного объекта назначение уже существует",
    "USER_RESERVE": "ресурс оставлен пользователем в резерве",
    "INCOMPATIBLE_KIND_DIRECTION": "тип или направление ресурса несовместимы",
    "INCOMPATIBLE_VOLTAGE_SIGNAL_POWER": "напряжение, род тока или сигнал несовместимы",
    "CAPACITY_CURRENT_CHANNEL_LIMIT": "недостаточно мощности, тока или каналов",
    "MISSING_OFFICIAL_OR_PROJECT_FACTS": (
        "не хватает подтверждённых паспортных или проектных данных"
    ),
    "GRAPH_CYCLE_RESTRICTION": "назначение нарушает допустимую структуру или создаёт цикл",
    "CROSS_PROJECT": "объект относится к другому проекту",
}


class GuidedActionService:
    """One human-first contour over the existing P0 canonical command services."""

    def __init__(
        self,
        engine: Engine,
        preference_profile: LocalApplicationProfile | None = None,
    ) -> None:
        self._engine = engine
        self._preference_profile = preference_profile
        self.constructor = ConstructorService(engine)
        self.automation = AutomationService(engine)
        self.field_model = TopologyPersistenceService(engine)

    def protection_candidates(self, *, project_id: str, target_resource_id: str) -> CandidateQuery:
        return self.candidates(GuidedAction.PROTECTION, project_id, target_resource_id)

    def power_candidates(self, *, project_id: str, target_resource_id: str) -> CandidateQuery:
        return self.candidates(GuidedAction.POWER, project_id, target_resource_id)

    def output_candidates(self, *, project_id: str, cable_line_id: str) -> CandidateQuery:
        return self.candidates(GuidedAction.OUTPUT, project_id, cable_line_id)

    def input_candidates(self, *, project_id: str, field_control_key_id: str) -> CandidateQuery:
        return self.candidates(GuidedAction.INPUT, project_id, field_control_key_id)

    def candidates(
        self, action: GuidedAction | str, project_id: str, owner_id: str
    ) -> CandidateQuery:
        action = GuidedAction(action)
        revision = self._project_revision(project_id)
        owner, records = self._records(action, project_id, owner_id)
        preferred_identity = None
        if self._preference_profile is not None:
            try:
                preferred_identity = self._preference_profile.resolve(
                    action.value,
                    (record.preference_identity for record in records),
                ).stable_identity
            except (OSError, ValueError):
                preferred_identity = None
        canonical_records = sorted(
            records,
            key=lambda item: (
                item.dto.target_label.casefold(),
                item.dto.technical_identity or "",
                item.dto.candidate_id,
            ),
        )
        candidates = tuple(
            record.dto
            for record in sorted(
                canonical_records,
                key=lambda item: (
                    0
                    if item.dto.selectable
                    and preferred_identity == item.preference_identity
                    else 1
                    if item.dto.selectable
                    else 2
                ),
            )
        )
        selectable_count = sum(item.selectable for item in candidates)
        if selectable_count:
            status = "READY"
            explanation = f"Доступно вариантов: {selectable_count}"
            suggestions: tuple[str, ...] = ()
        elif candidates:
            status = "NO_SELECTABLE_CANDIDATES"
            explanation = "Подходящих свободных ресурсов нет; причины показаны у каждого варианта"
            suggestions = ("Создать или выбрать подходящее оборудование явным действием",)
        else:
            status = "NO_CANDIDATES"
            explanation = "В проекте нет ресурсов подходящего назначения"
            suggestions = ("Создать подходящее оборудование явным действием",)
        return CandidateQuery(
            action,
            action.label,
            owner.label,
            revision,
            candidates,
            status,
            explanation,
            suggestions,
        )

    def preview(
        self,
        action: GuidedAction | str,
        project_id: str,
        owner_id: str,
        candidate_id: str,
    ) -> GuidedActionPreview:
        action = GuidedAction(action)
        revision = self._project_revision(project_id)
        owner, records = self._records(action, project_id, owner_id)
        record = next((item for item in records if item.dto.candidate_id == candidate_id), None)
        if record is None:
            raise CandidateUnavailable("Выбранный вариант отсутствует в актуальном списке")
        if not record.dto.selectable:
            raise CandidateUnavailable(record.dto.explanation)
        payload = {
            "version": 1,
            "project_id": project_id,
            "action": action.value,
            "owner_id": owner_id,
            "candidate_id": candidate_id,
        }
        token = base64.urlsafe_b64encode(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).decode("ascii")
        fingerprint = self._fingerprint(token, revision)
        missing = tuple(
            warning
            for warning in record.dto.warnings
            if "не хватает" in warning.casefold() or "неизвест" in warning.casefold()
        )
        changes = (
            f"{action.label}: {owner.label}",
            f"Выбран ресурс: {record.dto.target_label}",
            "Будет создано одно каноническое назначение после подтверждения",
        )
        return GuidedActionPreview(
            action,
            action.label,
            owner.label,
            record.dto.target_label,
            changes,
            owner.existing_state,
            record.dto.warnings,
            missing,
            revision,
            fingerprint,
            token,
        )

    def confirm(
        self, preview: GuidedActionPreview, *, confirmed: bool
    ) -> GuidedActionReceipt:
        if not confirmed:
            raise ConfirmationRequired("Назначение выполняется только после явного подтверждения")
        if preview.fingerprint != self._fingerprint(
            preview.confirmation_token, preview.project_revision
        ):
            raise GuidedActionError("PREVIEW_FINGERPRINT_INVALID")
        payload = self._decode_token(preview.confirmation_token)
        action = GuidedAction(payload["action"])
        project_id = payload["project_id"]
        owner_id = payload["owner_id"]
        if action != preview.action:
            raise GuidedActionError("PREVIEW_ACTION_MISMATCH")
        actual_revision = self._project_revision(project_id)
        if actual_revision != preview.project_revision:
            raise StalePreview(
                "Проект изменился после preview; сформируйте preview заново"
            )
        owner, records = self._records(action, project_id, owner_id)
        record = next(
            (item for item in records if item.dto.candidate_id == payload["candidate_id"]),
            None,
        )
        if record is None or not record.dto.selectable:
            raise CandidateUnavailable(
                "Вариант стал недоступен; список кандидатов и preview нужно обновить"
            )
        try:
            fact_kind, fact_count = self._execute(
                action,
                project_id,
                owner_id,
                record.command,
                preview.project_revision,
            )
        except (BlockingViolation, AutomationError, FieldModelError) as exc:
            if "STALE_PROJECT_REVISION" in str(exc):
                raise StalePreview(str(exc)) from exc
            raise CandidateUnavailable(str(exc)) from exc
        revision_after = self._project_revision(project_id)
        preference_updated = False
        preference_diagnostic = None
        if self._preference_profile is not None:
            try:
                self._preference_profile.update(action.value, record.preference_identity)
                preference_updated = True
            except Exception as exc:  # optional local profile must not reverse Project commit
                preference_diagnostic = (
                    f"LOCAL_PREFERENCE_UPDATE_FAILED:{type(exc).__name__}"
                )
        return GuidedActionReceipt(
            action,
            action.label,
            preview.project_revision,
            revision_after,
            fact_kind,
            fact_count,
            owner.label,
            self._updated_state(action, project_id, owner_id),
            record.preference_identity,
            preference_updated,
            preference_diagnostic,
        )

    def _records(
        self, action: GuidedAction, project_id: str, owner_id: str
    ) -> tuple[_Owner, list[_CandidateRecord]]:
        if action in {GuidedAction.PROTECTION, GuidedAction.POWER}:
            return self._relation_records(action, project_id, owner_id)
        if action == GuidedAction.OUTPUT:
            return self._output_records(project_id, owner_id)
        return self._input_records(project_id, owner_id)

    def _relation_records(
        self, action: GuidedAction, project_id: str, target_resource_id: str
    ) -> tuple[_Owner, list[_CandidateRecord]]:
        resources = self.constructor.list_resources(project_id)
        target = next((row for row in resources if row["id"] == target_resource_id), None)
        if target is None:
            raise GuidedActionError("Владелец назначения не найден в выбранном проекте")
        existing = [
            row
            for row in self.constructor.list_relations(project_id)
            if row["target_resource_id"] == target_resource_id
        ]
        owner = _Owner(
            target["user_label"],
            (
                ("Назначение отсутствует",)
                if not existing
                else ("Назначение уже существует",)
            ),
        )
        reserved = self._reserved_resource_ids(project_id, resources)
        relation_edges = tuple(
            (row["source_resource_id"], row["target_resource_id"])
            for row in self.constructor.list_relations(project_id)
            if row["relation_kind"] == "POWER_FLOW"
        )
        records: list[_CandidateRecord] = []
        for source in resources:
            if source["id"] == target_resource_id or not self._plausible_relation_source(
                action, source
            ):
                continue
            preview = self.constructor.preview_relation(
                project_id=project_id,
                relation_kind="POWER_FLOW",
                source_resource_id=source["id"],
                target_resource_id=target_resource_id,
            )
            reasons, warnings = self._relation_reasons(action, preview.results)
            if existing:
                reasons.append("OWNER_ALREADY_ASSIGNED")
            if source["id"] in reserved:
                reasons.append("USER_RESERVE")
            if find_cycle(relation_edges + ((source["id"], target_resource_id),)):
                reasons.append("GRAPH_CYCLE_RESTRICTION")
            state = self._state(reasons)
            identity = f"{source['passport_key']} / {source['resource_key']}"
            dto = self._candidate(
                action,
                project_id,
                target_resource_id,
                "RELATION",
                (source["id"],),
                source["user_label"],
                source["instance_designation"],
                state,
                reasons,
                warnings,
                identity,
            )
            records.append(
                _CandidateRecord(
                    dto,
                    {
                        "kind": "RELATION",
                        "source_resource_id": source["id"],
                        "target_resource_id": target_resource_id,
                    },
                    self._resource_preference_identity(source),
                )
            )
        return owner, records

    def _output_records(
        self, project_id: str, cable_line_id: str
    ) -> tuple[_Owner, list[_CandidateRecord]]:
        with self._engine.connect() as connection:
            line = (
                connection.execute(
                    select(cable_line).where(
                        cable_line.c.id == cable_line_id,
                        cable_line.c.project_id == project_id,
                        cable_line.c.lifecycle == "ACTIVE",
                    )
                )
                .mappings()
                .one_or_none()
            )
            profile = (
                connection.execute(
                    select(led_line_profile).where(
                        led_line_profile.c.project_id == project_id,
                        led_line_profile.c.cable_line_id == cable_line_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
            line_assigned = connection.scalar(
                select(cable_line_assignment.c.id).where(
                    cable_line_assignment.c.project_id == project_id,
                    cable_line_assignment.c.cable_line_id == cable_line_id,
                )
            ) is not None
        if line is None:
            raise GuidedActionError("Кабельная линия не найдена в выбранном проекте")
        facts = dict(line["cable_facts_json"] or {})
        load_name = facts.get("LOAD_NAME") or facts.get("load_name")
        owner_label = f"Линия {line['designation']}" + (
            "" if not load_name else f" — {load_name}"
        )
        owner = _Owner(
            owner_label,
            ("Выход не назначен",) if not line_assigned else ("Выход уже назначен",),
        )
        if profile is not None:
            return owner, self._led_output_records(
                project_id, line, profile, line_assigned
            )
        resources = self.constructor.list_resources(project_id)
        reserved = self._reserved_resource_ids(project_id, resources)
        records: list[_CandidateRecord] = []
        for resource in resources:
            reasons: list[str] = []
            if line_assigned:
                reasons.append("OWNER_ALREADY_ASSIGNED")
            if resource["direction"] not in {"OUT", "BIDIRECTIONAL"} or not resource[
                "assignable"
            ]:
                reasons.append("INCOMPATIBLE_KIND_DIRECTION")
            if resource["occupied"]:
                reasons.append("OCCUPIED")
            if resource["id"] in reserved:
                reasons.append("USER_RESERVE")
            state = self._state(reasons)
            dto = self._candidate(
                GuidedAction.OUTPUT,
                project_id,
                cable_line_id,
                "RESOURCE_OUTPUT",
                (resource["id"],),
                resource["user_label"],
                resource["instance_designation"],
                state,
                reasons,
                (),
                resource["technical_identity"],
            )
            records.append(
                _CandidateRecord(
                    dto,
                    {"kind": "RESOURCE_OUTPUT", "id": resource["id"]},
                    self._resource_preference_identity(resource),
                )
            )
        for port in self.field_model.field_port_read_model(project_id):
            reasons = []
            if line_assigned:
                reasons.append("OWNER_ALREADY_ASSIGNED")
            if port["direction"] not in {"OUT", "BIDIRECTIONAL"}:
                reasons.append("INCOMPATIBLE_KIND_DIRECTION")
            if port["linked_cable_line_ids"]:
                reasons.append("OCCUPIED")
            label = f"{port['block_kind']} / {port['port_tag']}"
            dto = self._candidate(
                GuidedAction.OUTPUT,
                project_id,
                cable_line_id,
                "FIELD_OUTPUT",
                (port["id"],),
                label,
                port["block_kind"],
                self._state(reasons),
                reasons,
                (),
                port["physical_identity"],
            )
            records.append(
                _CandidateRecord(
                    dto,
                    {"kind": "FIELD_OUTPUT", "id": port["id"]},
                    self._field_preference_identity(port),
                )
            )
        return owner, records

    def _led_output_records(self, project_id, line, profile, line_assigned):
        resources = self.constructor.list_resources(project_id)
        reserved = self._reserved_resource_ids(project_id, resources)
        pwm_by_instance: dict[str, list[dict]] = {}
        for resource in resources:
            if resource["resource_key"] == "PWM_OUTPUT":
                pwm_by_instance.setdefault(resource["project_instance_id"], []).append(resource)
        with self._engine.connect() as connection:
            parameters = {
                row["id"]: dict(row["project_parameters_json"] or {})
                for row in connection.execute(
                    select(
                        project_instance.c.id,
                        product_definition.c.project_parameters_json,
                    )
                    .join(
                        product_definition,
                        product_definition.c.id == project_instance.c.product_definition_id,
                    )
                    .where(
                        project_instance.c.project_id == project_id,
                        project_instance.c.id.in_(tuple(pwm_by_instance)),
                    )
                ).mappings()
            }
        try:
            calculation = self.automation.calculate_profile(project_id, profile["id"])
        except (AutomationError, ValueError) as exc:
            calculation = None
            calculation_warning = str(exc)
        else:
            calculation_warning = "LED load facts are incomplete"
        required = int(profile["channels"])
        records: list[_CandidateRecord] = []
        for instance_id, instance_resources in pwm_by_instance.items():
            ordered = sorted(instance_resources, key=lambda item: item["ordinal"])
            for bundle in combinations(ordered, required):
                reasons: list[str] = []
                warnings: list[str] = []
                if line_assigned:
                    reasons.append("OWNER_ALREADY_ASSIGNED")
                if any(item["occupied"] for item in bundle):
                    reasons.append("OCCUPIED")
                if any(item["id"] in reserved for item in bundle):
                    reasons.append("USER_RESERVE")
                params = parameters.get(instance_id, {})
                if calculation is None or calculation.load is None:
                    reasons.append("MISSING_OFFICIAL_OR_PROJECT_FACTS")
                    warnings.append(calculation_warning)
                else:
                    status, trace = assess_pwm_capacity(
                        calculation.load,
                        selected_channel_count=len(bundle),
                        maximum_current_a_per_channel=params.get(
                            "maximum_current_a_per_channel"
                        ),
                        maximum_combined_current_a=params.get(
                            "maximum_combined_current_a"
                        ),
                    )
                    voltage_limit = _number(params.get("maximum_load_voltage_v_dc"))
                    line_voltage = _number(profile["voltage_decimal"])
                    if status == "LIMIT_EXCEEDED":
                        reasons.append("CAPACITY_CURRENT_CHANNEL_LIMIT")
                    elif status != "VERIFIED" or voltage_limit is None or line_voltage is None:
                        reasons.append("MISSING_OFFICIAL_OR_PROJECT_FACTS")
                    elif line_voltage > voltage_limit:
                        reasons.append("INCOMPATIBLE_VOLTAGE_SIGNAL_POWER")
                    warnings.extend(
                        str(item.get("rule"))
                        for item in trace
                        if item.get("result") not in {"PASS", "VERIFIED"}
                    )
                instance_label = bundle[0]["instance_designation"]
                channel_labels = [
                    item["user_label"].split(" / ", 1)[-1] for item in bundle
                ]
                label = f"{instance_label} / {' + '.join(channel_labels)}"
                ids = tuple(item["id"] for item in bundle)
                dto = self._candidate(
                    GuidedAction.OUTPUT,
                    project_id,
                    line["id"],
                    "LED_BUNDLE",
                    ids,
                    label,
                    instance_label,
                    self._state(reasons),
                    reasons,
                    warnings,
                    f"PWM bundle {required} channel(s)",
                )
                records.append(
                    _CandidateRecord(
                        dto,
                        {
                            "kind": "LED_BUNDLE",
                            "profile_id": profile["id"],
                            "module_instance_id": instance_id,
                            "channel_ordinals": tuple(item["ordinal"] for item in bundle),
                        },
                        self._resource_preference_identity(bundle[0]),
                    )
                )
        return records

    def _input_records(
        self, project_id: str, field_control_key_id: str
    ) -> tuple[_Owner, list[_CandidateRecord]]:
        key = next(
            (
                row
                for row in self.field_model.control_key_read_model(project_id)
                if row["id"] == field_control_key_id
            ),
            None,
        )
        if key is None:
            raise GuidedActionError("Физическая клавиша не найдена в выбранном проекте")
        key_label = (
            f"{key['physical_identity']} — "
            f"{key['functional_target_text'] or 'цель не указана'}"
        )
        assigned = key["status"] == "ASSIGNED"
        owner = _Owner(
            key_label,
            ("Вход не назначен",)
            if not assigned
            else (f"Назначен вход: {key['input_label']}",),
        )
        records: list[_CandidateRecord] = []
        resources = self.constructor.list_resources(project_id)
        effective_reserved = self._reserved_resource_ids(project_id, resources)
        for item in self.field_model.list_control_input_candidates(
            project_id, include_unavailable=True
        ):
            reasons: list[str] = []
            if assigned:
                reasons.append("OWNER_ALREADY_ASSIGNED")
            if item["occupied"]:
                reasons.append("OCCUPIED")
            if item["id"] in effective_reserved:
                reasons.append("USER_RESERVE")
            if item["direction"] not in {"IN", "BIDIRECTIONAL"} or item[
                "resource_kind"
            ] not in {"DRY_CONTACT_INPUT", "DIGITAL_INPUT"}:
                reasons.append("INCOMPATIBLE_KIND_DIRECTION")
            dto = self._candidate(
                GuidedAction.INPUT,
                project_id,
                field_control_key_id,
                "KEY_RESOURCE_INPUT",
                (item["id"],),
                item["label"],
                item["instance_designation"],
                self._state(reasons),
                reasons,
                (),
                f"{item['resource_key']} / input resource",
            )
            records.append(
                _CandidateRecord(
                    dto,
                    {"kind": "KEY_RESOURCE_INPUT", "id": item["id"]},
                    self._resource_preference_identity(item),
                )
            )
        for port in self.field_model.field_port_read_model(project_id):
            reasons = []
            if assigned:
                reasons.append("OWNER_ALREADY_ASSIGNED")
            if port["port_kind"] != "DIGITAL_INPUT" or port["direction"] != "IN":
                reasons.append("INCOMPATIBLE_KIND_DIRECTION")
            if port["linked_key_id"] is not None:
                reasons.append("OCCUPIED")
            label = f"{port['block_kind']} / {port['port_tag']}"
            dto = self._candidate(
                GuidedAction.INPUT,
                project_id,
                field_control_key_id,
                "KEY_FIELD_INPUT",
                (port["id"],),
                label,
                port["block_kind"],
                self._state(reasons),
                reasons,
                (),
                port["physical_identity"],
            )
            records.append(
                _CandidateRecord(
                    dto,
                    {"kind": "KEY_FIELD_INPUT", "id": port["id"]},
                    self._field_preference_identity(port),
                )
            )
        return owner, records

    def _execute(self, action, project_id, owner_id, command, revision):
        kind = command["kind"]
        if kind == "RELATION":
            self.constructor.create_relation(
                project_id=project_id,
                relation_kind="POWER_FLOW",
                source_resource_id=command["source_resource_id"],
                target_resource_id=command["target_resource_id"],
                expected_project_revision=revision,
            )
            return "FUNCTIONAL_RELATION", 1
        if kind == "RESOURCE_OUTPUT":
            self.automation.assign_output_line(
                project_id=project_id,
                cable_line_id=owner_id,
                output_resource_id=command["id"],
                expected_project_revision=revision,
            )
            return "CABLE_LINE_ASSIGNMENT", 1
        if kind == "FIELD_OUTPUT":
            self.field_model.assign_line_to_field_port(
                project_id=project_id,
                cable_line_id=owner_id,
                field_port_id=command["id"],
                assignment_role="PHYSICAL_SOURCE",
                expected_project_revision=revision,
            )
            return "CABLE_LINE_ASSIGNMENT", 1
        if kind == "LED_BUNDLE":
            result = self.automation.assign_led_channels(
                project_id=project_id,
                profile_id=command["profile_id"],
                module_instance_id=command["module_instance_id"],
                channel_ordinals=command["channel_ordinals"],
                expected_project_revision=revision,
            )
            return "CABLE_LINE_ASSIGNMENT", len(result.assignment_ids)
        if kind == "KEY_RESOURCE_INPUT":
            self.field_model.assign_control_key_input(
                project_id=project_id,
                field_control_key_id=owner_id,
                input_resource_id=command["id"],
                expected_project_revision=revision,
            )
            return "CONTROL_KEY_INPUT_ASSIGNMENT", 1
        if kind == "KEY_FIELD_INPUT":
            self.field_model.assign_control_key_field_port(
                project_id=project_id,
                field_control_key_id=owner_id,
                field_port_id=command["id"],
                expected_project_revision=revision,
            )
            return "CONTROL_KEY_INPUT_ASSIGNMENT", 1
        raise GuidedActionError(f"Unsupported guided command: {kind}")

    def _updated_state(self, action, project_id, owner_id):
        if action in {GuidedAction.PROTECTION, GuidedAction.POWER}:
            return (
                "ASSIGNED"
                if any(
                    row["target_resource_id"] == owner_id
                    for row in self.constructor.list_relations(project_id)
                )
                else "UNASSIGNED"
            )
        if action == GuidedAction.OUTPUT:
            return (
                "ASSIGNED"
                if any(
                    row["cable_line_id"] == owner_id
                    for row in self.automation.list_assignments(project_id)
                )
                else "UNASSIGNED"
            )
        model = self.field_model.control_key_read_model(project_id)
        return next(row["status"] for row in model if row["id"] == owner_id)

    def _project_revision(self, project_id: str) -> int:
        with self._engine.connect() as connection:
            revision = connection.scalar(
                select(project.c.project_revision).where(
                    project.c.id == project_id, project.c.lifecycle == "ACTIVE"
                )
            )
        if revision is None:
            raise GuidedActionError("Проект не найден или не активен")
        return int(revision)

    def _reserved_resource_ids(self, project_id, resources):
        with self._engine.connect() as connection:
            rows = list(
                connection.execute(
                    select(
                        user_reserve.c.target_kind,
                        user_reserve.c.project_instance_id,
                        user_reserve.c.instance_resource_id,
                    ).where(
                        user_reserve.c.project_id == project_id,
                        user_reserve.c.lifecycle == "ACTIVE",
                    )
                )
            )
        reserved_resources = {
            row.instance_resource_id
            for row in rows
            if row.target_kind == "INSTANCE_RESOURCE"
        }
        reserved_instances = {
            row.project_instance_id for row in rows if row.target_kind == "PROJECT_INSTANCE"
        }
        reserved_resources.update(
            row["id"] for row in resources if row["project_instance_id"] in reserved_instances
        )
        return reserved_resources

    @staticmethod
    def _resource_preference_identity(resource):
        snapshot = dict(resource.get("snapshot_json") or {})
        variant = snapshot.get("product_key") or resource.get("passport_key")
        if not variant:
            variant = "unresolved-catalog-variant"
        return f"catalog:{variant}:{resource['resource_key']}"

    @staticmethod
    def _field_preference_identity(port):
        return f"field:{port['block_kind']}:{port['port_kind']}"

    @staticmethod
    def _plausible_relation_source(action, resource):
        if action == GuidedAction.PROTECTION:
            return str(resource.get("passport_key", "")).startswith("protection.")
        if resource["direction"] not in {"OUT", "BIDIRECTIONAL"}:
            return False
        kind = str(resource.get("resource_kind", "")).upper()
        return any(
            token in kind
            for token in ("POWER", "VOUT", "PROTECTED", "LIMITED", "BUSBAR")
        )

    @staticmethod
    def _relation_reasons(action, results):
        reasons: list[str] = []
        warnings: list[str] = []
        for result in results:
            suffix = result.rule_id.rsplit(".", 1)[-1]
            if result.outcome == "ERROR":
                if suffix in {
                    "direction",
                    "assignable",
                    "resource_family",
                    "source_kind",
                    "target_kind",
                }:
                    reasons.append("INCOMPATIBLE_KIND_DIRECTION")
                elif suffix in {"current_kind", "voltage_range", "signal_type", "signal_range"}:
                    reasons.append("INCOMPATIBLE_VOLTAGE_SIGNAL_POWER")
                elif suffix in {"capacity"}:
                    reasons.append("CAPACITY_CURRENT_CHANNEL_LIMIT")
                elif suffix in {"exclusivity"}:
                    reasons.append("OCCUPIED")
                elif suffix in {"branching", "self_loop"}:
                    reasons.append("GRAPH_CYCLE_RESTRICTION")
                else:
                    reasons.append("INCOMPATIBLE_KIND_DIRECTION")
            elif result.outcome == "INCOMPLETE":
                warning = result.message
                warnings.append(warning)
                if action == GuidedAction.POWER and suffix in {
                    "current_kind",
                    "voltage_range",
                }:
                    reasons.append("MISSING_OFFICIAL_OR_PROJECT_FACTS")
        return reasons, warnings

    @staticmethod
    def _state(reasons):
        unique = set(reasons)
        if "MISSING_OFFICIAL_OR_PROJECT_FACTS" in unique and len(unique) == 1:
            return CandidateState.INCOMPLETE
        if unique:
            return CandidateState.UNAVAILABLE
        return CandidateState.SELECTABLE

    def _candidate(
        self,
        action,
        project_id,
        owner_id,
        command_kind,
        canonical_ids,
        target_label,
        instance_label,
        state,
        reasons,
        warnings,
        technical_identity,
    ):
        unique_reasons = tuple(dict.fromkeys(reasons))
        unique_warnings = tuple(dict.fromkeys(str(item) for item in warnings if item))
        if unique_reasons:
            explanation = "; ".join(_REASON_TEXT[item] for item in unique_reasons)
        elif unique_warnings:
            explanation = "Совместимо и доступно; есть предупреждения о полноте данных"
        else:
            explanation = "Совместимо и доступно"
        candidate_id = self._candidate_id(
            action.value,
            project_id,
            owner_id,
            command_kind,
            *canonical_ids,
        )
        return GuidedCandidate(
            candidate_id,
            target_label,
            instance_label,
            None,
            state,
            state == CandidateState.SELECTABLE,
            unique_reasons,
            explanation,
            unique_warnings,
            technical_identity,
        )

    @staticmethod
    def _candidate_id(*parts):
        digest = hashlib.sha256("\x1f".join(map(str, parts)).encode("utf-8")).hexdigest()
        return f"candidate-{digest[:24]}"

    @staticmethod
    def _fingerprint(token, revision):
        return hashlib.sha256(f"{token}|{revision}".encode()).hexdigest()

    @staticmethod
    def _decode_token(token):
        try:
            payload = json.loads(base64.urlsafe_b64decode(token.encode("ascii")))
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise GuidedActionError("PREVIEW_TOKEN_INVALID") from exc
        if payload.get("version") != 1:
            raise GuidedActionError("PREVIEW_TOKEN_VERSION_UNSUPPORTED")
        return payload


def _number(value) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None
