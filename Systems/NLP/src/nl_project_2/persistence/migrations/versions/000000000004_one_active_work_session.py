"""Enforce one active work period across the application database.

Revision ID: 000000000004
Revises: 000000000003
Affected entity: work_session.
"""

from __future__ import annotations

from alembic import op

revision = "000000000004"
down_revision = "000000000003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX uq_work_session_one_active "
        "ON work_session ((1)) WHERE stopped_at_utc IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX uq_work_session_one_active")
