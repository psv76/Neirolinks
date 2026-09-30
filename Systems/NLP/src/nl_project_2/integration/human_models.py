"""Human-facing diagnostic and journal DTOs derived from canonical Project facts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class UserStatus(StrEnum):
    READY = "Готово"
    ACTION_REQUIRED = "Требуется действие"
    DATA_REQUIRED = "Нужны данные"
    PROJECT_ERROR = "Ошибка проекта"


STATUS_PRIORITY = {
    UserStatus.READY: 0,
    UserStatus.ACTION_REQUIRED: 1,
    UserStatus.DATA_REQUIRED: 2,
    UserStatus.PROJECT_ERROR: 3,
}


@dataclass(frozen=True, slots=True)
class NavigationTarget:
    section: str
    entity_kind: str
    entity_id: str
    context: str = ""


@dataclass(frozen=True, slots=True)
class EngineeringDetails:
    machine_code: str
    rule: str = ""
    source: str = ""
    technical_ids: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ActionableIssue:
    status: UserStatus
    title: str
    reason: str
    impact: str
    blocking: bool
    required_action: str
    navigation: NavigationTarget
    section: str
    source_kind: str
    source_id: str
    engineering: EngineeringDetails

    @property
    def severity(self) -> str:
        return "ERROR" if self.blocking else "WARNING"

    @property
    def code(self) -> str:
        return self.engineering.machine_code

    @property
    def message(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class UserStatusSummary:
    status: UserStatus
    title: str
    result: str
    confirmed: tuple[str, ...]
    missing_or_violated: tuple[str, ...]
    blocking: bool
    required_action: str
    navigation: NavigationTarget
    engineering: tuple[EngineeringDetails, ...] = ()


@dataclass(frozen=True, slots=True)
class CableJournalSegment:
    segment_id: str
    source_label: str
    target_label: str
    mount_way: str
    conduit_label: str
    length_m: str | None


@dataclass(frozen=True, slots=True)
class CableJournalRow:
    cable_line_id: str
    cable_id: str
    load_name: str
    load_type: str
    board: str
    building: str
    room: str
    cable_type: str
    mount_way: str
    conduit: str
    total_length_m: str | None
    length_mode: str
    length_explanation: str
    status: UserStatus
    segments: tuple[CableJournalSegment, ...]


@dataclass(frozen=True, slots=True)
class OperationJournalRow:
    operation_id: str
    occurred_at: str
    action: str
    summary: str
    status: str
    context: str
    revision_before: int | None
    revision_after: int | None
    correlation_id: str
    command_id: str
    source_kind: str


def aggregate_status(
    issues: tuple[ActionableIssue, ...] | list[ActionableIssue],
    *,
    ready_title: str = "Готово",
    ready_result: str = "Обязательные данные и связи подтверждены",
    navigation: NavigationTarget | None = None,
) -> UserStatusSummary:
    ordered = sorted(
        issues,
        key=lambda item: (
            STATUS_PRIORITY[item.status],
            item.blocking,
            item.code,
        ),
        reverse=True,
    )
    relevant = [item for item in ordered if item.status != UserStatus.READY]
    if not relevant:
        target = navigation or NavigationTarget("Линии", "PROJECT", "")
        return UserStatusSummary(
            UserStatus.READY,
            ready_title,
            ready_result,
            (ready_result,),
            (),
            False,
            "Действие не требуется",
            target,
        )
    primary = relevant[0]
    return UserStatusSummary(
        primary.status,
        primary.title,
        primary.reason,
        (),
        tuple(dict.fromkeys(item.reason for item in relevant)),
        any(item.blocking for item in relevant),
        primary.required_action,
        primary.navigation,
        tuple(item.engineering for item in relevant),
    )
