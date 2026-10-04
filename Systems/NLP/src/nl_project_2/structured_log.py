"""Small structured startup logger owned by the 3.0 application."""

from __future__ import annotations

from pathlib import Path

from nl_project_2.config import PathConfig, ensure_operational_directories
from nl_project_2.operations.diagnostics import StructuredLogger


def record_fatal_startup(error: Exception, paths: PathConfig) -> Path:
    ensure_operational_directories(paths)
    target = paths.log_root / "fatal-startup.jsonl"
    StructuredLogger(target).record(
        level="FATAL",
        component="app_shell",
        operation="startup",
        result="failed",
        duration_ms=0,
        error=error,
    )
    return target
