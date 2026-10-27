"""Guarded live release of nullable Project-owned BUS display_name schema rev18.

Must be run only after verifying all GUI NLP/Python processes are closed.
Usage:
  .venv\\Scripts\\python.exe tools\\apply_nlp32_bus_display_name.py ^
     --database D:\\NL_Project_3_Data\\Projects\\nl_project_3.sqlite ^
     --backup-root D:\\NLP_3_BACKUPS ^
     --expected-sha256 <exact 64-char digest from immediate preflight>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

from nl_project_2.buses import BusService
from nl_project_2.persistence.database import DatabaseManager
from nl_project_2.persistence.migration import (
    HEAD_REVISION, TRANSIT_LINE_COMMIT_REVISION,
    current_revision_read_only, upgrade_database,
)

TABLES = (
    "project", "board", "building", "room", "bus", "bus_endpoint",
    "bus_segment", "field_device", "cable_line", "cable_segment",
    "conduit", "conduit_segment_assignment", "project_instance",
    "instance_resource", "functional_relation",
)


def read_counts(path: Path) -> dict[str, int]:
    with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as c:
        return {name: int(c.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0])
                for name in TABLES}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--backup-root", required=True, type=Path)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args()
    dbpath = args.database.resolve()
    if not dbpath.is_file() or args.expected_sha256.lower() != hashlib.sha256(
        dbpath.read_bytes()
    ).hexdigest().lower():
        raise RuntimeError("WORKING_DB_SHA_MISMATCH: no changes performed")
    previous = current_revision_read_only(dbpath)
    if previous != TRANSIT_LINE_COMMIT_REVISION:
        raise RuntimeError(f"Expected revision 17, got {previous}; no changes performed")
    before = read_counts(dbpath)
    folder = args.backup_root.resolve() / (
        "nlp32_bus_title_schema18_" + datetime.now().strftime("%Y%m%dT%H%M%S%f")
    )
    receipt = upgrade_database(dbpath, folder)
    if not receipt.path.is_file() or receipt.source_revision != previous:
        raise RuntimeError("Verified backup missing or unexpected revision")
    if current_revision_read_only(dbpath) != HEAD_REVISION:
        raise RuntimeError("Schema head after upgrade is not current")
    after = read_counts(dbpath)
    if before != after:
        raise RuntimeError(f"Row counts changed: before={before}, after={after}")
    with sqlite3.connect(f"file:{dbpath.as_posix()}?mode=ro", uri=True) as con:
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("SQLite integrity check failed after migration")
        if con.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("SQLite foreign key check failed after migration")
        if "display_name" not in {r[1] for r in con.execute("pragma table_info(bus)")}:
            raise RuntimeError("New bus.display_name missing after migration")
    db = DatabaseManager().open_existing(dbpath)
    try:
        with db.engine.connect() as connection:
            project_ids = connection.execute(text("select id from project")).scalars().all()
        bus_svc = BusService(db.engine)
        bus_count = sum(len(bus_svc.journal_cards(pid)) for pid in project_ids)
        if bus_count != after["bus"]:
            raise RuntimeError(f"Bus runtime count={bus_count}, SQL count={after['bus']}")
        for project_id in project_ids:
            for card in bus_svc.journal_cards(project_id):
                if card.get("room_names") and not card.get("room_markers"):
                    print("WARNING: no canonical colored room markers:", card["designation"])
    finally:
        db.close()
    result = {
        "status": "PASS", "database": str(dbpath),
        "previous_schema": previous, "new_schema": HEAD_REVISION,
        "backup": str(receipt.path), "backup_sha256": receipt.sha256,
        "rows_preserved": before, "bus_count": bus_count,
        "integrity_check": "ok", "foreign_key_errors": 0,
        "live_dwg_modified": False,
    }
    (folder / "migration_receipt.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
