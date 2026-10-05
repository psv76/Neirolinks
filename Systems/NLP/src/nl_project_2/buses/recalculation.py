"""Derived physical lengths for persisted bus segments."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select, update

from nl_project_2.cables.domain import (
    ROUTE_METHOD_BY_MOUNT_WAY,
    CablePointInput,
    RouteMethod,
    calculate_segment_length,
)
from nl_project_2.persistence.schema import (
    board,
    bus,
    bus_endpoint,
    bus_segment,
    field_device,
    instance_resource,
    project_instance,
    room,
)


def recalculate_bus_segments(
    uow, project_id: str, *, bus_ids: set[str] | None = None
) -> tuple[str, ...]:
    """Recalculate stored lengths from accepted Project geometry only."""

    statement = (
        select(bus_segment, bus.c.root_resource_id)
        .join(bus, bus.c.id == bus_segment.c.bus_id)
        .where(
            bus_segment.c.project_id == project_id,
            bus.c.project_id == project_id,
            bus.c.lifecycle == "ACTIVE",
        )
    )
    if bus_ids is not None:
        if not bus_ids:
            return ()
        statement = statement.where(bus_segment.c.bus_id.in_(bus_ids))

    rows = [dict(row) for row in uow.execute(statement).mappings()]
    now = datetime.now(UTC)
    changed: list[str] = []
    for segment in rows:
        route = _route_method(segment.get("mount_way"))
        length = None
        if route is not None:
            source, source_missing = (
                _root_geometry(uow, project_id, segment["root_resource_id"], route)
                if segment.get("source_endpoint_id") is None
                else _endpoint_geometry(uow, project_id, segment["source_endpoint_id"], route)
            )
            target, target_missing = _endpoint_geometry(
                uow, project_id, segment["target_endpoint_id"], route
            )
            if not source_missing and not target_missing:
                length, _trace = calculate_segment_length(source, target, route)

        next_value = None if length is None else str(length)
        if segment.get("length_m_decimal") != next_value:
            uow.execute(
                update(bus_segment)
                .where(bus_segment.c.id == segment["id"])
                .values(
                    length_m_decimal=next_value,
                    row_version=bus_segment.c.row_version + 1,
                    updated_at_utc=now,
                )
            )
            changed.append(segment["id"])
    return tuple(changed)


def _route_method(value: str | None) -> RouteMethod | None:
    return ROUTE_METHOD_BY_MOUNT_WAY.get(str(value or ""))


def _root_geometry(uow, project_id: str, resource_id: str, route: RouteMethod):
    instance = (
        uow.execute(
            select(
                project_instance.c.room_id,
                project_instance.c.board_id,
                project_instance.c.parameters_json,
                board.c.designation.label("board_designation"),
            )
            .select_from(
                project_instance.join(
                    instance_resource,
                    instance_resource.c.project_instance_id == project_instance.c.id,
                ).outerjoin(board, board.c.id == project_instance.c.board_id)
            )
            .where(
                instance_resource.c.id == resource_id,
                instance_resource.c.project_id == project_id,
                project_instance.c.project_id == project_id,
                project_instance.c.lifecycle == "ACTIVE",
            )
        )
        .mappings()
        .one_or_none()
    )
    if instance is None:
        return None, {"root_resource"}

    board_designation = str(instance.get("board_designation") or "").strip()
    if board_designation:
        rows = [
            dict(row)
            for row in uow.execute(
                select(field_device).where(
                    field_device.c.project_id == project_id,
                    field_device.c.lifecycle == "ACTIVE",
                    field_device.c.normalized_fields_json["DEVICE_TYPE"].as_string() == "BOARD",
                    field_device.c.normalized_fields_json["BOARD_ID"].as_string()
                    == board_designation,
                )
            ).mappings()
        ]
        return _geometry_from_device_rows(uow, rows, route)

    return _geometry_from_candidates(
        uow,
        ((dict(instance.get("parameters_json") or {}), instance.get("room_id")),),
        route,
    )


def _endpoint_geometry(uow, project_id: str, endpoint_id: str, route: RouteMethod):
    endpoint = (
        uow.execute(
            select(bus_endpoint).where(
                bus_endpoint.c.id == endpoint_id,
                bus_endpoint.c.project_id == project_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if endpoint is None:
        return None, {"endpoint"}

    if endpoint["endpoint_kind"] == "FIELD_DEVICE":
        row = (
            uow.execute(
                select(field_device).where(
                    field_device.c.id == endpoint["field_device_id"],
                    field_device.c.project_id == project_id,
                    field_device.c.lifecycle == "ACTIVE",
                )
            )
            .mappings()
            .one_or_none()
        )
        return _geometry_from_device_rows(uow, [] if row is None else [dict(row)], route)

    if endpoint["endpoint_kind"] == "INSTANCE_RESOURCE":
        instance = (
            uow.execute(
                select(project_instance)
                .join(
                    instance_resource,
                    instance_resource.c.project_instance_id == project_instance.c.id,
                )
                .where(
                    instance_resource.c.id == endpoint["resource_id"],
                    instance_resource.c.project_id == project_id,
                    project_instance.c.project_id == project_id,
                    project_instance.c.lifecycle == "ACTIVE",
                )
            )
            .mappings()
            .one_or_none()
        )
        if instance is None:
            return None, {"instance_resource"}
        return _geometry_from_candidates(
            uow,
            ((dict(instance.get("parameters_json") or {}), instance.get("room_id")),),
            route,
        )

    return None, {"endpoint_kind"}


def _geometry_from_device_rows(uow, rows: list[dict], route: RouteMethod):
    candidates = [
        (dict(row.get("normalized_fields_json") or {}), row.get("room_id")) for row in rows
    ]
    return _geometry_from_candidates(uow, tuple(candidates), route)


def _geometry_from_candidates(uow, candidates, route: RouteMethod):
    if not candidates:
        return None, {"geometry"}

    facts = []
    for fields, room_id in candidates:
        room_row = (
            uow.execute(select(room).where(room.c.id == room_id)).mappings().one_or_none()
            if room_id
            else None
        )
        facts.append(
            {
                "x": _first(fields, "x", "X"),
                "y": _first(fields, "y", "Y"),
                "mount": _first(fields, "mount_height_mm", "MOUNT_HEIGHT"),
                "base": None if room_row is None else room_row["base_mark"],
                "height": None if room_row is None else room_row["height_m_decimal"],
                "room_id": room_id,
            }
        )

    required = {"x", "y"}
    if route in {
        RouteMethod.FLOOR,
        RouteMethod.CEILING,
        RouteMethod.WALL,
        RouteMethod.TIMBER,
    }:
        required.add("mount")
    if route is RouteMethod.FLOOR:
        required.add("base")
    if route is RouteMethod.CEILING:
        required.add("height")

    missing = {key for fact in facts for key in required if fact[key] in (None, "")}
    if route in {RouteMethod.FLOOR, RouteMethod.CEILING} and any(
        not fact["room_id"] for fact in facts
    ):
        missing.add("room")
    complete = [fact for fact in facts if all(fact[key] not in (None, "") for key in required)]
    try:
        signatures = {
            tuple(Decimal(str(fact[key])) for key in sorted(required)) for fact in complete
        }
    except InvalidOperation:
        return None, {"invalid_endpoint_geometry"}
    if len(signatures) > 1:
        missing.add("ambiguous_endpoint_geometry")
    if missing:
        return None, missing

    fact = complete[0]
    try:
        return (
            CablePointInput.from_values(
                x_mm=fact["x"],
                y_mm=fact["y"],
                mount_height_mm=fact["mount"] or 0,
                base_mark_mm=fact["base"] or 0,
                room_height_m=fact["height"] or 0,
            ),
            set(),
        )
    except (ValueError, InvalidOperation):
        return None, {"invalid_endpoint_geometry"}


def _first(values: dict, *keys: str):
    for key in keys:
        if values.get(key) not in (None, ""):
            return values[key]
    return None
