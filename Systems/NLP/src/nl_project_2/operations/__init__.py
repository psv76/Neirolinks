"""Operational services: background work, backups, logs and self-check."""

from .background import (
    BackgroundOperationManager,
    CancellationToken,
    OperationCancelled,
    OperationHandle,
    OperationResult,
    OperationSnapshot,
    StaleOperationResult,
)
from .backup import BackupError, BackupService, OperationalBackupReceipt, RetentionResult
from .diagnostics import StructuredLogger, create_diagnostic_directory, timed
from .profile import LastUsedPreference, LocalApplicationProfile
from .self_check import CheckResult, SelfCheckReport, SelfCheckService

__all__ = [
    "BackupError",
    "BackupService",
    "BackgroundOperationManager",
    "CancellationToken",
    "CheckResult",
    "LastUsedPreference",
    "LocalApplicationProfile",
    "OperationCancelled",
    "OperationHandle",
    "OperationResult",
    "OperationSnapshot",
    "OperationalBackupReceipt",
    "RetentionResult",
    "SelfCheckReport",
    "SelfCheckService",
    "StaleOperationResult",
    "StructuredLogger",
    "create_diagnostic_directory",
    "timed",
]
