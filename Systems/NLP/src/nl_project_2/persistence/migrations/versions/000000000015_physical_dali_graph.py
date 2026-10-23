"""Create canonical typed, non-addressable physical DALI topology.

Revision ID: 000000000015
Revises: 000000000014

This is a *schema-only* migration: previously accepted passive BOX/TRACK
field_device JSON and older bus_endpoint/bus_segment records are untouched.
Backfilling legacy BUS_POINT_ID or source references requires a separate
approved, evidence-based mapping; no interpretation is performed here.
"""

from __future__ import annotations

from alembic import op

revision = "000000000015"
down_revision = "000000000014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from nl_project_2.persistence.schema import bus_physical_link, bus_physical_node

    bind = op.get_bind()
    bus_physical_node.create(bind, checkfirst=False)
    bus_physical_link.create(bind, checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()
    # No silent loss of accepted physical graph facts on downgrade.
    for table in ("bus_physical_link", "bus_physical_node"):
        count = bind.exec_driver_sql(f'SELECT COUNT(*) FROM "{table}"').scalar_one()
        if count:
            raise RuntimeError(
                f"DALI_PHYSICAL_DOWNGRADE_REQUIRES_EXPLICIT_REVIEW:{table}:"
                "physical graph is not empty"
            )
    op.drop_table("bus_physical_link")
    op.drop_table("bus_physical_node")
