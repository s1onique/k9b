"""SQLite schema definitions for incident event store.

This module defines the append-only event sourcing schema for incidents:
- incident_events: immutable source of truth (append-only)
- incident_current: rebuildable projection/cache of current state
- schema_migrations: version tracking for schema evolution

Hard constraints:
- incident_events is append-only (triggers prevent UPDATE/DELETE)
- incident_current is a projection, may be truncated/rebuilt
- No WAL mode by default (unsafe on network filesystems)
"""

from __future__ import annotations

import re
from typing import Any

# =============================================================================
# Schema Version
# =============================================================================

# Schema version 2 introduced the ``lifecycle_idempotency`` table +
# UNIQUE index for the internal ``diagnosis-loop-transition`` endpoint.
#
# The version bump is required because the production backend can ship
# with an existing v1 database that does NOT have the table. The
# :mod:`incident_store_sqlite_migrations` module applies the v2 upgrade
# to bring the database forward so the durable critical section does
# not crash on the first lifecycle request after the upgrade.
SCHEMA_VERSION = 2

# =============================================================================
# SQL Statements
# =============================================================================

# Schema migrations table
CREATE_SCHEMA_MIGRATIONS = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
"""

# Immutable event table - source of truth
CREATE_INCIDENT_EVENTS = """
CREATE TABLE IF NOT EXISTS incident_events (
    event_seq INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    incident_id TEXT NOT NULL,
    aggregate_version INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    actor TEXT NOT NULL,
    actor_id TEXT,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    previous_event_sha256 TEXT,
    event_sha256 TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
"""

# Indexes for incident_events
CREATE_EVENTS_INDICES = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_incident_events_incident_version
    ON incident_events(incident_id, aggregate_version);

CREATE INDEX IF NOT EXISTS idx_incident_events_incident_seq
    ON incident_events(incident_id, event_seq);

CREATE INDEX IF NOT EXISTS idx_incident_events_type_time
    ON incident_events(event_type, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_incident_events_event_id
    ON incident_events(event_id);
"""

# Projection table - current state cache
CREATE_INCIDENT_CURRENT = """
CREATE TABLE IF NOT EXISTS incident_current (
    incident_id TEXT PRIMARY KEY,
    aggregate_version INTEGER NOT NULL,
    source_candidate_id TEXT NOT NULL,
    namespace TEXT NOT NULL,
    object_kind TEXT NOT NULL,
    object_name TEXT NOT NULL,
    raw_object_kind TEXT,
    candidate_class TEXT NOT NULL,
    severity TEXT NOT NULL,
    status TEXT NOT NULL,
    first_observed_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL,
    current_state_json TEXT NOT NULL,
    last_event_seq INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
"""

# Indexes for incident_current
CREATE_CURRENT_INDICES = """
CREATE INDEX IF NOT EXISTS idx_incident_current_status_seen
    ON incident_current(status, last_observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_incident_current_namespace_object
    ON incident_current(namespace, object_kind, object_name);

CREATE INDEX IF NOT EXISTS idx_incident_current_candidate
    ON incident_current(source_candidate_id);

CREATE INDEX IF NOT EXISTS idx_incident_current_diagnosis_scan
    ON incident_current(first_observed_at, incident_id);

-- Partial index for active incidents keyset pagination
-- Covers ORDER BY first_observed_at, incident_id with active status filter
CREATE INDEX IF NOT EXISTS idx_incident_current_active_diagnosis_scan
    ON incident_current(first_observed_at, incident_id)
    WHERE status IN ('open', 'collecting_evidence', 'investigating', 'ready_for_review');
"""

# Lifecycle idempotency registry: durable dedupe across processes and restarts.
#
# Each row records one accepted (key, fingerprint) pair for the
# internal ``diagnosis-loop-transition`` endpoint. The composite
# UNIQUE index makes ``INSERT OR IGNORE`` the canonical atomic
# ``check-then-insert`` primitive: if the row already exists, the
# mutation MUST NOT run; if it does not, the mutation AND the row
# insert MUST land in the same ``BEGIN IMMEDIATE`` transaction so
# crash-restart and multi-process replay converge on a single
# observable transition.
#
# The table is intentionally append-only. Same-key/different-fingerprint
# replays are surfaced as 409 by application code, never by mutating
# the existing record.
CREATE_LIFECYCLE_IDEMPOTENCY = """
CREATE TABLE IF NOT EXISTS lifecycle_idempotency (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT NOT NULL,
    transition TEXT NOT NULL,
    collector_run_id TEXT NOT NULL,
    diagnosis_run_id TEXT,
    fingerprint TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    applied_at TEXT NOT NULL
);
"""

# R3-5: SQLite treats NULL as distinct in UNIQUE constraints, so the
# bare index ``(..., diagnosis_run_id)`` would allow two otherwise
# identical rows with ``diagnosis_run_id IS NULL`` to coexist. We use
# ``COALESCE(diagnosis_run_id, '')`` in the index expression so the
# NULL value still participates in the uniqueness check, while keeping
# the column itself nullable for callers that legitimately do not
# have a run id.
#
# Application lookups MUST mirror the index expression
# (``COALESCE(diagnosis_run_id, '') = ?``) so the comparison matches
# the indexed key. The ``incident_store_sqlite_context`` module owns
# the canonical lookup and uses this exact comparison.
CREATE_LIFECYCLE_IDEMPOTENCY_INDICES = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_lifecycle_idempotency_key
    ON lifecycle_idempotency(
        incident_id,
        transition,
        collector_run_id,
        COALESCE(diagnosis_run_id, '')
    );
"""

# Append-only enforcement triggers
CREATE_TRIGGERS = """
-- Prevent UPDATE on incident_events (append-only)
CREATE TRIGGER IF NOT EXISTS incident_events_no_update
BEFORE UPDATE ON incident_events
BEGIN
    SELECT RAISE(ABORT, 'incident_events is append-only');
END;

-- Prevent DELETE on incident_events (append-only)
CREATE TRIGGER IF NOT EXISTS incident_events_no_delete
BEFORE DELETE ON incident_events
BEGIN
    SELECT RAISE(ABORT, 'incident_events is append-only');
END;
"""

# All initialization statements in order
INIT_STATEMENTS = [
    CREATE_SCHEMA_MIGRATIONS,
    CREATE_INCIDENT_EVENTS,
    CREATE_EVENTS_INDICES,
    CREATE_INCIDENT_CURRENT,
    CREATE_CURRENT_INDICES,
    CREATE_LIFECYCLE_IDEMPOTENCY,
    CREATE_LIFECYCLE_IDEMPOTENCY_INDICES,
    CREATE_TRIGGERS,
]


def get_schema_sql() -> list[str]:
    """Return all SQL statements needed to initialize the schema.

    Returns:
        List of SQL statements to execute in order
    """
    return INIT_STATEMENTS.copy()


def get_create_trigger_sql() -> str:
    """Return SQL to create immutability triggers only.

    This is used by the immutability verifier to check trigger presence.
    """
    return CREATE_TRIGGERS


def verify_append_only_constraint() -> dict[str, Any]:
    """Return configuration for append-only constraint verification.

    This helper provides a canonical reference for what tables and
    operations are protected by immutability constraints.

    Returns:
        Dict with immutable_tables, blocked_operations, and
        journal_mode_recommendation
    """
    return {
        "immutable_tables": ["incident_events"],
        "blocked_operations": ["UPDATE", "DELETE"],
        "journal_mode_recommendation": "DELETE",
        "wal_warning_paths": [
            "/mnt/",
            "/volumes/",
            "/network/",
            "//",
        ],
        "is_network_path_patterns": [
            r"^/mnt/",
            r"^/volumes/",
            r"^/network/",
            r"^//",
        ],
    }


def is_network_path(db_path: str) -> bool:
    """Check if a database path looks like a network filesystem.

    Args:
        db_path: Path to the SQLite database file

    Returns:
        True if the path looks like a network mount
    """
    patterns = [
        r"^/mnt/",
        r"^/volumes/",
        r"^/network/",
        r"^//",  # UNC path
    ]
    for pattern in patterns:
        if re.match(pattern, db_path):
            return True
    return False


__all__ = [
    "SCHEMA_VERSION",
    "CREATE_SCHEMA_MIGRATIONS",
    "CREATE_INCIDENT_EVENTS",
    "CREATE_INCIDENT_CURRENT",
    "CREATE_TRIGGERS",
    "INIT_STATEMENTS",
    "get_schema_sql",
    "get_create_trigger_sql",
    "verify_append_only_constraint",
    "is_network_path",
]
