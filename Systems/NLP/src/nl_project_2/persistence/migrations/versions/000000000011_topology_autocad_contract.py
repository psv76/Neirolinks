"""Repair 08 physical bus segments and canonical CAD identities.

Revision ID: 000000000011
Revises: 000000000010
"""

from __future__ import annotations

import json
import re

import sqlalchemy as sa
from alembic import op

from nl_project_2.persistence.ids import new_id

revision = "000000000011"
down_revision = "000000000010"
branch_labels = None
depends_on = None

_LEGACY_BLOCK_NAMES = {
    "LIGHT_IN": "LIGHT_IN_230V",
    "LIGHT_OUT": "LIGHT_OUT_230V",
    "SENSOR_M1W2": "WB_M1W2",
    "SENSOR_MAI2": "WB_MAI2",
}
_LEGACY_RS485 = re.compile(r"^(9[0-9]{2})\.([0-9]{2})$")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    bus_columns = {item["name"] for item in inspector.get_columns("bus")}
    if "cable_type" not in bus_columns:
        op.add_column("bus", sa.Column("cable_type", sa.Text(), nullable=True))

    indexes = {item["name"] for item in inspector.get_indexes("bus_endpoint")}
    if "uq_bus_endpoint_id_project_id" not in indexes:
        op.create_index(
            "uq_bus_endpoint_id_project_id",
            "bus_endpoint",
            ["id", "project_id"],
            unique=True,
        )

    field_port_sql = bind.exec_driver_sql(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='field_port'"
    ).scalar_one()
    if "RELAY_COMMON" not in field_port_sql:
        with op.batch_alter_table("field_port", recreate="always") as batch:
            batch.drop_constraint("ck_field_port_port_kind", type_="check")
            batch.create_check_constraint(
                "port_kind",
                "port_kind IN ('RELAY_COMMON', 'RELAY_OUTPUT', 'DIGITAL_INPUT', "
                "'ONEWIRE_CHANNEL', 'BUS_INTERFACE')",
            )

    from nl_project_2.persistence.schema import (
        bus_segment,
        bus_segment_conduit_assignment,
    )

    bus_segment.create(bind, checkfirst=True)
    bus_segment_conduit_assignment.create(bind, checkfirst=True)
    _normalize_legacy_identities(bind)
    _materialize_existing_bus_segments(bind)


def _normalize_legacy_identities(bind) -> None:
    rows = bind.exec_driver_sql(
        "SELECT id, block_kind, normalized_fields_json FROM field_device"
    ).mappings()
    for row in rows:
        block_kind = _LEGACY_BLOCK_NAMES.get(row["block_kind"], row["block_kind"])
        fields = json.loads(row["normalized_fields_json"] or "{}")
        changed = block_kind != row["block_kind"]
        old_block = fields.get("BLOCK_NAME")
        if old_block in _LEGACY_BLOCK_NAMES:
            fields["BLOCK_NAME"] = _LEGACY_BLOCK_NAMES[old_block]
            changed = True
        bus_point = fields.get("BUS_POINT_ID")
        match = _LEGACY_RS485.fullmatch(str(bus_point or ""))
        if match:
            fields["BUS_POINT_ID"] = f"{match.group(1)}.{int(match.group(2)):03d}"
            changed = True
        if changed:
            bind.exec_driver_sql(
                "UPDATE field_device SET block_kind=?, normalized_fields_json=? WHERE id=?",
                (block_kind, json.dumps(fields, ensure_ascii=False), row["id"]),
            )

    endpoints = list(
        bind.exec_driver_sql(
            "SELECT e.id, e.bus_id, e.address, e.endpoint_order, b.bus_kind, b.designation "
            "FROM bus_endpoint e JOIN bus b ON b.id=e.bus_id "
            "ORDER BY e.bus_id, e.endpoint_order, e.address"
        ).mappings()
    )
    proposed: dict[tuple[str, str], str] = {}
    for row in endpoints:
        address = str(row["address"] or "")
        match = _LEGACY_RS485.fullmatch(address) if row["bus_kind"] == "RS485" else None
        normalized = (
            f"{match.group(1)}.{int(match.group(2)):03d}" if match else address
        )
        key = (row["bus_id"], normalized)
        previous = proposed.get(key)
        if previous is not None and previous != row["id"]:
            raise RuntimeError(
                f"AMBIGUOUS_RS485_ADDRESS_MIGRATION:{row['bus_id']}:{normalized}"
            )
        proposed[key] = row["id"]
        if normalized != address:
            bind.exec_driver_sql(
                "UPDATE bus_endpoint SET address=? WHERE id=?", (normalized, row["id"])
            )


def _materialize_existing_bus_segments(bind) -> None:
    buses = list(bind.exec_driver_sql("SELECT id, project_id, bus_kind FROM bus").mappings())
    for bus_row in buses:
        endpoints = list(
            bind.exec_driver_sql(
                "SELECT id, resource_id, endpoint_order, address FROM bus_endpoint "
                "WHERE bus_id=? ORDER BY endpoint_order, address, id",
                (bus_row["id"],),
            ).mappings()
        )
        if bus_row["bus_kind"] == "RS485":
            edges = []
            previous = None
            for endpoint in endpoints:
                edges.append((previous, endpoint["id"]))
                previous = endpoint["id"]
        else:
            endpoint_by_resource = {row["resource_id"]: row["id"] for row in endpoints}
            branch_rows = list(
                bind.exec_driver_sql(
                    "SELECT bp.bus_branch_id, bp.resource_id, bp.point_order "
                    "FROM bus_branch_point bp JOIN bus_branch br ON br.id=bp.bus_branch_id "
                    "WHERE br.bus_id=? ORDER BY br.branch_order, bp.point_order",
                    (bus_row["id"],),
                ).mappings()
            )
            branches: dict[str, list[str]] = {}
            for row in branch_rows:
                branches.setdefault(row["bus_branch_id"], []).append(row["resource_id"])
            candidate_parents: dict[str, set[str | None]] = {}
            for branch_index, resources in enumerate(branches.values()):
                previous = None
                branch_resources = resources
                if branch_index > 0 and resources:
                    previous = endpoint_by_resource[resources[0]]
                    branch_resources = resources[1:]
                for resource_id in branch_resources:
                    target = endpoint_by_resource[resource_id]
                    candidate_parents.setdefault(target, set()).add(previous)
                    previous = target
            if not branches:
                previous = None
                for endpoint in endpoints:
                    candidate_parents.setdefault(endpoint["id"], set()).add(previous)
                    previous = endpoint["id"]
            ambiguous = {
                target: parents for target, parents in candidate_parents.items() if len(parents) > 1
            }
            if ambiguous:
                raise RuntimeError(
                    f"AMBIGUOUS_LEGACY_BUS_TOPOLOGY:{bus_row['id']}:{ambiguous}"
                )
            edges = [(next(iter(parents)), target) for target, parents in candidate_parents.items()]
        for source, target in edges:
            bind.exec_driver_sql(
                "INSERT INTO bus_segment "
                "(id, project_id, bus_id, source_endpoint_id, target_endpoint_id, "
                "connection_kind, origin_kind, migration_state) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id(),
                    bus_row["project_id"],
                    bus_row["id"],
                    source,
                    target,
                    "CABLE",
                    "MIGRATION",
                    "CONFIRMED",
                ),
            )


def downgrade() -> None:
    op.drop_table("bus_segment_conduit_assignment")
    op.drop_table("bus_segment")
    op.drop_index("uq_bus_endpoint_id_project_id", table_name="bus_endpoint")
    op.drop_column("bus", "cable_type")
