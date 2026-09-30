"""Allow timber as a persisted cable-segment mount way.

Revision ID: 000000000012
Revises: 000000000011

The accepted product rule adds MOUNT_WAY="В брусе".  Existing topology,
identities and route data are not rewritten.  Only the cable_segment mount-way
CHECK is widened.  Downgrade refuses while timber segments exist because the
previous schema cannot represent them losslessly.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "000000000012"
down_revision = "000000000011"
branch_labels = None
depends_on = None

_OLD_MOUNT_WAYS = ("По полу", "По потолку", "В стене", "В кабель-канале")
_NEW_MOUNT_WAYS = ("По полу", "По потолку", "В стене", "В брусе", "В кабель-канале")


def _check_sql(values: tuple[str, ...]) -> str:
    quoted = ",".join("'" + value.replace("'", "''") + "'" for value in values)
    return f"mount_way IS NULL OR mount_way IN ({quoted})"


def _replace_mount_way_check(table_name: str, values: tuple[str, ...]) -> None:
    bind = op.get_bind()
    constraint_name = f"ck_{table_name}_mount_way"
    checks = {
        item.get("name")
        for item in sa.inspect(bind).get_check_constraints(table_name)
    }
    with op.batch_alter_table(table_name, recreate="always") as batch:
        if constraint_name in checks:
            batch.drop_constraint(constraint_name, type_="check")
        batch.create_check_constraint("mount_way", _check_sql(values))


def _drop_mount_way_check(table_name: str) -> None:
    bind = op.get_bind()
    constraint_name = f"ck_{table_name}_mount_way"
    checks = {
        item.get("name")
        for item in sa.inspect(bind).get_check_constraints(table_name)
    }
    if constraint_name not in checks:
        return
    with op.batch_alter_table(table_name, recreate="always") as batch:
        batch.drop_constraint(constraint_name, type_="check")


def upgrade() -> None:
    _replace_mount_way_check("cable_segment", _NEW_MOUNT_WAYS)
    _replace_mount_way_check("bus_segment", _NEW_MOUNT_WAYS)


def downgrade() -> None:
    bind = op.get_bind()
    cable_timber_count = bind.exec_driver_sql(
        "SELECT COUNT(*) FROM cable_segment WHERE mount_way = ?",
        ("В брусе",),
    ).scalar_one()
    bus_timber_count = bind.exec_driver_sql(
        "SELECT COUNT(*) FROM bus_segment WHERE mount_way = ?",
        ("В брусе",),
    ).scalar_one()
    if cable_timber_count or bus_timber_count:
        raise RuntimeError(
            "Cannot downgrade while cable or bus segments use MOUNT_WAY=В брусе"
        )
    _replace_mount_way_check("cable_segment", _OLD_MOUNT_WAYS)
    _drop_mount_way_check("bus_segment")
