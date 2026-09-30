from __future__ import annotations

import hashlib
import os
import subprocess

from nl_project_2.persistence.diagnostics import inspect_database
from nl_project_2.persistence.schema import HEAD_TABLE_NAMES


def sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_diagnostic_is_complete_and_read_only(database) -> None:
    database.close()
    before = sha256(database.path)
    result = inspect_database(database.path)
    after = sha256(database.path)

    assert result.ok
    assert result.missing_tables == ()
    assert result.unexpected_tables == ()
    assert len(HEAD_TABLE_NAMES) == 67
    assert before == after


def test_diagnostic_command_returns_json(database, project_root) -> None:
    database.close()
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(project_root / "src")
    completed = subprocess.run(
        [
            str(project_root / ".venv" / "Scripts" / "python.exe"),
            str(project_root / "tools" / "db_check.py"),
            str(database.path),
        ],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert completed.returncode == 0, completed.stderr
    assert '"ok": true' in completed.stdout
