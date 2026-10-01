"""Verified SQLite backup, restore and ADR-007 retention policy."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from nl_project_2.persistence.migration import current_revision_read_only


class BackupError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class OperationalBackupReceipt:
    path: Path
    kind: str
    sha256: str
    source_revision: str
    created: bool = True


@dataclass(frozen=True, slots=True)
class RetentionResult:
    kept: tuple[Path, ...]
    deleted: tuple[Path, ...]


_BACKUP_RE = re.compile(
    r"^(?P<stem>.+)\.(?P<kind>daily|manual|pre_migration)\."
    r"(?P<stamp>\d{8}T\d{12}Z)\.[0-9a-f]{8}\.sqlite$"
)


class BackupService:
    def __init__(self, root: Path, *, clock=None) -> None:
        self.root = root.resolve()
        self.clock = clock or (lambda: datetime.now(UTC))

    def create_daily_if_changed(
        self, source: Path, *, opening_sha256: str
    ) -> OperationalBackupReceipt | None:
        source = source.resolve()
        if _sha(source) == opening_sha256:
            return None
        today = self.clock().astimezone(UTC).date()
        existing = [
            path for path, stamp in self._dated("daily", source.stem) if stamp.date() == today
        ]
        if existing:
            path = max(existing)
            return self._receipt(path, "DAILY", created=False)
        receipt = self._create(source, "DAILY")
        self.apply_retention(source.stem)
        return receipt

    def create_manual(self, source: Path) -> OperationalBackupReceipt:
        return self._create(source.resolve(), "MANUAL")

    def create_pre_migration(self, source: Path) -> OperationalBackupReceipt:
        return self._create(source.resolve(), "PRE_MIGRATION")

    def restore_to(self, backup: Path, target: Path) -> OperationalBackupReceipt:
        backup = backup.resolve()
        target = target.resolve()
        if target.exists():
            raise BackupError(f"Restore target already exists: {target}")
        revision = _verify_sqlite(backup)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with sqlite3.connect(f"file:{backup.as_posix()}?mode=ro", uri=True) as source:
                with sqlite3.connect(target) as destination:
                    source.backup(destination)
            restored_revision = _verify_sqlite(target)
            if restored_revision != revision:
                raise BackupError("Restored schema revision differs from backup")
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return OperationalBackupReceipt(target, "RESTORE", _sha(target), restored_revision, True)

    def apply_retention(self, source_stem: str) -> RetentionResult:
        dated = self._dated("daily", source_stem)
        by_day = _newest_by(dated, lambda stamp: stamp.date())
        by_week = _newest_by(dated, lambda stamp: stamp.isocalendar()[:2])
        by_month = _newest_by(dated, lambda stamp: (stamp.year, stamp.month))
        keep = {
            path for path, _stamp in sorted(by_day, key=lambda pair: pair[1], reverse=True)[:14]
        }
        keep.update(
            path for path, _stamp in sorted(by_week, key=lambda pair: pair[1], reverse=True)[:8]
        )
        keep.update(
            path for path, _stamp in sorted(by_month, key=lambda pair: pair[1], reverse=True)[:12]
        )
        deleted = []
        for path, _stamp in dated:
            if path not in keep:
                path.unlink()
                deleted.append(path)
        return RetentionResult(tuple(sorted(keep)), tuple(sorted(deleted)))

    def _create(self, source: Path, kind: str) -> OperationalBackupReceipt:
        revision = _verify_sqlite(source)
        now = self.clock().astimezone(UTC)
        stamp = now.strftime("%Y%m%dT%H%M%S%fZ")
        directory = self.root / kind.lower()
        directory.mkdir(parents=True, exist_ok=True)
        source_digest = _sha(source)
        target = directory / (f"{source.stem}.{kind.lower()}.{stamp}.{source_digest[:8]}.sqlite")
        if target.exists():
            raise BackupError(f"Backup target already exists: {target}")
        try:
            with sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True) as source_db:
                with sqlite3.connect(target) as target_db:
                    source_db.backup(target_db)
            copied_revision = _verify_sqlite(target)
        except Exception as exc:
            target.unlink(missing_ok=True)
            raise BackupError("SQLite backup or verification failed") from exc
        if copied_revision != revision:
            target.unlink(missing_ok=True)
            raise BackupError("Backup schema revision mismatch")
        return OperationalBackupReceipt(target, kind, _sha(target), revision, True)

    def _receipt(self, path: Path, kind: str, *, created: bool):
        return OperationalBackupReceipt(path, kind, _sha(path), _verify_sqlite(path), created)

    def _dated(self, kind: str, source_stem: str) -> list[tuple[Path, datetime]]:
        directory = self.root / kind
        if not directory.exists():
            return []
        result = []
        for path in directory.glob(f"{source_stem}.{kind}.*.sqlite"):
            match = _BACKUP_RE.match(path.name)
            if match is None:
                continue
            stamp = datetime.strptime(match.group("stamp"), "%Y%m%dT%H%M%S%fZ").replace(tzinfo=UTC)
            result.append((path, stamp))
        return result


def _newest_by(dated, key):
    selected = {}
    for path, stamp in dated:
        bucket = key(stamp)
        if bucket not in selected or stamp > selected[bucket][1]:
            selected[bucket] = (path, stamp)
    return list(selected.values())


def _verify_sqlite(path: Path) -> str:
    if not path.is_file():
        raise BackupError(f"SQLite file not found: {path}")
    try:
        with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
    except sqlite3.DatabaseError as exc:
        raise BackupError(f"Invalid SQLite backup: {path}") from exc
    revision = current_revision_read_only(path)
    if integrity != ("ok",) or foreign_keys or revision is None:
        raise BackupError("Backup integrity, foreign keys or schema revision failed")
    return revision


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
