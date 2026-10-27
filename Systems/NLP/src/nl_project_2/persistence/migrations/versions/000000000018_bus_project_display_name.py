"""Optional Project-authored bus title, independent of DWG device LOAD_NAME.

Revision ID: 000000000018
Revises: 000000000017
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "000000000018"
down_revision = "000000000017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Foundation bootstrap uses the current SQLAlchemy metadata for some
    # tables. Fresh revision-17 test fixtures may already contain this additive
    # column; real historic revision-17 databases do not.
    if "display_name" not in {col["name"] for col in inspect(op.get_bind()).get_columns("bus")}:
        op.add_column("bus", sa.Column("display_name", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    count = bind.exec_driver_sql(
        'SELECT COUNT(*) FROM "bus" WHERE "display_name" IS NOT NULL '
        "AND TRIM(display_name) != ''"
    ).scalar_one()
    if count:
        raise RuntimeError("BUS_DISPLAY_NAME_DOWNGRADE_REQUIRES_EXPLICIT_REVIEW")
    op.drop_column("bus", "display_name")
