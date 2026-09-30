"""Add explicit Project-owned DALI logical groups and membership.

Revision ID: 000000000005
Revises: 000000000004
Affected entities: dali_group, dali_group_member.
"""

from __future__ import annotations

from alembic import op

from nl_project_2.persistence.schema import (
    DALI_GROUP_TABLE_NAMES,
    create_tables,
    drop_tables,
)

revision = "000000000005"
down_revision = "000000000004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    create_tables(op.get_bind(), DALI_GROUP_TABLE_NAMES)


def downgrade() -> None:
    drop_tables(op.get_bind(), DALI_GROUP_TABLE_NAMES)
