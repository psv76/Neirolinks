"""Persist canonical conduit number and color for DWG reconciliation.

Revision ID: 000000000006
Revises: 000000000005
Affected entity: conduit.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "000000000006"
down_revision = "000000000005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {item["name"] for item in sa.inspect(bind).get_columns("conduit")}
    if "conduit_number" not in columns:
        op.add_column("conduit", sa.Column("conduit_number", sa.Integer(), nullable=True))
    if "color" not in columns:
        op.add_column("conduit", sa.Column("color", sa.Text(), nullable=True))
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_conduit_project_number "
        "ON conduit (project_id, conduit_number)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_conduit_project_number")
    bind = op.get_bind()
    columns = {item["name"] for item in sa.inspect(bind).get_columns("conduit")}
    if "color" in columns:
        op.drop_column("conduit", "color")
    if "conduit_number" in columns:
        op.drop_column("conduit", "conduit_number")
