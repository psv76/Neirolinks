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


def _replace_mount_way_check(values: tuple[str, ...]) -> None:
    bind = op.get_bind()
    checks = {
        item.get("name")
        for item in sa.inspect(bind).get_check_constraints("cable_segment")
    }
    with op.batch_alter_table("cable_segment", recreate="always") as batch:
        if "ck_cable_segment_mount_way" in checks:
            batch.drop_constraint("ck_cable_segment_mount_way", type_="check")
        batch.create_check_constraint("mount_way", _check_sql(values))


def upgrade() -> None:
    _replace_mount_way_check(_NEW_MOUNT_WAYS)


def downgrade() -> None:
    bind = op.get_bind()
    timber_count = bind.exec_driver_sql(
        "SELECT COUNT(*) FROM cable_segment WHERE mount_way = ?",
        ("В брусе",),
    ).scalar_one()
    if timber_count:
        raise RuntimeError(
            "Cannot downgrade while cable_segment rows use MOUNT_WAY=В брусе"
        )
    _replace_mount_way_check(_OLD_MOUNT_WAYS)
