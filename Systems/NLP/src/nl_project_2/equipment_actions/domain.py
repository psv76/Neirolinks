"""Immutable human-facing contracts for P1_002 equipment actions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DesignationPlanItem:
    proposed_designation: str
    conflict_codes: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.conflict_codes


@dataclass(frozen=True, slots=True)
class DesignationPlan:
    project_revision: int
    existing_designations: tuple[str, ...]
    proposed: tuple[DesignationPlanItem, ...]
    fingerprint: str
    formatter_path: str = "EXPLICIT_PROPOSED_SEQUENCE"

    @property
    def valid(self) -> bool:
        return bool(self.proposed) and all(item.valid for item in self.proposed)


@dataclass(frozen=True, slots=True)
class DuplicatePreview:
    source_instance_id: str
    source_designation: str
    equipment_name: str
    passport_name: str
    product_name: str | None
    proposed_designation: str
    copied_facts: tuple[str, ...]
    excluded_facts: tuple[str, ...]
    conflicts: tuple[str, ...]
    project_revision: int
    source_row_version: int
    fingerprint: str
    confirmation_token: str

    @property
    def valid(self) -> bool:
        return not self.conflicts


@dataclass(frozen=True, slots=True)
class DuplicateReceipt:
    new_instance_id: str
    new_designation: str
    resource_count: int
    project_revision_before: int
    project_revision_after: int


@dataclass(frozen=True, slots=True)
class ReserveState:
    target_type: str
    target_label: str
    target_id: str
    effective_reserved: bool
    direct_reserved: bool
    inherited_from_instance: bool
    note: str | None
    reason: str
    project_revision: int
    unavailable_reason: str | None = None


@dataclass(frozen=True, slots=True)
class EmptyInstanceIssue:
    code: str
    status: str
    instance_id: str
    instance_label: str
    message: str
    suggested_actions: tuple[str, ...]


class EquipmentActionError(RuntimeError):
    pass


class ConfirmationRequired(EquipmentActionError):
    pass


class StaleEquipmentPreview(EquipmentActionError):
    pass
