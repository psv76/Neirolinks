"""Read-only operational self-check for the independent 2.0 application."""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from nl_project_2.config import PathConfig
from nl_project_2.persistence.migration import (
    HEAD_REVISION,
    MigrationError,
    current_revision_read_only,
)


@dataclass(frozen=True, slots=True)
class CheckResult:
    code: str
    status: str
    message: str


@dataclass(frozen=True, slots=True)
class SelfCheckReport:
    checks: tuple[CheckResult, ...]
    database_sha256_before: str
    database_sha256_after: str

    @property
    def ok(self) -> bool:
        return all(check.status == "PASS" for check in self.checks)


class SelfCheckService:
    def __init__(self, database_path: Path, paths: PathConfig) -> None:
        self.database_path = database_path.resolve()
        self.paths = paths

    def run(self) -> SelfCheckReport:
        before = _sha(self.database_path)
        checks = [self._paths(), self._schema()]
        try:
            with closing(
                sqlite3.connect(f"file:{self.database_path.as_posix()}?mode=ro", uri=True)
            ) as connection:
                checks.extend(
                    (
                        self._integrity(connection),
                        self._foreign_keys(connection),
                        self._catalog(connection),
                        self._instance_resources(connection),
                    )
                )
        except sqlite3.DatabaseError as exc:
            checks.append(CheckResult("DATABASE_OPEN", "FAIL", type(exc).__name__))
        after = _sha(self.database_path)
        checks.append(
            CheckResult(
                "READ_ONLY_INVARIANT",
                "PASS" if before == after else "FAIL",
                "Database bytes unchanged" if before == after else "Self-check changed database",
            )
        )
        return SelfCheckReport(tuple(checks), before, after)

    def _paths(self) -> CheckResult:
        candidates = (
            self.database_path,
            self.paths.backup_root.resolve(),
            self.paths.local_state_root.resolve(),
            self.paths.user_projects_root.resolve(),
        )
        forbidden = Path("D:/NLP").resolve()
        unsafe = [path for path in candidates if _is_within(path, forbidden)]
        return CheckResult(
            "PATH_ISOLATION",
            "FAIL" if unsafe else "PASS",
            "No operational path uses D:/NLP" if not unsafe else "Forbidden legacy path",
        )

    def _schema(self) -> CheckResult:
        try:
            revision = current_revision_read_only(self.database_path)
        except MigrationError as exc:
            return CheckResult("SCHEMA_REVISION", "FAIL", type(exc).__name__)
        return CheckResult(
            "SCHEMA_REVISION",
            "PASS" if revision == HEAD_REVISION else "FAIL",
            f"schema={revision}; expected={HEAD_REVISION}",
        )

    @staticmethod
    def _integrity(connection) -> CheckResult:
        value = connection.execute("PRAGMA integrity_check").fetchone()
        return CheckResult("SQLITE_INTEGRITY", "PASS" if value == ("ok",) else "FAIL", str(value))

    @staticmethod
    def _foreign_keys(connection) -> CheckResult:
        rows = connection.execute("PRAGMA foreign_key_check").fetchall()
        return CheckResult(
            "FOREIGN_KEYS",
            "PASS" if not rows else "FAIL",
            "No FK violations" if not rows else f"{len(rows)} FK violation(s)",
        )

    @staticmethod
    def _catalog(connection) -> CheckResult:
        passports = connection.execute(
            "SELECT COUNT(*) FROM passport_definition WHERE lifecycle='ACTIVE'"
        ).fetchone()[0]
        products = connection.execute(
            "SELECT COUNT(*) FROM product_definition WHERE lifecycle='ACTIVE'"
        ).fetchone()[0]
        ok = (passports, products) == (18, 31)
        return CheckResult(
            "CATALOG_18_31",
            "PASS" if ok else "FAIL",
            f"passports={passports}; products={products}",
        )

    @staticmethod
    def _instance_resources(connection) -> CheckResult:
        missing = connection.execute(
            """
            SELECT COUNT(*)
            FROM project_instance i
            JOIN passport_resource_definition d
              ON d.passport_definition_id=i.passport_definition_id
            LEFT JOIN instance_resource r
              ON r.project_instance_id=i.id
             AND r.passport_resource_definition_id=d.id
             AND r.active=1
            WHERE i.lifecycle='ACTIVE' AND r.id IS NULL
            """
        ).fetchone()[0]
        return CheckResult(
            "INSTANCE_RESOURCES",
            "PASS" if missing == 0 else "FAIL",
            "All active instances have passport resources"
            if missing == 0
            else f"{missing} missing materialized resource(s)",
        )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
