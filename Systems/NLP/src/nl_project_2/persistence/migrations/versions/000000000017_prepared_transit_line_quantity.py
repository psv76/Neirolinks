"""Immutable prepared transit line quantity receipts (not canonical length facts).

Revision ID: 000000000017
Revises: 000000000016

Additive only. Never remeasure a legacy edge, change manual overrides, adopt
Conduit, or populate authoritative cable_length_fact in this migration.
"""

from __future__ import annotations

from alembic import op

revision = "000000000017"
down_revision = "000000000016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from nl_project_2.persistence.schema import cable_transit_line_commit

    cable_transit_line_commit.create(op.get_bind(), checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()
    count = bind.exec_driver_sql('SELECT COUNT(*) FROM "cable_transit_line_commit"').scalar_one()
    if count:
        raise RuntimeError("TRANSIT_LINE_COMMIT_DOWNGRADE_REQUIRES_EXPLICIT_REVIEW")
    op.drop_table("cable_transit_line_commit")
