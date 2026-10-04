"""Run an isolated first-start smoke against a verified frozen distribution."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inspect_database(path: Path) -> dict:
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        connection.execute("PRAGMA query_only = ON")
        return {
            "integrity_check": connection.execute("PRAGMA integrity_check").fetchone()[0],
            "foreign_key_violations": len(
                connection.execute("PRAGMA foreign_key_check").fetchall()
            ),
            "revision": connection.execute("SELECT version_num FROM alembic_version").fetchone()[0],
            "passports": connection.execute("SELECT COUNT(*) FROM passport_definition").fetchone()[
                0
            ],
            "products": connection.execute("SELECT COUNT(*) FROM product_definition").fetchone()[0],
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
    finally:
        connection.close()


def run_process(executable: Path, arguments: list[str], cwd: Path, environment: dict) -> dict:
    completed = subprocess.run(
        [str(executable), *arguments],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return {
        "arguments": arguments,
        "exit_code": completed.returncode,
        "stdout": completed.stdout[-2000:],
        "stderr": completed.stderr[-2000:],
    }


def smoke(source_dist: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="nlp3-package-smoke-") as temporary:
        root = Path(temporary)
        isolated_dist = root / "package" / "NLProject3"
        shutil.copytree(source_dist, isolated_dist)
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment.update(
            {
                "NLP3_PROJECTS_ROOT": str(root / "user" / "projects"),
                "NLP3_LOCAL_STATE_ROOT": str(root / "user" / "state"),
                "NLP3_BACKUP_ROOT": str(root / "user" / "backups"),
                "NLP3_RELEASE_ROOT": str(root / "user" / "releases"),
                "QT_QPA_PLATFORM": "offscreen",
            }
        )
        executable = isolated_dist / "NLProject3.exe"
        application = run_process(executable, ["--auto-close-ms", "200"], root, environment)
        bridge = run_process(executable, ["--nlp3-cad-bridge", "--help"], root, environment)
        version = run_process(executable, ["--version"], root, environment)
        database = root / "user" / "projects" / "nl_project_3.sqlite"
        fatal_log = root / "user" / "state" / "logs" / "fatal-startup.jsonl"
        if application["exit_code"] != 0:
            raise RuntimeError(f"Packaged application failed: {application}")
        if bridge["exit_code"] != 0:
            raise RuntimeError(f"Packaged STA bridge component failed self-check: {bridge}")
        if version["exit_code"] != 0 or "NL Project 3.0" not in version["stdout"]:
            raise RuntimeError(f"Packaged version command failed: {version}")
        if fatal_log.exists():
            raise RuntimeError(
                f"Fatal startup log was created: {fatal_log.read_text(encoding='utf-8')}"
            )
        if not database.is_file():
            raise RuntimeError("Packaged first start did not create its isolated clean database")
        database_receipt = inspect_database(database)
        expected = {
            "integrity_check": "ok",
            "foreign_key_violations": 0,
            "revision": "000000000012",
            "passports": 18,
            "products": 31,
        }
        if any(database_receipt[key] != value for key, value in expected.items()):
            raise RuntimeError(f"Packaged database validation failed: {database_receipt}")
        return {
            "status": "PASSED",
            "source_dist": str(source_dist),
            "source_dist_executable_sha256": sha256(source_dist / "NLProject3.exe"),
            "isolation": {
                "copied_distribution": True,
                "source_pythonpath_removed": True,
                "all_user_paths_under_os_temp": True,
            },
            "application": application,
            "sta_bridge_component": bridge,
            "version": version,
            "fatal_startup_log": False,
            "database": database_receipt,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    receipt = smoke(args.dist.resolve())
    output = json.dumps(receipt, indent=2, ensure_ascii=False) + "\n"
    if args.receipt:
        destination = args.receipt.resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(output, encoding="utf-8")
    print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
