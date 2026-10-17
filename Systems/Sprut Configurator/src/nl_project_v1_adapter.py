from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


def _connect_readonly(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path).resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _json_object(value: Any) -> dict[str, Any]:
    text = _clean(value)
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _find_object(conn: sqlite3.Connection, object_name: str) -> sqlite3.Row:
    rows = conn.execute(
        "SELECT * FROM objects WHERE name = ? ORDER BY object_id",
        (object_name,),
    ).fetchall()
    if not rows:
        raise ValueError(f"NL Project 1.0: объект {object_name!r} не найден.")
    if len(rows) != 1:
        raise ValueError(
            f"NL Project 1.0: найдено {len(rows)} объектов с именем {object_name!r}; "
            "legacy adapter не выбирает объект угадыванием."
        )
    return rows[0]


def _merged_normalized_lines(
    conn: sqlite3.Connection,
    object_id: int,
) -> list[dict[str, Any]]:
    """Repeat the merge rule used by NL Project 1.0 repository.py.

    Object-scope rows are loaded first. Controller-scope rows for the same
    object are loaded second and replace equal
    (line_id, parent_line_id, record_kind) keys.
    """
    object_rows = [
        dict(row)
        for row in conn.execute(
            """SELECT *
                 FROM normalized_lines
                WHERE object_id = ? AND controller_id IS NULL
                ORDER BY normalized_line_id""",
            (object_id,),
        ).fetchall()
    ]
    work_rows = [
        dict(row)
        for row in conn.execute(
            """SELECT n.*
                 FROM normalized_lines n
                 JOIN controllers c ON c.controller_id = n.controller_id
                WHERE c.object_id = ?
                ORDER BY n.normalized_line_id""",
            (object_id,),
        ).fetchall()
    ]

    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in [*object_rows, *work_rows]:
        key = (
            _clean(row.get("line_id")),
            _clean(row.get("parent_line_id")),
            _clean(row.get("record_kind")),
        )
        merged[key] = row

    return sorted(
        merged.values(),
        key=lambda row: (
            _clean(row.get("line_id")),
            _clean(row.get("parent_line_id")),
            _clean(row.get("record_kind")),
        ),
    )


def extract_object_source_model(
    db_path: str | Path,
    object_name: str,
) -> dict[str, Any]:
    """Extract a neutral Sprut source model from NL Project 1.0.

    The function is intentionally read-only and strips legacy database IDs from
    the returned model. It does not invent MQTT/SERIAL identity.
    """
    with _connect_readonly(db_path) as conn:
        obj = _find_object(conn, object_name)
        object_id = int(obj["object_id"])

        board_rows = [
            dict(row)
            for row in conn.execute(
                """SELECT board_code, name, installation_place, board_load_type
                     FROM boards
                    WHERE object_id = ?
                    ORDER BY board_code""",
                (object_id,),
            ).fetchall()
        ]

        module_rows = [
            dict(row)
            for row in conn.execute(
                """SELECT m.module_code, m.module_type, m.modbus_address,
                          b.board_code
                     FROM wb_modules m
                     JOIN controllers c ON c.controller_id = m.controller_id
                     LEFT JOIN boards b ON b.board_id = m.board_id
                    WHERE c.object_id = ?
                    ORDER BY m.module_code""",
                (object_id,),
            ).fetchall()
        ]

        field_rows = [
            dict(row)
            for row in conn.execute(
                """SELECT f.line_id, b.board_code, f.power_mode, f.voltage_v,
                          f.data_kind, f.data_point, f.device_profile,
                          f.config_json, f.note
                     FROM field_device_settings f
                     JOIN controllers c ON c.controller_id = f.controller_id
                     LEFT JOIN boards b ON b.board_id = f.board_id
                    WHERE c.object_id = ?
                    ORDER BY f.line_id""",
                (object_id,),
            ).fetchall()
        ]

        line_rows = _merged_normalized_lines(conn, object_id)

    boards = [
        {
            "code": _clean(row.get("board_code")),
            "name": _clean(row.get("name")),
            "installation_place": _clean(row.get("installation_place")),
            "kind": _clean(row.get("board_load_type")),
        }
        for row in board_rows
    ]

    modules = [
        {
            "code": _clean(row.get("module_code")),
            "type": _clean(row.get("module_type")),
            "modbus_address": _clean(row.get("modbus_address")),
            "board": _clean(row.get("board_code")),
        }
        for row in module_rows
    ]

    lines = [
        {
            "id": _clean(row.get("line_id")),
            "parent_id": _clean(row.get("parent_line_id")),
            "kind": _clean(row.get("record_kind")),
            "board": _clean(row.get("board")),
            "room": _clean(row.get("room")),
            "purpose": _clean(row.get("purpose")),
            "cable_type": _clean(row.get("cable_type")),
            "connection_point": _clean(row.get("connection_point")),
            "module_code": _clean(row.get("module_code")),
            "details": _json_object(row.get("details_json")),
        }
        for row in line_rows
    ]

    field_devices = [
        {
            "line_id": _clean(row.get("line_id")),
            "board": _clean(row.get("board_code")),
            "power_mode": _clean(row.get("power_mode")),
            "voltage_v": row.get("voltage_v"),
            "data_kind": _clean(row.get("data_kind")),
            "data_point": _clean(row.get("data_point")),
            "device_profile": _clean(row.get("device_profile")),
            "config": _json_object(row.get("config_json")),
            "note": _clean(row.get("note")),
        }
        for row in field_rows
    ]

    return {
        "source": {
            "adapter": "nl_project_v1",
            "object_name": _clean(obj["name"]),
            "project_folder": _clean(obj["project_folder"]),
            "layout_dwg_path": _clean(obj["layout_dwg_path"]),
        },
        "boards": boards,
        "modules": modules,
        "lines": lines,
        "field_devices": field_devices,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only extractor from NL Project 1.0 SQLite."
    )
    parser.add_argument("database", help="Path to a COPY of nl_project.sqlite")
    parser.add_argument("--object", required=True, dest="object_name")
    parser.add_argument("--output", help="Optional JSON output path")
    args = parser.parse_args()

    model = extract_object_source_model(args.database, args.object_name)
    text = json.dumps(model, ensure_ascii=False, indent=2)

    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
