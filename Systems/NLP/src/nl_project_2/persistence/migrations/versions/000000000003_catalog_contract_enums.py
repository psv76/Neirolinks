"""Align catalog directions and supply-scope vocabulary with approved contracts.

Revision ID: 000000000003
Revises: 000000000002
"""

from __future__ import annotations

from alembic import op

revision = "000000000003"
down_revision = "000000000002"
branch_labels = None
depends_on = None

DIRECTIONS = ("IN", "OUT", "BIDIRECTIONAL", "PASSIVE", "INTERNAL")
SUPPLY_SCOPES = ("NEIROLINKS", "CUSTOMER", "ASSEMBLY_WORKSHOP", "BY_CONTRACT")


def _check(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


def _replace_check(table: str, name: str, column: str, values: tuple[str, ...]) -> None:
    with op.batch_alter_table(table) as batch:
        batch.drop_constraint(op.f(f"ck_{table}_{name}"), type_="check")
        batch.create_check_constraint(name, _check(column, values))


def upgrade() -> None:
    _replace_check("passport_resource_definition", "direction", "direction", DIRECTIONS)
    _replace_check("instance_resource", "direction", "direction", DIRECTIONS)
    for table in (
        "project_instance",
        "conduit",
        "led_line_profile",
        "specification_override",
    ):
        _replace_check(table, "supply_scope", "supply_scope", SUPPLY_SCOPES)


def downgrade() -> None:
    legacy_directions = ("IN", "OUT", "BIDIRECTIONAL", "PASSIVE")
    legacy_scopes = ("CUSTOMER", "CONTRACTOR", "OTHER")
    _replace_check("passport_resource_definition", "direction", "direction", legacy_directions)
    _replace_check("instance_resource", "direction", "direction", legacy_directions)
    for table in (
        "project_instance",
        "conduit",
        "led_line_profile",
        "specification_override",
    ):
        _replace_check(table, "supply_scope", "supply_scope", legacy_scopes)
