"""Add typed physical-key inputs and RS-485 field-device endpoints.

Revision ID: 000000000008
Revises: 000000000007
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from nl_project_2.persistence import schema

revision = "000000000008"
down_revision = "000000000007"
branch_labels = None
depends_on = None


def _columns(bind, table: str) -> set[str]:
    return {item["name"] for item in sa.inspect(bind).get_columns(table)}


def _rebuild_key_inputs(bind) -> None:
    if "input_kind" in _columns(bind, "control_key_input_assignment"):
        return
    op.rename_table(
        "control_key_input_assignment",
        "legacy_control_key_input_assignment_000000000008",
    )
    schema.control_key_input_assignment.create(bind, checkfirst=False)
    bind.execute(
        sa.text(
            "INSERT INTO control_key_input_assignment "
            "(id,project_id,field_control_key_id,input_kind,input_resource_id,field_port_id,"
            "reservation_id,created_at_utc,updated_at_utc,row_version) "
            "SELECT id,project_id,field_control_key_id,'INSTANCE_RESOURCE',input_resource_id,"
            "NULL,reservation_id,created_at_utc,updated_at_utc,row_version "
            "FROM legacy_control_key_input_assignment_000000000008"
        )
    )
    op.drop_table("legacy_control_key_input_assignment_000000000008")


def _rebuild_bus_endpoints(bind) -> None:
    if "endpoint_kind" in _columns(bind, "bus_endpoint"):
        return
    op.rename_table("bus_endpoint", "legacy_bus_endpoint_000000000008")
    op.execute("DROP INDEX IF EXISTS uq_bus_endpoint_address_known")
    schema.bus_endpoint.create(bind, checkfirst=False)
    bind.execute(
        sa.text(
            "INSERT INTO bus_endpoint "
            "(id,project_id,bus_id,endpoint_kind,resource_id,field_device_id,endpoint_role,"
            "address,endpoint_order,bus_branch_id,created_at_utc,updated_at_utc,row_version) "
            "SELECT id,project_id,bus_id,'INSTANCE_RESOURCE',resource_id,NULL,endpoint_role,"
            "address,endpoint_order,bus_branch_id,created_at_utc,updated_at_utc,row_version "
            "FROM legacy_bus_endpoint_000000000008"
        )
    )
    op.drop_table("legacy_bus_endpoint_000000000008")


def upgrade() -> None:
    bind = op.get_bind()
    _rebuild_key_inputs(bind)
    _rebuild_bus_endpoints(bind)


def _assert_downgrade_safe(bind) -> None:
    field_key_inputs = bind.execute(
        sa.text(
            "SELECT count(*) FROM control_key_input_assignment "
            "WHERE input_kind <> 'INSTANCE_RESOURCE'"
        )
    ).scalar_one()
    field_bus_endpoints = bind.execute(
        sa.text("SELECT count(*) FROM bus_endpoint WHERE endpoint_kind <> 'INSTANCE_RESOURCE'")
    ).scalar_one()
    if field_key_inputs or field_bus_endpoints:
        raise RuntimeError(
            "Revision 000000000008 downgrade would lose typed field facts: "
            f"field key inputs={field_key_inputs}, field bus endpoints={field_bus_endpoints}"
        )


def downgrade() -> None:
    bind = op.get_bind()
    _assert_downgrade_safe(bind)

    op.rename_table(
        "control_key_input_assignment",
        "successor_control_key_input_assignment_000000000008",
    )
    op.create_table(
        "control_key_input_assignment",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("field_control_key_id", sa.String(36), nullable=False, unique=True),
        sa.Column("input_resource_id", sa.String(36), nullable=False, unique=True),
        sa.Column("reservation_id", sa.String(36), nullable=False, unique=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True)),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["field_control_key_id", "project_id"],
            ["field_control_key.id", "field_control_key.project_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["input_resource_id", "project_id"],
            ["instance_resource.id", "instance_resource.project_id"],
        ),
        sa.ForeignKeyConstraint(["reservation_id"], ["resource_reservation.id"]),
        sa.UniqueConstraint("id", "project_id"),
        sa.CheckConstraint("length(id)=36 AND lower(id)=id", name="id_canonical_uuid"),
    )
    bind.execute(
        sa.text(
            "INSERT INTO control_key_input_assignment "
            "(id,project_id,field_control_key_id,input_resource_id,reservation_id,"
            "created_at_utc,updated_at_utc,row_version) "
            "SELECT id,project_id,field_control_key_id,input_resource_id,reservation_id,"
            "created_at_utc,updated_at_utc,row_version "
            "FROM successor_control_key_input_assignment_000000000008"
        )
    )
    op.drop_table("successor_control_key_input_assignment_000000000008")

    op.rename_table("bus_endpoint", "successor_bus_endpoint_000000000008")
    op.execute("DROP INDEX IF EXISTS uq_bus_endpoint_address_known")
    op.create_table(
        "bus_endpoint",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("bus_id", sa.String(36), nullable=False),
        sa.Column("resource_id", sa.String(36), nullable=False),
        sa.Column("endpoint_role", sa.String(64), nullable=False),
        sa.Column("address", sa.String(120)),
        sa.Column("endpoint_order", sa.Integer()),
        sa.Column("bus_branch_id", sa.String(36)),
        sa.Column("created_at_utc", sa.DateTime(timezone=True)),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["bus_id", "project_id"], ["bus.id", "bus.project_id"]),
        sa.ForeignKeyConstraint(
            ["resource_id", "project_id"],
            ["instance_resource.id", "instance_resource.project_id"],
        ),
        sa.ForeignKeyConstraint(
            ["bus_branch_id", "project_id"], ["bus_branch.id", "bus_branch.project_id"]
        ),
        sa.UniqueConstraint("bus_id", "resource_id"),
        sa.CheckConstraint("length(id)=36 AND lower(id)=id", name="id_canonical_uuid"),
    )
    op.create_index(
        "uq_bus_endpoint_address_known",
        "bus_endpoint",
        ["bus_id", "address"],
        unique=True,
        sqlite_where=sa.text("address IS NOT NULL"),
    )
    bind.execute(
        sa.text(
            "INSERT INTO bus_endpoint "
            "(id,project_id,bus_id,resource_id,endpoint_role,address,endpoint_order,"
            "bus_branch_id,created_at_utc,updated_at_utc,row_version) "
            "SELECT id,project_id,bus_id,resource_id,endpoint_role,address,endpoint_order,"
            "bus_branch_id,created_at_utc,updated_at_utc,row_version "
            "FROM successor_bus_endpoint_000000000008"
        )
    )
    op.drop_table("successor_bus_endpoint_000000000008")
