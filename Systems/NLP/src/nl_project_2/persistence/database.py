"""Safe lifecycle for the single SQLite project database."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine, create_engine, event

from nl_project_2.persistence.migration import (
    HEAD_REVISION,
    KNOWN_REVISIONS,
    current_revision_read_only,
    initialize_database,
)


class DatabaseOpenError(RuntimeError):
    """Base error for a database that is unsafe to open."""


class UninitializedSchemaError(DatabaseOpenError):
    """The file has no managed schema version."""


class SchemaUpgradeRequiredError(DatabaseOpenError):
    """The schema is known but older than the application contract."""


class NewerSchemaError(DatabaseOpenError):
    """The schema was produced by a newer application."""


class IncompatibleSchemaError(DatabaseOpenError):
    """The schema version is unknown to this application."""


def _engine(path: Path) -> Engine:
    engine = create_engine(f"sqlite:///{path.resolve().as_posix()}", future=True)

    @event.listens_for(engine, "connect")
    def configure_sqlite(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    return engine


@dataclass
class DatabaseHandle:
    path: Path
    engine: Engine
    revision: str
    _closed: bool = False

    @property
    def is_closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        if not self._closed:
            self.engine.dispose()
            self._closed = True

    def __enter__(self) -> DatabaseHandle:
        if self._closed:
            raise RuntimeError("A closed database handle cannot be reused")
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.close()


class DatabaseManager:
    """Initializes new databases and opens only the exact supported revision."""

    def initialize_new(self, path: str | Path) -> DatabaseHandle:
        resolved = Path(path).resolve()
        revision = initialize_database(resolved)
        return DatabaseHandle(resolved, _engine(resolved), revision)

    def open_existing(self, path: str | Path) -> DatabaseHandle:
        resolved = Path(path).resolve()
        revision = current_revision_read_only(resolved)
        if revision is None:
            raise UninitializedSchemaError(f"No managed schema at {resolved}")
        if revision == HEAD_REVISION:
            return DatabaseHandle(resolved, _engine(resolved), revision)
        if revision in KNOWN_REVISIONS:
            raise SchemaUpgradeRequiredError(
                f"Schema {revision} requires explicit upgrade to {HEAD_REVISION}"
            )
        if revision.isdecimal() and int(revision) > int(HEAD_REVISION):
            raise NewerSchemaError(f"Schema {revision} is newer than supported {HEAD_REVISION}")
        raise IncompatibleSchemaError(f"Unknown schema revision: {revision}")
