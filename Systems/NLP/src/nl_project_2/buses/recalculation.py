"""Derived physical lengths for persisted bus segments."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal, InvalidOperation

from sqlalchemy import select, update

from nl_project_2.cables.domain import (
    ROUTE_METHOD_BY_MOUNT_WAY,
    CablePointInput,
    RouteMethod,
    calculate_segment_length,
    conduit_length_from_segment_length,
)
from nl_project_2.cables.recalculation import (
    CableLengthBreakdown,
    cable_length_policy,
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


def bus_length_breakdown(uow, project_id: str, bus_id: str) -> CableLengthBreakdown:
    policy = cable_length_policy(uow, project_id)
    bus_row = (
        uow.execute(
            select(bus.c.root_resource_id).where(
                bus.c.id == bus_id,
                bus.c.project_id == project_id,
                bus.c.lifecycle == "ACTIVE",
            )
        )
        .mappings()
        .one_or_none()
    )
    if bus_row is None:
        raise ValueError("Bus not found")

    segments = [
        dict(row)
        for row in uow.execute(
            select(bus_segment).where(
                bus_segment.c.project_id == project_id,
                bus_segment.c.bus_id == bus_id,
            )
        ).mappings()
    ]
    if not segments or any(row["length_m_decimal"] is None for row in segments):
        raise ValueError("Bus length is incomplete")

    route_geometry = Decimal(0)
    timber_segments = 0
    for segment in segments:
        route = _route_method(segment.get("mount_way"))
        if route is None:
            raise ValueError("Bus mount way is incomplete")
        length = Decimal(str(segment["length_m_decimal"]))
        route_geometry += conduit_length_from_segment_length(length, route)
        if route is RouteMethod.TIMBER:
            timber_segments += 1

    owner_board_id = uow.execute(
        select(project_instance.c.board_id)
        .join(
            instance_resource,
            instance_resource.c.project_instance_id == project_instance.c.id,
        )
        .where(
            instance_resource.c.id == bus_row["root_resource_id"],
            instance_resource.c.project_id == project_id,
            project_instance.c.project_id == project_id,
            project_instance.c.lifecycle == "ACTIVE",
        )
    ).scalar_one_or_none()
    board_reserve = policy.board_reserve_m if owner_board_id is not None else Decimal(0)

    endpoint_rows = uow.execute(
        select(field_device.c.normalized_fields_json)
        .select_from(
            bus_endpoint.join(
                field_device,
                field_device.c.id == bus_endpoint.c.field_device_id,
            )
        )
        .where(
            bus_endpoint.c.project_id == project_id,
            bus_endpoint.c.bus_id == bus_id,
            bus_endpoint.c.endpoint_kind == "FIELD_DEVICE",
            field_device.c.lifecycle == "ACTIVE",
        )
    ).scalars()
    endpoint_mechanisms = sum(
        1
        for fields in endpoint_rows
        if str((fields or {}).get("DEVICE_TYPE") or "").strip().upper()
        in {"SOCKET", "SWITCH", "BUTTON"}
    )
    endpoint_reserve = policy.endpoint_reserve_m * endpoint_mechanisms
    geometric = route_geometry + board_reserve + endpoint_reserve
    meander = geometric * policy.meander_percent / Decimal(100)
    obstacle = geometric * policy.obstacle_percent / Decimal(100)
    timber = policy.timber_segment_reserve_m * timber_segments
    unrounded = geometric + meander + obstacle + timber
    rounded = unrounded.to_integral_value(rounding=ROUND_CEILING)

    return CableLengthBreakdown(
        route_geometry_m=route_geometry,
        board_reserve_m=board_reserve,
        distribution_box_reserve_m=Decimal(0),
        endpoint_reserve_m=endpoint_reserve,
        geometric_m=geometric,
        meander_reserve_m=meander,
        obstacle_reserve_m=obstacle,
        timber_reserve_m=timber,
        additional_m=Decimal(0),
        unrounded_m=unrounded,
        rounded_m=rounded,
        distribution_box_lines=0,
        endpoint_mechanisms=endpoint_mechanisms,
        timber_segments=timber_segments,
    )


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
