"""Explicit offline maintenance entry point for equipment-catalog reconciliation."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if not (PROJECT_ROOT / "src" / "nl_project_2").exists():
    PROJECT_ROOT = Path.cwd().resolve()
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from nl_project_2.catalog.installer import CatalogInstaller  # noqa: E402
from nl_project_2.catalog.payload import load_payload  # noqa: E402
from nl_project_2.persistence.database import DatabaseManager  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_exclusive_access(path: Path) -> None:
    connection = sqlite3.connect(path, timeout=0)
    try:
        connection.execute("BEGIN EXCLUSIVE")
        connection.rollback()
    except sqlite3.OperationalError as exc:
        raise RuntimeError(
            "Database is busy; close NL Project before catalog reconciliation"
        ) from exc
    finally:
        connection.close()


def reconcile_database(
    *,
    database_path: Path,
    catalog_directory: Path,
    backup_path: Path,
    expected_database_sha256: str,
) -> dict:
    database = database_path.resolve()
    catalog = catalog_directory.resolve()
    backup = backup_path.resolve()
    if not database.is_file():
        raise FileNotFoundError(database)
    if backup.exists():
        raise FileExistsError(f"Backup target already exists: {backup}")
    expected = expected_database_sha256.strip().lower()
    actual = _sha256(database)
    if actual != expected:
        raise RuntimeError(f"Database SHA-256 changed: expected {expected}, actual {actual}")

    payload = load_payload(catalog)
    _require_exclusive_access(database)
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(database, backup)
    backup_sha256 = _sha256(backup)
    if backup_sha256 != actual:
        raise RuntimeError("Verified backup hash does not match the source database")

    handle = DatabaseManager().open_existing(database)
    try:
        receipt = CatalogInstaller(handle.engine).reconcile_active(payload)
    finally:
        handle.close()
    with sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
    if integrity != "ok" or foreign_key_errors:
        raise RuntimeError(
            f"Post-reconciliation SQLite check failed: {integrity}, "
            f"foreign_key_errors={len(foreign_key_errors)}"
        )
    return {
        "database": str(database),
        "database_sha256_before": actual,
        "database_sha256_after": _sha256(database),
        "backup": str(backup),
        "backup_sha256": backup_sha256,
        "release_id": receipt.release_id,
        "previous_release_code": receipt.previous_release_code,
        "release_code": receipt.release_code,
        "content_sha256": receipt.content_sha256,
        "changed_passport_count": receipt.changed_passport_count,
        "refreshed_resource_count": receipt.refreshed_resource_count,
        "already_current": receipt.already_current,
        "sqlite_integrity": integrity,
        "foreign_key_errors": len(foreign_key_errors),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile an offline NL Project equipment catalog after a verified backup"
    )
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--backup", required=True, type=Path)
    parser.add_argument("--expected-database-sha256", required=True)
    parser.add_argument(
        "--confirm-project-closed",
        action="store_true",
        help="Required acknowledgement that NL Project is closed",
    )
    args = parser.parse_args(argv)
    if not args.confirm_project_closed:
        parser.error("--confirm-project-closed is required")
    result = reconcile_database(
        database_path=args.database,
        catalog_directory=args.catalog,
        backup_path=args.backup,
        expected_database_sha256=args.expected_database_sha256,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
