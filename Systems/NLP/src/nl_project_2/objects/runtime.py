"""Application-owned database and current-object lifecycle coordinator."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nl_project_2.automation import AutomationService
from nl_project_2.bulk_actions import BulkActionService
from nl_project_2.buses import BusService
from nl_project_2.cables import CableService
from nl_project_2.cad_sync import AutoCadBridgeClient, DwgSyncService
from nl_project_2.catalog.installer import CatalogInstaller
from nl_project_2.catalog.payload import load_packaged_payload
from nl_project_2.config import PathConfig
from nl_project_2.constructor import ConstructorService
from nl_project_2.distribution import DistributionService, distribution_relation_definitions
from nl_project_2.equipment_actions import EquipmentActionService
from nl_project_2.guided_actions import GuidedActionService
from nl_project_2.integration import IntegratedUiService
from nl_project_2.local_state import UiStateStore
from nl_project_2.operations import (
    BackgroundOperationManager,
    BackupService,
    LocalApplicationProfile,
    SelfCheckService,
    StructuredLogger,
)
from nl_project_2.panels import PanelService
from nl_project_2.persistence.database import DatabaseHandle, DatabaseManager
from nl_project_2.persistence.ids import new_id
from nl_project_2.specification import SpecificationService

from .service import ObjectService
from .time_tracking import WorkTimeService


@dataclass
class ApplicationRuntime:
    database: DatabaseHandle
    objects: ObjectService
    work_time: WorkTimeService
    dwg_sync: DwgSyncService | None = None
    cables: CableService | None = None
    constructor: ConstructorService | None = None
    distribution: DistributionService | None = None
    automation: AutomationService | None = None
    buses: BusService | None = None
    panels: PanelService | None = None
    specification: SpecificationService | None = None
    integrated_ui: IntegratedUiService | None = None
    ui_state: UiStateStore | None = None
    backup_service: BackupService | None = None
    paths: PathConfig | None = None
    opening_database_sha256: str | None = None
    last_daily_backup: object | None = None
    background_operations: BackgroundOperationManager | None = None
    current_project_id: str | None = None
    local_profile: LocalApplicationProfile | None = None
    guided_actions: GuidedActionService | None = None
    bulk_actions: BulkActionService | None = None
    equipment_actions: EquipmentActionService | None = None
    _closed: bool = False

    @classmethod
    def open(
        cls,
        paths: PathConfig,
        *,
        database_path: Path | None = None,
        clock=None,
        local_timezone=None,
    ) -> ApplicationRuntime:
        target = (database_path or paths.user_projects_root / "nl_project_2.sqlite").resolve()
        manager = DatabaseManager()
        created = not target.exists()
        if not created:
            database = manager.open_existing(target)
        else:
            database = manager.initialize_new(target)
        try:
            CatalogInstaller(database.engine).install(load_packaged_payload())
        except Exception:
            database.close()
            if created:
                target.unlink(missing_ok=True)
            raise
        work_time = WorkTimeService(
            database.engine,
            new_id(),
            clock=clock,
            local_timezone=local_timezone,
        )
        automation = AutomationService(database.engine)
        cables = CableService(database.engine)
        constructor = ConstructorService(database.engine, distribution_relation_definitions())
        panels = PanelService(database.engine)
        specification = SpecificationService(database.engine, automation, cables)
        distribution = DistributionService(database.engine)
        buses = BusService(database.engine)
        equipment_actions = EquipmentActionService(database.engine)
        bridge_logger = StructuredLogger(paths.log_root / "operations.jsonl")
        local_profile = LocalApplicationProfile(paths.local_state_root)
        return cls(
            database=database,
            objects=ObjectService(database.engine),
            work_time=work_time,
            dwg_sync=DwgSyncService(database.engine, AutoCadBridgeClient(logger=bridge_logger)),
            cables=cables,
            constructor=constructor,
            distribution=distribution,
            automation=automation,
            buses=buses,
            panels=panels,
            specification=specification,
            integrated_ui=IntegratedUiService(
                constructor=constructor,
                cables=cables,
                panels=panels,
                specification=specification,
                engine=database.engine,
                equipment_actions=equipment_actions,
                distribution=distribution,
                automation=automation,
                buses=buses,
            ),
            ui_state=UiStateStore(paths.local_state_root),
            backup_service=BackupService(paths.backup_root / target.stem),
            paths=paths,
            opening_database_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
            background_operations=BackgroundOperationManager(),
            local_profile=local_profile,
            guided_actions=GuidedActionService(database.engine, local_profile),
            bulk_actions=BulkActionService(database.engine, local_profile),
            equipment_actions=equipment_actions,
        )

    def open_project(self, project_id: str):
        detail = self.objects.get_project(project_id)
        self.work_time.switch_to(project_id)
        self.current_project_id = project_id
        return detail

    def close_project(self) -> None:
        if self.current_project_id is not None:
            self.work_time.pause(self.current_project_id, reason="PROJECT_CLOSE")
            self.current_project_id = None

    def toggle_time(self) -> bool:
        if self.current_project_id is None:
            return False
        summary = self.work_time.summary(self.current_project_id)
        if summary.is_running:
            self.work_time.pause(self.current_project_id)
            return False
        self.work_time.play(self.current_project_id)
        return True

    def navigate_within_project(self, section: Any) -> None:
        """Navigation deliberately has no work-session side effect."""
        if self.ui_state is not None:
            self.ui_state.update(last_object_tab=int(section))

    def close(self) -> None:
        if self._closed:
            return
        self.work_time.close_application()
        if self.background_operations is not None:
            self.background_operations.close()
        self.database.close()
        self._closed = True
        if self.backup_service is not None and self.opening_database_sha256 is not None:
            self.last_daily_backup = self.backup_service.create_daily_if_changed(
                self.database.path,
                opening_sha256=self.opening_database_sha256,
            )

    def manual_backup(self):
        if self.backup_service is None:
            raise RuntimeError("Backup service is unavailable")
        return self.backup_service.create_manual(self.database.path)

    def self_check(self):
        if self.paths is None:
            raise RuntimeError("Path configuration is unavailable")
        return SelfCheckService(self.database.path, self.paths).run()
