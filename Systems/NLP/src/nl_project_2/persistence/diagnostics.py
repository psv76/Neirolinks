"""Read-only structure and integrity diagnostics for a project database."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

from nl_project_2.persistence.migration import HEAD_REVISION, current_revision_read_only
from nl_project_2.persistence.schema import HEAD_TABLE_NAMES


@dataclass(frozen=True)
class DatabaseDiagnostic:
    path: str
    revision: str | None
    expected_revision: str
    integrity_check: tuple[str, ...]
    foreign_key_violations: tuple[tuple[object, ...], ...]
    missing_tables: tuple[str, ...]
    unexpected_tables: tuple[str, ...]
    ok: bool

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def inspect_database(path: str | Path) -> DatabaseDiagnostic:
    resolved = Path(path).resolve()
    revision = current_revision_read_only(resolved)
    expected_tables = set(HEAD_TABLE_NAMES) | {"alembic_version"}
    uri = f"file:{resolved.as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        table_rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        integrity = tuple(row[0] for row in connection.execute("PRAGMA integrity_check"))
        foreign_keys = tuple(tuple(row) for row in connection.execute("PRAGMA foreign_key_check"))
    actual_tables = {str(row[0]) for row in table_rows}
    missing = tuple(sorted(expected_tables - actual_tables))
    unexpected = tuple(sorted(actual_tables - expected_tables))
    ok = (
        revision == HEAD_REVISION
        and integrity == ("ok",)
        and not foreign_keys
        and not missing
        and not unexpected
    )
    return DatabaseDiagnostic(
        path=str(resolved),
        revision=revision,
        expected_revision=HEAD_REVISION,
        integrity_check=integrity,
        foreign_key_violations=foreign_keys,
        missing_tables=missing,
        unexpected_tables=unexpected,
        ok=ok,
    )
