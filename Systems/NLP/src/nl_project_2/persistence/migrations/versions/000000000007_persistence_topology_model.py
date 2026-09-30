"""Add persisted physical-topology identities and owner-safe migration.

Revision ID: 000000000007
Revises: 000000000006
Affected entities: field devices/ports/keys, cable points/endpoints/segments,
segment conduit assignments, cable-line assignments, user reserve, LED sync facts.

The upgrade converts only a legacy line with exactly one physical point into a
segment. Other legacy point orders and line-owned conduit facts are preserved in
``topology_migration_review`` with ``MIGRATION_REVIEW_REQUIRED``; no route is guessed.
Downgrade is supported only while the new topology contains migration-produced,
losslessly representable facts. It refuses before DDL when new project facts exist.
"""

from __future__ import annotations

import json
import uuid
from collections import defaultdict
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

from nl_project_2.persistence import schema

revision = "000000000007"
down_revision = "000000000006"
branch_labels = None
depends_on = None

ROUTE_KEYS = ("MOUNT_WAY", "GOFRA_TYPE", "GOFRA_COLOR", "GOFRA_ID")
PORTS_BY_BLOCK = {
    "WB_MRM2_MINI": {
        "K1": ("RELAY_OUTPUT", "OUT"),
        "K2": ("RELAY_OUTPUT", "OUT"),
        "IN_1": ("DIGITAL_INPUT", "IN"),
        "IN_2": ("DIGITAL_INPUT", "IN"),
    },
    "SENSOR_M1W2": {
        "W1": ("ONEWIRE_CHANNEL", "BIDIRECTIONAL"),
        "W2": ("ONEWIRE_CHANNEL", "BIDIRECTIONAL"),
    },
}


def _id() -> str:
    return str(uuid.uuid4())


def _tables(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def _columns(bind, table: str) -> set[str]:
    if table not in _tables(bind):
        return set()
    return {item["name"] for item in sa.inspect(bind).get_columns(table)}


def _json(value) -> dict:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {"_legacy_raw": value}
        return dict(decoded) if isinstance(decoded, dict) else {"_legacy_value": decoded}
    return dict(value)


def _datetime(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _dump(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _add_cable_point_columns(bind) -> bool:
    columns = _columns(bind, "cable_point")
    legacy_shape = "logical_identity" not in columns
    if not legacy_shape:
        return False
    op.add_column("cable_point", sa.Column("logical_identity", sa.String(160)))
    op.add_column(
        "cable_point",
        sa.Column(
            "origin_kind",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'MIGRATION'"),
        ),
    )
    op.add_column(
        "cable_point",
        sa.Column(
            "migration_state",
            sa.String(40),
            nullable=False,
            server_default=sa.text("'CONFIRMED'"),
        ),
    )
    return True


def _normalize_legacy_points(
    bind,
    point_rows: list[dict],
    device_rows: dict[str, dict],
) -> tuple[list[dict], list[dict]]:
    grouped: dict[tuple[str, str | None, str | None], list[dict]] = defaultdict(list)
    for source_row in point_rows:
        row = dict(source_row)
        fields = _json(
            device_rows.get(row.get("field_device_id"), {}).get("normalized_fields_json")
        )
        logical_identity = str(fields.get("CABLE_ID") or "").strip() or None
        row["logical_identity"] = logical_identity
        grouped[
            (
                str(row["project_id"]),
                logical_identity,
                None if logical_identity is not None else str(row["id"]),
            )
        ].append(row)

    topology_rows: list[dict] = []
    membership_rows: list[dict] = []
    for group_key in sorted(
        grouped,
        key=lambda item: (item[0], item[1] or "", item[2] or ""),
    ):
        rows = sorted(
            grouped[group_key],
            key=lambda item: (int(item.get("ordinal") or 0), str(item["id"])),
        )
        logical_identity = group_key[1]
        line_ids = {str(row["cable_line_id"]) for row in rows}
        if logical_identity is not None and len(line_ids) != 1:
            raise RuntimeError(
                "Legacy shared cable identity spans multiple cable lines: "
                f"project={group_key[0]}, identity={logical_identity}"
            )

        canonical = dict(rows[0])
        canonical["field_device_id"] = None
        canonical["point_kind"] = (
            "INSTALLATION_GROUP"
            if logical_identity is not None and len(rows) > 1
            else "DEVICE_POINT"
        )
        bind.execute(
            sa.text(
                "UPDATE cable_point SET point_kind=:point_kind, logical_identity=:identity, "
                "origin_kind='MIGRATION', migration_state='CONFIRMED', field_device_id=NULL "
                "WHERE id=:point_id"
            ),
            {
                "identity": logical_identity,
                "point_kind": canonical["point_kind"],
                "point_id": canonical["id"],
            },
        )
        for row in rows:
            membership = dict(row)
            membership["id"] = canonical["id"]
            membership_rows.append(membership)
        for duplicate in rows[1:]:
            bind.execute(
                sa.text("DELETE FROM cable_point WHERE id=:point_id"),
                {"point_id": duplicate["id"]},
            )
        topology_rows.append(canonical)

    with op.batch_alter_table("cable_point") as batch:
        batch.create_unique_constraint(
            "uq_cable_point_id_project",
            ["id", "project_id"],
        )
        batch.create_unique_constraint(
            "uq_cable_point_id_project_line",
            ["id", "project_id", "cable_line_id"],
        )
        batch.create_check_constraint(
            "point_kind",
            "point_kind IN ('INTERNAL_SOURCE','DEVICE_POINT','INSTALLATION_GROUP',"
            "'EL_BOX','BUS_POINT')",
        )
        batch.create_check_constraint("origin_kind", "origin_kind IN ('MIGRATION','PROJECT')")
        batch.create_check_constraint(
            "migration_state",
            "migration_state IN ('CONFIRMED','MIGRATION_REVIEW_REQUIRED')",
        )
        batch.create_check_constraint("legacy_device_owner_empty", "field_device_id IS NULL")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_cable_point_project_identity "
        "ON cable_point (project_id, logical_identity) WHERE logical_identity IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_cable_point_id_project "
        "ON cable_point (id, project_id)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_cable_point_id_project_line "
        "ON cable_point (id, project_id, cable_line_id)"
    )
    return topology_rows, membership_rows


def _upgrade_led_profile(bind) -> bool:
    columns = _columns(bind, "led_line_profile")
    if "sync_state" in columns:
        return False
    op.add_column(
        "led_line_profile",
        sa.Column(
            "led_type_origin",
            sa.String(24),
            nullable=False,
            server_default=sa.text("'MIGRATION'"),
        ),
    )
    op.add_column("led_line_profile", sa.Column("sync_baseline_json", sa.JSON()))
    op.add_column(
        "led_line_profile",
        sa.Column(
            "sync_state",
            sa.String(40),
            nullable=False,
            server_default=sa.text("'UNCONFIRMED'"),
        ),
    )
    checks = {
        item.get("name") for item in sa.inspect(bind).get_check_constraints("led_line_profile")
    }
    with op.batch_alter_table("led_line_profile") as batch:
        if "ck_led_line_profile_led_kind" in checks:
            batch.drop_constraint(op.f("ck_led_line_profile_led_kind"), type_="check")
        if "ck_led_line_profile_channels_positive" in checks:
            batch.drop_constraint(
                op.f("ck_led_line_profile_channels_positive"),
                type_="check",
            )
        batch.alter_column("voltage_decimal", existing_type=sa.Text(), nullable=True)
        batch.create_check_constraint("led_kind", "led_kind IN ('MONO','CCT','RGB','RGBW')")
        batch.create_check_constraint(
            "led_type_origin", "led_type_origin IN ('DWG','PROJECT','MIGRATION')"
        )
        batch.create_check_constraint(
            "sync_state",
            "sync_state IN ('UNCONFIRMED','IN_SYNC','DWG_CHANGED','PROJECT_CHANGED',"
            "'BOTH_CHANGED_CONFLICT')",
        )
        batch.create_check_constraint(
            "channels_match_kind",
            "(led_kind='MONO' AND channels=1) OR (led_kind='CCT' AND channels=2) OR "
            "(led_kind='RGB' AND channels=3) OR (led_kind='RGBW' AND channels=4)",
        )
    return True


def _review(
    bind,
    *,
    project_id: str,
    line_id: str,
    kind: str,
    legacy_id: str | None,
    reason: str,
    payload: dict,
) -> None:
    bind.execute(
        schema.topology_migration_review.insert().values(
            id=_id(),
            project_id=project_id,
            cable_line_id=line_id,
            review_kind=kind,
            legacy_source_id=legacy_id,
            reason=reason,
            legacy_payload_json=payload,
            review_state="MIGRATION_REVIEW_REQUIRED",
        )
    )


def _endpoint(
    bind,
    *,
    project_id: str,
    line_id: str,
    kind: str,
    point_id: str | None = None,
    resource_id: str | None = None,
    port_id: str | None = None,
) -> str:
    filters = [
        schema.cable_topology_endpoint.c.project_id == project_id,
        schema.cable_topology_endpoint.c.cable_line_id == line_id,
        schema.cable_topology_endpoint.c.endpoint_kind == kind,
    ]
    values = {
        "cable_point_id": point_id,
        "instance_resource_id": resource_id,
        "field_port_id": port_id,
    }
    if point_id is not None:
        filters.append(schema.cable_topology_endpoint.c.cable_point_id == point_id)
    elif resource_id is not None:
        filters.append(schema.cable_topology_endpoint.c.instance_resource_id == resource_id)
    else:
        filters.append(schema.cable_topology_endpoint.c.field_port_id == port_id)
    existing = bind.execute(
        sa.select(schema.cable_topology_endpoint.c.id).where(*filters)
    ).scalar_one_or_none()
    if existing is not None:
        return str(existing)
    identifier = _id()
    bind.execute(
        schema.cable_topology_endpoint.insert().values(
            id=identifier,
            project_id=project_id,
            cable_line_id=line_id,
            endpoint_kind=kind,
            **values,
        )
    )
    return identifier


def _materialize_memberships(bind, point_rows: list[dict]) -> None:
    for row in point_rows:
        device_id = row.get("field_device_id")
        if device_id is None:
            continue
        bind.execute(
            schema.cable_point_field_device.insert().values(
                id=_id(),
                project_id=row["project_id"],
                cable_point_id=row["id"],
                field_device_id=device_id,
            )
        )


def _materialize_ports_and_keys(bind, device_rows: dict[str, dict]) -> None:
    for device in device_rows.values():
        project_id = device["project_id"]
        block_kind = str(device.get("block_kind") or "").upper()
        for tag, (kind, direction) in PORTS_BY_BLOCK.get(block_kind, {}).items():
            bind.execute(
                schema.field_port.insert().values(
                    id=_id(),
                    project_id=project_id,
                    field_device_id=device["id"],
                    port_tag=tag,
                    port_kind=kind,
                    direction=direction,
                    contract_version=1,
                )
            )
        fields = _json(device.get("normalized_fields_json"))
        for key_tag in ("KEY_1", "KEY_2", "KEY_3", "KEY_4"):
            if key_tag not in fields:
                continue
            target_text = str(fields.get(key_tag) or "").strip()
            target_kind = "UNRESOLVED"
            line_id = None
            dali_id = None
            if target_text:
                line_id = bind.execute(
                    sa.select(schema.cable_line.c.id).where(
                        schema.cable_line.c.project_id == project_id,
                        schema.cable_line.c.designation == target_text,
                    )
                ).scalar_one_or_none()
                if line_id is not None:
                    target_kind = "CABLE_LINE"
                else:
                    dali_id = bind.execute(
                        sa.select(schema.dali_group.c.id).where(
                            schema.dali_group.c.project_id == project_id,
                            schema.dali_group.c.group_key == target_text,
                        )
                    ).scalar_one_or_none()
                    if dali_id is not None:
                        target_kind = "DALI_GROUP"
            bind.execute(
                schema.field_control_key.insert().values(
                    id=_id(),
                    project_id=project_id,
                    field_device_id=device["id"],
                    key_tag=key_tag,
                    functional_target_text=target_text or None,
                    target_kind=target_kind,
                    target_cable_line_id=line_id,
                    target_dali_group_id=dali_id,
                    origin_json={"kind": "MIGRATION", "field": key_tag},
                    baseline_json={"value": target_text} if target_text else None,
                )
            )


def _migrate_line_assignments(bind, legacy_assignments: list[dict]) -> dict[str, list[str]]:
    endpoints_by_line: dict[str, list[str]] = defaultdict(list)
    for row in legacy_assignments:
        endpoint_id = _endpoint(
            bind,
            project_id=row["project_id"],
            line_id=row["cable_line_id"],
            kind="INSTANCE_RESOURCE",
            resource_id=row["output_resource_id"],
        )
        bind.execute(
            schema.cable_line_assignment.insert().values(
                id=row["id"],
                project_id=row["project_id"],
                cable_line_id=row["cable_line_id"],
                endpoint_id=endpoint_id,
                assignment_role=row["assignment_role"],
                reservation_id=row.get("reservation_id"),
                created_at_utc=_datetime(row.get("created_at_utc")),
                updated_at_utc=_datetime(row.get("updated_at_utc")),
                row_version=row.get("row_version") or 1,
            )
        )
        endpoints_by_line[row["cable_line_id"]].append(endpoint_id)
    return endpoints_by_line


def _migrate_topology(
    bind,
    point_rows: list[dict],
    conduit_rows: list[dict],
    assignment_endpoints: dict[str, list[str]],
) -> None:
    points_by_line: dict[str, list[dict]] = defaultdict(list)
    for row in point_rows:
        points_by_line[row["cable_line_id"]].append(row)
    conduits_by_line: dict[str, list[dict]] = defaultdict(list)
    for row in conduit_rows:
        conduits_by_line[row["cable_line_id"]].append(row)

    line_rows = list(bind.execute(sa.select(schema.cable_line)).mappings())
    for line in line_rows:
        line_id = line["id"]
        project_id = line["project_id"]
        facts = _json(line.get("cable_facts_json"))
        route = {key: facts.get(key) for key in ROUTE_KEYS if key in facts}
        for key in ROUTE_KEYS:
            facts.pop(key, None)
        bind.execute(
            schema.cable_line.update()
            .where(schema.cable_line.c.id == line_id)
            .values(cable_facts_json=facts)
        )
        points = sorted(points_by_line.get(line_id, []), key=lambda item: item["ordinal"])
        line_conduits = conduits_by_line.get(line_id, [])
        if len(points) != 1:
            _review(
                bind,
                project_id=project_id,
                line_id=line_id,
                kind="LEGACY_LINE_TOPOLOGY",
                legacy_id=line_id,
                reason=(
                    "Legacy point order is absent"
                    if not points
                    else "Legacy multi-point ordinal may reflect scan order"
                ),
                payload={
                    "points": [
                        {
                            "id": point["id"],
                            "ordinal": point["ordinal"],
                            "point_kind": point.get("point_kind"),
                        }
                        for point in points
                    ],
                    "route_facts": route,
                    "conduit_assignments": [dict(item) for item in line_conduits],
                },
            )
            continue

        target_point = points[0]
        target_endpoint = _endpoint(
            bind,
            project_id=project_id,
            line_id=line_id,
            kind="TOPOLOGY_POINT",
            point_id=target_point["id"],
        )
        source_candidates = assignment_endpoints.get(line_id, [])
        if len(source_candidates) == 1:
            source_endpoint = source_candidates[0]
        else:
            source_point_id = _id()
            bind.execute(
                schema.cable_point.insert().values(
                    id=source_point_id,
                    project_id=project_id,
                    cable_line_id=line_id,
                    field_device_id=None,
                    point_kind="INTERNAL_SOURCE",
                    ordinal=max(int(target_point["ordinal"]) + 1, 1),
                    logical_identity=f"internal:{line_id}:source",
                    origin_kind="MIGRATION",
                    migration_state="CONFIRMED",
                    location_json=None,
                    dwg_observation_id=None,
                )
            )
            source_endpoint = _endpoint(
                bind,
                project_id=project_id,
                line_id=line_id,
                kind="TOPOLOGY_POINT",
                point_id=source_point_id,
            )
        mount_way = route.get("MOUNT_WAY")
        if mount_way not in schema.MOUNT_WAYS:
            if mount_way not in (None, ""):
                _review(
                    bind,
                    project_id=project_id,
                    line_id=line_id,
                    kind="LEGACY_ROUTE_VALUE",
                    legacy_id=line_id,
                    reason="Legacy mount way is not a canonical segment value",
                    payload=route,
                )
            mount_way = None
        segment_id = _id()
        bind.execute(
            schema.cable_segment.insert().values(
                id=segment_id,
                project_id=project_id,
                cable_line_id=line_id,
                source_endpoint_id=source_endpoint,
                target_endpoint_id=target_endpoint,
                mount_way=mount_way,
                gofra_type=route.get("GOFRA_TYPE") or None,
                gofra_color=route.get("GOFRA_COLOR") or None,
                origin_kind="MIGRATION",
                migration_state="CONFIRMED",
            )
        )
        if len(line_conduits) == 1:
            old = line_conduits[0]
            bind.execute(
                schema.conduit_segment_assignment.insert().values(
                    id=old["id"],
                    project_id=project_id,
                    conduit_id=old["conduit_id"],
                    cable_segment_id=segment_id,
                    created_at_utc=_datetime(old.get("created_at_utc")),
                    updated_at_utc=_datetime(old.get("updated_at_utc")),
                    row_version=old.get("row_version") or 1,
                )
            )
        elif len(line_conduits) > 1 or route.get("GOFRA_ID"):
            _review(
                bind,
                project_id=project_id,
                line_id=line_id,
                kind="LEGACY_LINE_CONDUIT",
                legacy_id=line_id,
                reason=(
                    "Multiple legacy line conduit assignments cannot select one segment owner"
                    if len(line_conduits) > 1
                    else "Legacy GOFRA_ID has no matching persisted conduit assignment"
                ),
                payload={"route_facts": route, "assignments": [dict(x) for x in line_conduits]},
            )


def upgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)
    if "cable_point" not in tables or "cable_line" not in tables:
        schema.metadata.create_all(bind, checkfirst=True)
        tables = _tables(bind)
    point_rows = []
    device_rows: dict[str, dict] = {}
    if "cable_point" in tables:
        point_rows = [
            dict(row) for row in bind.execute(sa.text("SELECT * FROM cable_point")).mappings()
        ]
    if "field_device" in tables:
        device_rows = {
            row["id"]: dict(row)
            for row in bind.execute(sa.text("SELECT * FROM field_device")).mappings()
        }
    legacy_point_shape = _add_cable_point_columns(bind)
    membership_rows = point_rows
    if legacy_point_shape:
        point_rows, membership_rows = _normalize_legacy_points(bind, point_rows, device_rows)

    legacy_line_assignments: list[dict] = []
    if "output_resource_id" in _columns(bind, "cable_line_assignment"):
        legacy_line_assignments = [
            dict(row)
            for row in bind.execute(sa.text("SELECT * FROM cable_line_assignment")).mappings()
        ]
        op.rename_table("cable_line_assignment", "legacy_cable_line_assignment_000000000007")

    legacy_conduits: list[dict] = []
    if "conduit_cable_assignment" in tables:
        legacy_conduits = [
            dict(row)
            for row in bind.execute(sa.text("SELECT * FROM conduit_cable_assignment")).mappings()
        ]

    _upgrade_led_profile(bind)
    schema.create_tables(bind, schema.TOPOLOGY_TABLE_NAMES - _tables(bind))
    if "legacy_cable_line_assignment_000000000007" in _tables(bind):
        schema.cable_line_assignment.create(bind, checkfirst=False)

    if legacy_point_shape:
        _materialize_memberships(bind, membership_rows)
    _materialize_ports_and_keys(bind, device_rows)
    assignment_endpoints = _migrate_line_assignments(bind, legacy_line_assignments)
    _migrate_topology(bind, point_rows, legacy_conduits, assignment_endpoints)

    if "conduit_cable_assignment" in _tables(bind):
        op.drop_table("conduit_cable_assignment")
    if "legacy_cable_line_assignment_000000000007" in _tables(bind):
        op.drop_table("legacy_cable_line_assignment_000000000007")


def _scalar(bind, sql: str):
    return bind.execute(sa.text(sql)).scalar_one()


def _assert_downgrade_safe(bind) -> None:
    blockers = {
        "project topology points": _scalar(
            bind, "SELECT count(*) FROM cable_point WHERE origin_kind='PROJECT'"
        ),
        "project cable segments": _scalar(
            bind, "SELECT count(*) FROM cable_segment WHERE origin_kind='PROJECT'"
        ),
        "migration reviews": _scalar(bind, "SELECT count(*) FROM topology_migration_review"),
        "key input assignments": _scalar(bind, "SELECT count(*) FROM control_key_input_assignment"),
        "field product selections": _scalar(
            bind, "SELECT count(*) FROM field_device_product_selection"
        ),
        "user reserves": _scalar(bind, "SELECT count(*) FROM user_reserve"),
        "RGB LED facts": _scalar(
            bind, "SELECT count(*) FROM led_line_profile WHERE led_kind='RGB'"
        ),
        "LED facts without voltage": _scalar(
            bind, "SELECT count(*) FROM led_line_profile WHERE voltage_decimal IS NULL"
        ),
        "field-port cable assignments": _scalar(
            bind,
            "SELECT count(*) FROM cable_line_assignment a "
            "JOIN cable_topology_endpoint e ON e.id=a.endpoint_id "
            "WHERE e.endpoint_kind <> 'INSTANCE_RESOURCE'",
        ),
    }
    nonzero = [f"{name}={count}" for name, count in blockers.items() if count]
    duplicate_line_conduits = _scalar(
        bind,
        "SELECT count(*) FROM (SELECT s.cable_line_id FROM conduit_segment_assignment a "
        "JOIN cable_segment s ON s.id=a.cable_segment_id "
        "GROUP BY s.cable_line_id HAVING count(DISTINCT a.conduit_id) > 1)",
    )
    if duplicate_line_conduits:
        nonzero.append(f"multi-conduit lines={duplicate_line_conduits}")
    if nonzero:
        raise RuntimeError(
            "Revision 000000000007 downgrade would lose successor facts: " + ", ".join(nonzero)
        )


def _restore_legacy_line_facts(bind) -> list[dict]:
    legacy_conduit_rows: list[dict] = []
    segments = list(bind.execute(sa.select(schema.cable_segment)).mappings())
    for segment in segments:
        line_id = segment["cable_line_id"]
        facts = _json(
            bind.execute(
                sa.select(schema.cable_line.c.cable_facts_json).where(
                    schema.cable_line.c.id == line_id
                )
            ).scalar_one()
        )
        if segment.get("mount_way"):
            facts["MOUNT_WAY"] = segment["mount_way"]
        if segment.get("gofra_type"):
            facts["GOFRA_TYPE"] = segment["gofra_type"]
        if segment.get("gofra_color"):
            facts["GOFRA_COLOR"] = segment["gofra_color"]
        assigned = (
            bind.execute(
                sa.select(schema.conduit_segment_assignment, schema.conduit.c.designation)
                .join(
                    schema.conduit,
                    schema.conduit.c.id == schema.conduit_segment_assignment.c.conduit_id,
                )
                .where(schema.conduit_segment_assignment.c.cable_segment_id == segment["id"])
            )
            .mappings()
            .one_or_none()
        )
        if assigned is not None:
            facts["GOFRA_ID"] = assigned["designation"]
            legacy_conduit_rows.append(
                {
                    "id": assigned["id"],
                    "project_id": assigned["project_id"],
                    "conduit_id": assigned["conduit_id"],
                    "cable_line_id": line_id,
                    "created_at_utc": assigned.get("created_at_utc"),
                    "updated_at_utc": assigned.get("updated_at_utc"),
                    "row_version": assigned.get("row_version") or 1,
                }
            )
        bind.execute(
            schema.cable_line.update()
            .where(schema.cable_line.c.id == line_id)
            .values(cable_facts_json=facts)
        )
    return legacy_conduit_rows


def _downgrade_line_assignments(bind) -> list[dict]:
    rows = list(
        bind.execute(
            sa.select(
                schema.cable_line_assignment,
                schema.cable_topology_endpoint.c.instance_resource_id,
            ).join(
                schema.cable_topology_endpoint,
                schema.cable_topology_endpoint.c.id == schema.cable_line_assignment.c.endpoint_id,
            )
        ).mappings()
    )
    return [dict(row) for row in rows]


def downgrade() -> None:
    bind = op.get_bind()
    _assert_downgrade_safe(bind)
    legacy_conduits = _restore_legacy_line_facts(bind)
    legacy_assignments = _downgrade_line_assignments(bind)

    memberships = {
        row["cable_point_id"]: row["field_device_id"]
        for row in bind.execute(sa.select(schema.cable_point_field_device)).mappings()
    }
    source_point_ids = list(
        bind.execute(
            sa.select(schema.cable_point.c.id).where(
                schema.cable_point.c.point_kind == "INTERNAL_SOURCE",
                schema.cable_point.c.origin_kind == "MIGRATION",
            )
        ).scalars()
    )

    schema.drop_tables(bind, schema.TOPOLOGY_TABLE_NAMES)

    op.drop_table("cable_line_assignment")
    op.create_table(
        "cable_line_assignment",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("cable_line_id", sa.String(36), nullable=False),
        sa.Column("output_resource_id", sa.String(36), nullable=False),
        sa.Column("assignment_role", sa.String(64), nullable=False),
        sa.Column("reservation_id", sa.String(36)),
        sa.Column("created_at_utc", sa.DateTime(timezone=True)),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["cable_line_id", "project_id"], ["cable_line.id", "cable_line.project_id"]
        ),
        sa.ForeignKeyConstraint(
            ["output_resource_id", "project_id"],
            ["instance_resource.id", "instance_resource.project_id"],
        ),
        sa.ForeignKeyConstraint(["reservation_id"], ["resource_reservation.id"]),
        sa.UniqueConstraint("cable_line_id", "assignment_role"),
        sa.UniqueConstraint("output_resource_id", "assignment_role"),
        sa.CheckConstraint("length(id)=36 AND lower(id)=id", name="id_canonical_uuid"),
    )
    for row in legacy_assignments:
        bind.execute(
            sa.text(
                "INSERT INTO cable_line_assignment "
                "(id,project_id,cable_line_id,output_resource_id,assignment_role,reservation_id,"
                "created_at_utc,updated_at_utc,row_version) "
                "VALUES (:id,:project_id,:cable_line_id,:output_resource_id,:assignment_role,"
                ":reservation_id,:created_at_utc,:updated_at_utc,:row_version)"
            ),
            {
                "id": row["id"],
                "project_id": row["project_id"],
                "cable_line_id": row["cable_line_id"],
                "output_resource_id": row["instance_resource_id"],
                "assignment_role": row["assignment_role"],
                "reservation_id": row.get("reservation_id"),
                "created_at_utc": row.get("created_at_utc"),
                "updated_at_utc": row.get("updated_at_utc") or datetime.now(UTC),
                "row_version": row.get("row_version") or 1,
            },
        )

    op.create_table(
        "conduit_cable_assignment",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("conduit_id", sa.String(36), nullable=False),
        sa.Column("cable_line_id", sa.String(36), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True)),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["conduit_id", "project_id"],
            ["conduit.id", "conduit.project_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["cable_line_id", "project_id"], ["cable_line.id", "cable_line.project_id"]
        ),
        sa.UniqueConstraint("conduit_id", "cable_line_id"),
        sa.CheckConstraint("length(id)=36 AND lower(id)=id", name="id_canonical_uuid"),
    )
    for row in legacy_conduits:
        bind.execute(
            sa.text(
                "INSERT INTO conduit_cable_assignment "
                "(id,project_id,conduit_id,cable_line_id,created_at_utc,"
                "updated_at_utc,row_version) "
                "VALUES (:id,:project_id,:conduit_id,:cable_line_id,:created_at_utc,"
                ":updated_at_utc,:row_version)"
            ),
            {**row, "updated_at_utc": row.get("updated_at_utc") or datetime.now(UTC)},
        )

    if source_point_ids:
        bind.execute(
            schema.cable_point.delete().where(schema.cable_point.c.id.in_(source_point_ids))
        )
    op.execute("DROP INDEX IF EXISTS uq_cable_point_project_identity")
    op.execute("DROP INDEX IF EXISTS uq_cable_point_id_project_line")
    op.execute("DROP INDEX IF EXISTS uq_cable_point_id_project")
    checks = {item.get("name") for item in sa.inspect(bind).get_check_constraints("cable_point")}
    uniques = {item.get("name") for item in sa.inspect(bind).get_unique_constraints("cable_point")}
    with op.batch_alter_table("cable_point") as batch:
        for name in (
            "ck_cable_point_point_kind",
            "ck_cable_point_origin_kind",
            "ck_cable_point_migration_state",
            "ck_cable_point_legacy_device_owner_empty",
        ):
            if name in checks:
                batch.drop_constraint(op.f(name), type_="check")
        if "uq_cable_point_id_project_line" in uniques:
            batch.drop_constraint(op.f("uq_cable_point_id_project_line"), type_="unique")
        if "uq_cable_point_id_project" in uniques:
            batch.drop_constraint(op.f("uq_cable_point_id_project"), type_="unique")
        batch.drop_column("migration_state")
        batch.drop_column("origin_kind")
        batch.drop_column("logical_identity")
    for point_id, device_id in memberships.items():
        bind.execute(
            sa.text(
                "UPDATE cable_point SET field_device_id=:device_id, point_kind='DWG_INSERTION' "
                "WHERE id=:point_id"
            ),
            {"device_id": device_id, "point_id": point_id},
        )

    checks = {
        item.get("name") for item in sa.inspect(bind).get_check_constraints("led_line_profile")
    }
    with op.batch_alter_table("led_line_profile") as batch:
        for name in (
            "ck_led_line_profile_led_kind",
            "ck_led_line_profile_led_type_origin",
            "ck_led_line_profile_sync_state",
            "ck_led_line_profile_channels_match_kind",
        ):
            if name in checks:
                batch.drop_constraint(op.f(name), type_="check")
        batch.alter_column("voltage_decimal", existing_type=sa.Text(), nullable=False)
        batch.create_check_constraint("led_kind", "led_kind IN ('MONO','CCT','RGBW')")
        batch.create_check_constraint("channels_positive", "channels >= 1")
        batch.drop_column("sync_state")
        batch.drop_column("sync_baseline_json")
        batch.drop_column("led_type_origin")
