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


def show_fatal_startup(error: Exception, log_path: Path) -> None:
    """Report startup failures even when launched with invisible pythonw.exe.

    The Windows native dialog is independent of Qt initialization and the
    availability of a console. The same information goes to stderr elsewhere.
    """
    import sys

    message = (
        "NL Project не удалось запустить.\n\n"
        f"Причина: {type(error).__name__}: {error}\n\n"
        f"Журнал диагностики: {log_path}\n\n"
        "Инженерная база не была сброшена. "
        "Перед повторным запуском проверьте сообщение и журнал."
    )
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                None, message, "NL Project — ошибка запуска", 0x00000010
            )
            return
        except Exception:
            pass
    print(message, file=sys.stderr)
