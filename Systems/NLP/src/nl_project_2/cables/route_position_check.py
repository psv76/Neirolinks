"""Verified endpoint-position tolerance for manual physical conduit operations.

The tolerance concerns *terminal devices*, not electrical segment identity.
Coordinates and mounting heights are stored in Project's DWG observations
in millimetres. Nothing here writes to SQLite or reads a live DWG.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import hypot, isfinite

from sqlalchemy import select

from nl_project_2.persistence.schema import (
    bus_endpoint,
    bus_segment,
    cable_point,
    cable_point_field_device,
    cable_segment,
    cable_topology_endpoint,
    field_device,
    field_port,
)

XY_LIMIT_MM = 1000.0
HEIGHT_LIMIT_MM = 2000.0


@dataclass(frozen=True)
class TerminalPosition:
    network_kind: str
    segment_id: str
    device_id: str | None
    x_mm: float | None
    y_mm: float | None
    height_mm: float | None
    problem: str = ""
    evidence: str = ""


@dataclass(frozen=True)
class PositionAssessment:
    terminals: tuple[TerminalPosition, ...]
    max_xy_mm: float | None
    max_height_mm: float | None
    requires_exception: bool
    reasons: tuple[str, ...]

    @property
    def point_count(self) -> int:
        return len(self.terminals)


def _millimetres(value) -> float | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        number = float(str(value).strip().replace(",", "."))
        return number if isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _select_one(connection, table, project_id: str, row_id: str | None):
    if not row_id:
        return None
    return (
        connection.execute(
            select(table).where(table.c.project_id == project_id, table.c.id == row_id)
        )
        .mappings()
        .one_or_none()
    )


def assess_terminal_positions(connection, project_id: str, member_keys) -> PositionAssessment:
    """Read all terminal positions in this transaction, including existing target members.

    Unknown/ambiguous owners, missing coordinates and height *require* an
    explicit extra operator acknowledgement. The assessment is compared again
    on apply to make modified DWG-snapshot data invalidate the old preview.
    """
    terminals = []
    for kind, segment_id in sorted(set(member_keys)):
        table = cable_segment if kind == "CABLE" else bus_segment
        segment = _select_one(connection, table, project_id, segment_id)
        device_id = None
        point = None
        problem = ""
        if segment is None:
            problem = "Физический сегмент отсутствует"
        elif kind == "CABLE":
            endpoint = _select_one(
                connection, cable_topology_endpoint, project_id, segment["target_endpoint_id"]
            )
            if endpoint is None:
                problem = "Нет конечной точки кабеля"
            elif endpoint["endpoint_kind"] == "TOPOLOGY_POINT":
                point = _select_one(connection, cable_point, project_id, endpoint["cable_point_id"])
                if point is None:
                    problem = "Нет точки подключения кабеля"
                else:
                    members = (
                        connection.execute(
                            select(cable_point_field_device.c.field_device_id).where(
                                cable_point_field_device.c.project_id == project_id,
                                cable_point_field_device.c.cable_point_id == point["id"],
                            )
                        )
                        .scalars()
                        .all()
                    )
                    if len(members) != 1:
                        problem = "Невозможно однозначно определить конечное устройство"
                    else:
                        device_id = members[0]
            elif endpoint["endpoint_kind"] == "FIELD_PORT":
                port = _select_one(connection, field_port, project_id, endpoint["field_port_id"])
                if port and port["lifecycle"] == "ACTIVE":
                    device_id = port["field_device_id"]
                else:
                    problem = "Неизвестный конечный физический порт"
            else:
                problem = "Конечная точка кабеля не является устройством"
        elif kind == "BUS":
            if segment["connection_kind"] != "CABLE":
                problem = "BUS TRACK не является физическим кабелем"
            else:
                endpoint = _select_one(
                    connection, bus_endpoint, project_id, segment["target_endpoint_id"]
                )
                if endpoint and endpoint["endpoint_kind"] == "FIELD_DEVICE":
                    device_id = endpoint["field_device_id"]
                else:
                    problem = "Нет однозначного устройства на конце BUS"
        else:
            problem = "Неизвестный тип сегмента"

        device = _select_one(connection, field_device, project_id, device_id)
        fields = (device["normalized_fields_json"] or {}) if device else {}
        x = y = h = None
        evidence = ""
        if device_id and (device is None or device["lifecycle"] != "ACTIVE"):
            problem = "Конечное устройство неактивно или отсутствует"
        elif device:
            location = (point["location_json"] or {}) if point else {}
            # Persisted topology-point geometry is authoritative for a cable;
            # normalized field device X/Y are the fallback for field ports/BUS.
            x = _millimetres(
                location.get("x") if location.get("x") is not None else fields.get("X")
            )
            y = _millimetres(
                location.get("y") if location.get("y") is not None else fields.get("Y")
            )
            h = _millimetres(fields.get("MOUNT_HEIGHT"))
            if not problem and (x is None or y is None or h is None):
                problem = "Неизвестны координаты или монтажная высота"
            # Include raw evidence, identity, and versions to reject stale
            # confirmations even when an editor fails to bump project revision.
            evidence = repr(
                (
                    device["id"],
                    device["row_version"],
                    fields,
                    point["id"] if point else None,
                    point["row_version"] if point else None,
                    point["location_json"] if point else None,
                )
            )
        terminals.append(TerminalPosition(kind, segment_id, device_id, x, y, h, problem, evidence))

    all_known = all(
        not t.problem and t.x_mm is not None and t.y_mm is not None and t.height_mm is not None
        for t in terminals
    )
    xy = height = None
    if all_known and terminals:
        xy = max(
            (hypot(a.x_mm - b.x_mm, a.y_mm - b.y_mm) for a, b in combinations(terminals, 2)),
            default=0.0,
        )
        height = max(
            (abs(a.height_mm - b.height_mm) for a, b in combinations(terminals, 2)), default=0.0
        )
    reasons = []
    if not all_known:
        reasons.append("Не все конечные устройства имеют подтверждённые X/Y/высоту.")
    else:
        if xy > XY_LIMIT_MM:
            reasons.append("Расстояние XY превышает 1 м.")
        if height > HEIGHT_LIMIT_MM:
            reasons.append("Разница монтажных высот превышает 2 м.")
    return PositionAssessment(tuple(terminals), xy, height, bool(reasons), tuple(reasons))


def format_position_assessment(assessment: PositionAssessment) -> str:
    xy = "неизвестно" if assessment.max_xy_mm is None else f"{assessment.max_xy_mm / 1000:.3f} м"
    h = (
        "неизвестно"
        if assessment.max_height_mm is None
        else f"{assessment.max_height_mm / 1000:.3f} м"
    )
    return (
        f"Максимальное расстояние XY: {xy} (допуск 1,000 м)\n"
        f"Разница высот: {h} (допуск 2,000 м)\n" + "\n".join(assessment.reasons)
    )
