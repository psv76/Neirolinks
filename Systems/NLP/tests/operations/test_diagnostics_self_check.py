from __future__ import annotations

import json

from nl_project_2.config import PathConfig
from nl_project_2.objects.models import ProjectCard
from nl_project_2.objects.runtime import ApplicationRuntime
from nl_project_2.operations import (
    SelfCheckService,
    StructuredLogger,
    create_diagnostic_directory,
)


def _paths(tmp_path):
    return PathConfig(
        app_root=tmp_path / "app",
        backup_root=tmp_path / "backups",
        release_root=tmp_path / "releases",
        user_projects_root=tmp_path / "projects",
        local_state_root=tmp_path / "state",
    )


def test_self_check_is_read_only_and_complete(database, tmp_path):
    report = SelfCheckService(database.path, _paths(tmp_path)).run()
    assert report.ok
    assert report.database_sha256_before == report.database_sha256_after
    assert {row.code for row in report.checks} == {
        "PATH_ISOLATION",
        "SCHEMA_REVISION",
        "SQLITE_INTEGRITY",
        "FOREIGN_KEYS",
        "CATALOG_19_32",
        "INSTANCE_RESOURCES",
        "READ_ONLY_INVARIANT",
    }
    path = database.path
    database.close()
    path.unlink()
    assert not path.exists()


def test_self_check_rejects_corrupt_copy_without_changing_it(tmp_path):
    corrupt = tmp_path / "corrupt.sqlite"
    corrupt.write_bytes(b"not a sqlite database")
    before = corrupt.read_bytes()

    report = SelfCheckService(corrupt, _paths(tmp_path)).run()

    assert not report.ok
    assert any(row.status == "FAIL" for row in report.checks)
    assert corrupt.read_bytes() == before
    assert report.database_sha256_before == report.database_sha256_after


def test_structured_log_redacts_rotates_and_diagnostic_is_not_archive(database, tmp_path):
    logger = StructuredLogger(
        tmp_path / "state" / "logs" / "operations.jsonl", max_bytes=300, backups=2
    )
    for index in range(8):
        logger.record(
            level="ERROR",
            component="test",
            operation="failure",
            result="failed",
            duration_ms=index,
            error=RuntimeError("secret message"),
            summary={"address": "private", "count": index},
        )
    current = logger.log_path.read_text(encoding="utf-8")
    event = json.loads(current.splitlines()[-1])
    assert event["error_category"] == "RuntimeError"
    assert "secret message" not in current
    assert event["summary"]["address"] == "<redacted>"
    assert logger.log_path.with_suffix(".jsonl.1").exists()

    report = SelfCheckService(database.path, _paths(tmp_path)).run()
    directory = create_diagnostic_directory(
        tmp_path / "diagnostics", self_check=report, recent_events=(event,)
    )
    assert directory.is_dir()
    assert (directory / "diagnostics.json").is_file()
    assert not list(directory.glob("*.zip"))


def test_runtime_manual_and_first_changed_close_daily_backup(tmp_path):
    paths = _paths(tmp_path)
    runtime = ApplicationRuntime.open(paths)
    runtime.objects.create_project(ProjectCard(name="Backup", project_code="BACKUP"))
    manual = runtime.manual_backup()
    runtime.close()
    daily = runtime.last_daily_backup
    assert manual.kind == "MANUAL" and manual.path.is_file()
    assert daily.kind == "DAILY" and daily.path.is_file()

    reopened = ApplicationRuntime.open(paths)
    reopened.close()
    # Work-session close without opening a project is unchanged, so no second daily is created.
    assert reopened.last_daily_backup is None
