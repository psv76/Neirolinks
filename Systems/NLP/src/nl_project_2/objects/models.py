"""Typed application DTOs for the object workspace."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ProjectCard:
    name: str
    project_code: str
    object_type: str = ""
    address: str = ""
    total_area_m2: Decimal | None = None
    customer: str = ""
    responsible_designer: str = ""
    note: str = ""


@dataclass(frozen=True, slots=True)
class ProjectSettings:
    project_folder: str = ""
    output_folder: str = ""
    versions_folder: str = ""
    initial_page_number: int | None = None
    cable_reserve_at_board_m: Decimal | None = Decimal("3")
    cable_reserve_at_distribution_box_m: Decimal | None = Decimal("0.2")
    cable_reserve_at_endpoint_m: Decimal | None = Decimal("0.3")
    cable_meander_percent: Decimal | None = Decimal("5")
    cable_obstacle_percent: Decimal | None = Decimal("10")
    cable_timber_segment_reserve_m: Decimal | None = Decimal("0.5")


@dataclass(frozen=True, slots=True)
class BuildingRecord:
    id: str
    name: str
    display_order: int


@dataclass(frozen=True, slots=True)
class RoomRecord:
    id: str
    building_id: str
    building_name: str
    name: str
    base_mark_mm: Decimal | None
    height_m: Decimal | None
    marking_color: str


@dataclass(frozen=True, slots=True)
class RoomMigrationAction:
    canonical_name: str
    action: str
    room_id: str | None = None
    source_name: str | None = None


@dataclass(frozen=True, slots=True)
class RoomMigrationPreview:
    project_id: str
    building_id: str
    actions: tuple[RoomMigrationAction, ...] = field(default_factory=tuple)
    device_reassignments: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    ambiguities: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class RoomAliasMergeAction:
    source_name: str
    target_name: str
    source_room_id: str
    target_room_id: str
    board_reassignments: int = 0
    project_instance_reassignments: int = 0
    field_device_reassignments: int = 0

    @property
    def reference_count(self) -> int:
        return (
            self.board_reassignments
            + self.project_instance_reassignments
            + self.field_device_reassignments
        )


@dataclass(frozen=True, slots=True)
class RoomAliasMergePreview:
    project_id: str
    building_id: str
    actions: tuple[RoomAliasMergeAction, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ProjectSummary:
    id: str
    name: str
    project_code: str


@dataclass(frozen=True, slots=True)
class ProjectDetail:
    id: str
    card: ProjectCard
    settings: ProjectSettings
    buildings: tuple[BuildingRecord, ...] = field(default_factory=tuple)
    rooms: tuple[RoomRecord, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class TimeSummary:
    today_seconds: int
    total_seconds: int
    is_running: bool

    @staticmethod
    def format_seconds(seconds: int) -> str:
        minutes = max(0, seconds) // 60
        return f"{minutes // 60} ч {minutes % 60} мин"
