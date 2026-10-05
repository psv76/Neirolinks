"""Transactional object/card/building/room/settings commands and read queries."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import Engine, delete, func, select, update
from sqlalchemy.exc import IntegrityError

from nl_project_2.cables.recalculation import recalculate_segments
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    board,
    building,
    cable_line,
    catalog_release,
    field_device,
    project,
    project_instance,
    project_setting,
    room,
)
from nl_project_2.persistence.uow import UnitOfWork

from .models import (
    BuildingRecord,
    ProjectCard,
    ProjectDetail,
    ProjectSettings,
    ProjectSummary,
    RoomAliasMergeAction,
    RoomAliasMergePreview,
    RoomMigrationAction,
    RoomMigrationPreview,
    RoomRecord,
)
from .room_rules import (
    DEFAULT_ROOM_COLOR,
    assign_default_room_colors,
    leading_room_number,
    normalize_room_name,
    resolve_room,
    room_natural_key,
)

SETTING_KEYS = {
    "project_folder": "STRING",
    "output_folder": "STRING",
    "versions_folder": "STRING",
    "initial_page_number": "INTEGER",
    "cable_reserve_at_board_m": "DECIMAL",
    "cable_reserve_at_distribution_box_m": "DECIMAL",
    "cable_reserve_at_endpoint_m": "DECIMAL",
    "cable_meander_percent": "DECIMAL",
    "cable_obstacle_percent": "DECIMAL",
    "cable_timber_segment_reserve_m": "DECIMAL",
}

CABLE_SETTING_DEFAULTS = {
    "cable_reserve_at_board_m": Decimal("3"),
    "cable_reserve_at_distribution_box_m": Decimal("0.2"),
    "cable_reserve_at_endpoint_m": Decimal("0.3"),
    "cable_meander_percent": Decimal("5"),
    "cable_obstacle_percent": Decimal("10"),
    "cable_timber_segment_reserve_m": Decimal("0.5"),
}


class ObjectValidationError(ValueError):
    pass


class DuplicateIdentityError(ObjectValidationError):
    pass


def normalize_identity(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _decimal(value: Any, field: str, *, non_negative: bool = False) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ObjectValidationError(f"{field} must be a decimal number") from exc
    if not result.is_finite() or (non_negative and result < 0):
        raise ObjectValidationError(f"{field} is outside the allowed range")
    return result


def _card_json(card: ProjectCard) -> dict[str, Any]:
    area = _decimal(card.total_area_m2, "total_area_m2", non_negative=True)
    return {
        "object_type": card.object_type.strip(),
        "address": card.address.strip(),
        "total_area_m2": None if area is None else str(area),
        "customer": card.customer.strip(),
        "responsible_designer": card.responsible_designer.strip(),
        "note": card.note.strip(),
    }


def _card(row: dict[str, Any]) -> ProjectCard:
    fields = row["card_fields_json"] or {}
    return ProjectCard(
        name=row["name"],
        project_code=row["project_code"],
        object_type=fields.get("object_type", ""),
        address=fields.get("address", ""),
        total_area_m2=_decimal(fields.get("total_area_m2"), "total_area_m2"),
        customer=fields.get("customer", ""),
        responsible_designer=fields.get("responsible_designer", ""),
        note=fields.get("note", ""),
    )


def _building_code(name: str) -> str:
    normalized = normalize_identity(name)
    code = re.sub(r"[^0-9a-zа-яё]+", "-", normalized, flags=re.IGNORECASE).strip("-")
    if not code:
        raise ObjectValidationError("Building name must contain visible characters")
    return code


@dataclass(frozen=True, slots=True)
class _RoomCandidate:
    id: str
    name: str


@dataclass(frozen=True, slots=True)
class _ColoredRoomCandidate:
    id: str
    name: str
    marking_color: str


def _canonical_room_names(values) -> tuple[str, ...]:
    names = tuple(str(value).strip() for value in values)
    if not names or any(not name for name in names):
        raise ObjectValidationError("Canonical room names are required")
    normalized = [normalize_room_name(name) for name in names]
    if len(set(normalized)) != len(normalized):
        raise ObjectValidationError("Canonical room names must be unique")
    return names


def _room_migration_plan(rows, names):
    actions: list[RoomMigrationAction] = []
    targets: list[_RoomCandidate] = []
    ambiguities: list[str] = []
    claimed: set[str] = set()
    for index, canonical_name in enumerate(names):
        available = [row for row in rows if row["id"] not in claimed]
        exact = [row for row in available if row["name"] == canonical_name]
        normalized = [
            row
            for row in available
            if normalize_room_name(row["name"]) == normalize_room_name(canonical_name)
        ]
        number = leading_room_number(canonical_name)
        numbered = [
            row
            for row in available
            if number is not None and leading_room_number(row["name"]) == number
        ]
        matches = exact or normalized or numbered
        if len(matches) > 1:
            ambiguities.append(
                f"{canonical_name}: {', '.join(sorted(row['name'] for row in matches))}"
            )
            continue
        if matches:
            source = matches[0]
            claimed.add(source["id"])
            action = "KEEP" if source["name"] == canonical_name else "RENAME"
            actions.append(
                RoomMigrationAction(
                    canonical_name=canonical_name,
                    action=action,
                    room_id=source["id"],
                    source_name=source["name"],
                )
            )
            targets.append(_RoomCandidate(source["id"], canonical_name))
        else:
            virtual_id = f"__create__:{index}"
            actions.append(RoomMigrationAction(canonical_name, "CREATE"))
            targets.append(_RoomCandidate(virtual_id, canonical_name))
    return actions, targets, ambiguities


def _validated_alias_pairs(rows, aliases) -> tuple[tuple[dict, dict], ...]:
    pairs = tuple((str(source).strip(), str(target).strip()) for source, target in aliases.items())
    if not pairs or any(not source or not target or source == target for source, target in pairs):
        raise ObjectValidationError("Distinct source and target room aliases are required")
    if len({normalize_room_name(source) for source, _target in pairs}) != len(pairs):
        raise ObjectValidationError("Alias source rooms must be unique")
    by_name: dict[str, list[dict]] = {}
    for row in rows:
        by_name.setdefault(row["name"], []).append(row)
    result = []
    for source_name, target_name in pairs:
        sources = by_name.get(source_name, [])
        targets = by_name.get(target_name, [])
        if len(sources) != 1:
            raise ObjectValidationError(f"Alias room must exist exactly once: {source_name}")
        if len(targets) != 1:
            raise ObjectValidationError(f"Target room must exist exactly once: {target_name}")
        result.append((sources[0], targets[0]))
    source_ids = {source["id"] for source, _target in result}
    target_ids = {target["id"] for _source, target in result}
    if source_ids & target_ids:
        raise ObjectValidationError("Alias chains are not supported in one reviewed merge")
    return tuple(result)


def _assign_default_colors_in_uow(uow, project_id: str, now: datetime) -> dict[str, str]:
    rows = list(
        uow.execute(
            select(room.c.id, room.c.name, room.c.display_json).where(
                room.c.project_id == project_id
            )
        ).mappings()
    )
    candidates = [
        _ColoredRoomCandidate(
            id=row["id"],
            name=row["name"],
            marking_color=(row["display_json"] or {}).get("marking_color", DEFAULT_ROOM_COLOR),
        )
        for row in rows
    ]
    assignments = assign_default_room_colors(candidates)
    for row in rows:
        color = assignments.get(row["id"])
        if color is None:
            continue
        display = dict(row["display_json"] or {})
        display["marking_color"] = color
        uow.execute(
            update(room)
            .where(room.c.id == row["id"], room.c.project_id == project_id)
            .values(
                display_json=display,
                updated_at_utc=now,
                row_version=room.c.row_version + 1,
            )
        )
    return assignments


class ObjectService:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def list_projects(self) -> list[ProjectSummary]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(project.c.id, project.c.name, project.c.project_code)
                .where(project.c.lifecycle == "ACTIVE")
                .order_by(func.lower(project.c.name), project.c.project_code)
            ).mappings()
            return [ProjectSummary(**dict(row)) for row in rows]

    def create_project(self, card: ProjectCard) -> str:
        name = card.name.strip()
        code = card.project_code.strip()
        if not name or not code:
            raise ObjectValidationError("Project name and code are required")
        with UnitOfWork(self._engine) as uow:
            release_id = uow.execute(
                select(catalog_release.c.id).where(catalog_release.c.status == "ACTIVE")
            ).scalar_one_or_none()
            if release_id is None:
                raise ObjectValidationError("An active equipment catalog is required")
            existing = uow.execute(
                select(project.c.id).where(
                    project.c.lifecycle == "ACTIVE",
                    func.lower(project.c.project_code) == code.casefold(),
                )
            ).first()
            if existing:
                raise DuplicateIdentityError(f"Project code already exists: {code}")
            project_id = new_id()
            uow.execute(
                project.insert().values(
                    id=project_id,
                    project_code=code,
                    name=name,
                    card_fields_json=_card_json(card),
                    active_catalog_release_id=release_id,
                    lifecycle="ACTIVE",
                )
            )
            uow.commit()
        return project_id

    def update_project(self, project_id: str, card: ProjectCard) -> None:
        name = card.name.strip()
        code = card.project_code.strip()
        if not name or not code:
            raise ObjectValidationError("Project name and code are required")
        with UnitOfWork(self._engine) as uow:
            duplicate = uow.execute(
                select(project.c.id).where(
                    project.c.id != project_id,
                    project.c.lifecycle == "ACTIVE",
                    func.lower(project.c.project_code) == code.casefold(),
                )
            ).first()
            if duplicate:
                raise DuplicateIdentityError(f"Project code already exists: {code}")
            result = uow.execute(
                update(project)
                .where(project.c.id == project_id, project.c.lifecycle == "ACTIVE")
                .values(
                    project_code=code,
                    name=name,
                    card_fields_json=_card_json(card),
                    updated_at_utc=datetime.now(UTC),
                    row_version=project.c.row_version + 1,
                    project_revision=project.c.project_revision + 1,
                )
            )
            if result.rowcount != 1:
                raise ObjectValidationError("Project not found")
            uow.commit()

    def add_building(self, project_id: str, name: str) -> str:
        clean = name.strip()
        code = _building_code(clean)
        with UnitOfWork(self._engine) as uow:
            next_order = uow.execute(
                select(func.coalesce(func.max(building.c.display_order), -1) + 1).where(
                    building.c.project_id == project_id
                )
            ).scalar_one()
            identifier = new_id()
            try:
                uow.execute(
                    building.insert().values(
                        id=identifier,
                        project_id=project_id,
                        code=clean,
                        normalized_code=code,
                        name=clean,
                        display_order=next_order,
                        properties_json={},
                    )
                )
                uow.execute(
                    update(project)
                    .where(project.c.id == project_id)
                    .values(
                        project_revision=project.c.project_revision + 1,
                        updated_at_utc=datetime.now(UTC),
                    )
                )
                uow.commit()
            except IntegrityError as exc:
                raise DuplicateIdentityError(f"Building already exists: {clean}") from exc
        return identifier

    def add_room(
        self,
        *,
        project_id: str,
        building_id: str,
        name: str,
        base_mark_mm: Decimal | str | None,
        height_m: Decimal | str | None,
        marking_color: str,
    ) -> str:
        clean = name.strip()
        if not clean:
            raise ObjectValidationError("Room name is required")
        base = _decimal(base_mark_mm, "base_mark_mm")
        height = _decimal(height_m, "height_m", non_negative=True)
        color = marking_color.strip().upper()
        if not re.fullmatch(r"#[0-9A-F]{6}", color):
            raise ObjectValidationError("marking_color must be #RRGGBB")
        identifier = new_id()
        with UnitOfWork(self._engine) as uow:
            try:
                uow.execute(
                    room.insert().values(
                        id=identifier,
                        project_id=project_id,
                        building_id=building_id,
                        name=clean,
                        normalized_name=normalize_identity(clean),
                        base_mark=None if base is None else str(base),
                        height_m_decimal=None if height is None else str(height),
                        display_json={"marking_color": color},
                    )
                )
                if color == DEFAULT_ROOM_COLOR:
                    _assign_default_colors_in_uow(uow, project_id, datetime.now(UTC))
                uow.execute(
                    update(project)
                    .where(project.c.id == project_id)
                    .values(
                        project_revision=project.c.project_revision + 1,
                        updated_at_utc=datetime.now(UTC),
                    )
                )
                uow.commit()
            except IntegrityError as exc:
                raise DuplicateIdentityError(
                    f"Room already exists in this building: {clean}"
                ) from exc
        return identifier

    def update_room(
        self,
        *,
        project_id: str,
        room_id: str,
        building_id: str,
        name: str,
        base_mark_mm: Decimal | str | None,
        height_m: Decimal | str | None,
        marking_color: str,
    ) -> None:
        clean = name.strip()
        base = _decimal(base_mark_mm, "base_mark_mm")
        height = _decimal(height_m, "height_m", non_negative=True)
        color = marking_color.strip().upper()
        if not clean or not re.fullmatch(r"#[0-9A-F]{6}", color):
            raise ObjectValidationError("Valid room name and #RRGGBB color are required")
        with UnitOfWork(self._engine) as uow:
            try:
                previous = (
                    uow.execute(
                        select(room.c.base_mark, room.c.height_m_decimal).where(
                            room.c.id == room_id, room.c.project_id == project_id
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if previous is None:
                    raise ObjectValidationError("Room not found")
                result = uow.execute(
                    update(room)
                    .where(room.c.id == room_id, room.c.project_id == project_id)
                    .values(
                        building_id=building_id,
                        name=clean,
                        normalized_name=normalize_identity(clean),
                        base_mark=None if base is None else str(base),
                        height_m_decimal=None if height is None else str(height),
                        display_json={"marking_color": color},
                        updated_at_utc=datetime.now(UTC),
                        row_version=room.c.row_version + 1,
                    )
                )
                if result.rowcount != 1:
                    raise ObjectValidationError("Room not found")
                if previous["base_mark"] != (None if base is None else str(base)) or previous[
                    "height_m_decimal"
                ] != (None if height is None else str(height)):
                    recalculate_segments(uow, project_id, room_ids={room_id})
                uow.execute(
                    update(project)
                    .where(project.c.id == project_id)
                    .values(
                        project_revision=project.c.project_revision + 1,
                        updated_at_utc=datetime.now(UTC),
                    )
                )
                uow.commit()
            except IntegrityError as exc:
                raise DuplicateIdentityError(
                    f"Room already exists in this building: {clean}"
                ) from exc

    def preview_room_migration(
        self,
        *,
        project_id: str,
        building_id: str,
        canonical_names: list[str] | tuple[str, ...],
    ) -> RoomMigrationPreview:
        names = _canonical_room_names(canonical_names)
        with self._engine.connect() as connection:
            building_exists = connection.scalar(
                select(building.c.id).where(
                    building.c.id == building_id,
                    building.c.project_id == project_id,
                )
            )
            if building_exists is None:
                raise ObjectValidationError("Building not found")
            rows = list(
                connection.execute(
                    select(room).where(
                        room.c.project_id == project_id,
                        room.c.building_id == building_id,
                    )
                ).mappings()
            )
            device_rooms = list(
                connection.execute(
                    select(field_device.c.id, field_device.c.room_id).where(
                        field_device.c.project_id == project_id,
                        field_device.c.lifecycle == "ACTIVE",
                        field_device.c.room_id.is_not(None),
                    )
                ).mappings()
            )
        actions, targets, ambiguities = _room_migration_plan(rows, names)
        reassigned: list[tuple[str, str]] = []
        target_by_id = {item.id: item for item in targets}
        existing_by_id = {row["id"]: row for row in rows}
        for device in device_rooms:
            source = existing_by_id.get(device["room_id"])
            if source is None:
                continue
            resolution = resolve_room(targets, source["name"])
            target = target_by_id.get(resolution.room_id or "")
            if target is not None and target.id != source["id"]:
                reassigned.append((device["id"], target.name))
        return RoomMigrationPreview(
            project_id=project_id,
            building_id=building_id,
            actions=tuple(actions),
            device_reassignments=tuple(sorted(reassigned)),
            ambiguities=tuple(ambiguities),
        )

    def migrate_rooms(
        self,
        *,
        project_id: str,
        building_id: str,
        canonical_names: list[str] | tuple[str, ...],
    ) -> RoomMigrationPreview:
        """Apply one reviewed canonical-room migration atomically through the UoW."""

        names = _canonical_room_names(canonical_names)
        with UnitOfWork(self._engine) as uow:
            building_exists = uow.execute(
                select(building.c.id).where(
                    building.c.id == building_id,
                    building.c.project_id == project_id,
                )
            ).scalar_one_or_none()
            if building_exists is None:
                raise ObjectValidationError("Building not found")
            rows = list(
                uow.execute(
                    select(room).where(
                        room.c.project_id == project_id,
                        room.c.building_id == building_id,
                    )
                ).mappings()
            )
            actions, _virtual_targets, ambiguities = _room_migration_plan(rows, names)
            if ambiguities:
                raise ObjectValidationError("Ambiguous room migration: " + "; ".join(ambiguities))

            target_ids: dict[str, str] = {}
            now = datetime.now(UTC)
            for action in actions:
                if action.action == "CREATE":
                    target_id = new_id()
                    uow.execute(
                        room.insert().values(
                            id=target_id,
                            project_id=project_id,
                            building_id=building_id,
                            name=action.canonical_name,
                            normalized_name=normalize_identity(action.canonical_name),
                            display_json={"marking_color": DEFAULT_ROOM_COLOR},
                        )
                    )
                else:
                    target_id = str(action.room_id)
                    if action.action == "RENAME":
                        uow.execute(
                            update(room)
                            .where(room.c.id == target_id, room.c.project_id == project_id)
                            .values(
                                name=action.canonical_name,
                                normalized_name=normalize_identity(action.canonical_name),
                                updated_at_utc=now,
                                row_version=room.c.row_version + 1,
                            )
                        )
                target_ids[action.canonical_name] = target_id

            target_rows = [_RoomCandidate(target_ids[name], name) for name in names]
            existing_by_id = {row["id"]: row for row in rows}
            device_rows = list(
                uow.execute(
                    select(field_device.c.id, field_device.c.room_id).where(
                        field_device.c.project_id == project_id,
                        field_device.c.lifecycle == "ACTIVE",
                        field_device.c.room_id.is_not(None),
                    )
                ).mappings()
            )
            reassignments: list[tuple[str, str]] = []
            for device in device_rows:
                source = existing_by_id.get(device["room_id"])
                if source is None:
                    continue
                resolution = resolve_room(target_rows, source["name"])
                if resolution.room_id is None or resolution.room_id == source["id"]:
                    continue
                uow.execute(
                    update(field_device)
                    .where(field_device.c.id == device["id"])
                    .values(
                        room_id=resolution.room_id,
                        updated_at_utc=now,
                        row_version=field_device.c.row_version + 1,
                    )
                )
                target_name = next(
                    item.name for item in target_rows if item.id == resolution.room_id
                )
                reassignments.append((device["id"], target_name))

            _assign_default_colors_in_uow(uow, project_id, now)
            uow.execute(
                update(project)
                .where(project.c.id == project_id)
                .values(
                    project_revision=project.c.project_revision + 1,
                    updated_at_utc=now,
                )
            )
            uow.commit()
        return RoomMigrationPreview(
            project_id=project_id,
            building_id=building_id,
            actions=tuple(actions),
            device_reassignments=tuple(sorted(reassignments)),
        )

    def preview_room_alias_merge(
        self,
        *,
        project_id: str,
        building_id: str,
        aliases: dict[str, str],
    ) -> RoomAliasMergePreview:
        """Preview exact, user-approved alias retirement without changing data."""

        with self._engine.connect() as connection:
            rows = list(
                connection.execute(
                    select(room).where(
                        room.c.project_id == project_id,
                        room.c.building_id == building_id,
                    )
                ).mappings()
            )
            pairs = _validated_alias_pairs(rows, aliases)
            actions = []
            for source, target in pairs:
                counts = {
                    table.name: int(
                        connection.scalar(
                            select(func.count())
                            .select_from(table)
                            .where(
                                table.c.project_id == project_id,
                                table.c.room_id == source["id"],
                            )
                        )
                        or 0
                    )
                    for table in (board, project_instance, field_device)
                }
                actions.append(
                    RoomAliasMergeAction(
                        source_name=source["name"],
                        target_name=target["name"],
                        source_room_id=source["id"],
                        target_room_id=target["id"],
                        board_reassignments=counts[board.name],
                        project_instance_reassignments=counts[project_instance.name],
                        field_device_reassignments=counts[field_device.name],
                    )
                )
        return RoomAliasMergePreview(project_id, building_id, tuple(actions))

    def merge_room_aliases(
        self,
        *,
        project_id: str,
        building_id: str,
        aliases: dict[str, str],
    ) -> RoomAliasMergePreview:
        """Atomically reassign all room FKs, prove zero dangling refs, then retire aliases."""

        with UnitOfWork(self._engine) as uow:
            rows = list(
                uow.execute(
                    select(room).where(
                        room.c.project_id == project_id,
                        room.c.building_id == building_id,
                    )
                ).mappings()
            )
            pairs = _validated_alias_pairs(rows, aliases)
            now = datetime.now(UTC)
            actions = []
            affected_target_ids: set[str] = set()
            for source, target in pairs:
                counts = {}
                for table in (board, project_instance, field_device):
                    result = uow.execute(
                        update(table)
                        .where(
                            table.c.project_id == project_id,
                            table.c.room_id == source["id"],
                        )
                        .values(
                            room_id=target["id"],
                            updated_at_utc=now,
                            row_version=table.c.row_version + 1,
                        )
                    )
                    counts[table.name] = int(result.rowcount or 0)
                remaining = sum(
                    int(
                        uow.execute(
                            select(func.count())
                            .select_from(table)
                            .where(
                                table.c.project_id == project_id,
                                table.c.room_id == source["id"],
                            )
                        ).scalar_one()
                    )
                    for table in (board, project_instance, field_device)
                )
                if remaining:
                    raise ObjectValidationError(
                        f"Alias still has references and cannot be retired: {source['name']}"
                    )
                deleted = uow.execute(
                    delete(room).where(
                        room.c.id == source["id"],
                        room.c.project_id == project_id,
                        room.c.building_id == building_id,
                    )
                )
                if deleted.rowcount != 1:
                    raise ObjectValidationError(f"Alias room was not retired: {source['name']}")
                affected_target_ids.add(target["id"])
                actions.append(
                    RoomAliasMergeAction(
                        source_name=source["name"],
                        target_name=target["name"],
                        source_room_id=source["id"],
                        target_room_id=target["id"],
                        board_reassignments=counts[board.name],
                        project_instance_reassignments=counts[project_instance.name],
                        field_device_reassignments=counts[field_device.name],
                    )
                )
            recalculate_segments(uow, project_id, room_ids=affected_target_ids)
            uow.execute(
                update(project)
                .where(project.c.id == project_id)
                .values(
                    project_revision=project.c.project_revision + 1,
                    updated_at_utc=now,
                )
            )
            uow.commit()
        return RoomAliasMergePreview(project_id, building_id, tuple(actions))

    def assign_default_room_colors(self, project_id: str) -> dict[str, str]:
        with UnitOfWork(self._engine) as uow:
            now = datetime.now(UTC)
            assignments = _assign_default_colors_in_uow(uow, project_id, now)
            if assignments:
                uow.execute(
                    update(project)
                    .where(project.c.id == project_id)
                    .values(
                        project_revision=project.c.project_revision + 1,
                        updated_at_utc=now,
                    )
                )
            uow.commit()
        return assignments

    def delete_room(self, project_id: str, room_id: str) -> None:
        with UnitOfWork(self._engine) as uow:
            uow.execute(delete(room).where(room.c.id == room_id, room.c.project_id == project_id))
            uow.execute(
                update(project)
                .where(project.c.id == project_id)
                .values(
                    project_revision=project.c.project_revision + 1,
                    updated_at_utc=datetime.now(UTC),
                )
            )
            uow.commit()

    def save_settings(self, project_id: str, settings: ProjectSettings) -> None:
        values = {
            "project_folder": settings.project_folder.strip(),
            "output_folder": settings.output_folder.strip(),
            "versions_folder": settings.versions_folder.strip(),
            "initial_page_number": settings.initial_page_number,
        }
        for key in CABLE_SETTING_DEFAULTS:
            raw = getattr(settings, key)
            values[key] = None if raw is None else str(_decimal(raw, key, non_negative=True))
        with UnitOfWork(self._engine) as uow:
            prior_values = dict(
                uow.execute(
                    select(project_setting.c.setting_key, project_setting.c.value_json).where(
                        project_setting.c.project_id == project_id,
                        project_setting.c.setting_key.in_(tuple(CABLE_SETTING_DEFAULTS)),
                    )
                ).all()
            )
            for key, value in values.items():
                existing = uow.execute(
                    select(project_setting.c.id).where(
                        project_setting.c.project_id == project_id,
                        project_setting.c.setting_key == key,
                    )
                ).scalar_one_or_none()
                if existing:
                    uow.execute(
                        update(project_setting)
                        .where(project_setting.c.id == existing)
                        .values(
                            value_type=SETTING_KEYS[key],
                            value_json=value,
                            updated_at_utc=datetime.now(UTC),
                            row_version=project_setting.c.row_version + 1,
                        )
                    )
                else:
                    uow.execute(
                        project_setting.insert().values(
                            id=new_id(),
                            project_id=project_id,
                            setting_key=key,
                            value_type=SETTING_KEYS[key],
                            value_json=value,
                        )
                    )
            if any(prior_values.get(key) != values[key] for key in CABLE_SETTING_DEFAULTS):
                line_ids = set(
                    uow.execute(
                        select(cable_line.c.id).where(cable_line.c.project_id == project_id)
                    ).scalars()
                )
                recalculate_segments(
                    uow,
                    project_id,
                    line_ids=line_ids,
                    recalculate_geometry=False,
                )
            uow.execute(
                update(project)
                .where(project.c.id == project_id)
                .values(
                    project_revision=project.c.project_revision + 1,
                    updated_at_utc=datetime.now(UTC),
                )
            )
            uow.commit()

    def get_project(self, project_id: str) -> ProjectDetail:
        with self._engine.connect() as connection:
            project_row = (
                connection.execute(
                    select(project).where(
                        project.c.id == project_id, project.c.lifecycle == "ACTIVE"
                    )
                )
                .mappings()
                .one_or_none()
            )
            if project_row is None:
                raise ObjectValidationError("Project not found")
            building_rows = list(
                connection.execute(
                    select(building)
                    .where(building.c.project_id == project_id)
                    .order_by(building.c.display_order, building.c.name)
                ).mappings()
            )
            room_rows = list(
                connection.execute(
                    select(room, building.c.name.label("building_name"))
                    .join(building, building.c.id == room.c.building_id)
                    .where(room.c.project_id == project_id)
                    .order_by(building.c.display_order, func.lower(room.c.name))
                ).mappings()
            )
            settings_rows = connection.execute(
                select(project_setting.c.setting_key, project_setting.c.value_json).where(
                    project_setting.c.project_id == project_id
                )
            ).all()
        settings_map = dict(settings_rows)
        settings = ProjectSettings(
            project_folder=settings_map.get("project_folder") or "",
            output_folder=settings_map.get("output_folder") or "",
            versions_folder=settings_map.get("versions_folder") or "",
            initial_page_number=settings_map.get("initial_page_number"),
            cable_reserve_at_board_m=_decimal(
                settings_map.get(
                    "cable_reserve_at_board_m",
                    str(CABLE_SETTING_DEFAULTS["cable_reserve_at_board_m"]),
                ),
                "cable_reserve_at_board_m",
            ),
            cable_reserve_at_distribution_box_m=_decimal(
                settings_map.get(
                    "cable_reserve_at_distribution_box_m",
                    str(CABLE_SETTING_DEFAULTS["cable_reserve_at_distribution_box_m"]),
                ),
                "cable_reserve_at_distribution_box_m",
            ),
            cable_reserve_at_endpoint_m=_decimal(
                settings_map.get(
                    "cable_reserve_at_endpoint_m",
                    str(CABLE_SETTING_DEFAULTS["cable_reserve_at_endpoint_m"]),
                ),
                "cable_reserve_at_endpoint_m",
            ),
            cable_meander_percent=_decimal(
                settings_map.get(
                    "cable_meander_percent",
                    str(CABLE_SETTING_DEFAULTS["cable_meander_percent"]),
                ),
                "cable_meander_percent",
            ),
            cable_obstacle_percent=_decimal(
                settings_map.get(
                    "cable_obstacle_percent",
                    str(CABLE_SETTING_DEFAULTS["cable_obstacle_percent"]),
                ),
                "cable_obstacle_percent",
            ),
            cable_timber_segment_reserve_m=_decimal(
                settings_map.get(
                    "cable_timber_segment_reserve_m",
                    str(CABLE_SETTING_DEFAULTS["cable_timber_segment_reserve_m"]),
                ),
                "cable_timber_segment_reserve_m",
            ),
        )
        room_records = [
            RoomRecord(
                id=row["id"],
                building_id=row["building_id"],
                building_name=row["building_name"],
                name=row["name"],
                base_mark_mm=_decimal(row["base_mark"], "base_mark"),
                height_m=_decimal(row["height_m_decimal"], "height_m"),
                marking_color=(row["display_json"] or {}).get("marking_color", "#FFFFFF"),
            )
            for row in room_rows
        ]
        building_order = {row["id"]: row["display_order"] for row in building_rows}
        room_records.sort(
            key=lambda item: (
                building_order.get(item.building_id, 10**9),
                room_natural_key(item),
            )
        )
        return ProjectDetail(
            id=project_id,
            card=_card(dict(project_row)),
            settings=settings,
            buildings=tuple(
                BuildingRecord(row["id"], row["name"], row["display_order"])
                for row in building_rows
            ),
            rooms=tuple(room_records),
        )
