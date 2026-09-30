from __future__ import annotations

from pathlib import Path


def test_production_and_tools_have_no_legacy_root_literal() -> None:
    root = Path(__file__).resolve().parents[1]
    forbidden = ("D:" + chr(92) + "NLP").encode()
    for directory in (root / "src", root / "tools"):
        for path in directory.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".py", ".ps1", ".vbs", ".json", ".toml"}:
                assert forbidden not in path.read_bytes(), path


def test_bootstrap_has_no_database_artifact() -> None:
    root = Path(__file__).resolve().parents[1]
    database_suffixes = {".db", ".sqlite", ".sqlite3"}
    found = [
        path for path in root.rglob("*") if path.is_file() and path.suffix in database_suffixes
    ]
    assert found == []
