"""Transactional cable, conduit, AV and cable-catalog use cases."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import Engine, delete, func, select, update
from sqlalchemy.exc import IntegrityError

from nl_project_2.objects.room_rules import DEFAULT_ROOM_COLOR
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    av_cable_profile,
    board,
    building,
    cable_catalog_release,
    cable_length_fact,
    cable_line,
    cable_line_product_selection,
    cable_point,
    cable_point_field_device,
    cable_product_definition,
    cable_segment,
    cable_topology_endpoint,
    catalog_release,
    conduit,
    conduit_segment_assignment,
    field_device,
    field_port,
    instance_resource,
    operation_journal,
    passport_definition,
    product_definition,
    project,
    project_instance,
    room,
)
from nl_project_2.persistence.uow import UnitOfWork
from nl_project_2.resource_labels import resource_user_label

from .domain import (
    MOUNT_WAY_BY_ROUTE_METHOD,
    ROUTE_METHOD_BY_MOUNT_WAY,
    ConduitContractError,
    LengthResult,
    RouteMethod,
    calculate_effective_length,
    conduit_length_from_segment_length,
    conduit_type_suffix,
    format_conduit_id,
    parse_conduit_id,
    validate_line_conduit_fields,
)
from .recalculation import (
    RecalculationError,
    _remove_assignment_and_empty_auto,
    board_reserve_for_line,
    recalculate_segments,
    refresh_conduit_length,
    segment_geometry_diagnostics,
)

AV_LOAD_TYPES = frozenset({"SPEAKER_CABLE", "HDMI"})
CABLE_CATEGORIES = frozenset({"SPEAKER_CABLE", "HDMI", "OTHER_APPROVED_CABLE"})


def _conduit_product_facts(row) -> tuple[str, int, str]:
    suffix = conduit_type_suffix(row["conduit_type"])
    match = re.fullmatch(r"([A-Z]+)([0-9]+)", suffix)
    if match is None:
        raise CableError("Conduit type has no canonical material and nominal size")
    color = str(row["color"] or "").strip().casefold()
    canonical_color = {"синий": "BLUE", "blue": "BLUE"}.get(color, color.upper())
    return match.group(1), int(match.group(2)), canonical_color


def _product_matches_conduit(row, parameters: dict) -> bool:
    material, nominal, color = _conduit_product_facts(row)
    return (
        str(parameters.get("material_code", "")).upper() == material
        and int(parameters.get("nominal_diameter_mm", -1)) == nominal
        and str(parameters.get("color", "")).upper() == color
    )


class CableError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class HdmiSelectionResult:
    product_id: str
    required_length_m: Decimal
    factory_length_m: Decimal
    warning: str | None


class CableService:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def list_lines(self, project_id: str) -> list[dict]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(cable_line)
                .where(cable_line.c.project_id == project_id, cable_line.c.lifecycle == "ACTIVE")
                .order_by(cable_line.c.system_kind, cable_line.c.designation)
            ).mappings()
            return [dict(row) for row in rows]

    def topology(self, project_id: str, cable_line_id: str) -> dict:
        """Return user-facing physical topology, segment facts and route breakdown."""

        with self._engine.connect() as connection:
            line = (
                connection.execute(
                    select(cable_line).where(
                        cable_line.c.id == cable_line_id,
                        cable_line.c.project_id == project_id,
                        cable_line.c.lifecycle == "ACTIVE",
                    )
                )
                .mappings()
                .one_or_none()
            )
            if line is None:
                raise CableError("Cable line not found")
            endpoint_rows = {
                row["id"]: dict(row)
                for row in connection.execute(
                    select(cable_topology_endpoint).where(
                        cable_topology_endpoint.c.project_id == project_id,
                        cable_topology_endpoint.c.cable_line_id == cable_line_id,
                    )
                ).mappings()
            }
            point_rows = {
                row["id"]: dict(row)
                for row in connection.execute(
                    select(cable_point).where(
                        cable_point.c.project_id == project_id,
                        cable_point.c.cable_line_id == cable_line_id,
                    )
                ).mappings()
            }
            point_devices: dict[str, list[dict]] = {}
            for device_row in connection.execute(
                select(
                    cable_point_field_device.c.cable_point_id,
                    field_device.c.block_kind,
                    field_device.c.room_id,
                    field_device.c.normalized_fields_json,
                    room.c.name.label("room_name"),
                    building.c.name.label("building_name"),
                )
                .join(
                    field_device,
                    field_device.c.id == cable_point_field_device.c.field_device_id,
                )
                .outerjoin(room, room.c.id == field_device.c.room_id)
                .outerjoin(building, building.c.id == room.c.building_id)
                .where(
                    cable_point_field_device.c.project_id == project_id,
                    cable_point_field_device.c.cable_point_id.in_(tuple(point_rows)),
                    field_device.c.lifecycle == "ACTIVE",
                )
            ).mappings():
                point_devices.setdefault(device_row["cable_point_id"], []).append(dict(device_row))
            port_rows = {
                row["id"]: dict(row)
                for row in connection.execute(
                    select(
                        field_port.c.id,
                        field_port.c.port_tag,
                        field_device.c.normalized_fields_json,
                    )
                    .select_from(
                        field_port.join(
                            field_device,
                            field_device.c.id == field_port.c.field_device_id,
                        )
                    )
                    .where(field_port.c.project_id == project_id)
                ).mappings()
            }
            resources = {
                row["id"]: dict(row)
                for row in connection.execute(
                    select(
                        instance_resource,
                        project_instance.c.designation.label("instance_designation"),
                    )
                    .join(
                        project_instance,
                        project_instance.c.id == instance_resource.c.project_instance_id,
                    )
                    .where(instance_resource.c.project_id == project_id)
                ).mappings()
            }
            segments = [
                dict(row)
                for row in connection.execute(
                    select(cable_segment).where(
                        cable_segment.c.project_id == project_id,
                        cable_segment.c.cable_line_id == cable_line_id,
                    )
                ).mappings()
            ]
            conduit_rows = {
                row["segment_id"]: dict(row)
                for row in connection.execute(
                    select(
                        conduit_segment_assignment.c.cable_segment_id.label("segment_id"),
                        conduit.c.id.label("conduit_id"),
                        conduit.c.designation.label("conduit_designation"),
                        conduit.c.conduit_type,
                        conduit.c.color.label("conduit_color"),
                        conduit.c.length_m_decimal.label("conduit_length_m"),
                        product_definition.c.name.label("conduit_product_name"),
                        product_definition.c.article.label("conduit_product_article"),
                    )
                    .select_from(
                        conduit_segment_assignment.join(
                            cable_segment,
                            cable_segment.c.id == conduit_segment_assignment.c.cable_segment_id,
                        )
                        .join(
                            conduit,
                            conduit.c.id == conduit_segment_assignment.c.conduit_id,
                        )
                        .outerjoin(
                            product_definition,
                            product_definition.c.id == conduit.c.product_definition_id,
                        )
                    )
                    .where(
                        conduit_segment_assignment.c.project_id == project_id,
                        cable_segment.c.project_id == project_id,
                        cable_segment.c.cable_line_id == cable_line_id,
                    )
                ).mappings()
            }
            length_row = (
                connection.execute(
                    select(cable_length_fact).where(
                        cable_length_fact.c.project_id == project_id,
                        cable_length_fact.c.cable_line_id == cable_line_id,
                    )
                )
                .mappings()
                .one_or_none()
            )

        facts = dict(line["cable_facts_json"] or {})

        def endpoint_value(endpoint_id: str) -> dict:
            endpoint = endpoint_rows[endpoint_id]
            if endpoint["endpoint_kind"] == "FIELD_PORT":
                port = port_rows[endpoint["field_port_id"]]
                point_id = str((port["normalized_fields_json"] or {}).get("BUS_POINT_ID", ""))
                reference = f"{point_id}/{port['port_tag']}"
                return {
                    "kind": "FIELD_PORT",
                    "reference": reference,
                    "label": reference,
                }
            if endpoint["endpoint_kind"] == "INSTANCE_RESOURCE":
                reference = str(endpoint["instance_resource_id"])
                return {
                    "kind": "INSTANCE_RESOURCE",
                    "resource_id": reference,
                    "label": resource_user_label(resources.get(reference)),
                }
            point = point_rows[endpoint["cable_point_id"]]
            if point["point_kind"] == "INTERNAL_SOURCE":
                board_name = str(facts.get("BOARD", "") or "")
                return {
                    "kind": "BOARD_OUTPUT",
                    "board": board_name,
                    "label": f"Щит {board_name}" if board_name else "Источник линии",
                }
            reference = str(point["logical_identity"])
            members = point_devices.get(point["id"], [])
            descriptions: list[str] = []
            room_names: list[str] = []
            building_names: list[str] = []
            unresolved_room = False
            for member in members:
                fields = dict(member["normalized_fields_json"] or {})
                description = str(
                    fields.get("DEVICE_NAME")
                    or fields.get("LOAD_NAME")
                    or member["block_kind"]
                    or ""
                ).strip()
                if description and description not in descriptions:
                    descriptions.append(description)
                canonical_room = str(member.get("room_name") or "").strip()
                raw_room = str(fields.get("ROOM") or "").strip()
                display_room = canonical_room or raw_room
                if display_room and display_room not in room_names:
                    room_names.append(display_room)
                canonical_building = str(member.get("building_name") or "").strip()
                raw_building = str(fields.get("BUILDING") or "").strip()
                display_building = canonical_building or raw_building
                if display_building and display_building not in building_names:
                    building_names.append(display_building)
                if raw_room and member.get("room_id") is None:
                    unresolved_room = True
            return {
                "kind": "TOPOLOGY_POINT",
                "reference": reference,
                "point_kind": point["point_kind"],
                "label": reference,
                "description": " / ".join(descriptions),
                "room_names": ", ".join(room_names),
                "building_names": ", ".join(building_names),
                "room_unresolved": unresolved_room,
            }

        diagnostics: dict[str, dict] = {}
        with UnitOfWork(self._engine) as uow:
            for row in segments:
                diagnostics[row["id"]] = segment_geometry_diagnostics(uow, project_id, row)
            board_reserve = board_reserve_for_line(uow, project_id, cable_line_id)
            uow.rollback()

        def missing_text(codes: tuple[str, ...]) -> str:
            labels = {
                "x": "координаты X",
                "y": "координаты Y",
                "mount": "высоты установки (MOUNT_HEIGHT)",
                "base": "отметки основания пола",
                "height": "высоты потолка помещения",
                "ambiguous_shared_endpoint_geometry": "неоднозначная геометрия общей точки",
                "invalid_endpoint_geometry": "некорректная геометрия точки",
                "mount_way": "способ прокладки",
                "room": "помещения (канонической связи)",
                "not_calculated": "сохранённый расчёт; выполните пересчёт",
                "stale_calculation": "актуальный расчёт; выполните пересчёт",
            }
            parts = []
            for code in codes:
                side, _, key = code.partition(":")
                if not key:
                    key = side
                    side = ""
                prefix = "Источник" if side == "source" else "Приёмник" if side == "target" else ""
                value = labels.get(key, key)
                reason = (
                    value
                    if key in {"ambiguous_shared_endpoint_geometry", "invalid_endpoint_geometry"}
                    else f"нет {value}"
                )
                parts.append(f"{prefix}: {reason}" if prefix else reason.capitalize())
            return "; ".join(parts)

        target_ids = {row["target_endpoint_id"] for row in segments}
        root_ids = {
            row["source_endpoint_id"]
            for row in segments
            if row["source_endpoint_id"] not in target_ids
        }
        root = endpoint_value(next(iter(root_ids))) if len(root_ids) == 1 else None

        adjacency: dict[str, list[dict]] = {}
        for row in segments:
            adjacency.setdefault(row["source_endpoint_id"], []).append(row)
        ordered: list[tuple[int, dict]] = []
        visited: set[str] = set()

        def walk(source_id: str, depth: int) -> None:
            rows = sorted(
                adjacency.get(source_id, []),
                key=lambda item: endpoint_value(item["target_endpoint_id"])["label"],
            )
            for row in rows:
                if row["id"] in visited:
                    continue
                visited.add(row["id"])
                ordered.append((depth, row))
                walk(row["target_endpoint_id"], depth + 1)

        for root_id in sorted(root_ids, key=lambda value: endpoint_value(value)["label"]):
            walk(root_id, 0)
        for row in sorted(segments, key=lambda item: item["id"]):
            if row["id"] not in visited:
                ordered.append((0, row))

        breakdown: dict[str, dict[str, object]] = {}
        edges = []
        for depth, row in ordered:
            diag = diagnostics[row["id"]]
            calculated = row["calculated_length_m_decimal"]
            if diag["complete"] and calculated is None:
                diag = {"complete": False, "missing": ("not_calculated",)}
            elif diag["complete"] and Decimal(calculated) != Decimal(diag["calculated_length_m"]):
                diag = {"complete": False, "missing": ("stale_calculation",)}
            if not diag["complete"]:
                calculated = None
            cable_length = Decimal(calculated) if calculated is not None else None
            route = ROUTE_METHOD_BY_MOUNT_WAY.get(str(row["mount_way"] or ""))
            physical_length = (
                conduit_length_from_segment_length(cable_length, route)
                if cable_length is not None and route is not None
                else None
            )
            mount_way = str(row["mount_way"] or "Не указано")
            summary = breakdown.setdefault(
                mount_way,
                {
                    "mount_way": mount_way,
                    "physical_m": Decimal(0),
                    "cable_m": Decimal(0),
                    "incomplete_segments": 0,
                },
            )
            if cable_length is None or physical_length is None:
                summary["incomplete_segments"] = int(summary["incomplete_segments"]) + 1
            else:
                summary["physical_m"] = Decimal(summary["physical_m"]) + physical_length
                summary["cable_m"] = Decimal(summary["cable_m"]) + cable_length
            conduit_info = conduit_rows.get(row["id"], {})
            edges.append(
                {
                    "segment_id": row["id"],
                    "depth": depth,
                    "source": endpoint_value(row["source_endpoint_id"]),
                    "target": endpoint_value(row["target_endpoint_id"]),
                    "connection_kind": "CABLE",
                    "mount_way": row["mount_way"] or "",
                    "gofra_type": row["gofra_type"] or "",
                    "gofra_color": row["gofra_color"] or "",
                    "gofra_id": conduit_info.get("conduit_designation") or "",
                    "conduit_id": conduit_info.get("conduit_id"),
                    "conduit_length_m": conduit_info.get("conduit_length_m"),
                    "conduit_product_name": conduit_info.get("conduit_product_name") or "",
                    "conduit_product_article": conduit_info.get("conduit_product_article") or "",
                    "physical_length_m": (
                        None if physical_length is None else str(physical_length)
                    ),
                    "cable_length_m": (None if cable_length is None else str(cable_length)),
                    "calculation_status": "READY" if diag["complete"] else "INCOMPLETE",
                    "calculation_reason": (
                        "" if diag["complete"] else missing_text(diag["missing"])
                    ),
                }
            )

        return {
            "cable_line_id": cable_line_id,
            "designation": line["designation"],
            "cable_type": facts.get("CABLE_TYPE", ""),
            "root_endpoint": root,
            "edges": tuple(edges),
            "route_breakdown": tuple(
                {
                    **value,
                    "physical_m": str(value["physical_m"]),
                    "cable_m": str(value["cable_m"]),
                }
                for _key, value in sorted(breakdown.items())
            ),
            "board_reserve_m": str(board_reserve),
            "additional_m": (
                "0" if length_row is None else str(length_row["additional_length_m_decimal"] or "0")
            ),
            "manual_full_m": (
                None if length_row is None else length_row["manual_full_length_m_decimal"]
            ),
        }

    def project_route_breakdown(self, project_id: str) -> dict:
        """Summarize unique active physical edges, never allocate line-only reserves to routes."""
        groups = {
            title: {
                "mount_way": title,
                "physical_m": Decimal(0),
                "cable_m": Decimal(0),
                "incomplete_segments": 0,
            }
            for title in MOUNT_WAY_BY_ROUTE_METHOD.values()
        }
        with self._engine.connect() as connection:
            segments = connection.execute(
                select(cable_segment)
                .join(cable_line, cable_line.c.id == cable_segment.c.cable_line_id)
                .where(cable_segment.c.project_id == project_id, cable_line.c.lifecycle == "ACTIVE")
            ).mappings()
            for segment in segments:
                method = segment["mount_way"] or "Не указано"
                group = groups.setdefault(
                    method,
                    {
                        "mount_way": method,
                        "physical_m": Decimal(0),
                        "cable_m": Decimal(0),
                        "incomplete_segments": 0,
                    },
                )
                value = segment["calculated_length_m_decimal"]
                route = ROUTE_METHOD_BY_MOUNT_WAY.get(method)
                if value is None or route is None:
                    group["incomplete_segments"] += 1
                else:
                    group["cable_m"] += Decimal(value)
                    group["physical_m"] += conduit_length_from_segment_length(value, route)
        cards = self.line_cards(project_id)
        return {
            "routes": tuple(
                {**group, "physical_m": str(group["physical_m"]), "cable_m": str(group["cable_m"])}
                for group in groups.values()
            ),
            "effective_m": str(
                sum(
                    (
                        Decimal(card["effective_m"])
                        for card in cards
                        if card["effective_m"] is not None
                    ),
                    Decimal(0),
                )
            ),
            "incomplete_lines": sum(card["effective_m"] is None for card in cards),
            "manual_lines": sum(card.get("manual_full_m") is not None for card in cards),
        }

    def line_cards(self, project_id: str) -> list[dict]:
        with self._engine.connect() as connection:
            room_rows = connection.execute(
                select(
                    cable_point.c.cable_line_id,
                    building.c.name.label("building_name"),
                    room.c.id.label("room_id"),
                    room.c.name.label("room_name"),
                    room.c.display_json.label("room_display_json"),
                )
                .join(
                    cable_point_field_device,
                    cable_point_field_device.c.cable_point_id == cable_point.c.id,
                )
                .join(
                    field_device,
                    field_device.c.id == cable_point_field_device.c.field_device_id,
                )
                .join(room, room.c.id == field_device.c.room_id)
                .join(building, building.c.id == room.c.building_id)
                .where(
                    cable_point.c.project_id == project_id,
                    field_device.c.lifecycle == "ACTIVE",
                )
                .order_by(cable_point.c.cable_line_id, cable_point.c.ordinal)
            ).all()
            unresolved_room_rows = connection.execute(
                select(
                    cable_point.c.cable_line_id,
                    field_device.c.normalized_fields_json,
                )
                .join(
                    cable_point_field_device,
                    cable_point_field_device.c.cable_point_id == cable_point.c.id,
                )
                .join(
                    field_device,
                    field_device.c.id == cable_point_field_device.c.field_device_id,
                )
                .where(
                    cable_point.c.project_id == project_id,
                    field_device.c.lifecycle == "ACTIVE",
                    field_device.c.room_id.is_(None),
                )
                .order_by(cable_point.c.cable_line_id, cable_point.c.ordinal)
            ).all()
        room_markers_by_line: dict[str, dict[str, dict[str, str]]] = {}
        building_names_by_line: dict[str, list[str]] = {}
        unresolved_room_names_by_line: dict[str, list[str]] = {}
        for cable_line_id, building_name, room_id, room_name, room_display in room_rows:
            clean_name = str(room_name or "").strip()
            if clean_name:
                markers = room_markers_by_line.setdefault(cable_line_id, {})
                markers.setdefault(
                    room_id,
                    {
                        "id": room_id,
                        "name": clean_name,
                        "color": (room_display or {}).get("marking_color", DEFAULT_ROOM_COLOR),
                    },
                )
            clean_building = str(building_name or "").strip()
            names = building_names_by_line.setdefault(cable_line_id, [])
            if clean_building and clean_building not in names:
                names.append(clean_building)
        for cable_line_id, fields in unresolved_room_rows:
            raw_room = str((fields or {}).get("ROOM") or "").strip()
            if not raw_room:
                continue
            names = unresolved_room_names_by_line.setdefault(cable_line_id, [])
            if raw_room not in names:
                names.append(raw_room)
        cards = []
        for row in self.list_lines(project_id):
            facts = dict(row["cable_facts_json"] or {})
            with self._engine.connect() as connection:
                route_rows = list(
                    connection.execute(
                        select(
                            cable_segment.c.mount_way,
                            cable_segment.c.gofra_type,
                            cable_segment.c.gofra_color,
                            cable_segment.c.calculated_length_m_decimal,
                            conduit.c.designation,
                        )
                        .outerjoin(
                            conduit_segment_assignment,
                            conduit_segment_assignment.c.cable_segment_id == cable_segment.c.id,
                        )
                        .outerjoin(
                            conduit,
                            conduit.c.id == conduit_segment_assignment.c.conduit_id,
                        )
                        .where(
                            cable_segment.c.project_id == project_id,
                            cable_segment.c.cable_line_id == row["id"],
                        )
                    ).mappings()
                )

            def uniform(key: str, route_rows=route_rows) -> str:
                values = {str(item[key] or "") for item in route_rows}
                return values.pop() if len(values) == 1 else ("" if not values else "MIXED")

            mount_way = uniform("mount_way")
            room_markers = tuple(room_markers_by_line.get(row["id"], {}).values())
            conduit_designations = {
                str(item["designation"])
                for item in route_rows
                if str(item["designation"] or "").strip()
            }
            incomplete_segments = sum(
                1 for item in route_rows if item["calculated_length_m_decimal"] is None
            )
            card = {
                **row,
                "route_method": str(ROUTE_METHOD_BY_MOUNT_WAY.get(mount_way, "")),
                "mount_way": mount_way,
                "gofra_type": uniform("gofra_type"),
                "gofra_color": uniform("gofra_color"),
                "gofra_id": uniform("designation"),
                "cable_type": facts.get("CABLE_TYPE", ""),
                "board": facts.get("BOARD", ""),
                "load_name": facts.get("LOAD_NAME", ""),
                "load_type": facts.get("LOAD_TYPE", ""),
                "building_names": ", ".join(building_names_by_line.get(row["id"], [])),
                "room_names": ", ".join(item["name"] for item in room_markers),
                "room_markers": room_markers,
                "unresolved_room_names": tuple(unresolved_room_names_by_line.get(row["id"], [])),
                "conduit_count": len(conduit_designations),
                "incomplete_segments": incomplete_segments,
                "automatic_m": None,
                "additional_m": None,
                "manual_full_m": None,
                "effective_m": None,
                "length_mode": "Не рассчитана",
                "length_explanation": "Итоговая длина пока не определена",
            }
            with self._engine.connect() as connection:
                length = (
                    connection.execute(
                        select(cable_length_fact).where(
                            cable_length_fact.c.project_id == project_id,
                            cable_length_fact.c.cable_line_id == row["id"],
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
            if length:
                manual = length["manual_full_length_m_decimal"]
                additional = Decimal(length["additional_length_m_decimal"] or "0")
                if manual is not None:
                    mode = "Полная ручная"
                    explanation = "Полная ручная длина заменяет автоматический расчёт и запас"
                elif additional:
                    mode = "Автоматическая + дополнительная"
                    explanation = "Сумма сегментов, дополнительная длина и применимый запас у щита"
                else:
                    mode = "Автоматическая"
                    explanation = "Сумма уникальных физических сегментов и применимый запас у щита"
                try:
                    effective = str(self.effective_length(project_id, row["id"]).effective_m)
                except CableError:
                    effective = None
                card.update(
                    automatic_m=length["calculated_length_m_decimal"],
                    additional_m=length["additional_length_m_decimal"],
                    manual_full_m=length["manual_full_length_m_decimal"],
                    effective_m=effective,
                    length_mode=mode,
                    length_explanation=explanation,
                )
            cards.append(card)
        return cards

    def batch_update_line_fields(self, *, project_id: str, edits: Iterable[dict]) -> None:
        """Atomically update existing line-owned scalar fields used by spreadsheet UI."""

        normalized: dict[tuple[str, str], str] = {}
        for edit in edits:
            line_id = str(edit.get("cable_line_id", "")).strip()
            field = str(edit.get("field", "")).strip().upper()
            if field not in {"BOARD", "CABLE_TYPE"}:
                raise CableError(f"Поле {field or '<empty>'} недоступно для табличного изменения")
            value = _required(str(edit.get("value", "")), field.lower())
            key = (line_id, field)
            if not line_id:
                raise CableError("Cable line id is required")
            if key in normalized and normalized[key] != value:
                raise CableError("Одна ячейка получила несколько разных значений")
            normalized[key] = value
        if not normalized:
            raise CableError("Не выбраны изменяемые ячейки")

        line_ids = {line_id for line_id, _field in normalized}
        now = datetime.now(UTC)
        with UnitOfWork(self._engine) as uow:
            revision_before = int(
                uow.execute(
                    select(project.c.project_revision).where(project.c.id == project_id)
                ).scalar_one()
            )
            rows = {
                row["id"]: dict(row)
                for row in uow.execute(
                    select(cable_line).where(
                        cable_line.c.project_id == project_id,
                        cable_line.c.id.in_(line_ids),
                        cable_line.c.lifecycle == "ACTIVE",
                    )
                ).mappings()
            }
            missing = sorted(line_ids - rows.keys())
            if missing:
                raise CableError(f"Кабельная линия не найдена: {missing[0]}")

            for line_id in sorted(line_ids):
                facts = dict(rows[line_id]["cable_facts_json"] or {})
                changed_values = {
                    field: value
                    for (owner_id, field), value in normalized.items()
                    if owner_id == line_id
                }
                facts.update(changed_values)
                uow.execute(
                    update(cable_line)
                    .where(cable_line.c.id == line_id)
                    .values(
                        cable_facts_json=facts,
                        row_version=cable_line.c.row_version + 1,
                        updated_at_utc=now,
                    )
                )
                self._set_device_line_fields(uow, project_id, line_id, changed_values)
                if "BOARD" in changed_values:
                    recalculate_segments(
                        uow, project_id, line_ids={line_id}, reconcile_conduits=False
                    )
            self._touch_project(uow, project_id, now)
            command_id = new_id()
            uow.execute(
                operation_journal.insert().values(
                    id=new_id(),
                    project_id=project_id,
                    command_id=command_id,
                    command_type="LINE_SCALAR_BATCH_UPDATE",
                    project_revision_before=revision_before,
                    project_revision_after=revision_before + 1,
                    correlation_id=command_id,
                    status="SUCCEEDED",
                    started_at_utc=now,
                    completed_at_utc=now,
                    summary_json={
                        "human_summary": "Изменены данные кабельных линий",
                        "selection_count": len(line_ids),
                        "canonical_fact_count": len(normalized),
                        "fields": sorted({field for _line_id, field in normalized}),
                    },
                )
            )
            uow.commit()

    def list_conduits(self, project_id: str) -> list[dict]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(
                    conduit,
                    product_definition.c.name.label("product_name"),
                    product_definition.c.article.label("product_article"),
                    func.count(conduit_segment_assignment.c.id).label("line_count"),
                )
                .outerjoin(
                    product_definition,
                    product_definition.c.id == conduit.c.product_definition_id,
                )
                .outerjoin(
                    conduit_segment_assignment,
                    conduit_segment_assignment.c.conduit_id == conduit.c.id,
                )
                .where(conduit.c.project_id == project_id, conduit.c.lifecycle == "ACTIVE")
                .group_by(conduit.c.id)
                .order_by(conduit.c.designation)
            ).mappings()
            return [dict(row) for row in rows]

    def list_conduit_routes(self, project_id: str) -> list[dict]:
        """Return conduit parents with exact segment children."""

        with self._engine.connect() as connection:
            parents = [
                dict(row)
                for row in connection.execute(
                    select(
                        conduit,
                        product_definition.c.name.label("product_name"),
                        product_definition.c.article.label("product_article"),
                    )
                    .outerjoin(
                        product_definition,
                        product_definition.c.id == conduit.c.product_definition_id,
                    )
                    .where(conduit.c.project_id == project_id, conduit.c.lifecycle == "ACTIVE")
                    .order_by(conduit.c.conduit_number, conduit.c.designation)
                ).mappings()
            ]
            children = list(
                connection.execute(
                    select(
                        conduit_segment_assignment.c.conduit_id,
                        cable_segment.c.id.label("segment_id"),
                        cable_line.c.id,
                        cable_line.c.designation,
                        cable_line.c.cable_facts_json,
                    )
                    .join(
                        cable_segment,
                        cable_segment.c.id == conduit_segment_assignment.c.cable_segment_id,
                    )
                    .join(
                        cable_line,
                        cable_line.c.id == cable_segment.c.cable_line_id,
                    )
                    .where(
                        conduit_segment_assignment.c.project_id == project_id,
                        cable_line.c.lifecycle == "ACTIVE",
                    )
                    .order_by(cable_line.c.designation)
                ).mappings()
            )
        by_conduit: dict[str, list[dict]] = {}
        for row in children:
            facts = dict(row["cable_facts_json"] or {})
            by_conduit.setdefault(row["conduit_id"], []).append(
                {
                    "id": row["segment_id"],
                    "cable_line_id": row["id"],
                    "designation": row["designation"],
                    "load_name": facts.get("LOAD_NAME", ""),
                    "cable_type": facts.get("CABLE_TYPE", ""),
                }
            )
        topologies = {
            line_id: {
                edge["segment_id"]: edge for edge in self.topology(project_id, line_id)["edges"]
            }
            for line_id in {
                child["cable_line_id"] for rows in by_conduit.values() for child in rows
            }
        }
        for parent in parents:
            parent["lines"] = by_conduit.get(parent["id"], [])
            for child in parent["lines"]:
                edge = topologies[child["cable_line_id"]][child["id"]]
                child.update(
                    source=edge["source"]["label"],
                    target=edge["target"]["label"],
                    mount_way=edge["mount_way"],
                    physical_m=edge["physical_length_m"],
                    cable_m=edge["cable_length_m"],
                    calculation_reason=edge["calculation_reason"],
                )
            parent["product_display"] = (
                f"{parent['product_name']} · арт. {parent['product_article']}"
                if parent["product_name"]
                else "Товар трубы не выбран"
            )
        return parents

    def conduit_product_candidates(self, *, project_id: str, conduit_id: str) -> list[dict]:
        """Return active catalog products compatible with exact conduit facts."""

        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    select(conduit).where(
                        conduit.c.id == conduit_id,
                        conduit.c.project_id == project_id,
                        conduit.c.lifecycle == "ACTIVE",
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise CableError("Conduit not found")
            products = connection.execute(
                select(
                    product_definition,
                    passport_definition.c.equipment_class,
                )
                .join(
                    passport_definition,
                    passport_definition.c.id == product_definition.c.passport_definition_id,
                )
                .join(
                    catalog_release,
                    catalog_release.c.id == product_definition.c.catalog_release_id,
                )
                .where(
                    catalog_release.c.status == "ACTIVE",
                    product_definition.c.lifecycle == "ACTIVE",
                    passport_definition.c.lifecycle == "ACTIVE",
                    passport_definition.c.equipment_class == "FLEXIBLE_CORRUGATED_PP_CONDUIT",
                )
                .order_by(product_definition.c.manufacturer, product_definition.c.article)
            ).mappings()
            return [
                dict(product)
                for product in products
                if _product_matches_conduit(row, product["project_parameters_json"] or {})
            ]

    def select_conduit_product(
        self, *, project_id: str, conduit_id: str, product_definition_id: str
    ) -> None:
        candidates = {
            row["id"]
            for row in self.conduit_product_candidates(project_id=project_id, conduit_id=conduit_id)
        }
        if product_definition_id not in candidates:
            raise CableError("Product is not compatible with conduit material, diameter and color")
        with UnitOfWork(self._engine) as uow:
            result = uow.execute(
                update(conduit)
                .where(
                    conduit.c.id == conduit_id,
                    conduit.c.project_id == project_id,
                    conduit.c.lifecycle == "ACTIVE",
                )
                .values(
                    product_definition_id=product_definition_id,
                    row_version=conduit.c.row_version + 1,
                    updated_at_utc=datetime.now(UTC),
                )
            )
            if result.rowcount != 1:
                raise CableError("Conduit not found")
            self._touch_project(uow, project_id, datetime.now(UTC))
            uow.commit()

    def update_line_fields(
        self,
        *,
        project_id: str,
        cable_line_id: str,
        cable_type: str,
        board_designation: str,
        mount_way: str | None = None,
        gofra_type: str | None = None,
        gofra_color: str | None = None,
        gofra_id: str | None = None,
    ) -> None:
        with UnitOfWork(self._engine) as uow:
            row = (
                uow.execute(
                    select(cable_line).where(
                        cable_line.c.id == cable_line_id,
                        cable_line.c.project_id == project_id,
                        cable_line.c.lifecycle == "ACTIVE",
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise CableError("Cable line not found")
            facts = dict(row["cable_facts_json"] or {})
            facts["CABLE_TYPE"] = _required(cable_type, "cable_type")
            facts["BOARD"] = _required(board_designation, "board")
            line_values = {
                "CABLE_TYPE": facts["CABLE_TYPE"],
                "BOARD": facts["BOARD"],
            }
            if mount_way is not None:
                segment_id = self._single_segment_id(uow, project_id, cable_line_id)
                values = {
                    "MOUNT_WAY": mount_way.strip(),
                    "GOFRA_TYPE": (gofra_type or "").strip(),
                    "GOFRA_COLOR": (gofra_color or "").strip(),
                    "GOFRA_ID": (gofra_id or "").strip(),
                }
                try:
                    validate_line_conduit_fields(
                        mount_way=values["MOUNT_WAY"],
                        conduit_type=values["GOFRA_TYPE"],
                        conduit_color=values["GOFRA_COLOR"],
                        conduit_id=values["GOFRA_ID"],
                    )
                except ConduitContractError as exc:
                    raise CableError(str(exc)) from exc
                uow.execute(
                    update(cable_segment)
                    .where(cable_segment.c.id == segment_id)
                    .values(
                        mount_way=values["MOUNT_WAY"] or None,
                        gofra_type=values["GOFRA_TYPE"] or None,
                        gofra_color=values["GOFRA_COLOR"] or None,
                        row_version=cable_segment.c.row_version + 1,
                        updated_at_utc=datetime.now(UTC),
                    )
                )
            uow.execute(
                update(cable_line)
                .where(cable_line.c.id == cable_line_id)
                .values(
                    cable_facts_json=facts,
                    row_version=cable_line.c.row_version + 1,
                    updated_at_utc=datetime.now(UTC),
                )
            )
            self._set_device_line_fields(uow, project_id, cable_line_id, line_values)
            self._touch_project(uow, project_id, datetime.now(UTC))
            uow.commit()

    def list_catalog_products(self) -> list[dict]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(
                    cable_product_definition,
                    cable_catalog_release.c.release_code,
                    cable_catalog_release.c.status.label("release_status"),
                )
                .join(
                    cable_catalog_release,
                    cable_catalog_release.c.id
                    == cable_product_definition.c.cable_catalog_release_id,
                )
                .order_by(
                    cable_catalog_release.c.installed_at_utc.desc(),
                    cable_product_definition.c.product_key,
                )
            ).mappings()
            return [dict(row) for row in rows]

    def calculate_and_save_length(
        self,
        *,
        project_id: str,
        cable_line_id: str,
        route_method: RouteMethod,
        additional_m=0,
        manual_full_m=None,
    ) -> LengthResult:
        """Compatibility command for a one-segment line.

        New callers should edit an exact segment and call ``recalculate``.  The
        compatibility boundary is deliberately rejected for branched lines.
        """
        now = datetime.now(UTC)
        with UnitOfWork(self._engine) as uow:
            segment_id = self._single_segment_id(uow, project_id, cable_line_id)
            line_row = (
                uow.execute(
                    select(cable_line).where(
                        cable_line.c.id == cable_line_id,
                        cable_line.c.project_id == project_id,
                        cable_line.c.lifecycle == "ACTIVE",
                    )
                )
                .mappings()
                .one_or_none()
            )
            if line_row is None:
                raise CableError("Cable line not found")
            segment_row = (
                uow.execute(select(cable_segment).where(cable_segment.c.id == segment_id))
                .mappings()
                .one()
            )
            mount_way = MOUNT_WAY_BY_ROUTE_METHOD[route_method]
            try:
                validate_line_conduit_fields(
                    mount_way=mount_way,
                    conduit_type=str(segment_row["gofra_type"] or ""),
                    conduit_color=str(segment_row["gofra_color"] or ""),
                    conduit_id="",
                )
            except ConduitContractError as exc:
                raise CableError(str(exc)) from exc
            uow.execute(
                update(cable_segment)
                .where(cable_segment.c.id == segment_id)
                .values(
                    mount_way=mount_way,
                    row_version=cable_segment.c.row_version + 1,
                    updated_at_utc=now,
                )
            )
            existing = (
                uow.execute(
                    select(cable_length_fact).where(
                        cable_length_fact.c.cable_line_id == cable_line_id,
                        cable_length_fact.c.project_id == project_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
            values = {
                "additional_length_m_decimal": str(
                    _non_negative(additional_m or 0, "additional_m")
                ),
                "manual_full_length_m_decimal": (
                    None
                    if manual_full_m in (None, "")
                    else str(_non_negative(manual_full_m, "manual_full_m"))
                ),
                "updated_at_utc": now,
            }
            if existing:
                uow.execute(
                    update(cable_length_fact)
                    .where(cable_length_fact.c.id == existing["id"])
                    .values(**values, row_version=cable_length_fact.c.row_version + 1)
                )
            else:
                uow.execute(
                    cable_length_fact.insert().values(
                        id=new_id(),
                        project_id=project_id,
                        cable_line_id=cable_line_id,
                        calculated_length_m_decimal=None,
                        calculation_source=None,
                        calculation_revision=None,
                        rounding_policy="NONE",
                        knowledge_status="INCOMPLETE",
                        **values,
                    )
                )
            try:
                recalculate_segments(uow, project_id, segment_ids={segment_id})
            except RecalculationError as exc:
                raise CableError(str(exc)) from exc
            self._touch_project(uow, project_id, now)
            uow.commit()
        return self.effective_length(project_id, cable_line_id)

    def update_segment_route(
        self,
        *,
        project_id: str,
        cable_segment_id: str,
        route_method: RouteMethod,
        conduit_type: str = "",
        conduit_color: str = "",
        conduit_designation: str | None = None,
    ) -> None:
        """Edit and recalculate one exact persisted segment."""

        mount_way = MOUNT_WAY_BY_ROUTE_METHOD[RouteMethod(route_method)]
        conduit_type = conduit_type.strip()
        conduit_color = conduit_color.strip()
        try:
            validate_line_conduit_fields(
                mount_way=mount_way,
                conduit_type=conduit_type.strip(),
                conduit_color=conduit_color.strip(),
                conduit_id=conduit_designation or "",
            )
        except ConduitContractError as exc:
            raise CableError(str(exc)) from exc
        with UnitOfWork(self._engine) as uow:
            changed = uow.execute(
                update(cable_segment)
                .where(
                    cable_segment.c.id == cable_segment_id,
                    cable_segment.c.project_id == project_id,
                )
                .values(
                    mount_way=mount_way,
                    gofra_type=conduit_type.strip() or None,
                    gofra_color=conduit_color.strip() or None,
                    row_version=cable_segment.c.row_version + 1,
                    updated_at_utc=datetime.now(UTC),
                )
            )
            if changed.rowcount != 1:
                raise CableError("Cable segment not found")
            current = (
                uow.execute(
                    select(conduit)
                    .join(
                        conduit_segment_assignment,
                        conduit_segment_assignment.c.conduit_id == conduit.c.id,
                    )
                    .where(conduit_segment_assignment.c.cable_segment_id == cable_segment_id)
                )
                .mappings()
                .one_or_none()
            )
            target = None
            if conduit_designation:
                target = (
                    uow.execute(
                        select(conduit).where(
                            conduit.c.project_id == project_id,
                            conduit.c.designation == conduit_designation,
                            conduit.c.lifecycle == "ACTIVE",
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if target is not None and (
                    target["conduit_type"] != conduit_type
                    or (target["color"] or "") != conduit_color
                ):
                    count = uow.execute(
                        select(func.count())
                        .select_from(conduit_segment_assignment)
                        .where(conduit_segment_assignment.c.conduit_id == target["id"])
                    ).scalar_one()
                    if current is None or target["id"] != current["id"] or count != 1:
                        raise CableError(
                            "Существующая труба имеет другой тип или цвет. "
                            "Для отдельного участка укажите новый номер."
                        )
                    uow.execute(
                        update(conduit)
                        .where(conduit.c.id == target["id"])
                        .values(
                            color=conduit_color or None,
                            product_definition_id=None,
                            row_version=conduit.c.row_version + 1,
                            updated_at_utc=datetime.now(UTC),
                        )
                    )
            elif (
                current is not None
                and current["conduit_type"] == conduit_type
                and (current["color"] or "") == conduit_color
            ):
                target = current
            if current is not None and (target is None or target["id"] != current["id"]):
                _remove_assignment_and_empty_auto(uow, project_id, cable_segment_id, current["id"])
            if conduit_designation and target is None:
                target = {"id": new_id(), "designation": conduit_designation}
                uow.execute(
                    conduit.insert().values(
                        id=target["id"],
                        project_id=project_id,
                        designation=conduit_designation,
                        conduit_number=parse_conduit_id(conduit_designation, conduit_type),
                        conduit_type=conduit_type,
                        color=conduit_color or None,
                        path_json={"origin": "USER_EMPTY", "length_source": "SEGMENT_GEOMETRY"},
                    )
                )
            if target is not None and (current is None or target["id"] != current["id"]):
                uow.execute(
                    conduit_segment_assignment.insert().values(
                        id=new_id(),
                        project_id=project_id,
                        conduit_id=target["id"],
                        cable_segment_id=cable_segment_id,
                    )
                )
            self._set_segment_device_fields(
                uow,
                project_id,
                cable_segment_id,
                {
                    "MOUNT_WAY": mount_way,
                    "GOFRA_TYPE": conduit_type,
                    "GOFRA_COLOR": conduit_color,
                    "GOFRA_ID": "" if target is None else target["designation"],
                },
            )
            try:
                recalculate_segments(uow, project_id, segment_ids={cable_segment_id})
            except RecalculationError as exc:
                raise CableError(str(exc)) from exc
            self._touch_project(uow, project_id, datetime.now(UTC))
            uow.commit()

    def set_line_length_adjustments(
        self,
        *,
        project_id: str,
        cable_line_id: str,
        additional_m=0,
        manual_full_m=None,
    ) -> LengthResult:
        """Persist line-only overrides without modifying segment/conduit geometry."""

        additional = str(_non_negative(additional_m or 0, "additional_m"))
        manual = (
            None
            if manual_full_m in (None, "")
            else str(_non_negative(manual_full_m, "manual_full_m"))
        )
        with UnitOfWork(self._engine) as uow:
            existing = (
                uow.execute(
                    select(cable_length_fact).where(
                        cable_length_fact.c.project_id == project_id,
                        cable_length_fact.c.cable_line_id == cable_line_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing is None:
                uow.execute(
                    cable_length_fact.insert().values(
                        id=new_id(),
                        project_id=project_id,
                        cable_line_id=cable_line_id,
                        calculated_length_m_decimal=None,
                        calculation_source=None,
                        calculation_revision=None,
                        additional_length_m_decimal=additional,
                        manual_full_length_m_decimal=manual,
                        rounding_policy="NONE",
                        knowledge_status="KNOWN" if manual is not None else "INCOMPLETE",
                    )
                )
            else:
                uow.execute(
                    update(cable_length_fact)
                    .where(cable_length_fact.c.id == existing["id"])
                    .values(
                        additional_length_m_decimal=additional,
                        manual_full_length_m_decimal=manual,
                        row_version=cable_length_fact.c.row_version + 1,
                        updated_at_utc=datetime.now(UTC),
                    )
                )
            recalculate_segments(
                uow,
                project_id,
                line_ids={cable_line_id},
                recalculate_geometry=False,
            )
            self._touch_project(uow, project_id, datetime.now(UTC))
            uow.commit()
        return self.effective_length(project_id, cable_line_id)

    def recalculate(
        self,
        *,
        project_id: str,
        segment_ids: Iterable[str] | None = None,
        cable_line_ids: Iterable[str] | None = None,
        room_ids: Iterable[str] | None = None,
        recalculate_geometry: bool = True,
    ):
        """Run an affected-set recalculation without any CAD access."""

        with UnitOfWork(self._engine) as uow:
            try:
                result = recalculate_segments(
                    uow,
                    project_id,
                    segment_ids=None if segment_ids is None else set(segment_ids),
                    line_ids=None if cable_line_ids is None else set(cable_line_ids),
                    room_ids=None if room_ids is None else set(room_ids),
                    recalculate_geometry=recalculate_geometry,
                )
            except RecalculationError as exc:
                raise CableError(str(exc)) from exc
            uow.commit()
        return result

    def effective_length(self, project_id: str, cable_line_id: str) -> LengthResult:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    select(cable_length_fact).where(
                        cable_length_fact.c.project_id == project_id,
                        cable_length_fact.c.cable_line_id == cable_line_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None or (
            row["knowledge_status"] != "KNOWN" and row["manual_full_length_m_decimal"] is None
        ):
            raise CableError("Cable length is incomplete")
        with UnitOfWork(self._engine) as uow:
            reserve = board_reserve_for_line(uow, project_id, cable_line_id)
        return calculate_effective_length(
            automatic_m=row["calculated_length_m_decimal"] or 0,
            additional_m=row["additional_length_m_decimal"] or 0,
            board_reserve_m=reserve,
            manual_full_m=row["manual_full_length_m_decimal"],
        )

    def create_empty_conduit(
        self,
        *,
        project_id: str,
        designation: str,
        conduit_type: str,
        color: str = "",
        diameter_mm=None,
        length_m=None,
    ) -> str:
        identifier = new_id()
        try:
            number = parse_conduit_id(designation, conduit_type)
        except ConduitContractError as exc:
            raise CableError(str(exc)) from exc
        with UnitOfWork(self._engine) as uow:
            uow.execute(
                conduit.insert().values(
                    id=identifier,
                    project_id=project_id,
                    designation=_required(designation, "designation"),
                    conduit_number=number,
                    conduit_type=_required(conduit_type, "conduit_type"),
                    color=color.strip() or None,
                    diameter_mm_decimal=_optional_non_negative(diameter_mm, "diameter_mm"),
                    length_m_decimal=(
                        None if length_m in (None, "") else str(_non_negative(length_m, "length_m"))
                    ),
                    path_json={
                        "origin": "USER_EMPTY",
                        "length_source": (
                            "USER_CONFIRMED" if length_m not in (None, "") else "UNKNOWN"
                        ),
                    },
                )
            )
            self._touch_project(uow, project_id, datetime.now(UTC))
            uow.commit()
        return identifier

    def move_line_to_conduit(
        self, *, project_id: str, cable_line_id: str, target_conduit_id: str
    ) -> None:
        with UnitOfWork(self._engine) as uow:
            segment_id = self._single_segment_id(uow, project_id, cable_line_id)
            uow.rollback()
        self.move_segment_to_conduit(
            project_id=project_id,
            cable_segment_id=segment_id,
            target_conduit_id=target_conduit_id,
        )

    def move_segment_to_conduit(
        self, *, project_id: str, cable_segment_id: str, target_conduit_id: str
    ) -> None:
        """Move one exact segment; conduit ownership is never line-derived."""

        with UnitOfWork(self._engine) as uow:
            target = (
                uow.execute(
                    select(conduit).where(
                        conduit.c.id == target_conduit_id,
                        conduit.c.project_id == project_id,
                        conduit.c.lifecycle == "ACTIVE",
                    )
                )
                .mappings()
                .one_or_none()
            )
            if target is None:
                raise CableError("Target conduit not found")
            segment_id = cable_segment_id
            segment_exists = uow.execute(
                select(cable_segment.c.id).where(
                    cable_segment.c.id == segment_id,
                    cable_segment.c.project_id == project_id,
                )
            ).scalar_one_or_none()
            if segment_exists is None:
                raise CableError("Cable segment not found")
            old_ids = list(
                uow.execute(
                    select(conduit_segment_assignment.c.conduit_id).where(
                        conduit_segment_assignment.c.project_id == project_id,
                        conduit_segment_assignment.c.cable_segment_id == segment_id,
                    )
                ).scalars()
            )
            uow.execute(
                delete(conduit_segment_assignment).where(
                    conduit_segment_assignment.c.project_id == project_id,
                    conduit_segment_assignment.c.cable_segment_id == segment_id,
                )
            )
            uow.execute(
                conduit_segment_assignment.insert().values(
                    id=new_id(),
                    project_id=project_id,
                    conduit_id=target_conduit_id,
                    cable_segment_id=segment_id,
                )
            )
            now = datetime.now(UTC)
            self._set_segment_conduit_facts(
                uow,
                project_id,
                segment_id,
                conduit_type=target["conduit_type"],
                color=target["color"] or "",
                designation=target["designation"],
                now=now,
            )
            for old_id in old_ids:
                if old_id == target_conduit_id:
                    continue
                count = uow.execute(
                    select(func.count())
                    .select_from(conduit_segment_assignment)
                    .where(conduit_segment_assignment.c.conduit_id == old_id)
                ).scalar_one()
                origin = uow.execute(
                    select(conduit.c.path_json).where(conduit.c.id == old_id)
                ).scalar_one_or_none()
                if count == 0 and (origin or {}).get("origin") in {
                    "AUTO_LINE",
                    "AUTO_SEGMENT",
                }:
                    uow.execute(delete(conduit).where(conduit.c.id == old_id))
                elif count:
                    refresh_conduit_length(uow, project_id, old_id)
            refresh_conduit_length(uow, project_id, target_conduit_id)
            self._touch_project(uow, project_id, now)
            uow.commit()

    def bulk_edit_conduits(
        self,
        *,
        project_id: str,
        conduit_ids: Iterable[str],
        conduit_type: str,
        diameter_mm,
        failure_hook: Callable[[], None] | None = None,
    ) -> None:
        identifiers = set(conduit_ids)
        if not identifiers:
            raise CableError("No conduits selected")
        clean_type = _required(conduit_type, "conduit_type")
        try:
            format_conduit_id(1, clean_type)
        except ConduitContractError as exc:
            raise CableError(str(exc)) from exc
        diameter = _optional_non_negative(diameter_mm, "diameter_mm")
        with UnitOfWork(self._engine) as uow:
            found_rows = list(
                uow.execute(
                    select(conduit).where(
                        conduit.c.project_id == project_id,
                        conduit.c.id.in_(identifiers),
                        conduit.c.lifecycle == "ACTIVE",
                    )
                ).mappings()
            )
            if {row["id"] for row in found_rows} != identifiers:
                raise CableError("One or more conduits are unavailable")
            now = datetime.now(UTC)
            for row in found_rows:
                if row["conduit_number"] is None:
                    raise CableError(
                        f"Conduit {row['designation']} has no canonical numeric project number"
                    )
                designation = format_conduit_id(row["conduit_number"], clean_type)
                uow.execute(
                    update(conduit)
                    .where(conduit.c.id == row["id"])
                    .values(
                        designation=designation,
                        conduit_type=clean_type,
                        diameter_mm_decimal=diameter,
                        row_version=conduit.c.row_version + 1,
                        updated_at_utc=now,
                    )
                )
                segment_ids = list(
                    uow.execute(
                        select(conduit_segment_assignment.c.cable_segment_id).where(
                            conduit_segment_assignment.c.project_id == project_id,
                            conduit_segment_assignment.c.conduit_id == row["id"],
                        )
                    ).scalars()
                )
                for segment_id in segment_ids:
                    self._set_segment_conduit_facts(
                        uow,
                        project_id,
                        segment_id,
                        conduit_type=clean_type,
                        color=row["color"] or "",
                        designation=designation,
                        now=now,
                    )
            if failure_hook:
                failure_hook()
            self._touch_project(uow, project_id, now)
            uow.commit()

    def bulk_edit_line_conduits(
        self,
        *,
        project_id: str,
        cable_line_ids: Iterable[str],
        conduit_type: str,
        diameter_mm,
        failure_hook: Callable[[], None] | None = None,
    ) -> None:
        line_ids = set(cable_line_ids)
        if not line_ids:
            raise CableError("No cable lines selected")
        with self._engine.connect() as connection:
            rows = list(
                connection.execute(
                    select(
                        cable_segment.c.cable_line_id,
                        conduit_segment_assignment.c.conduit_id,
                    )
                    .join(
                        cable_segment,
                        cable_segment.c.id == conduit_segment_assignment.c.cable_segment_id,
                    )
                    .where(
                        conduit_segment_assignment.c.project_id == project_id,
                        cable_segment.c.cable_line_id.in_(line_ids),
                    )
                )
            )
        assigned_lines = [row.cable_line_id for row in rows]
        if set(assigned_lines) != line_ids or len(assigned_lines) != len(line_ids):
            raise CableError(
                "Every selected cable line must have exactly one segment assigned to a conduit"
            )
        self.bulk_edit_conduits(
            project_id=project_id,
            conduit_ids={row.conduit_id for row in rows},
            conduit_type=conduit_type,
            diameter_mm=diameter_mm,
            failure_hook=failure_hook,
        )

    def update_conduit_length(self, *, project_id: str, conduit_id: str, length_m) -> None:
        value = str(_non_negative(length_m, "length_m"))
        now = datetime.now(UTC)
        with UnitOfWork(self._engine) as uow:
            row = (
                uow.execute(
                    select(conduit).where(
                        conduit.c.id == conduit_id,
                        conduit.c.project_id == project_id,
                        conduit.c.lifecycle == "ACTIVE",
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise CableError("Conduit not found")
            path = dict(row["path_json"] or {})
            path["length_source"] = "USER_CONFIRMED"
            result = uow.execute(
                update(conduit)
                .where(
                    conduit.c.id == conduit_id,
                    conduit.c.project_id == project_id,
                    conduit.c.lifecycle == "ACTIVE",
                )
                .values(
                    length_m_decimal=value,
                    path_json=path,
                    row_version=conduit.c.row_version + 1,
                    updated_at_utc=now,
                )
            )
            if result.rowcount != 1:
                raise CableError("Conduit not found")
            self._touch_project(uow, project_id, now)
            uow.commit()

    def update_conduit_details(
        self,
        *,
        project_id: str,
        conduit_id: str,
        conduit_number: int,
        conduit_type: str,
        color: str,
        length_m=None,
    ) -> None:
        try:
            designation = format_conduit_id(conduit_number, conduit_type)
        except ConduitContractError as exc:
            raise CableError(str(exc)) from exc
        length = None if length_m in (None, "") else str(_non_negative(length_m, "length_m"))
        now = datetime.now(UTC)
        with UnitOfWork(self._engine) as uow:
            row = (
                uow.execute(
                    select(conduit).where(
                        conduit.c.id == conduit_id,
                        conduit.c.project_id == project_id,
                        conduit.c.lifecycle == "ACTIVE",
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise CableError("Conduit not found")
            path = dict(row["path_json"] or {})
            path["length_source"] = "USER_CONFIRMED" if length is not None else "UNKNOWN"
            result = uow.execute(
                update(conduit)
                .where(
                    conduit.c.id == conduit_id,
                    conduit.c.project_id == project_id,
                    conduit.c.lifecycle == "ACTIVE",
                )
                .values(
                    designation=designation,
                    conduit_number=conduit_number,
                    conduit_type=conduit_type.strip(),
                    color=color.strip() or None,
                    length_m_decimal=length,
                    path_json=path,
                    row_version=conduit.c.row_version + 1,
                    updated_at_utc=now,
                )
            )
            if result.rowcount != 1:
                raise CableError("Conduit not found")
            segment_ids = list(
                uow.execute(
                    select(conduit_segment_assignment.c.cable_segment_id).where(
                        conduit_segment_assignment.c.project_id == project_id,
                        conduit_segment_assignment.c.conduit_id == conduit_id,
                    )
                ).scalars()
            )
            for segment_id in segment_ids:
                self._set_segment_conduit_facts(
                    uow,
                    project_id,
                    segment_id,
                    conduit_type=conduit_type.strip(),
                    color=color.strip(),
                    designation=designation,
                    now=now,
                )
            self._touch_project(uow, project_id, now)
            uow.commit()

    def create_board_av(self, *, project_id: str, designation: str, title: str = "") -> str:
        identifier = new_id()
        with UnitOfWork(self._engine) as uow:
            uow.execute(
                board.insert().values(
                    id=identifier,
                    project_id=project_id,
                    designation=_required(designation, "designation"),
                    board_kind="BOARD_AV",
                    title=title.strip(),
                )
            )
            self._touch_project(uow, project_id, datetime.now(UTC))
            uow.commit()
        return identifier

    def create_av_line(
        self,
        *,
        project_id: str,
        board_id: str,
        cable_id: str,
        load_type: str,
        cable_type: str,
    ) -> str:
        normalized = _required(cable_id, "cable_id").strip().upper()
        if load_type not in AV_LOAD_TYPES:
            raise CableError("AV LOAD_TYPE must be SPEAKER_CABLE or HDMI")
        line_id = new_id()
        with UnitOfWork(self._engine) as uow:
            board_row = uow.execute(
                select(board.c.designation, board.c.board_kind).where(
                    board.c.id == board_id,
                    board.c.project_id == project_id,
                    board.c.lifecycle == "ACTIVE",
                )
            ).one_or_none()
            if board_row is None or board_row.board_kind != "BOARD_AV":
                raise CableError("AV line requires an existing BOARD_AV")
            try:
                uow.execute(
                    cable_line.insert().values(
                        id=line_id,
                        project_id=project_id,
                        designation=f"{board_row.designation} / {normalized}",
                        system_kind="AV",
                        board_id=board_id,
                        cable_facts_json={
                            "BOARD": board_row.designation,
                            "CABLE_ID": normalized,
                            "LOAD_TYPE": load_type,
                            "CABLE_TYPE": _required(cable_type, "cable_type"),
                            "EXCLUDE_FROM_POWER_DIN": True,
                        },
                    )
                )
                uow.execute(
                    av_cable_profile.insert().values(
                        id=new_id(),
                        project_id=project_id,
                        cable_line_id=line_id,
                        board_id=board_id,
                        cable_id=normalized,
                        profile_json={"load_type": load_type},
                    )
                )
                self._touch_project(uow, project_id, datetime.now(UTC))
                uow.commit()
            except IntegrityError as exc:
                raise CableError(
                    f"CABLE_ID {normalized} already exists inside this BOARD_AV"
                ) from exc
        return line_id

    def start_catalog_draft(self, release_code: str) -> str:
        identifier = new_id()
        with UnitOfWork(self._engine) as uow:
            if uow.execute(
                select(cable_catalog_release.c.id).where(cable_catalog_release.c.status == "DRAFT")
            ).scalar_one_or_none():
                raise CableError("A cable catalog draft already exists")
            uow.execute(
                cable_catalog_release.insert().values(
                    id=identifier,
                    release_code=_required(release_code, "release_code"),
                    schema_version=1,
                    content_sha256="0" * 64,
                    installed_at_utc=datetime.now(UTC),
                    status="DRAFT",
                )
            )
            active_products = list(
                uow.execute(
                    select(cable_product_definition)
                    .join(
                        cable_catalog_release,
                        cable_catalog_release.c.id
                        == cable_product_definition.c.cable_catalog_release_id,
                    )
                    .where(
                        cable_catalog_release.c.status == "ACTIVE",
                        cable_product_definition.c.lifecycle == "ACTIVE",
                    )
                ).mappings()
            )
            for product in active_products:
                uow.execute(
                    cable_product_definition.insert().values(
                        id=new_id(),
                        cable_catalog_release_id=identifier,
                        product_key=product["product_key"],
                        version=product["version"] + 1,
                        category=product["category"],
                        manufacturer=product["manufacturer"],
                        model=product["model"],
                        article=product["article"],
                        technical_properties_json=product["technical_properties_json"],
                        factory_length_m_decimal=product["factory_length_m_decimal"],
                        lifecycle=product["lifecycle"],
                    )
                )
            uow.commit()
        return identifier

    def current_draft_release_id(self) -> str | None:
        with self._engine.connect() as connection:
            return connection.scalar(
                select(cable_catalog_release.c.id).where(cable_catalog_release.c.status == "DRAFT")
            )

    def add_catalog_product(
        self,
        *,
        draft_release_id: str,
        product_key: str,
        category: str,
        manufacturer: str,
        model: str = "",
        article: str = "",
        cable_type: str,
        factory_length_m=None,
        properties: dict | None = None,
    ) -> str:
        if category not in CABLE_CATEGORIES:
            raise CableError("Unsupported cable product category")
        factory = _optional_non_negative(factory_length_m, "factory_length_m")
        if category == "HDMI" and (factory is None or Decimal(factory) <= 0):
            raise CableError("HDMI requires a positive factory length")
        identifier = new_id()
        with UnitOfWork(self._engine) as uow:
            status = uow.execute(
                select(cable_catalog_release.c.status).where(
                    cable_catalog_release.c.id == draft_release_id
                )
            ).scalar_one_or_none()
            if status != "DRAFT":
                raise CableError("Products can be added only to a draft release")
            version = (
                uow.execute(
                    select(func.max(cable_product_definition.c.version)).where(
                        cable_product_definition.c.product_key == product_key
                    )
                ).scalar_one_or_none()
                or 0
            ) + 1
            technical = dict(properties or {})
            technical["cable_type"] = _required(cable_type, "cable_type")
            uow.execute(
                cable_product_definition.insert().values(
                    id=identifier,
                    cable_catalog_release_id=draft_release_id,
                    product_key=_required(product_key, "product_key"),
                    version=version,
                    category=category,
                    manufacturer=_required(manufacturer, "manufacturer"),
                    model=model.strip(),
                    article=article.strip(),
                    technical_properties_json=technical,
                    factory_length_m_decimal=factory,
                )
            )
            uow.commit()
        return identifier

    def publish_catalog(self, draft_release_id: str) -> str:
        with UnitOfWork(self._engine) as uow:
            release = (
                uow.execute(
                    select(cable_catalog_release).where(
                        cable_catalog_release.c.id == draft_release_id,
                        cable_catalog_release.c.status == "DRAFT",
                    )
                )
                .mappings()
                .one_or_none()
            )
            if release is None:
                raise CableError("Draft release not found")
            products = list(
                uow.execute(
                    select(cable_product_definition).where(
                        cable_product_definition.c.cable_catalog_release_id == draft_release_id
                    )
                ).mappings()
            )
            if not products:
                raise CableError("An empty cable catalog cannot be published")
            payload = [
                {key: row[key] for key in row if key != "id"}
                for row in sorted(products, key=lambda item: (item["product_key"], item["version"]))
            ]
            content_hash = hashlib.sha256(
                json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()
            uow.execute(
                update(cable_catalog_release)
                .where(cable_catalog_release.c.status == "ACTIVE")
                .values(status="RETIRED")
            )
            uow.execute(
                update(cable_catalog_release)
                .where(cable_catalog_release.c.id == draft_release_id)
                .values(status="ACTIVE", content_sha256=content_hash)
            )
            uow.commit()
        return content_hash

    def auto_select_hdmi(self, *, project_id: str, cable_line_id: str) -> HdmiSelectionResult:
        required = self.effective_length(project_id, cable_line_id).effective_m
        cable_type = self._line_cable_type(project_id, cable_line_id, required_load_type="HDMI")
        products = self._hdmi_products(cable_type)
        if not products:
            raise CableError("No active HDMI products match CABLE_TYPE")
        sufficient = [item for item in products if item[1] >= required]
        chosen = (
            min(sufficient, key=lambda item: item[1])
            if sufficient
            else max(products, key=lambda item: item[1])
        )
        warning = None if sufficient else "NO_SUFFICIENT_HDMI_LENGTH"
        self._save_product_selection(project_id, cable_line_id, chosen[0], required)
        return HdmiSelectionResult(chosen[0], required, chosen[1], warning)

    def select_hdmi_manually(
        self, *, project_id: str, cable_line_id: str, product_id: str
    ) -> HdmiSelectionResult:
        required = self.effective_length(project_id, cable_line_id).effective_m
        cable_type = self._line_cable_type(project_id, cable_line_id, required_load_type="HDMI")
        products = dict(self._hdmi_products(cable_type))
        if product_id not in products:
            raise CableError("HDMI product does not match line CABLE_TYPE or active release")
        factory = products[product_id]
        warning = "HDMI_SHORTER_THAN_REQUIRED" if factory < required else None
        self._save_product_selection(project_id, cable_line_id, product_id, required)
        return HdmiSelectionResult(product_id, required, factory, warning)

    def select_speaker_product(
        self, *, project_id: str, cable_line_id: str, product_id: str
    ) -> None:
        cable_type = self._line_cable_type(
            project_id, cable_line_id, required_load_type="SPEAKER_CABLE"
        )
        with self._engine.connect() as connection:
            product = connection.execute(
                select(cable_product_definition.c.technical_properties_json)
                .join(
                    cable_catalog_release,
                    cable_catalog_release.c.id
                    == cable_product_definition.c.cable_catalog_release_id,
                )
                .where(
                    cable_product_definition.c.id == product_id,
                    cable_product_definition.c.category == "SPEAKER_CABLE",
                    cable_product_definition.c.lifecycle == "ACTIVE",
                    cable_catalog_release.c.status == "ACTIVE",
                )
            ).scalar_one_or_none()
        if product is None or (product or {}).get("cable_type") != cable_type:
            raise CableError("Speaker product does not match line CABLE_TYPE or active release")
        try:
            required = self.effective_length(project_id, cable_line_id).effective_m
        except CableError:
            required = Decimal("0")
        self._save_product_selection(project_id, cable_line_id, product_id, required)

    def hdmi_selection_status(self, project_id: str, cable_line_id: str) -> str:
        required = self.effective_length(project_id, cable_line_id).effective_m
        with self._engine.connect() as connection:
            profile = connection.scalar(
                select(av_cable_profile.c.profile_json).where(
                    av_cable_profile.c.project_id == project_id,
                    av_cable_profile.c.cable_line_id == cable_line_id,
                )
            )
            selected = connection.scalar(
                select(cable_line_product_selection.c.id).where(
                    cable_line_product_selection.c.project_id == project_id,
                    cable_line_product_selection.c.cable_line_id == cable_line_id,
                )
            )
        if selected is None:
            return "NOT_SELECTED"
        prior = (profile or {}).get("selected_required_length_m")
        return "CURRENT" if prior == str(required) else "RECONFIRM_REQUIRED"

    def _single_segment_id(self, uow, project_id: str, cable_line_id: str) -> str:
        segment_ids = list(
            uow.execute(
                select(cable_segment.c.id).where(
                    cable_segment.c.project_id == project_id,
                    cable_segment.c.cable_line_id == cable_line_id,
                )
            ).scalars()
        )
        if len(segment_ids) != 1:
            raise CableError("Legacy line-level cable operation requires exactly one cable segment")
        return segment_ids[0]

    def _set_segment_conduit_facts(
        self, uow, project_id, segment_id, *, conduit_type, color, designation, now
    ) -> None:
        uow.execute(
            update(cable_segment)
            .where(
                cable_segment.c.id == segment_id,
                cable_segment.c.project_id == project_id,
            )
            .values(
                gofra_type=conduit_type,
                gofra_color=color or None,
                row_version=cable_segment.c.row_version + 1,
                updated_at_utc=now,
            )
        )
        self._set_segment_device_fields(
            uow,
            project_id,
            segment_id,
            {"GOFRA_TYPE": conduit_type, "GOFRA_COLOR": color, "GOFRA_ID": designation},
        )

    def _set_segment_device_fields(self, uow, project_id, segment_id, values) -> None:
        device_ids = list(
            uow.execute(
                select(cable_point_field_device.c.field_device_id)
                .join(
                    cable_topology_endpoint,
                    cable_topology_endpoint.c.cable_point_id
                    == cable_point_field_device.c.cable_point_id,
                )
                .join(
                    cable_segment,
                    cable_segment.c.target_endpoint_id == cable_topology_endpoint.c.id,
                )
                .where(
                    cable_segment.c.id == segment_id,
                    cable_segment.c.project_id == project_id,
                )
            ).scalars()
        )
        self._set_device_fields(uow, device_ids, values)

    def _set_device_line_fields(self, uow, project_id, line_id, values) -> None:
        device_ids = list(
            uow.execute(
                select(cable_point_field_device.c.field_device_id)
                .join(
                    cable_point,
                    cable_point.c.id == cable_point_field_device.c.cable_point_id,
                )
                .where(
                    cable_point.c.project_id == project_id,
                    cable_point.c.cable_line_id == line_id,
                )
            ).scalars()
        )
        self._set_device_fields(uow, device_ids, values)

    def _set_device_fields(self, uow, device_ids, values) -> None:
        for device_id in device_ids:
            fields = dict(
                uow.execute(
                    select(field_device.c.normalized_fields_json).where(
                        field_device.c.id == device_id
                    )
                ).scalar_one()
                or {}
            )
            fields.update(values)
            uow.execute(
                update(field_device)
                .where(field_device.c.id == device_id)
                .values(
                    normalized_fields_json=fields,
                    row_version=field_device.c.row_version + 1,
                    updated_at_utc=datetime.now(UTC),
                )
            )

    def _line_cable_type(self, project_id, cable_line_id, *, required_load_type):
        with self._engine.connect() as connection:
            row = connection.execute(
                select(cable_line.c.cable_facts_json).where(
                    cable_line.c.id == cable_line_id,
                    cable_line.c.project_id == project_id,
                    cable_line.c.system_kind == "AV",
                )
            ).scalar_one_or_none()
        if row is None or row.get("LOAD_TYPE") != required_load_type:
            raise CableError(f"Line must be AV {required_load_type}")
        return row.get("CABLE_TYPE", "")

    def _hdmi_products(self, cable_type: str):
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(
                    cable_product_definition.c.id,
                    cable_product_definition.c.factory_length_m_decimal,
                    cable_product_definition.c.technical_properties_json,
                )
                .join(
                    cable_catalog_release,
                    cable_catalog_release.c.id
                    == cable_product_definition.c.cable_catalog_release_id,
                )
                .where(
                    cable_catalog_release.c.status == "ACTIVE",
                    cable_product_definition.c.category == "HDMI",
                    cable_product_definition.c.lifecycle == "ACTIVE",
                )
            ).mappings()
            return [
                (row["id"], Decimal(row["factory_length_m_decimal"]))
                for row in rows
                if (row["technical_properties_json"] or {}).get("cable_type") == cable_type
            ]

    def _save_product_selection(self, project_id, line_id, product_id, required):
        now = datetime.now(UTC)
        with UnitOfWork(self._engine) as uow:
            existing = uow.execute(
                select(cable_line_product_selection.c.id).where(
                    cable_line_product_selection.c.project_id == project_id,
                    cable_line_product_selection.c.cable_line_id == line_id,
                )
            ).scalar_one_or_none()
            values = {
                "cable_product_definition_id": product_id,
                "selected_at_utc": now,
                "command_id": new_id(),
            }
            if existing:
                uow.execute(
                    update(cable_line_product_selection)
                    .where(cable_line_product_selection.c.id == existing)
                    .values(**values)
                )
            else:
                uow.execute(
                    cable_line_product_selection.insert().values(
                        id=new_id(),
                        project_id=project_id,
                        cable_line_id=line_id,
                        **values,
                    )
                )
            profile = (
                uow.execute(
                    select(av_cable_profile).where(
                        av_cable_profile.c.project_id == project_id,
                        av_cable_profile.c.cable_line_id == line_id,
                    )
                )
                .mappings()
                .one()
            )
            data = dict(profile["profile_json"] or {})
            data["selected_required_length_m"] = str(required)
            uow.execute(
                update(av_cable_profile)
                .where(av_cable_profile.c.id == profile["id"])
                .values(profile_json=data, row_version=av_cable_profile.c.row_version + 1)
            )
            self._touch_project(uow, project_id, now)
            uow.commit()

    @staticmethod
    def _touch_project(uow, project_id: str, now: datetime) -> None:
        uow.execute(
            update(project)
            .where(project.c.id == project_id)
            .values(project_revision=project.c.project_revision + 1, updated_at_utc=now)
        )


def _required(value: str, field: str) -> str:
    clean = str(value).strip()
    if not clean:
        raise CableError(f"{field} is required")
    return clean


def _non_negative(value, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise CableError(f"{field} must be a decimal") from exc
    if not result.is_finite() or result < 0:
        raise CableError(f"{field} must be non-negative")
    return result


def _optional_non_negative(value, field: str) -> str | None:
    if value in (None, ""):
        return None
    return str(_non_negative(value, field))
