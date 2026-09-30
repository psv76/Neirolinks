"""Add exact catalog product selection to conduit.

Revision ID: 000000000010
Revises: 000000000009
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "000000000010"
down_revision = "000000000009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {item["name"] for item in sa.inspect(bind).get_columns("conduit")}
    if "product_definition_id" not in columns:
        op.execute(
            "ALTER TABLE conduit ADD COLUMN product_definition_id VARCHAR(36) "
            "REFERENCES product_definition(id)"
        )


def downgrade() -> None:
    bind = op.get_bind()
    columns = {item["name"] for item in sa.inspect(bind).get_columns("conduit")}
    if "product_definition_id" in columns:
        tables = set(sa.inspect(bind).get_table_names())
        dependent_rows = {
            table_name: [
                dict(row) for row in bind.execute(sa.text(f"SELECT * FROM {table_name}")).mappings()
            ]
            for table_name in ("conduit_cable_assignment", "conduit_segment_assignment")
            if table_name in tables
        }
        with op.batch_alter_table("conduit", recreate="always") as batch:
            batch.drop_column("product_definition_id")
        for table_name, rows in dependent_rows.items():
            if rows:
                columns = tuple(rows[0])
                sql = (
                    f"INSERT INTO {table_name} ({','.join(columns)}) "
                    f"VALUES ({','.join('?' for _ in columns)})"
                )
                for row in rows:
                    bind.exec_driver_sql(sql, tuple(row[column] for column in columns))
