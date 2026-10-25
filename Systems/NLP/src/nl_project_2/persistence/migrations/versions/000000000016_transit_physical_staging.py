"""Stage physical CABLE_TRANSIT without touching electrical CableSegments.

Revision ID: 000000000016
Revises: 000000000015

Additive-only: no legacy migration, no conduit reassignment, no generated
physical path, and no recalculation of an accepted cable line. Real working
database migration requires a separate approved verified-backup gate.
"""

from __future__ import annotations

from alembic import op

revision = "000000000016"
down_revision = "000000000015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from nl_project_2.persistence.schema import cable_transit_route, cable_transit_span

    bind = op.get_bind()
    cable_transit_route.create(bind, checkfirst=False)
    cable_transit_span.create(bind, checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()
    # Refuse to discard accepted physical route evidence on downgrade.
    for table in ("cable_transit_span", "cable_transit_route"):
        count = bind.exec_driver_sql(f'SELECT COUNT(*) FROM "{table}"').scalar_one()
        if count:
            raise RuntimeError(f"TRANSIT_PHYSICAL_DOWNGRADE_REQUIRES_EXPLICIT_REVIEW:{table}")
    op.drop_table("cable_transit_span")
    op.drop_table("cable_transit_route")
