# ruff: noqa: E501
"""Segment-native cable and conduit recalculation for schema revision 7.

The functions in this module accept an existing unit of work so callers can
materialize Project topology and its derived lengths atomically.  They never
scan a DWG and never open another database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import delete, func, select, update

from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.schema import (
    cable_length_fact,
    cable_line,
    cable_point,
    cable_point_field_device,
    cable_segment,
    cable_topology_endpoint,
    conduit,
    conduit_segment_assignment,
    field_device,
    field_port,
    instance_resource,
    project_instance,
    project_setting,
    room,
)

from .domain import (
    ROUTE_METHOD_BY_MOUNT_WAY,
    CablePointInput,
    ConduitContractError,
    RouteMethod,
    calculate_segment_length,
    conduit_is_present,
    conduit_length_from_segment_length,
    format_conduit_id,
)

CALCULATION_REVISION = 1
CALCULATION_SOURCE = "PERSISTED_CABLE_SEGMENTS_V1"


class RecalculationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RecalculationResult:
    segment_ids: tuple[str, ...]
    line_ids: tuple[str, ...]
    incomplete_segment_ids: tuple[str, ...]


def recalculate_segments(
    uow,
    project_id: str,
    *,
    segment_ids: set[str] | None = None,
    line_ids: set[str] | None = None,
    room_ids: set[str] | None = None,
    device_ids: set[str] | None = None,
    recalculate_geometry: bool = True,
    reconcile_conduits: bool = True,
) -> RecalculationResult:
    """Recalculate the affected persisted segments, lines and conduits."""

    selected = select(cable_segment).where(cable_segment.c.project_id == project_id)
    if segment_ids is not None:
        selected = selected.where(cable_segment.c.id.in_(segment_ids))
    if line_ids is not None:
        selected = selected.where(cable_segment.c.cable_line_id.in_(line_ids))
    rows = [dict(row) for row in uow.execute(selected).mappings()]
    if device_ids is not None:
        endpoint_ids = _device_endpoint_ids(uow, project_id, device_ids)
        rows = [
            row
            for row in rows
            if row["source_endpoint_id"] in endpoint_ids
            or row["target_endpoint_id"] in endpoint_ids
        ]
    if room_ids is not None:
        rows = [row for row in rows if _segment_room_ids(uow, project_id, row) & room_ids]
    affected_segments = {row["id"] for row in rows}
    affected_lines = {row["cable_line_id"] for row in rows}

    incomplete: set[str] = set()
    now = datetime.now(UTC)
    if recalculate_geometry:
        for segment_row in rows:
            route = _route_method(segment_row["mount_way"])
            source, source_missing = _endpoint_geometry(
                uow, project_id, segment_row["source_endpoint_id"], route
            )
            target, target_missing = _endpoint_geometry(
                uow, project_id, segment_row["target_endpoint_id"], route
            )
            missing = source_missing | target_missing
            length: Decimal | None = None
            if not missing:
                length, _trace = calculate_segment_length(source, target, route)
            else:
                incomplete.add(segment_row["id"])
            stored = segment_row["calculated_length_m_decimal"]
            next_value = None if length is None else str(length)
            if stored != next_value or segment_row["calculation_revision"] != CALCULATION_REVISION:
                uow.execute(
                    update(cable_segment)
                    .where(cable_segment.c.id == segment_row["id"])
                    .values(
                        calculated_length_m_decimal=next_value,
                        calculation_revision=CALCULATION_REVISION,
                        row_version=cable_segment.c.row_version + 1,
                        updated_at_utc=now,
                    )
                )
                segment_row["calculated_length_m_decimal"] = next_value
            if reconcile_conduits:
                _reconcile_segment_conduit(uow, project_id, segment_row, now)
            else:
                assigned = uow.execute(
                    select(conduit_segment_assignment.c.conduit_id).where(
                        conduit_segment_assignment.c.cable_segment_id == segment_row["id"]
                    )
                ).scalar_one_or_none()
                if assigned:
                    _refresh_conduit_length(uow, project_id, assigned, now)

    for line_id in affected_lines | (line_ids or set()):
        _recalculate_line_fact(uow, project_id, line_id, now)
    return RecalculationResult(
        tuple(sorted(affected_segments)),
        tuple(sorted(affected_lines | (line_ids or set()))),
        tuple(sorted(incomplete)),
    )


def _device_endpoint_ids(uow, project_id: str, device_ids: set[str]) -> set[str]:
    """Include both sides of shared points/ports and all roots of accepted BOARD devices."""
    points = select(cable_point_field_device.c.cable_point_id).where(
        cable_point_field_device.c.field_device_id.in_(device_ids)
    )
    ports = select(field_port.c.id).where(field_port.c.field_device_id.in_(device_ids))
    board_names = [
        fields["BOARD_ID"]
        for fields in uow.execute(
            select(field_device.c.normalized_fields_json).where(
                field_device.c.project_id == project_id,
                field_device.c.id.in_(device_ids),
                field_device.c.lifecycle == "ACTIVE",
            )
        ).scalars()
        if fields.get("DEVICE_TYPE") == "BOARD" and fields.get("BOARD_ID")
    ]
    board_lines = select(cable_line.c.id).where(
        cable_line.c.project_id == project_id,
        cable_line.c.cable_facts_json["BOARD"].as_string().in_(board_names),
    )
    internal = select(cable_point.c.id).where(
        cable_point.c.point_kind == "INTERNAL_SOURCE", cable_point.c.cable_line_id.in_(board_lines)
    )
    return set(
        uow.execute(
            select(cable_topology_endpoint.c.id).where(
                cable_topology_endpoint.c.project_id == project_id,
                cable_topology_endpoint.c.cable_point_id.in_(points)
                | cable_topology_endpoint.c.field_port_id.in_(ports)
                | cable_topology_endpoint.c.cable_point_id.in_(internal),
            )
        ).scalars()
    )


def _route_method(mount_way: str | None) -> RouteMethod:
    try:
        return ROUTE_METHOD_BY_MOUNT_WAY[str(mount_way or "")]
    except KeyError as exc:
        raise RecalculationError("Cable segment has no supported MOUNT_WAY") from exc


def segment_geometry_diagnostics(uow, project_id: str, segment_row: dict) -> dict:
    """Return calculation readiness for one persisted segment without mutating data."""

    try:
        route = _route_method(segment_row.get("mount_way"))
    except RecalculationError:
        return {
            "complete": False,
            "calculated_length_m": None,
            "missing": ("mount_way",),
        }
    source, source_missing = _endpoint_geometry(
        uow, project_id, segment_row["source_endpoint_id"], route
    )
    target, target_missing = _endpoint_geometry(
        uow, project_id, segment_row["target_endpoint_id"], route
    )
    missing = tuple(
        sorted(
            {f"source:{value}" for value in source_missing}
            | {f"target:{value}" for value in target_missing}
        )
    )
    if missing:
        return {
            "complete": False,
            "calculated_length_m": None,
            "missing": missing,
        }
    length, _trace = calculate_segment_length(source, target, route)
    return {
        "complete": True,
        "calculated_length_m": str(length),
        "missing": (),
    }


def _endpoint_geometry(uow, project_id: str, endpoint_id: str, route: RouteMethod):
    endpoint = (
        uow.execute(
            select(cable_topology_endpoint).where(
                cable_topology_endpoint.c.id == endpoint_id,
                cable_topology_endpoint.c.project_id == project_id,
            )
        )
        .mappings()
        .one()
    )
    location: dict = {}
    device_rows: list[dict] = []
    direct_room_id = None
    if endpoint["endpoint_kind"] == "TOPOLOGY_POINT":
        point = (
            uow.execute(select(cable_point).where(cable_point.c.id == endpoint["cable_point_id"]))
            .mappings()
            .one()
        )
        location = dict(point["location_json"] or {})
        if point["point_kind"] == "INTERNAL_SOURCE":
            line_facts = (
                uow.execute(
                    select(cable_line.c.cable_facts_json).where(
                        cable_line.c.id == point["cable_line_id"],
                        cable_line.c.project_id == project_id,
                    )
                ).scalar_one_or_none()
                or {}
            )
            board_designation = str(line_facts.get("BOARD") or "").strip()
            device_rows = (
                [
                    dict(row)
                    for row in uow.execute(
                        select(field_device).where(
                            field_device.c.project_id == project_id,
                            field_device.c.lifecycle == "ACTIVE",
                            field_device.c.normalized_fields_json["DEVICE_TYPE"].as_string()
                            == "BOARD",
                            field_device.c.normalized_fields_json["BOARD_ID"].as_string()
                            == board_designation,
                        )
                    ).mappings()
                ]
                if board_designation
                else []
            )
        else:
            device_rows = [
                dict(row)
                for row in uow.execute(
                    select(field_device)
                    .join(
                        cable_point_field_device,
                        cable_point_field_device.c.field_device_id == field_device.c.id,
                    )
                    .where(cable_point_field_device.c.cable_point_id == point["id"])
                ).mappings()
            ]
    elif endpoint["endpoint_kind"] == "FIELD_PORT":
        device_rows = [
            dict(
                uow.execute(
                    select(field_device)
                    .join(field_port, field_port.c.field_device_id == field_device.c.id)
                    .where(field_port.c.id == endpoint["field_port_id"])
                )
                .mappings()
                .one()
            )
        ]
    elif endpoint["endpoint_kind"] == "INSTANCE_RESOURCE":
        instance = (
            uow.execute(
                select(project_instance)
                .join(
                    instance_resource,
                    instance_resource.c.project_instance_id == project_instance.c.id,
                )
                .where(instance_resource.c.id == endpoint["instance_resource_id"])
            )
            .mappings()
            .one()
        )
        location = dict(instance["parameters_json"] or {})
        direct_room_id = instance["room_id"]

    candidates = []
    if device_rows:
        for device in device_rows:
            fields = dict(device["normalized_fields_json"] or {})
            candidates.append((fields, device["room_id"]))
    else:
        candidates.append((location, direct_room_id))

    facts = []
    for fields, room_id in candidates:
        merged = {**location, **fields}
        room_row = None
        if room_id:
            room_row = (
                uow.execute(select(room).where(room.c.id == room_id)).mappings().one_or_none()
            )
        facts.append(
            {
                "x": _first(merged, "x", "X"),
                "y": _first(merged, "y", "Y"),
                "mount": _first(merged, "mount_height_mm", "MOUNT_HEIGHT"),
                "base": None if room_row is None else room_row["base_mark"],
                "height": None if room_row is None else room_row["height_m_decimal"],
                "room_id": room_id,
            }
        )
    required = {"x", "y"}
    if route in {RouteMethod.FLOOR, RouteMethod.CEILING, RouteMethod.WALL, RouteMethod.TIMBER}:
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
        missing.add("ambiguous_shared_endpoint_geometry")
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


def _segment_room_ids(uow, project_id: str, segment_row: dict) -> set[str]:
    result: set[str] = set()
    for endpoint_id in (segment_row["source_endpoint_id"], segment_row["target_endpoint_id"]):
        endpoint = (
            uow.execute(
                select(cable_topology_endpoint).where(cable_topology_endpoint.c.id == endpoint_id)
            )
            .mappings()
            .one()
        )
        if endpoint["endpoint_kind"] == "TOPOLOGY_POINT":
            point = (
                uow.execute(
                    select(cable_point).where(cable_point.c.id == endpoint["cable_point_id"])
                )
                .mappings()
                .one()
            )
            if point["point_kind"] == "INTERNAL_SOURCE":
                line_facts = (
                    uow.execute(
                        select(cable_line.c.cable_facts_json).where(
                            cable_line.c.id == point["cable_line_id"],
                            cable_line.c.project_id == project_id,
                        )
                    ).scalar_one_or_none()
                    or {}
                )
                board_designation = str(line_facts.get("BOARD") or "").strip()
                if board_designation:
                    result.update(
                        room_id
                        for room_id in uow.execute(
                            select(field_device.c.room_id).where(
                                field_device.c.project_id == project_id,
                                field_device.c.lifecycle == "ACTIVE",
                                field_device.c.normalized_fields_json["DEVICE_TYPE"].as_string()
                                == "BOARD",
                                field_device.c.normalized_fields_json["BOARD_ID"].as_string()
                                == board_designation,
                            )
                        ).scalars()
                        if room_id
                    )
            else:
                result.update(
                    room_id
                    for room_id in uow.execute(
                        select(field_device.c.room_id)
                        .join(
                            cable_point_field_device,
                            cable_point_field_device.c.field_device_id == field_device.c.id,
                        )
                        .where(
                            cable_point_field_device.c.cable_point_id == endpoint["cable_point_id"],
                            field_device.c.project_id == project_id,
                        )
                    ).scalars()
                    if room_id
                )
        elif endpoint["endpoint_kind"] == "FIELD_PORT":
            room_id = uow.execute(
                select(field_device.c.room_id)
                .join(field_port, field_port.c.field_device_id == field_device.c.id)
                .where(field_port.c.id == endpoint["field_port_id"])
            ).scalar_one_or_none()
            if room_id:
                result.add(room_id)
        else:
            room_id = uow.execute(
                select(project_instance.c.room_id)
                .join(
                    instance_resource,
                    instance_resource.c.project_instance_id == project_instance.c.id,
                )
                .where(instance_resource.c.id == endpoint["instance_resource_id"])
            ).scalar_one_or_none()
            if room_id:
                result.add(room_id)
    return result


def _recalculate_line_fact(uow, project_id: str, line_id: str, now: datetime) -> None:
    segments = list(
        uow.execute(
            select(
                cable_segment.c.calculated_length_m_decimal,
                cable_segment.c.source_endpoint_id,
                cable_segment.c.target_endpoint_id,
            ).where(
                cable_segment.c.project_id == project_id,
                cable_segment.c.cable_line_id == line_id,
            )
        ).mappings()
    )
    existing = (
        uow.execute(
            select(cable_length_fact).where(
                cable_length_fact.c.project_id == project_id,
                cable_length_fact.c.cable_line_id == line_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    additional = "0" if existing is None else existing["additional_length_m_decimal"] or "0"
    manual = None if existing is None else existing["manual_full_length_m_decimal"]
    complete = bool(segments) and all(
        row["calculated_length_m_decimal"] is not None for row in segments
    )
    automatic = (
        str(sum((Decimal(row["calculated_length_m_decimal"]) for row in segments), Decimal(0)))
        if complete
        else None
    )
    status = "KNOWN" if complete or manual is not None else "INCOMPLETE"
    values = {
        "calculated_length_m_decimal": automatic,
        "calculation_source": CALCULATION_SOURCE,
        "calculation_revision": CALCULATION_REVISION,
        "additional_length_m_decimal": additional,
        "manual_full_length_m_decimal": manual,
        "rounding_policy": "NONE",
        "knowledge_status": status,
    }
    if existing is None:
        uow.execute(
            cable_length_fact.insert().values(
                id=new_id(), project_id=project_id, cable_line_id=line_id, **values
            )
        )
    elif any(existing[key] != value for key, value in values.items()):
        uow.execute(
            update(cable_length_fact)
            .where(cable_length_fact.c.id == existing["id"])
            .values(**values, row_version=cable_length_fact.c.row_version + 1, updated_at_utc=now)
        )


def board_reserve_for_line(uow, project_id: str, line_id: str) -> Decimal:
    """Return reserve when the physical graph root is owned by the line board."""

    target_ids = select(cable_segment.c.target_endpoint_id).where(
        cable_segment.c.project_id == project_id,
        cable_segment.c.cable_line_id == line_id,
    )
    source_ids = select(cable_segment.c.source_endpoint_id).where(
        cable_segment.c.project_id == project_id,
        cable_segment.c.cable_line_id == line_id,
    )
    roots = [
        dict(row)
        for row in uow.execute(
            select(cable_topology_endpoint).where(
                cable_topology_endpoint.c.project_id == project_id,
                cable_topology_endpoint.c.cable_line_id == line_id,
                cable_topology_endpoint.c.id.in_(source_ids),
                cable_topology_endpoint.c.id.not_in(target_ids),
            )
        ).mappings()
    ]
    board_owned = False
    for endpoint in roots:
        if endpoint["endpoint_kind"] == "INSTANCE_RESOURCE":
            if endpoint["instance_resource_id"] is None:
                continue
            owner_board_id = uow.execute(
                select(project_instance.c.board_id)
                .join(
                    instance_resource,
                    instance_resource.c.project_instance_id == project_instance.c.id,
                )
                .where(instance_resource.c.id == endpoint["instance_resource_id"])
            ).scalar_one_or_none()
            if owner_board_id is not None:
                board_owned = True
                break
        elif endpoint["endpoint_kind"] == "TOPOLOGY_POINT":
            point_kind = uow.execute(
                select(cable_point.c.point_kind).where(
                    cable_point.c.id == endpoint["cable_point_id"]
                )
            ).scalar_one_or_none()
            if point_kind == "INTERNAL_SOURCE":
                line_board_id = uow.execute(
                    select(cable_line.c.board_id).where(
                        cable_line.c.id == line_id,
                        cable_line.c.project_id == project_id,
                    )
                ).scalar_one_or_none()
                if line_board_id is not None:
                    board_owned = True
                    break
    if not board_owned:
        return Decimal(0)
    value = uow.execute(
        select(project_setting.c.value_json).where(
            project_setting.c.project_id == project_id,
            project_setting.c.setting_key == "cable_reserve_at_board_m",
        )
    ).scalar_one_or_none()
    return Decimal(str(value or 0))


def _reconcile_segment_conduit(uow, project_id: str, segment_row: dict, now: datetime) -> None:
    mount_way = str(segment_row["mount_way"] or "")
    conduit_type = str(segment_row["gofra_type"] or "")
    try:
        present = conduit_is_present(mount_way, conduit_type)
    except ConduitContractError as exc:
        raise RecalculationError(str(exc)) from exc
    assignment = uow.execute(
        select(conduit_segment_assignment.c.conduit_id).where(
            conduit_segment_assignment.c.project_id == project_id,
            conduit_segment_assignment.c.cable_segment_id == segment_row["id"],
        )
    ).scalar_one_or_none()
    if not present:
        if assignment:
            _remove_assignment_and_empty_auto(uow, project_id, segment_row["id"], assignment)
        return
    if assignment is None:
        number = (
            uow.execute(
                select(func.max(conduit.c.conduit_number)).where(conduit.c.project_id == project_id)
            ).scalar_one()
            or 0
        ) + 1
        if number > 999:
            raise RecalculationError("No automatic conduit number remains")
        designation = format_conduit_id(number, conduit_type)
        conduit_id = new_id()
        calculated_length = segment_row["calculated_length_m_decimal"]
        conduit_length = (
            None
            if calculated_length is None
            else str(
                conduit_length_from_segment_length(
                    calculated_length, _route_method(segment_row["mount_way"])
                )
            )
        )
        uow.execute(
            conduit.insert().values(
                id=conduit_id,
                project_id=project_id,
                designation=designation,
                conduit_number=number,
                conduit_type=conduit_type,
                color=segment_row["gofra_color"],
                length_m_decimal=conduit_length,
                path_json={
                    "origin": "AUTO_SEGMENT",
                    "source_segment_id": segment_row["id"],
                    "length_source": "SEGMENT_GEOMETRY",
                },
            )
        )
        uow.execute(
            conduit_segment_assignment.insert().values(
                id=new_id(),
                project_id=project_id,
                conduit_id=conduit_id,
                cable_segment_id=segment_row["id"],
            )
        )
        _set_target_gofra_id(uow, segment_row["id"], designation, now)
        return
    _refresh_conduit_length(uow, project_id, assignment, now)


def _refresh_conduit_length(uow, project_id: str, conduit_id: str, now: datetime) -> None:
    conduit_row = uow.execute(select(conduit).where(conduit.c.id == conduit_id)).mappings().one()
    path = dict(conduit_row["path_json"] or {})
    if path.get("length_source") == "USER_CONFIRMED":
        return
    segments = list(
        uow.execute(
            select(
                cable_segment.c.calculated_length_m_decimal,
                cable_segment.c.mount_way,
            )
            .join(
                conduit_segment_assignment,
                conduit_segment_assignment.c.cable_segment_id == cable_segment.c.id,
            )
            .where(conduit_segment_assignment.c.conduit_id == conduit_id)
        ).mappings()
    )
    value = None
    if len(segments) == 1 and segments[0]["calculated_length_m_decimal"] is not None:
        value = str(
            conduit_length_from_segment_length(
                segments[0]["calculated_length_m_decimal"],
                _route_method(segments[0]["mount_way"]),
            )
        )
    if len(segments) == 1:
        path["length_source"] = "SEGMENT_GEOMETRY" if value is not None else "INCOMPLETE_SEGMENT"
    else:
        path["length_source"] = "INCOMPLETE_SHARED"
    if conduit_row["length_m_decimal"] != value or conduit_row["path_json"] != path:
        uow.execute(
            update(conduit)
            .where(conduit.c.id == conduit_id)
            .values(
                length_m_decimal=value,
                path_json=path,
                row_version=conduit.c.row_version + 1,
                updated_at_utc=now,
            )
        )


def refresh_conduit_length(uow, project_id: str, conduit_id: str) -> None:
    _refresh_conduit_length(uow, project_id, conduit_id, datetime.now(UTC))


def _remove_assignment_and_empty_auto(
    uow, project_id: str, segment_id: str, conduit_id: str
) -> None:
    uow.execute(
        delete(conduit_segment_assignment).where(
            conduit_segment_assignment.c.project_id == project_id,
            conduit_segment_assignment.c.cable_segment_id == segment_id,
        )
    )
    count = uow.execute(
        select(func.count())
        .select_from(conduit_segment_assignment)
        .where(conduit_segment_assignment.c.conduit_id == conduit_id)
    ).scalar_one()
    path = uow.execute(
        select(conduit.c.path_json).where(conduit.c.id == conduit_id)
    ).scalar_one_or_none()
    if count == 0 and (path or {}).get("origin") in {"AUTO_LINE", "AUTO_SEGMENT"}:
        uow.execute(delete(conduit).where(conduit.c.id == conduit_id))
    elif count:
        _refresh_conduit_length(uow, project_id, conduit_id, datetime.now(UTC))


def _set_target_gofra_id(uow, segment_id: str, designation: str, now: datetime) -> None:
    device_ids = list(
        uow.execute(
            select(cable_point_field_device.c.field_device_id)
            .join(
                cable_topology_endpoint,
                cable_topology_endpoint.c.cable_point_id
                == cable_point_field_device.c.cable_point_id,
            )
            .join(cable_segment, cable_segment.c.target_endpoint_id == cable_topology_endpoint.c.id)
            .where(cable_segment.c.id == segment_id)
        ).scalars()
    )
    for device_id in device_ids:
        fields = dict(
            uow.execute(
                select(field_device.c.normalized_fields_json).where(field_device.c.id == device_id)
            ).scalar_one()
            or {}
        )
        if fields.get("GOFRA_ID") == designation:
            continue
        fields["GOFRA_ID"] = designation
        uow.execute(
            update(field_device)
            .where(field_device.c.id == device_id)
            .values(
                normalized_fields_json=fields,
                row_version=field_device.c.row_version + 1,
                updated_at_utc=now,
            )
        )
