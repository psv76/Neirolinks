"""Persistence foundation for the single NL Project 2.0 SQLite database."""

from nl_project_2.persistence.database import (
    DatabaseHandle,
    DatabaseManager,
    IncompatibleSchemaError,
    NewerSchemaError,
    SchemaUpgradeRequiredError,
    UninitializedSchemaError,
)
from nl_project_2.persistence.ids import new_id
from nl_project_2.persistence.uow import UnitOfWork

__all__ = [
    "DatabaseHandle",
    "DatabaseManager",
    "IncompatibleSchemaError",
    "NewerSchemaError",
    "SchemaUpgradeRequiredError",
    "UnitOfWork",
    "UninitializedSchemaError",
    "new_id",
]
