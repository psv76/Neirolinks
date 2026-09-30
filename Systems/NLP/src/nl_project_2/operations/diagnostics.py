"""Redacted structured logs and non-archive diagnostic package."""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

SENSITIVE_KEYS = frozenset({"name", "address", "customer", "path", "notes", "payload"})


class StructuredLogger:
    def __init__(self, log_path: Path, *, max_bytes: int = 2_000_000, backups: int = 5):
        self.log_path = log_path
        self.max_bytes = max_bytes
        self.backups = backups

    def record(
        self,
        *,
        level: str,
        component: str,
        operation: str,
        result: str,
        duration_ms: int,
        correlation_id: str | None = None,
        error: Exception | None = None,
        summary: dict | None = None,
    ) -> dict:
        event = {
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "level": level,
            "component": component,
            "operation": operation,
            "correlation_id": correlation_id or str(uuid.uuid4()),
            "result": result,
            "duration_ms": duration_ms,
            "error_category": None if error is None else type(error).__name__,
            "summary": _redact(summary or {}),
        }
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        encoded = (json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n").encode(
            "utf-8"
        )
        self._rotate(len(encoded))
        with self.log_path.open("ab") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        return event

    def _rotate(self, incoming: int) -> None:
        if not self.log_path.exists() or self.log_path.stat().st_size + incoming <= self.max_bytes:
            return
        oldest = self.log_path.with_suffix(self.log_path.suffix + f".{self.backups}")
        oldest.unlink(missing_ok=True)
        for index in range(self.backups - 1, 0, -1):
            source = self.log_path.with_suffix(self.log_path.suffix + f".{index}")
            if source.exists():
                os.replace(
                    source,
                    self.log_path.with_suffix(self.log_path.suffix + f".{index + 1}"),
                )
        os.replace(self.log_path, self.log_path.with_suffix(self.log_path.suffix + ".1"))


def create_diagnostic_directory(
    root: Path, *, self_check, recent_events: tuple[dict, ...] = ()
) -> Path:
    """Create a redacted directory, deliberately not a ZIP/task archive."""
    target = root / datetime.now(UTC).strftime("diagnostic-%Y%m%dT%H%M%SZ")
    target.mkdir(parents=True, exist_ok=False)
    payload = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "self_check": [
            {"code": row.code, "status": row.status, "message": row.message}
            for row in self_check.checks
        ],
        "recent_events": [_redact(event) for event in recent_events[-100:]],
    }
    (target / "diagnostics.json").write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    return target


def timed(logger: StructuredLogger, *, component: str, operation: str):
    def decorate(function):
        def wrapper(*args, **kwargs):
            started = perf_counter()
            correlation = str(uuid.uuid4())
            try:
                value = function(*args, **kwargs)
            except Exception as exc:
                logger.record(
                    level="ERROR",
                    component=component,
                    operation=operation,
                    correlation_id=correlation,
                    result="failed",
                    duration_ms=int((perf_counter() - started) * 1000),
                    error=exc,
                )
                raise
            logger.record(
                level="INFO",
                component=component,
                operation=operation,
                correlation_id=correlation,
                result="succeeded",
                duration_ms=int((perf_counter() - started) * 1000),
            )
            return value

        return wrapper

    return decorate


def _redact(value):
    if isinstance(value, dict):
        return {
            str(key): "<redacted>" if str(key).casefold() in SENSITIVE_KEYS else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value
