"""Complete the approved MVP storage schema.

Revision ID: 000000000002
Revises: 000000000001
"""

from alembic import op

from nl_project_2.persistence.schema import FEATURE_TABLE_NAMES, create_tables, drop_tables

revision = "000000000002"
down_revision = "000000000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    create_tables(op.get_bind(), FEATURE_TABLE_NAMES)


def downgrade() -> None:
    drop_tables(op.get_bind(), FEATURE_TABLE_NAMES)
