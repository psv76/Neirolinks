from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from nl_project_2.config import PathConfig
from nl_project_2.objects.models import ProjectCard, ProjectSettings
from nl_project_2.objects.runtime import ApplicationRuntime


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


def test_close_and_reopen_application_restores_object_and_total_time(tmp_path):
    paths = PathConfig(
        app_root=tmp_path / "app",
        backup_root=tmp_path / "backups",
        release_root=tmp_path / "releases",
        user_projects_root=tmp_path / "projects",
        local_state_root=tmp_path / "state",
    )
    clock = MutableClock(datetime(2026, 8, 8, 7, 0, tzinfo=UTC))
    runtime = ApplicationRuntime.open(paths, clock=clock)
    project_id = runtime.objects.create_project(
        ProjectCard(
            name="Повторное открытие",
            project_code="REOPEN-1",
            total_area_m2=Decimal("99.9"),
        )
    )
    runtime.objects.save_settings(
        project_id,
        ProjectSettings(project_folder="D:/Independent/Project", initial_page_number=3),
    )
    runtime.open_project(project_id)
    clock.value += timedelta(minutes=42)
    runtime.close()

    reopened = ApplicationRuntime.open(paths, clock=clock)
    try:
        detail = reopened.open_project(project_id)
        summary = reopened.work_time.summary(project_id)
        assert detail.card.total_area_m2 == Decimal("99.9")
        assert detail.settings.project_folder == "D:/Independent/Project"
        assert detail.settings.initial_page_number == 3
        assert summary.total_seconds == 42 * 60
        assert summary.is_running is True
    finally:
        reopened.close()
