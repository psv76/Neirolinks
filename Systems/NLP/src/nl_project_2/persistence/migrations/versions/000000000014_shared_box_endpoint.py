"""Allow one physical cable point to serve endpoints of multiple CableLines.

Revision ID: 000000000014
Revises: 000000000013
"""

from __future__ import annotations

from alembic import op

revision = "000000000014"
down_revision = "000000000013"
branch_labels = None
depends_on = None

_FK = "fk_cable_topology_endpoint_cable_point_id_cable_point"


def _replace_point_fk(*, shared: bool) -> None:
    bind = op.get_bind()
    with op.get_context().autocommit_block():
        bind.exec_driver_sql("PRAGMA foreign_keys=OFF")
        try:
            with op.batch_alter_table("cable_topology_endpoint", recreate="always") as batch:
                batch.drop_constraint(_FK, type_="foreignkey")
                if shared:
                    batch.create_foreign_key(
                        _FK,
                        "cable_point",
                        ["cable_point_id", "project_id"],
                        ["id", "project_id"],
                        ondelete="CASCADE",
                    )
                else:
                    batch.create_foreign_key(
                        _FK,
                        "cable_point",
                        ["cable_point_id", "project_id", "cable_line_id"],
                        ["id", "project_id", "cable_line_id"],
                        ondelete="CASCADE",
                    )
        finally:
            bind.exec_driver_sql("PRAGMA foreign_keys=ON")
        violations = bind.exec_driver_sql("PRAGMA foreign_key_check").all()
        if violations:
            raise RuntimeError(f"Foreign-key violations after endpoint migration: {violations[:5]}")


def upgrade() -> None:
    _replace_point_fk(shared=True)


def downgrade() -> None:
    _replace_point_fk(shared=False)
