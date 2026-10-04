"""DWG synchronization application service and isolated bridge adapter."""

from .bridge import ActiveDocumentInfo, AutoCadBridgeClient, BridgeError, BridgeTimeout
from .models import (
    ChangeClass,
    DwgWritePlan,
    DwgWriteTarget,
    ScanProposal,
    SyncChange,
    SyncOwnerKind,
    SyncSummary,
    WriteExecutionReceipt,
    WriteResult,
)
from .selection import AtomicLineImportGroup, atomic_line_import_groups
from .service import DwgSyncError, DwgSyncService
from .workflow import DwgUpdatePlan, build_dwg_update_plan

__all__ = [
    "ActiveDocumentInfo",
    "AutoCadBridgeClient",
    "BridgeError",
    "BridgeTimeout",
    "ChangeClass",
    "DwgWritePlan",
    "DwgWriteTarget",
    "DwgSyncError",
    "DwgSyncService",
    "ScanProposal",
    "SyncChange",
    "SyncOwnerKind",
    "SyncSummary",
    "WriteResult",
    "WriteExecutionReceipt",
    "AtomicLineImportGroup",
    "atomic_line_import_groups",
    "DwgUpdatePlan",
    "build_dwg_update_plan",
]
