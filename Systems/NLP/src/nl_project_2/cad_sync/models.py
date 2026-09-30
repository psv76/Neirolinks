"""Immutable DTOs for previewing and applying DWG synchronization."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from nl_project_2.cad_contract import CadObservationBatch, ValidationIssue


class ChangeClass(StrEnum):
    EQUAL = "EQUAL"
    DWG_CHANGED = "DWG_CHANGED"
    PROJECT_CHANGED = "PROJECT_CHANGED"
    BOTH_CHANGED_CONFLICT = "BOTH_CHANGED_CONFLICT"
    NEW_DWG_INSERTION = "NEW_DWG_INSERTION"
    MISSING_DWG_INSERTION = "MISSING_DWG_INSERTION"
    IDENTITY_COLLISION = "IDENTITY_COLLISION"
    INVALID_DWG_DATA = "INVALID_DWG_DATA"


class SyncOwnerKind(StrEnum):
    INSERTION = "INSERTION"
    BASE_LINE = "BASE_LINE"
    TOPOLOGY_POINT = "TOPOLOGY_POINT"
    SEGMENT = "SEGMENT"
    CONTROL_KEY = "CONTROL_KEY"
    TOPOLOGY_OUTPUT = "TOPOLOGY_OUTPUT"
    FIELD_PORT = "FIELD_PORT"


@dataclass(frozen=True, slots=True)
class DwgScanProgress:
    stage: str
    processed: int | None = None
    total: int | None = None


@dataclass(frozen=True, slots=True)
class SyncChange:
    field_path: str
    handle: str
    field: str
    baseline_value: Any
    project_value: Any
    dwg_value: Any
    change_class: ChangeClass
    reason: str
    owner_kind: SyncOwnerKind = SyncOwnerKind.INSERTION
    owner_key: str = ""
    owner_path: str = ""
    affected_handles: tuple[str, ...] = ()
    structural: bool = False
    detail_status: str = ""
    display_context: dict[str, str] = field(default_factory=dict, compare=False)


@dataclass(frozen=True, slots=True)
class SyncSummary:
    new: int = 0
    changed: int = 0
    missing: int = 0
    invalid: int = 0
    conflicts: int = 0


@dataclass(frozen=True, slots=True)
class ScanProposal:
    project_id: str
    batch: CadObservationBatch
    changes: tuple[SyncChange, ...]
    issues: tuple[ValidationIssue, ...]
    summary: SyncSummary
    project_revision: int
    binding_id: str | None

    @property
    def can_apply(self) -> bool:
        return not any(issue.blocks_acceptance for issue in self.issues)


@dataclass(frozen=True, slots=True)
class WriteResult:
    document_identity: str
    readback: tuple[dict[str, str], ...]
    no_save_confirmed: bool
    document_saved: bool
    status: str = "READ_BACK_OK"
    failures: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class DwgWriteTarget:
    document_identity: str
    handle: str
    tag: str
    expected_old_value: str
    new_value: str
    expected_block_name: str
    expected_layer: str
    owner_kind: SyncOwnerKind
    owner_key: str
    owner_path: str
    reason: str

    def bridge_command(self) -> dict[str, str]:
        return {
            "handle": self.handle,
            "tag": self.tag,
            "old_value": self.expected_old_value,
            "new_value": self.new_value,
            "expected_block_name": self.expected_block_name,
            "expected_layer": self.expected_layer,
        }


@dataclass(frozen=True, slots=True)
class DwgWritePlan:
    plan_id: str
    correlation_id: str
    project_id: str
    binding_id: str
    document_identity: str
    project_revision: int
    selected_paths: tuple[str, ...]
    targets: tuple[DwgWriteTarget, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class WriteExecutionReceipt:
    plan_id: str
    correlation_id: str
    status: str
    completed_targets: tuple[tuple[str, str], ...]
    failed_targets: tuple[dict[str, str], ...]
    no_save_confirmed: bool
    document_saved: bool
    result: WriteResult | None = field(default=None, compare=False)
