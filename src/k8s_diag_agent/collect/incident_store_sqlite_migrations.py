"""Schema migration management for SQLite incident store.

This module handles database schema migrations for the incident event store.
Migrations are tracked in the schema_migrations table to ensure idempotent,
ordered application.

Design:
- All migrations are forward-only (no downgrades needed)
- Each migration has a unique version number
- Applied migrations are recorded with timestamp
- On startup, we apply any unapplied migrations
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime
from typing import Any

from .incident_store_sqlite_schema import (
    CREATE_LIFECYCLE_IDEMPOTENCY,
    CREATE_LIFECYCLE_IDEMPOTENCY_INDICES,
    SCHEMA_VERSION,
    get_schema_sql,
)

# TYPE_CHECKING is used for conditional imports that are only needed for type hints

_logger = logging.getLogger(__name__)


# Migration definitions - each tuple is (version, upgrade_sql_list).
#
# Version 1: Initial schema (created by ``get_schema_sql()``).
# Version 2: Adds the ``lifecycle_idempotency`` table + UNIQUE index so
# existing v1 production databases can be upgraded in place. Without
# this entry, a v1 database would crash on the first
# ``diagnosis-loop-transition`` request with
# ``sqlite3.OperationalError: no such table: lifecycle_idempotency``.
#
# The SQL uses ``IF NOT EXISTS`` so applying it on a fresh database
# (which already has the table from ``get_schema_sql()``) is a no-op.
MIGRATIONS: list[tuple[int, list[str]]] = [
    (
        2,
        [
            CREATE_LIFECYCLE_IDEMPOTENCY,
            CREATE_LIFECYCLE_IDEMPOTENCY_INDICES,
        ],
    ),
]


def get_current_version(conn: sqlite3.Connection) -> int:
    """Get the current schema version from the database.

    Args:
        conn: SQLite connection

    Returns:
        Current schema version, or 0 if no migrations applied yet
    """
    try:
        cursor = conn.execute(
            "SELECT MAX(version) FROM schema_migrations"
        )
        row = cursor.fetchone()
        if row is None or row[0] is None:
            return 0
        return int(row[0])
    except sqlite3.OperationalError:
        # Table doesn't exist yet
        return 0


def run_migrations(conn: sqlite3.Connection) -> int:
    """Run any pending schema migrations.

    This function:
    1. Gets the current applied version
    2. Applies any migrations with higher version numbers
    3. Records each applied migration with timestamp

    Args:
        conn: SQLite connection (should be in transaction)

    Returns:
        The new schema version after migrations complete
    """
    current_version = get_current_version(conn)

    if current_version == 0:
        # Fresh database - apply initial schema
        _logger.info(
            "Initializing incident event store schema",
            extra={
                "event": "schema-migration-start",
                "target_version": SCHEMA_VERSION,
            },
        )
        for sql in get_schema_sql():
            conn.executescript(sql)

        # Record initial schema version
        now = datetime.now(UTC).isoformat()
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (SCHEMA_VERSION, now),
        )
        conn.commit()
        current_version = SCHEMA_VERSION

        _logger.info(
            "Incident event store schema initialized",
            extra={
                "event": "schema-migration-complete",
                "version": SCHEMA_VERSION,
            },
        )

    elif current_version < SCHEMA_VERSION:
        # Apply pending migrations
        _logger.info(
            "Applying schema migrations",
            extra={
                "event": "schema-migration-start",
                "from_version": current_version,
                "to_version": SCHEMA_VERSION,
            },
        )

        for target_version, migration_sqls in MIGRATIONS:
            if target_version > current_version:
                for sql in migration_sqls:
                    conn.executescript(sql)

                # Record migration
                now = datetime.now(UTC).isoformat()
                conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                    (target_version, now),
                )
                current_version = target_version

                _logger.info(
                    "Applied migration",
                    extra={
                        "event": "schema-migration-applied",
                        "version": target_version,
                    },
                )

        conn.commit()

        _logger.info(
            "Schema migrations complete",
            extra={
                "event": "schema-migration-complete",
                "version": current_version,
            },
        )

    return current_version


def verify_schema(conn: sqlite3.Connection) -> dict[str, Any]:
    """Verify the schema is properly initialized.

    Args:
        conn: SQLite connection

    Returns:
        Dict with schema verification info
    """
    result: dict[str, Any] = {
        "schema_version": get_current_version(conn),
        "tables": {},
        "triggers": {},
    }

    # Check tables exist
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    for (name,) in cursor.fetchall():
        result["tables"][name] = True

    # Check triggers exist
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='trigger'"
    )
    for (name,) in cursor.fetchall():
        result["triggers"][name] = True

    # Check indexes exist
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
    )
    result["indexes"] = [name for (name,) in cursor.fetchall()]

    return result


__all__ = [
    "MIGRATIONS",
    "SCHEMA_VERSION",
    "get_current_version",
    "run_migrations",
    "verify_schema",
]
