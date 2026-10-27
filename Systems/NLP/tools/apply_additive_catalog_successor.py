"""Apply one approved additive equipment catalog successor to a CLOSED NLP 3.1 database.

Verified SQLite backup, schema-head guard, predecessor check, atomic installer and
post-install startup/readback smoke. Never auto-restore a backup over a live database.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nl_project_2.catalog.installer import CatalogInstaller  # noqa: E402
from nl_project_2.catalog.payload import load_payload  # noqa: E402
from nl_project_2.catalog.validation import validate_payload  # noqa: E402
from nl_project_2.constructor import ConstructorService  # noqa: E402
from nl_project_2.buses import BusService  # noqa: E402
from nl_project_2.persistence.database import DatabaseManager  # noqa: E402
from nl_project_2.persistence.migration import (  # noqa: E402
    HEAD_REVISION, create_verified_backup, current_revision_read_only,
)
from nl_project_2.persistence.schema import (  # noqa: E402
    bus, catalog_release, functional_relation, instance_resource, passport_definition,
    product_definition, project, project_instance,
)
from sqlalchemy import func, select  # noqa: E402


def require_app_closed() -> None:
    if sys.platform != "win32":
        raise RuntimeError("Production catalog installation requires Windows process verification")
    script = (
        "Get-CimInstance Win32_Process | Where-Object {"
        " ($_.Name -eq 'python.exe' -or $_.Name -eq 'pythonw.exe')"
        " -and $_.CommandLine -like '*-m nl_project_2*'"
        " } | Select-Object -ExpandProperty ProcessId"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, check=True,
    )
    active = [line for line in result.stdout.splitlines() if line.strip().isdigit()]
    if active:
        raise RuntimeError(
            "NL Project is running; close ALL application instances before catalog install: "
            + ", ".join(active)
        )


def fingerprint(connection) -> dict:
    return {
        name: set(connection.execute(select(table.c.id)).scalars())
        for name, table in {
            "project": project, "project_instance": project_instance,
            "instance_resource": instance_resource,
            "functional_relation": functional_relation, "bus": bus,
        }.items()
    }


def check_integrity(db_path: Path) -> None:
    with sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True) as conn:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("SQLite integrity_check failed")
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("SQLite foreign_key_check failed")


def apply_successor(database: Path, catalog: Path, backup_root: Path, expected_sha: str) -> dict:
    require_app_closed()
    database = database.resolve()
    catalog = catalog.resolve()
    if not database.is_file():
        raise FileNotFoundError(database)
    payload = load_payload(catalog)
    validate_payload(payload)
    if current_revision_read_only(database) != HEAD_REVISION:
        raise RuntimeError("Schema head mismatch; run the official verified migration API first")

    # A database selected before approval must not be replaced silently.
    digest = hashlib.sha256(database.read_bytes()).hexdigest()
    if digest != expected_sha:
        raise RuntimeError("Database SHA-256 differs from approved snapshot")

    check_integrity(database)
    connection = sqlite3.connect(database, timeout=0)
    try:
        connection.execute("BEGIN EXCLUSIVE")
        connection.rollback()
    finally:
        connection.close()

    handle = DatabaseManager().open_existing(database)
    try:
        with handle.engine.connect() as conn:
            before = fingerprint(conn)
            prior = conn.execute(
                select(catalog_release.c.release_code).where(
                    catalog_release.c.status == "ACTIVE"
                )
            ).scalar_one()
    finally:
        handle.close()

    if prior not in (payload.manifest.get("additive_predecessors") or {}):
        raise RuntimeError(f"Active release {prior!r} is not an approved additive predecessor")

    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    directory = backup_root.resolve() / f"issue293_wbe2_successor_{stamp}"
    if directory.exists():
        raise FileExistsError(directory)
    verified = create_verified_backup(database, directory)
    if hashlib.sha256(database.read_bytes()).hexdigest() != digest:
        raise RuntimeError("Working database changed after backup; abort without installing")

    handle = DatabaseManager().open_existing(database)
    try:
        receipt = CatalogInstaller(handle.engine).install(payload)
    finally:
        handle.close()
    check_integrity(database)

    handle = DatabaseManager().open_existing(database)
    try:
        with handle.engine.connect() as conn:
            after = fingerprint(conn)
            if before != after:
                raise RuntimeError("Existing Project/instance/resource/relation/bus identities changed")
            live = conn.execute(
                select(catalog_release.c.release_code, catalog_release.c.content_sha256)
                .where(catalog_release.c.status == "ACTIVE")
            ).one()
            if (live.release_code, live.content_sha256) != (
                payload.manifest["release_code"], payload.content_sha256
            ):
                raise RuntimeError("Installed release hash/readback mismatch")
            if conn.scalar(select(func.count()).select_from(passport_definition)) != payload.manifest["expected_counts"]["passports"]:
                raise RuntimeError("Passport count mismatch")
            if conn.scalar(select(func.count()).select_from(product_definition)) != payload.manifest["expected_counts"]["products"]:
                raise RuntimeError("Product count mismatch")
        for p in before["project"]:
            service = ConstructorService(handle.engine)
            if not any(
                x["passport_key"] == "module.wirenboard.wbe2_i_rs485_iso"
                for x in service.list_available_passports(p)
            ):
                raise RuntimeError("New passport is missing from Constructor selector")
            service.list_resources(p)
            BusService(handle.engine).list_buses(p)
        if not CatalogInstaller(handle.engine).install(payload).already_installed:
            raise RuntimeError("Idempotency smoke failed")
    finally:
        handle.close()
    report = {
        "status": "PASS",
        "database": str(database),
        "previous_release": prior,
        "new_release": receipt.release_code,
        "schema_head": HEAD_REVISION,
        "backup": str(verified.path),
        "backup_sha256": verified.sha256,
        "new_content_sha256": payload.content_sha256,
        "existing_records_preserved": True,
        "sqlite_integrity": "ok",
    }
    (directory / "release_receipt.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=ROOT / "resources/catalogs")
    parser.add_argument("--backup-root", type=Path, required=True)
    parser.add_argument("--expected-database-sha256", required=True)
    parser.add_argument("--confirm-project-closed", action="store_true")
    args = parser.parse_args()
    if not args.confirm_project_closed:
        parser.error("--confirm-project-closed is required")
    result = apply_successor(
        args.database, args.catalog, args.backup_root, args.expected_database_sha256
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
