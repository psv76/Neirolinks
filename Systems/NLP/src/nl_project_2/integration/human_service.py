"""Human diagnostics and journals assembled read-only from canonical feature facts."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sqlalchemy import and_, select

from nl_project_2.persistence.schema import (
    background_job,
    cable_point,
    cable_segment,
    cable_topology_endpoint,
    conduit,
    conduit_segment_assignment,
    dwg_observation,
    dwg_scan,
    dwg_sync_change,
    dwg_sync_operation,
    operation_journal,
)
from nl_project_2.resource_labels import resource_user_label

from .human_models import (
    ActionableIssue,
    CableJournalRow,
    CableJournalSegment,
    EngineeringDetails,
    NavigationTarget,
    OperationJournalRow,
    UserStatus,
    UserStatusSummary,
    aggregate_status,
)

_STATUS_TEXT = {
    "SUCCEEDED": "Успешно",
    "APPLIED": "Успешно",
    "ACCEPTED": "Успешно",
    "READ_BACK_OK": "Успешно",
    "FAILED": "Не выполнено",
    "REJECTED": "Отклонено",
    "UNRESOLVED": "Требуется действие",
    "PARTIAL": "Выполнено частично",
    "CANCELLED": "Отменено",
    "STALE": "Устаревший результат",
    "PENDING": "Выполняется",
    "RUNNING": "Выполняется",
}

_ACTION_TEXT = {
    "BULK_PROTECTION": "Массово назначена защита",
    "BULK_POWER": "Массово назначено питание",
    "BULK_OUTPUT": "Массово назначены выходы / каналы",
    "BULK_INPUT": "Массово назначены входы",
    "LINE_SCALAR_BATCH_UPDATE": "Изменены данные кабельных линий",
    "EQUIPMENT_DUPLICATE": "Создана копия оборудования",
    "EQUIPMENT_RESERVE_SET": "Установлен резерв оборудования",
    "EQUIPMENT_RESERVE_REMOVED": "Снят резерв оборудования",
    "DWG_TO_PROJECT": "Применены данные DWG в проект",
    "PROJECT_TO_DWG": "Записаны данные проекта в DWG",
}

_DWG_RULE_TEXT = {
    "UNKNOWN_BLOCK_NAME": "Имя блока с атрибутами NL Project не распознано",
    "BLOCK_NAME_FORMAT": "Имя блока с атрибутами NL Project имеет неверный формат",
    "REQUIRED_ATTRIBUTE_MISSING": "В блоке отсутствует обязательное поле",
    "DEVICE_TYPE_MISMATCH": "Тип устройства не соответствует имени блока",
    "LAYER_FUNCTION_GROUP_MISMATCH": "Блок находится на неподходящем слое",
    "CABLE_ID_FORMAT": "Некорректно указан номер кабельной линии",
    "DUPLICATE_FULL_CABLE_ID": "Номер точки кабельной линии не уникален",
    "FRAME_IP44_POSTS_DEFICIT": "Для рамки IP44 недостаточно постов",
}


def _human_dwg_reason(code: str, diagnostic: dict, observation: dict) -> str:
    title = _DWG_RULE_TEXT.get(code, "Нарушено правило данных DWG")
    block = str(observation.get("effective_block_name") or "").strip()
    field = str(diagnostic.get("field") or "").strip()
    details = []
    if block:
        details.append(f"блок {block}")
    if field and field != "$":
        details.append(f"поле {field}")
    return title if not details else f"{title}: {', '.join(details)}"


class IntegratedUiService:
    """One read-only presenter over existing validators, facts and journals."""

    def __init__(
        self,
        *,
        constructor,
        cables,
        panels,
        specification,
        engine=None,
        equipment_actions=None,
        distribution=None,
        automation=None,
        buses=None,
    ) -> None:
        self.constructor = constructor
        self.cables = cables
        self.panels = panels
        self.specification = specification
        self.engine = engine or getattr(constructor, "_engine", None)
        self.equipment_actions = equipment_actions
        self.distribution = distribution
        self.automation = automation
        self.buses = buses

    def validation_items(self, project_id: str) -> tuple[ActionableIssue, ...]:
        """Compatibility name used by the existing validation-center presentation."""

        return self.issues(project_id)

    def issues(self, project_id: str) -> tuple[ActionableIssue, ...]:
        items: list[ActionableIssue] = []
        line_cards = list(self.cables.line_cards(project_id)) if self.cables else []
        assignments = (
            list(self.constructor.list_cable_assignments(project_id)) if self.constructor else []
        )
        items.extend(self._line_issues(line_cards, assignments))
        items.extend(self._constructor_issues(project_id))
        items.extend(self._distribution_issues(project_id))
        items.extend(self._automation_issues(project_id))
        items.extend(self._bus_issues(project_id))
        items.extend(self._conduit_issues(project_id))
        items.extend(self._panel_issues(project_id))
        items.extend(self._specification_issues(project_id))
        items.extend(self._dwg_issues(project_id))
        unique: dict[tuple[str, str, str], ActionableIssue] = {}
        for item in items:
            unique[(item.code, item.source_kind, item.source_id)] = item
        return tuple(
            sorted(
                unique.values(),
                key=lambda item: (
                    0 if item.blocking else 1,
                    item.status.value,
                    item.section,
                    item.code,
                    item.source_id,
                ),
            )
        )

    def line_statuses(self, project_id: str) -> dict[str, UserStatusSummary]:
        cards = list(self.cables.line_cards(project_id)) if self.cables else []
        issues = self.issues(project_id)
        by_line: dict[str, list[ActionableIssue]] = {card["id"]: [] for card in cards}
        for item in issues:
            if item.source_kind == "CABLE_LINE" and item.source_id in by_line:
                by_line[item.source_id].append(item)
        return {
            card["id"]: aggregate_status(
                tuple(by_line[card["id"]]),
                ready_title="Линия готова",
                ready_result="Данные линии, длина и обязательное назначение подтверждены",
                navigation=NavigationTarget("Линии", "CABLE_LINE", card["id"]),
            )
            for card in cards
        }

    def status_for_line(self, project_id: str, line_id: str) -> UserStatusSummary:
        return self.line_statuses(project_id).get(
            line_id,
            aggregate_status((), navigation=NavigationTarget("Линии", "CABLE_LINE", line_id)),
        )

    def instance_statuses(self, project_id: str) -> dict[str, UserStatusSummary]:
        instances = list(self.constructor.list_instances(project_id)) if self.constructor else []
        resources = list(self.constructor.list_resources(project_id)) if self.constructor else []
        resource_owner = {row["id"]: row["project_instance_id"] for row in resources}
        by_instance: dict[str, list[ActionableIssue]] = {row["id"]: [] for row in instances}
        for item in self.issues(project_id):
            owner = (
                item.source_id
                if item.source_kind == "PROJECT_INSTANCE"
                else resource_owner.get(item.source_id)
                if item.source_kind == "RESOURCE"
                else None
            )
            if owner in by_instance:
                by_instance[owner].append(item)
        return {
            row["id"]: aggregate_status(
                tuple(by_instance[row["id"]]),
                ready_title="Оборудование готово",
                ready_result="Экземпляр имеет подтверждённое полезное назначение",
                navigation=NavigationTarget("Оборудование", "PROJECT_INSTANCE", row["id"]),
            )
            for row in instances
        }

    def status_for_instance(self, project_id: str, instance_id: str) -> UserStatusSummary:
        return self.instance_statuses(project_id).get(
            instance_id,
            aggregate_status(
                (),
                navigation=NavigationTarget("Оборудование", "PROJECT_INSTANCE", instance_id),
            ),
        )

    def cable_journal_rows(self, project_id: str) -> tuple[CableJournalRow, ...]:
        cards = list(self.cables.line_cards(project_id)) if self.cables else []
        statuses = self.line_statuses(project_id)
        segments = self._segments_by_line(project_id)
        rows = []
        for card in cards:
            rows.append(
                CableJournalRow(
                    cable_line_id=card["id"],
                    cable_id=str(card.get("designation") or ""),
                    load_name=str(card.get("load_name") or "Не указано"),
                    load_type=str(card.get("load_type") or ""),
                    board=str(card.get("board") or ""),
                    building=str(card.get("building_names") or ""),
                    room=str(card.get("room_names") or ""),
                    cable_type=str(card.get("cable_type") or ""),
                    mount_way=str(card.get("mount_way") or ""),
                    conduit=str(card.get("gofra_id") or ""),
                    total_length_m=(
                        None if card.get("effective_m") is None else str(card.get("effective_m"))
                    ),
                    length_mode=str(card.get("length_mode") or "Не рассчитана"),
                    length_explanation=str(card.get("length_explanation") or ""),
                    status=statuses[card["id"]].status,
                    segments=tuple(segments.get(card["id"], ())),
                )
            )
        return tuple(sorted(rows, key=lambda row: _natural_key(row.cable_id)))

    def operation_rows(self, project_id: str) -> tuple[OperationJournalRow, ...]:
        if self.engine is None:
            return ()
        rows: list[OperationJournalRow] = []
        with self.engine.connect() as connection:
            for row in connection.execute(
                select(operation_journal)
                .where(operation_journal.c.project_id == project_id)
                .order_by(operation_journal.c.started_at_utc, operation_journal.c.id)
            ).mappings():
                summary = dict(row["summary_json"] or {})
                rows.append(
                    OperationJournalRow(
                        row["id"],
                        _date_text(row["completed_at_utc"] or row["started_at_utc"]),
                        _ACTION_TEXT.get(row["command_type"], _human_code(row["command_type"])),
                        _summary_text(summary),
                        _STATUS_TEXT.get(row["status"], _human_code(row["status"])),
                        _context_text(summary),
                        row["project_revision_before"],
                        row["project_revision_after"],
                        row["correlation_id"],
                        row["command_id"],
                        "OPERATION_JOURNAL",
                    )
                )
            for row in connection.execute(
                select(dwg_sync_operation)
                .where(dwg_sync_operation.c.project_id == project_id)
                .order_by(dwg_sync_operation.c.created_at_utc, dwg_sync_operation.c.id)
            ).mappings():
                result = dict(row["result_json"] or {})
                status = str(result.get("status") or result.get("result") or "SUCCEEDED")
                direction = str(row["direction"])
                rows.append(
                    OperationJournalRow(
                        row["id"],
                        _date_text(row["created_at_utc"]),
                        _ACTION_TEXT.get(direction, f"Синхронизация DWG: {direction}"),
                        _summary_text(result) or "Результат синхронизации сохранён",
                        _STATUS_TEXT.get(status, _human_code(status)),
                        "DWG",
                        None,
                        None,
                        row["correlation_id"],
                        "",
                        "DWG_SYNC_OPERATION",
                    )
                )
            for row in connection.execute(
                select(background_job)
                .where(background_job.c.project_id == project_id)
                .order_by(background_job.c.created_at_utc, background_job.c.id)
            ).mappings():
                rows.append(
                    OperationJournalRow(
                        row["id"],
                        _date_text(row["updated_at_utc"] or row["created_at_utc"]),
                        f"Фоновая операция: {_human_code(row['job_kind'])}",
                        "Результат фоновой операции сохранён"
                        if row["result_reference"]
                        else "Результат отсутствует",
                        _STATUS_TEXT.get(row["status"], _human_code(row["status"])),
                        "Проект",
                        row["input_revision"],
                        None,
                        row["correlation_id"],
                        "",
                        "BACKGROUND_JOB",
                    )
                )
        return tuple(sorted(rows, key=lambda item: (item.occurred_at, item.operation_id)))

    def _line_issues(self, cards, assignments) -> list[ActionableIssue]:
        assigned = {row["cable_line_id"] for row in assignments}
        items: list[ActionableIssue] = []
        for card in cards:
            line_id = card["id"]
            label = str(card.get("designation") or "Линия")
            missing = [
                title
                for key, title in (
                    ("load_name", "имя потребителя"),
                    ("board", "щит или источник"),
                    ("cable_type", "тип кабеля"),
                )
                if not str(card.get(key) or "").strip()
            ]
            if card.get("effective_m") is None:
                missing.append("итоговая длина")
            if missing:
                items.append(
                    self._issue(
                        UserStatus.DATA_REQUIRED,
                        "Данные линии неполны",
                        f"{label}: не указаны {', '.join(missing)}",
                        "Кабельный журнал и выпуск нельзя подтвердить",
                        False,
                        "Заполните исходные данные в разделе «Линии»",
                        "CABLES",
                        "CABLE_LENGTH_INCOMPLETE"
                        if card.get("effective_m") is None
                        else "CABLE_LINE_DATA_INCOMPLETE",
                        "CABLE_LINE",
                        line_id,
                        NavigationTarget("Линии", "CABLE_LINE", line_id),
                        "cables.line_cards",
                    )
                )
            if line_id not in assigned and str(card.get("system_kind") or "") != "AV":
                items.append(
                    self._issue(
                        UserStatus.ACTION_REQUIRED,
                        "Требуется назначение линии",
                        f"{label}: выход или канал не назначен",
                        "Функциональная цепь линии остаётся незавершённой",
                        False,
                        "Откройте линию и выполните «Назначить выход/канал»",
                        "CONSTRUCTOR",
                        "CABLE_OUTPUT_ACTION_REQUIRED",
                        "CABLE_LINE",
                        line_id,
                        NavigationTarget("Линии", "CABLE_LINE", line_id, "OUTPUT"),
                        "constructor.cable_line_assignment",
                    )
                )
        return items

    def _constructor_issues(self, project_id: str) -> list[ActionableIssue]:
        if self.constructor is None:
            return []
        resources = {row["id"]: row for row in self.constructor.list_resources(project_id)}
        items = []
        for result in self.constructor.validate_required_resources(project_id):
            if result.outcome == "PASS":
                continue
            source_id = result.entity_ids[0]
            resource = resources.get(source_id, {})
            label = "Ресурс" if not resource else resource_user_label(resource)
            items.append(
                self._issue(
                    UserStatus.ACTION_REQUIRED,
                    "Обязательный ресурс не назначен",
                    f"{label}: требуется назначение",
                    "Связанная функциональная цепь не подтверждена",
                    bool(result.blocking),
                    "Откройте оборудование и назначьте совместимый ресурс",
                    "CONSTRUCTOR",
                    "REQUIRED_RESOURCE_UNASSIGNED",
                    "RESOURCE",
                    source_id,
                    NavigationTarget("Оборудование", "RESOURCE", source_id),
                    result.rule,
                    evidence=(str(result.actual), str(result.required)),
                )
            )
        if self.equipment_actions is not None:
            for item in self.equipment_actions.empty_instance_issues(project_id=project_id):
                instance_label = getattr(item, "instance_label", None) or getattr(
                    item, "target_label", "Оборудование"
                )
                instance_id = getattr(item, "instance_id", None) or getattr(item, "target_id", "")
                items.append(
                    self._issue(
                        UserStatus.ACTION_REQUIRED,
                        "Пустой экземпляр оборудования",
                        f"{instance_label}: нет полезного назначения и резерва",
                        "Экземпляр может быть лишним или ещё не распределён",
                        False,
                        "Назначьте ресурс, установите РЕЗЕРВ или удалите экземпляр",
                        "EQUIPMENT",
                        item.code,
                        "PROJECT_INSTANCE",
                        instance_id,
                        NavigationTarget("Оборудование", "PROJECT_INSTANCE", instance_id),
                        "equipment_actions.empty_instance_issues",
                    )
                )
        return items

    def _distribution_issues(self, project_id: str) -> list[ActionableIssue]:
        if self.distribution is None:
            return []
        items = []
        for instance in self.distribution.list_instances(project_id):
            equipment_class = str(instance.get("equipment_class") or "")
            assessment = None
            try:
                if equipment_class.startswith("AC_DC_POWER_SUPPLY"):
                    assessment = self.distribution.assess_psu_instance(project_id, instance["id"])
                elif equipment_class == "DISTRIBUTION_BLOCK":
                    assessment = self.distribution.assess_cross_module_instance(
                        project_id, instance["id"]
                    )
                elif equipment_class == "INRUSH_CURRENT_LIMITER":
                    assessment = self.distribution.assess_linked_icl(
                        project_id=project_id, icl_instance_id=instance["id"]
                    )
            except (KeyError, TypeError, ValueError):
                assessment = None
            if assessment is None or assessment.status == "VERIFIED":
                continue
            data_missing = assessment.status == "DATA_INCOMPLETE"
            items.append(
                self._issue(
                    UserStatus.DATA_REQUIRED if data_missing else UserStatus.PROJECT_ERROR,
                    "Проверка питания не завершена" if data_missing else "Ошибка питания",
                    f"{instance['designation']}: {_human_code(assessment.status)}",
                    "Нельзя подтвердить питание, защиту или допустимую нагрузку",
                    not data_missing,
                    "Откройте оборудование и проверьте цепь питания и исходные данные",
                    "DISTRIBUTION",
                    f"DISTRIBUTION_{assessment.status}",
                    "PROJECT_INSTANCE",
                    instance["id"],
                    NavigationTarget("Оборудование", "PROJECT_INSTANCE", instance["id"], "POWER"),
                    "distribution.assessment",
                    evidence=tuple(str(item) for item in assessment.trace),
                )
            )
        return items

    def _automation_issues(self, project_id: str) -> list[ActionableIssue]:
        if self.automation is None:
            return []
        items = []
        for profile in self.automation.list_led_profiles(project_id):
            try:
                result = self.automation.calculate_profile(project_id, profile["id"])
            except (KeyError, TypeError, ValueError):
                result = None
            status = "DATA_INCOMPLETE" if result is None else result.packing.status
            if status == "VERIFIED":
                continue
            line_id = profile["cable_line_id"]
            items.append(
                self._issue(
                    UserStatus.DATA_REQUIRED,
                    "LED-расчёт не подтверждён",
                    f"{profile['cable_designation']}: не хватает данных для расчёта LED",
                    "Каналы, нагрузка и закупка ленты не подтверждены",
                    False,
                    "Откройте автоматизацию и заполните LED-профиль и участки",
                    "AUTOMATION",
                    f"LED_{status}",
                    "CABLE_LINE",
                    line_id,
                    NavigationTarget("Линии", "CABLE_LINE", line_id, "LED"),
                    "automation.calculate_profile",
                )
            )
        return items

    def _bus_issues(self, project_id: str) -> list[ActionableIssue]:
        if self.buses is None:
            return []
        items = []
        for bus_row in self.buses.list_buses(project_id):
            stored = self.buses.get_bus(project_id, bus_row["id"])
            if not stored["endpoints"]:
                items.append(
                    self._issue(
                        UserStatus.ACTION_REQUIRED,
                        "Шина не содержит точек",
                        f"{bus_row['designation']}: добавьте устройства шины",
                        "Топология и связь устройств не подтверждены",
                        False,
                        "Откройте «Шины» и добавьте точки",
                        "BUSES",
                        "BUS_ENDPOINTS_ACTION_REQUIRED",
                        "BUS",
                        bus_row["id"],
                        NavigationTarget("Оборудование", "BUS", bus_row["id"], "BUS"),
                        "buses.get_bus",
                    )
                )
            for state in self.buses.connection_states(project_id, bus_row["id"]):
                if state["power_state"] in {"VERIFIED", "NOT_APPLICABLE"}:
                    continue
                source_id = state.get("resource_id") or state.get("field_device_id") or ""
                items.append(
                    self._issue(
                        UserStatus.ACTION_REQUIRED,
                        "Не подтверждено питание точки шины",
                        f"{bus_row['designation']}: назначьте питание устройства",
                        "Связь по шине не подтверждает питание устройства",
                        False,
                        "Откройте оборудование и назначьте питание",
                        "BUSES",
                        "BUS_POINT_POWER_ACTION_REQUIRED",
                        "RESOURCE" if state.get("resource_id") else "FIELD_DEVICE",
                        source_id,
                        NavigationTarget("Оборудование", "RESOURCE", source_id, "BUS"),
                        "buses.connection_states",
                    )
                )
        return items

    def _conduit_issues(self, project_id: str) -> list[ActionableIssue]:
        if self.engine is None:
            return []
        items = []
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(
                    cable_segment.c.id,
                    cable_segment.c.cable_line_id,
                    cable_segment.c.mount_way,
                    conduit_segment_assignment.c.conduit_id,
                )
                .outerjoin(
                    conduit_segment_assignment,
                    and_(
                        conduit_segment_assignment.c.cable_segment_id == cable_segment.c.id,
                        conduit_segment_assignment.c.project_id == project_id,
                    ),
                )
                .where(cable_segment.c.project_id == project_id)
            ).mappings()
            for row in rows:
                if row["mount_way"] == "По полу" and row["conduit_id"] is None:
                    items.append(
                        self._issue(
                            UserStatus.ACTION_REQUIRED,
                            "Защитная труба не назначена",
                            "Для сегмента «По полу» требуется защитная труба",
                            "Трасса и потребность в трубе не завершены",
                            False,
                            "Откройте «Трассы» и назначьте сегмент в трубу",
                            "CONDUITS",
                            "CONDUIT_REQUIRED_FOR_FLOOR_SEGMENT",
                            "CABLE_LINE",
                            row["cable_line_id"],
                            NavigationTarget("Трассы", "CABLE_SEGMENT", row["id"]),
                            "cables.segment_conduit",
                            technical_ids=(row["id"],),
                        )
                    )
            for row in connection.execute(
                select(conduit.c.id, conduit.c.designation).where(
                    conduit.c.project_id == project_id,
                    conduit.c.lifecycle == "ACTIVE",
                    conduit.c.length_m_decimal.is_(None),
                )
            ).mappings():
                items.append(
                    self._issue(
                        UserStatus.DATA_REQUIRED,
                        "Длина трубы не подтверждена",
                        f"{row['designation']}: длина не задана",
                        "Количество трубы в документах нельзя подтвердить",
                        False,
                        "Откройте «Трассы» и подтвердите длину",
                        "CONDUITS",
                        "CONDUIT_LENGTH_DATA_REQUIRED",
                        "CONDUIT",
                        row["id"],
                        NavigationTarget("Трассы", "CONDUIT", row["id"]),
                        "cables.conduit",
                    )
                )
        return items

    def _panel_issues(self, project_id: str) -> list[ActionableIssue]:
        if self.panels is None:
            return []
        items = []
        for board in self.panels.list_boards(project_id):
            if board["board_kind"] == "BOARD_AV":
                continue
            layout = self.panels.board_layout(project_id=project_id, board_id=board["id"])
            for rail in layout["rails"]:
                for issue in rail["evaluation"].issues:
                    items.append(
                        self._issue(
                            UserStatus.PROJECT_ERROR
                            if issue.blocking
                            else UserStatus.DATA_REQUIRED,
                            "Проверка щита",
                            issue.message,
                            "DIN-компоновка щита не подтверждена",
                            issue.blocking,
                            "Откройте щит и исправьте размещение или данные изделия",
                            "PANELS",
                            issue.code,
                            "PANEL_RAIL",
                            rail["id"],
                            NavigationTarget("Щиты", "PANEL_RAIL", rail["id"]),
                            "panels.evaluate_rail",
                            technical_ids=tuple(issue.placement_ids),
                        )
                    )
            for instance in layout["instances"]:
                if instance["layout_state"] == "READY":
                    continue
                items.append(
                    self._issue(
                        UserStatus.ACTION_REQUIRED,
                        "Оборудование не размещено в щите",
                        f"{instance['designation']}: требуется размещение",
                        "Компоновка щита остаётся незавершённой",
                        False,
                        "Откройте щит и разместите экземпляр",
                        "PANELS",
                        instance["layout_state"],
                        "PROJECT_INSTANCE",
                        instance["id"],
                        NavigationTarget("Щиты", "PROJECT_INSTANCE", instance["id"]),
                        "panels.board_layout",
                    )
                )
        return items

    def _specification_issues(self, project_id: str) -> list[ActionableIssue]:
        if self.specification is None:
            return []
        items = []
        specification_result = self.specification.build(project_id)
        for issue in specification_result["issues"]:
            status = UserStatus.__members__.get(
                getattr(issue, "status", "PROJECT_ERROR"), UserStatus.PROJECT_ERROR
            )
            blocking = bool(getattr(issue, "blocking", True))
            items.append(
                self._issue(
                    status,
                    "Ошибка спецификации" if blocking else "Данные спецификации",
                    issue.message,
                    (
                        "Состав или область поставки спецификации нарушены"
                        if blocking
                        else "Расчётная потребность сохранена без неподтверждённых товарных фактов"
                    ),
                    blocking,
                    getattr(issue, "required_action", None)
                    or "Откройте спецификацию и перейдите к исходной сущности",
                    "SPECIFICATION",
                    issue.code,
                    issue.source_kind,
                    issue.source_id,
                    NavigationTarget(
                        "Документы", issue.source_kind, issue.source_id, "SPECIFICATION"
                    ),
                    "specification.group_sources",
                )
            )
        for row in specification_result["rows"]:
            if not row.budget_included or row.cost is not None or not row.source_refs:
                continue
            source_kind, source_id = row.source_refs[0]
            items.append(
                self._issue(
                    UserStatus.DATA_REQUIRED,
                    "Стоимость не указана",
                    f"{row.name}: стоимость не определена",
                    "Сметную стоимость нельзя подтвердить; количество сохраняется",
                    False,
                    "Укажите подтверждённую цену или источник коммерческих данных",
                    "SPECIFICATION",
                    "COST_UNKNOWN",
                    source_kind,
                    source_id,
                    NavigationTarget("Документы", source_kind, source_id, "SPECIFICATION"),
                    "specification.commercial_fact",
                )
            )
        return items

    def _dwg_issues(self, project_id: str) -> list[ActionableIssue]:
        if self.engine is None:
            return []
        items = []
        with self.engine.connect() as connection:
            latest_scan_id = connection.scalar(
                select(dwg_scan.c.id)
                .where(dwg_scan.c.project_id == project_id)
                .order_by(dwg_scan.c.started_at_utc.desc(), dwg_scan.c.id.desc())
                .limit(1)
            )
            if latest_scan_id:
                for row in connection.execute(
                    select(dwg_observation).where(
                        dwg_observation.c.project_id == project_id,
                        dwg_observation.c.dwg_scan_id == latest_scan_id,
                    )
                ).mappings():
                    for diagnostic in row["diagnostics_json"] or []:
                        code = str(diagnostic.get("code") or "DWG_VALIDATION")
                        blocking = bool(diagnostic.get("blocks_acceptance"))
                        items.append(
                            self._issue(
                                UserStatus.PROJECT_ERROR
                                if blocking
                                else UserStatus.ACTION_REQUIRED,
                                "Проверка DWG",
                                _human_dwg_reason(code, diagnostic, row),
                                "Данные DWG нельзя считать подтверждёнными"
                                if blocking
                                else "Требуется проверить чертёж",
                                blocking,
                                "Откройте раздел DWG и исправьте указанную вставку",
                                "DWG",
                                code,
                                "DWG_INSERTION",
                                row["id"],
                                NavigationTarget(
                                    "DWG", "DWG_INSERTION", row["id"], row["entity_handle"]
                                ),
                                "cad_contract.validator",
                                technical_ids=(row["entity_handle"],),
                                evidence=(
                                    str(diagnostic.get("field") or ""),
                                    _safe_text(diagnostic.get("message") or code),
                                ),
                            )
                        )
            latest_operation_id = connection.scalar(
                select(dwg_sync_operation.c.id)
                .where(dwg_sync_operation.c.project_id == project_id)
                .order_by(
                    dwg_sync_operation.c.created_at_utc.desc(),
                    dwg_sync_operation.c.id.desc(),
                )
                .limit(1)
            )
            if latest_operation_id:
                for row in connection.execute(
                    select(dwg_sync_change).where(
                        dwg_sync_change.c.project_id == project_id,
                        dwg_sync_change.c.dwg_sync_operation_id == latest_operation_id,
                        dwg_sync_change.c.change_class.in_(
                            (
                                "BOTH_CHANGED_CONFLICT",
                                "IDENTITY_COLLISION",
                                "INVALID_DWG_DATA",
                                "MISSING_DWG_INSERTION",
                            )
                        ),
                    )
                ).mappings():
                    blocking = row["change_class"] != "MISSING_DWG_INSERTION"
                    items.append(
                        self._issue(
                            UserStatus.PROJECT_ERROR if blocking else UserStatus.ACTION_REQUIRED,
                            "Расхождение Project / DWG",
                            f"{row['field_path']}: {_human_code(row['change_class'])}",
                            "Синхронизация выбранного поля заблокирована",
                            blocking,
                            "Откройте DWG preview и явно разрешите расхождение",
                            "DWG",
                            row["change_class"],
                            "DWG_CHANGE",
                            row["id"],
                            NavigationTarget("DWG", "DWG_CHANGE", row["id"]),
                            "cad_sync.three_way_diff",
                            evidence=(row["field_path"],),
                        )
                    )
        return items

    def _segments_by_line(self, project_id: str) -> dict[str, list[CableJournalSegment]]:
        if self.engine is None:
            return {}
        source_endpoint = cable_topology_endpoint.alias("journal_source_endpoint")
        target_endpoint = cable_topology_endpoint.alias("journal_target_endpoint")
        source_point = cable_point.alias("journal_source_point")
        target_point = cable_point.alias("journal_target_point")
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(
                    cable_segment.c.id,
                    cable_segment.c.cable_line_id,
                    cable_segment.c.mount_way,
                    cable_segment.c.calculated_length_m_decimal,
                    source_endpoint.c.endpoint_kind.label("source_kind"),
                    target_endpoint.c.endpoint_kind.label("target_kind"),
                    source_point.c.logical_identity.label("source_identity"),
                    target_point.c.logical_identity.label("target_identity"),
                    conduit.c.designation.label("conduit_designation"),
                )
                .join(source_endpoint, source_endpoint.c.id == cable_segment.c.source_endpoint_id)
                .join(target_endpoint, target_endpoint.c.id == cable_segment.c.target_endpoint_id)
                .outerjoin(source_point, source_point.c.id == source_endpoint.c.cable_point_id)
                .outerjoin(target_point, target_point.c.id == target_endpoint.c.cable_point_id)
                .outerjoin(
                    conduit_segment_assignment,
                    conduit_segment_assignment.c.cable_segment_id == cable_segment.c.id,
                )
                .outerjoin(conduit, conduit.c.id == conduit_segment_assignment.c.conduit_id)
                .where(cable_segment.c.project_id == project_id)
                .order_by(cable_segment.c.cable_line_id, cable_segment.c.id)
            ).mappings()
            result: dict[str, list[CableJournalSegment]] = {}
            for row in rows:
                result.setdefault(row["cable_line_id"], []).append(
                    CableJournalSegment(
                        row["id"],
                        row["source_identity"] or _endpoint_label(row["source_kind"]),
                        row["target_identity"] or _endpoint_label(row["target_kind"]),
                        row["mount_way"] or "Не указано",
                        row["conduit_designation"] or "Не назначена",
                        row["calculated_length_m_decimal"],
                    )
                )
            return result

    @staticmethod
    def _issue(
        status,
        title,
        reason,
        impact,
        blocking,
        required_action,
        section,
        code,
        source_kind,
        source_id,
        navigation,
        rule,
        *,
        technical_ids=(),
        evidence=(),
    ) -> ActionableIssue:
        return ActionableIssue(
            status,
            title,
            _safe_text(reason),
            impact,
            blocking,
            required_action,
            navigation,
            section,
            source_kind,
            source_id,
            EngineeringDetails(
                code,
                rule,
                section,
                tuple(str(item) for item in technical_ids if item),
                tuple(_safe_text(item) for item in evidence if item),
            ),
        )


def _natural_key(value: str) -> tuple:
    return tuple(
        int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", value)
    )


def _endpoint_label(kind: str) -> str:
    return {
        "INSTANCE_RESOURCE": "Источник оборудования",
        "FIELD_PORT": "Полевой порт",
        "TOPOLOGY_POINT": "Точка линии",
    }.get(str(kind), "Точка")


def _date_text(value: datetime | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    return _safe_text(value)


def _human_code(value: Any) -> str:
    return str(value or "").replace("_", " ").strip().capitalize()


def _safe_text(value: Any) -> str:
    text = str(value or "")
    lines = []
    for line in text.replace("\r", "\n").split("\n"):
        lowered = line.casefold()
        if any(
            token in lowered
            for token in ("traceback", "stack trace", "select ", "insert ", "update ")
        ):
            continue
        line = re.sub(r"File \"[^\"]+\", line \d+", "технические сведения скрыты", line)
        if line.strip():
            lines.append(line.strip())
    return " ".join(lines)[:600]


def _summary_text(summary: dict[str, Any]) -> str:
    preferred = (
        "human_summary",
        "summary",
        "message",
        "action_label",
        "chosen_variant",
        "result",
    )
    parts = [_safe_text(summary[key]) for key in preferred if summary.get(key)]
    if summary.get("selection_count") is not None:
        parts.append(f"Затронуто: {summary['selection_count']}")
    if summary.get("canonical_fact_count") is not None:
        parts.append(f"Изменений: {summary['canonical_fact_count']}")
    return "; ".join(dict.fromkeys(part for part in parts if part)) or "Операция сохранена"


def _context_text(summary: dict[str, Any]) -> str:
    for key in ("context_label", "owner_label", "chosen_variant", "action_label"):
        if summary.get(key):
            return _safe_text(summary[key])
    return "Проект"
