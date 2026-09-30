"""Allow the canonical timber route value in persisted cable segments.

Revision ID: 000000000012
Revises: 000000000011
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "000000000012"
down_revision = "000000000011"
branch_labels = None
depends_on = None

_PREVIOUS_MOUNT_WAYS = ("По полу", "По потолку", "В стене", "В кабель-канале")
_CURRENT_MOUNT_WAYS = (*_PREVIOUS_MOUNT_WAYS[:-1], "В брусе", _PREVIOUS_MOUNT_WAYS[-1])
_CONDUIT_PARENT_KEY = ("id", "project_id")


def _constraint(values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"mount_way IN ({quoted})"


def _has_conduit_parent_key() -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for constraint in inspector.get_unique_constraints("conduit"):
        if tuple(constraint.get("column_names") or ()) == _CONDUIT_PARENT_KEY:
            return True
    for index in inspector.get_indexes("conduit"):
        if index.get("unique") and tuple(index.get("column_names") or ()) == _CONDUIT_PARENT_KEY:
            return True
    return False


def _ensure_conduit_parent_key() -> None:
    if not _has_conduit_parent_key():
        op.create_index(
            "uq_conduit_id_project_id",
            "conduit",
            list(_CONDUIT_PARENT_KEY),
            unique=True,
        )


def _replace_mount_way_check(values: tuple[str, ...]) -> None:
    _ensure_conduit_parent_key()
    with op.batch_alter_table("cable_segment", recreate="always") as batch:
        batch.drop_constraint(op.f("ck_cable_segment_mount_way"), type_="check")
        batch.create_check_constraint("mount_way", _constraint(values))


def upgrade() -> None:
    _replace_mount_way_check(_CURRENT_MOUNT_WAYS)


def downgrade() -> None:
    _replace_mount_way_check(_PREVIOUS_MOUNT_WAYS)
