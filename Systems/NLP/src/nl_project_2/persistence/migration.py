"""Explicit, versioned creation and upgrade of NL Project 3.0 databases."""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from alembic import command
from alembic.config import Config

from nl_project_2.runtime_resources import package_data_path

FOUNDATION_REVISION = "000000000001"
FULL_MVP_REVISION = "000000000002"
CATALOG_CONTRACT_REVISION = "000000000003"
WORK_SESSION_REVISION = "000000000004"
DALI_GROUP_REVISION = "000000000005"
CONDUIT_DWG_CONTRACT_REVISION = "000000000006"
PERSISTENCE_TOPOLOGY_REVISION = "000000000007"
KEYS_FIELD_BUS_REVISION = "000000000008"
BULK_OPERATION_REVISION = "000000000009"
CONDUIT_PRODUCT_REVISION = "000000000010"
TOPOLOGY_AUTOCAD_CONTRACT_REVISION = "000000000011"
TIMBER_MOUNT_WAY_REVISION = "000000000012"
SCREED_MOUNT_WAY_REVISION = "000000000013"
SHARED_BOX_ENDPOINT_REVISION = "000000000014"
HEAD_REVISION = SHARED_BOX_ENDPOINT_REVISION
KNOWN_REVISIONS = frozenset(
    {
        FOUNDATION_REVISION,
        FULL_MVP_REVISION,
        CATALOG_CONTRACT_REVISION,
        WORK_SESSION_REVISION,
        DALI_GROUP_REVISION,
        CONDUIT_DWG_CONTRACT_REVISION,
        PERSISTENCE_TOPOLOGY_REVISION,
        KEYS_FIELD_BUS_REVISION,
        BULK_OPERATION_REVISION,
        CONDUIT_PRODUCT_REVISION,
        TOPOLOGY_AUTOCAD_CONTRACT_REVISION,
        TIMBER_MOUNT_WAY_REVISION,
        SCREED_MOUNT_WAY_REVISION,
        HEAD_REVISION,
    }
)


class MigrationError(RuntimeError):
    """Base class for controlled migration failures."""


class DatabaseAlreadyExistsError(MigrationError):
    """Raised when clean initialization targets an existing path."""


class BackupVerificationError(MigrationError):
    """Raised if the mandatory pre-upgrade copy cannot be verified."""


@dataclass(frozen=True)
class BackupReceipt:
    path: Path
    sha256: str
    source_revision: str


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.resolve().as_posix()}"


def _config(path: Path) -> Config:
    config = Config()
    config.set_main_option("script_location", str(package_data_path("persistence", "migrations")))
    config.set_main_option("sqlalchemy.url", _sqlite_url(path))
    return config


def current_revision_read_only(path: Path) -> str | None:
    """Read the Alembic revision without creating or modifying the database."""
    resolved = path.resolve()
    if not resolved.is_file():
        return None
    uri = f"file:{resolved.as_posix()}?mode=ro"
    try:
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            row = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'"
            ).fetchone()
            if row is None:
                return None
            revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    except sqlite3.DatabaseError as exc:
        raise MigrationError(f"Cannot inspect database revision: {resolved}") from exc
    return None if revision is None else str(revision[0])


def initialize_database(path: Path, *, target: str = "head") -> str:
    """Create a new database only at a path that does not already exist."""
    resolved = path.resolve()
    if resolved.exists():
        raise DatabaseAlreadyExistsError(f"Database already exists: {resolved}")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    command.upgrade(_config(resolved), target)
    revision = current_revision_read_only(resolved)
    if revision is None:
        raise MigrationError("Migration completed without a recorded schema revision")
    return revision


def create_verified_backup(source: Path, backup_directory: Path) -> BackupReceipt:
    """Create and integrity-check a SQLite online backup before an upgrade."""
    source = source.resolve()
    revision = current_revision_read_only(source)
    if revision is None:
        raise BackupVerificationError("A versioned source database is required")
    backup_directory = backup_directory.resolve()
    backup_directory.mkdir(parents=True, exist_ok=True)
    target = backup_directory / f"{source.stem}.{revision}.backup.sqlite"
    if target.exists():
        raise BackupVerificationError(f"Backup target already exists: {target}")
    source_uri = f"file:{source.as_posix()}?mode=ro"
    try:
        with sqlite3.connect(source_uri, uri=True) as source_connection:
            with sqlite3.connect(target) as target_connection:
                source_connection.backup(target_connection)
        with sqlite3.connect(f"file:{target.as_posix()}?mode=ro", uri=True) as connection:
            result = connection.execute("PRAGMA integrity_check").fetchone()
            copied_revision = connection.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone()
    except sqlite3.DatabaseError as exc:
        target.unlink(missing_ok=True)
        raise BackupVerificationError("SQLite backup or verification failed") from exc
    if result != ("ok",) or copied_revision != (revision,):
        target.unlink(missing_ok=True)
        raise BackupVerificationError("Backup integrity or revision verification failed")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    return BackupReceipt(path=target, sha256=digest, source_revision=revision)


def upgrade_database(path: Path, backup_directory: Path, *, target: str = "head") -> BackupReceipt:
    """Upgrade a versioned database after creating a verified backup."""
    resolved = path.resolve()
    receipt = create_verified_backup(resolved, backup_directory)
    try:
        command.upgrade(_config(resolved), target)
    except Exception:
        # The verified backup is deliberately retained for controlled recovery.
        raise
    return receipt


def downgrade_database(path: Path, backup_directory: Path, *, target: str) -> BackupReceipt:
    """Downgrade a versioned database after creating a verified backup."""

    resolved = path.resolve()
    receipt = create_verified_backup(resolved, backup_directory)
    command.downgrade(_config(resolved), target)
    return receipt
