"""Create catalog, project, instance, resource and work-session foundation.

Revision ID: 000000000001
Revises: None
"""

from alembic import op

from nl_project_2.persistence.schema import (
    FOUNDATION_TABLE_NAMES,
    create_tables,
    drop_tables,
)

revision = "000000000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    create_tables(op.get_bind(), FOUNDATION_TABLE_NAMES)


def downgrade() -> None:
    drop_tables(op.get_bind(), FOUNDATION_TABLE_NAMES)
