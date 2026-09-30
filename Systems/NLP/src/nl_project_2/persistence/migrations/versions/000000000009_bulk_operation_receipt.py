"""Persist controlled bulk-operation receipts.

Revision ID: 000000000009
Revises: 000000000008
Affected entity: bulk_operation_receipt.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from nl_project_2.persistence import schema

revision = "000000000009"
down_revision = "000000000008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # P0_001 can repair deliberately sparse legacy test shapes with metadata.create_all.
    # The linear head must therefore accept an already-created, schema-identical table.
    schema.bulk_operation_receipt.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    count = bind.execute(
        sa.text("SELECT count(*) FROM bulk_operation_receipt")
    ).scalar_one()
    if count:
        raise RuntimeError(
            "Revision 000000000009 downgrade would discard bulk operation receipts: "
            f"count={count}"
        )
    schema.bulk_operation_receipt.drop(bind, checkfirst=False)
