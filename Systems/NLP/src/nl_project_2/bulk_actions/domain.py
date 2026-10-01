"""Immutable human-first contracts for controlled bulk actions."""

from __future__ import annotations

from dataclasses import dataclass

from nl_project_2.guided_actions import GuidedAction


@dataclass(frozen=True, slots=True)
class BulkOwner:
    owner_id: str
    label: str
    context_kind: str
    reason_codes: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.reason_codes


@dataclass(frozen=True, slots=True)
class BulkSelectionSnapshot:
    project_id: str
    project_revision: int
    action: GuidedAction
    action_label: str
    owners: tuple[BulkOwner, ...]
    fingerprint: str

    @property
    def valid(self) -> bool:
        return bool(self.owners) and all(owner.valid for owner in self.owners)


@dataclass(frozen=True, slots=True)
class BulkVariant:
    stable_identity: str
    label: str
    passport_key: str | None
    product_key: str | None
    resource_key: str
    selectable: bool
    existing_resource_count: int
    auto_creatable: bool
    preferred: bool
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BulkVariantQuery:
    action: GuidedAction
    action_label: str
    selection_fingerprint: str
    project_revision: int
    variants: tuple[BulkVariant, ...]
    status: str


@dataclass(frozen=True, slots=True)
class BulkMapping:
    owner_id: str
    owner_label: str
    instance_designation: str
    instance_state: str
    resource_labels: tuple[str, ...]
    change_summary: str
    canonical_fact_kind: str
    canonical_fact_count: int
    technical_resource_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BulkActionPreview:
    project_id: str
    project_revision: int
    action: GuidedAction
    action_label: str
    selected_owner_count: int
    chosen_variant_identity: str
    chosen_variant_label: str
    mappings: tuple[BulkMapping, ...]
    unavailable_owners: tuple[BulkOwner, ...]
    new_designations: tuple[str, ...]
    shortage_owner_count: int
    new_instance_count: int
    canonical_fact_count: int
    warnings: tuple[str, ...]
    conflicts: tuple[str, ...]
    fingerprint: str
    confirmation_token: str
    correlation_id: str

    @property
    def confirmable(self) -> bool:
        return (
            self.selected_owner_count > 0
            and not self.unavailable_owners
            and not self.conflicts
            and len(self.mappings) == self.selected_owner_count
        )


@dataclass(frozen=True, slots=True)
class BulkActionReceipt:
    receipt_id: str
    command_id: str
    action: GuidedAction
    action_label: str
    selected_owner_count: int
    new_designations: tuple[str, ...]
    canonical_fact_count: int
    project_revision_before: int
    project_revision_after: int
    result_status: str
    correlation_id: str
    preference_identity: str
    preference_updated: bool = False
    preference_diagnostic: str | None = None


class BulkActionError(RuntimeError):
    pass


class BulkConfirmationRequired(BulkActionError):
    pass


class BulkPlanBlocked(BulkActionError):
    pass


class StaleBulkPreview(BulkActionError):
    pass
