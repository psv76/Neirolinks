"""Controlled 2.0 -> 3.0 clean-seed cutover helpers."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from nl_project_2.catalog.installer import CatalogInstaller
from nl_project_2.catalog.payload import load_packaged_payload
from nl_project_2.objects.models import ProjectCard
from nl_project_2.objects.service import SETTING_KEYS, ObjectService
from nl_project_2.persistence.database import DatabaseManager
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.migration import HEAD_REVISION, current_revision_read_only
from nl_project_2.persistence.schema import project_setting

FORBIDDEN_WORKING_TABLES = (
    "field_device",
    "field_port",
    "field_device_product_selection",
    "cable_line",
    "cable_point",
    "cable_point_field_device",
    "cable_topology_endpoint",
    "cable_segment",
    "conduit",
    "cable_segment_conduit",
    "bus",
    "bus_point",
    "bus_segment",
    "dwg_document_binding",
    "dwg_scan",
    "dwg_observation",
    "dwg_baseline",
)


class CleanSeedError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CleanSeedReceipt:
    legacy_database: str
    legacy_sha256: str
    legacy_revision: str
    legacy_snapshot: str
    legacy_snapshot_sha256: str
    target_database: str
    target_sha256: str
    target_revision: str
    project_count: int
    building_count: int
    room_count: int
    copied_setting_keys: tuple[str, ...]
    source_excluded_counts: dict[str, int]
    target_forbidden_counts: dict[str, int]

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def create_clean_seed(
    *,
    legacy_database: Path,
    target_database: Path,
    legacy_snapshot_root: Path,
    copied_setting_keys: tuple[str, ...] = (),
    clock=None,
) -> CleanSeedReceipt:
    legacy_database = legacy_database.resolve()
    target_database = target_database.resolve()
    legacy_snapshot_root = legacy_snapshot_root.resolve()
    if not legacy_database.is_file():
        raise CleanSeedError(f"Legacy database not found: {legacy_database}")
    if target_database.exists():
        raise CleanSeedError(f"Target database already exists: {target_database}")
    unknown_settings = sorted(set(copied_setting_keys) - set(SETTING_KEYS))
    if unknown_settings:
        raise CleanSeedError(f"Unknown project setting keys: {', '.join(unknown_settings)}")

    legacy_revision = _verify_database(legacy_database)
    legacy_sha256 = _sha256(legacy_database)
    snapshot = _create_immutable_snapshot(
        legacy_database,
        legacy_snapshot_root,
        clock=clock,
    )
    source = _read_seed(legacy_database, copied_setting_keys)
    source_excluded_counts = _table_counts(legacy_database, FORBIDDEN_WORKING_TABLES)

    database = DatabaseManager().initialize_new(target_database)
    try:
        CatalogInstaller(database.engine).install(load_packaged_payload())
        objects = ObjectService(database.engine)
        project_map: dict[str, str] = {}
        building_map: dict[str, str] = {}

        for source_project in source["projects"]:
            card_fields = _json_value(source_project["card_fields_json"]) or {}
            area = card_fields.get("total_area_m2")
            card = ProjectCard(
                name=source_project["name"],
                project_code=source_project["project_code"],
                object_type=card_fields.get("object_type", ""),
                address=card_fields.get("address", ""),
                total_area_m2=None if area in (None, "") else Decimal(str(area)),
                customer=card_fields.get("customer", ""),
                responsible_designer=card_fields.get("responsible_designer", ""),
                note=card_fields.get("note", ""),
            )
            project_map[source_project["id"]] = objects.create_project(card)

        for source_building in source["buildings"]:
            target_project_id = project_map[source_building["project_id"]]
            target_building_id = objects.add_building(target_project_id, source_building["name"])
            building_map[source_building["id"]] = target_building_id

        for source_room in source["rooms"]:
            display = _json_value(source_room["display_json"]) or {}
            color = str(display.get("marking_color") or "#EEF0F2")
            objects.add_room(
                project_id=project_map[source_room["project_id"]],
                building_id=building_map[source_room["building_id"]],
                name=source_room["name"],
                base_mark_mm=source_room["base_mark"],
                height_m=source_room["height_m_decimal"],
                marking_color=color,
            )

        if source["settings"]:
            with database.engine.begin() as connection:
                for setting in source["settings"]:
                    connection.execute(
                        project_setting.insert().values(
                            id=new_id(),
                            project_id=project_map[setting["project_id"]],
                            setting_key=setting["setting_key"],
                            value_type=setting["value_type"],
                            value_json=_json_value(setting["value_json"]),
                        )
                    )
    except Exception:
        database.close()
        target_database.unlink(missing_ok=True)
        raise
    database.close()

    target_revision = _verify_database(target_database)
    if target_revision != HEAD_REVISION:
        target_database.unlink(missing_ok=True)
        raise CleanSeedError(
            f"Clean target revision {target_revision} does not match current head {HEAD_REVISION}"
        )

    target_forbidden_counts = _table_counts(target_database, FORBIDDEN_WORKING_TABLES)
    non_empty = {key: value for key, value in target_forbidden_counts.items() if value}
    if non_empty:
        target_database.unlink(missing_ok=True)
        raise CleanSeedError(f"Forbidden working state leaked into clean database: {non_empty}")

    with closing(
        sqlite3.connect(f"file:{target_database.as_posix()}?mode=ro", uri=True)
    ) as connection:
        project_count = connection.execute("SELECT COUNT(*) FROM project").fetchone()[0]
        building_count = connection.execute("SELECT COUNT(*) FROM building").fetchone()[0]
        room_count = connection.execute("SELECT COUNT(*) FROM room").fetchone()[0]

    reopened = DatabaseManager().open_existing(target_database)
    try:
        ObjectService(reopened.engine).list_projects()
    finally:
        reopened.close()

    return CleanSeedReceipt(
        legacy_database=str(legacy_database),
        legacy_sha256=legacy_sha256,
        legacy_revision=legacy_revision,
        legacy_snapshot=str(snapshot),
        legacy_snapshot_sha256=_sha256(snapshot),
        target_database=str(target_database),
        target_sha256=_sha256(target_database),
        target_revision=target_revision,
        project_count=project_count,
        building_count=building_count,
        room_count=room_count,
        copied_setting_keys=tuple(copied_setting_keys),
        source_excluded_counts=source_excluded_counts,
        target_forbidden_counts=target_forbidden_counts,
    )


def _read_seed(path: Path, setting_keys: tuple[str, ...]) -> dict[str, list[dict[str, Any]]]:
    uri = f"file:{path.as_posix()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        projects = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM project WHERE lifecycle = 'ACTIVE' ORDER BY project_code"
            )
        ]
        if not projects:
            raise CleanSeedError("Legacy database has no active project to seed")
        project_ids = tuple(row["id"] for row in projects)
        placeholders = ",".join("?" for _ in project_ids)
        buildings = [
            dict(row)
            for row in connection.execute(
                f"SELECT * FROM building WHERE project_id IN ({placeholders}) "
                "ORDER BY project_id, display_order, name",
                project_ids,
            )
        ]
        rooms = [
            dict(row)
            for row in connection.execute(
                f"SELECT * FROM room WHERE project_id IN ({placeholders}) "
                "ORDER BY project_id, building_id, name",
                project_ids,
            )
        ]
        settings: list[dict[str, Any]] = []
        if setting_keys:
            setting_placeholders = ",".join("?" for _ in setting_keys)
            settings = [
                dict(row)
                for row in connection.execute(
                    f"SELECT * FROM project_setting WHERE project_id IN ({placeholders}) "
                    f"AND setting_key IN ({setting_placeholders}) ORDER BY project_id, setting_key",
                    project_ids + tuple(setting_keys),
                )
            ]
    return {
        "projects": projects,
        "buildings": buildings,
        "rooms": rooms,
        "settings": settings,
    }


def _create_immutable_snapshot(source: Path, root: Path, *, clock=None) -> Path:
    now = (clock or (lambda: datetime.now(UTC)))().astimezone(UTC)
    stamp = now.strftime("%Y%m%dT%H%M%S%fZ")
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{source.stem}.legacy_nlp2.{stamp}.{_sha256(source)[:8]}.sqlite"
    if target.exists():
        raise CleanSeedError(f"Legacy snapshot already exists: {target}")
    try:
        with closing(sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)) as source_db:
            with closing(sqlite3.connect(target)) as target_db:
                source_db.backup(target_db)
        _verify_database(target)
        os.chmod(target, stat.S_IREAD)
    except Exception:
        os.chmod(target, stat.S_IWRITE)
        target.unlink(missing_ok=True)
        raise
    return target


def _table_counts(path: Path, tables: tuple[str, ...]) -> dict[str, int]:
    result: dict[str, int] = {}
    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as connection:
        existing = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for table in tables:
            if table in existing:
                result[table] = int(
                    connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                )
    return result


def _verify_database(path: Path) -> str:
    revision = current_revision_read_only(path)
    if revision is None:
        raise CleanSeedError(f"Database has no schema revision: {path}")
    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as connection:
        if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise CleanSeedError(f"Database integrity check failed: {path}")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise CleanSeedError(f"Database foreign-key check failed: {path}")
    return revision


def _json_value(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
