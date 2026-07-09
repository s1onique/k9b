"""SQLite-backed incident store with event sourcing.

This module provides a production-grade incident store backed by SQLite:
- Append-only incident_events table (immutable source of truth)
- incident_current projection (rebuildable cache)
- Atomic transactions for event append + projection update
- Hash chain for tamper evidence
- Trigger-protected immutability
- Thread-safe connection factory (each operation gets its own connection)

Thread safety design:
- Each store operation opens a fresh connection via _connect() context manager
- All write operations are serialized via _write_lock
- Connections are NOT shared across threads to avoid sqlite3.ProgrammingError
- SQLite check_same_thread=True is preserved (default)

Hard constraints:
- NO remediation actions
- NO Kubernetes resource mutation
- NO LLM calls
- Scheduler does NOT write SQLite directly (backend-owned)
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator

from .incident_candidates import IncidentCandidate
from .incident_evidence import EvidenceRole
from .incident_lifecycle import (
    Incident,
)
from .incident_store import IncidentStore
from .incident_store_sqlite_config import (
    DEFAULT_JOURNAL_MODE,
    DEFAULT_SQLITE_PATH,
    ENV_BACKEND,
    ENV_FILE_PATH,
    ENV_JOURNAL_MODE,
    ENV_SQLITE_PATH,
    VALID_JOURNAL_MODES,
    SQLiteConnectionConfig,
)
from .incident_store_sqlite_context import (
    SQLiteWriteContext,
)
from .incident_store_sqlite_events import (
    StoredEvent,
    parse_stored_event,
)
from .incident_store_sqlite_lifecycle import (
    add_incident_impl,
    attach_evidence_impl,
    mark_diagnosis_loop_completed_impl,
    mark_diagnosis_loop_failed_impl,
    mark_diagnosis_loop_started_impl,
    promote_candidates_impl,
)
from .incident_store_sqlite_migrations import run_migrations
from .incident_store_sqlite_state import (
    mark_collecting_evidence_impl,
    mark_duplicate_impl,
    mark_investigating_impl,
    mark_ready_for_review_impl,
    resolve_impl,
    suppress_impl,
)

if TYPE_CHECKING:
    pass

_logger = logging.getLogger(__name__)


# =============================================================================
# Connection Factory
# =============================================================================


def _create_connection(path: Path, journal_mode: str) -> sqlite3.Connection:
    """Create a configured SQLite connection.

    This factory creates connections without sharing state between threads.
    Each operation gets its own connection, and writes are serialized via lock.

    Args:
        path: Path to the SQLite database
        journal_mode: SQLite journal mode (DELETE, TRUNCATE, PERSIST, WAL)

    Returns:
        Configured SQLite connection with row_factory and pragmas
    """
    conn = sqlite3.connect(
        str(path),
        isolation_level="DEFERRED",  # Explicit transaction management
        timeout=5.0,  # 5 second busy timeout
    )
    conn.row_factory = sqlite3.Row

    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys=ON")

    # Set busy timeout (ms)
    conn.execute("PRAGMA busy_timeout=5000")

    # Set journal mode
    _set_journal_mode(conn, journal_mode, path)

    return conn


def _set_journal_mode(conn: sqlite3.Connection, mode: str, path: Path) -> None:
    """Set SQLite journal mode with safety checks.

    Args:
        conn: SQLite connection
        mode: Journal mode (DELETE, TRUNCATE, PERSIST, WAL)
        path: Path to database (for logging)
    """
    mode = mode.upper()
    if mode not in VALID_JOURNAL_MODES:
        _logger.warning(
            "Invalid journal mode %s, using DELETE",
            mode,
        )
        mode = "DELETE"

    # WAL warning for network filesystems
    if mode == "WAL":
        _logger.warning(
            "WAL journal mode requested for %s. "
            "WAL mode is UNSAFE on network filesystems (NFS, RWX volumes). "
            "Consider using DELETE mode for Kubernetes shared storage.",
            path,
            extra={
                "event": "sqlite-wal-warning",
                "path": str(path),
            },
        )

    conn.execute(f"PRAGMA journal_mode={mode}")
    _logger.debug(
        "SQLite journal mode set to %s for %s",
        mode,
        path,
    )


# =============================================================================
# SQLiteIncidentStore
# =============================================================================


class SQLiteIncidentStore(IncidentStore):
    """SQLite-backed incident store with event sourcing.

    This store implements the IncidentStore interface with:
    - Append-only incident_events table
    - incident_current projection cache
    - Atomic transactions for event + projection updates
    - Hash chain for tamper evidence
    - Trigger-protected immutability

    Thread safety:
    - Each operation opens a fresh connection via _connect()
    - All write operations are serialized via _write_lock
    - Connections are NOT shared across threads

    Backend ownership model:
    - Only k9b-backend process writes to SQLite
    - k9b-scheduler submits promotion requests via internal API
    - /api/incidents reads from incident_current projection
    """

    def __init__(
        self,
        path: Path | str,
        journal_mode: str = DEFAULT_JOURNAL_MODE,
    ) -> None:
        """Initialize SQLite incident store."""
        super().__init__()
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._journal_mode = journal_mode

        # Write serialization lock - MUST be acquired before any write operation
        self._write_lock = threading.Lock()

        # Create initial connection for schema setup and initial load
        # This connection is only used during __init__, then closed
        init_conn = _create_connection(self._path, journal_mode)
        try:
            self._schema_version = run_migrations(init_conn)
        finally:
            init_conn.close()

        # Load incidents from projection into memory cache
        self._load_from_projection()

        _logger.info(
            "SQLite incident store configured",
            extra={
                "event": "incident-store-configured",
                "store_kind": "sqlite",
                "path": str(self._path),
                "journal_mode": journal_mode,
                "schema_version": self._schema_version,
                "loaded_incidents": len(self._incidents),
            },
        )

    @property
    def path(self) -> Path:
        """Return the path to the SQLite database."""
        return self._path

    @property
    def store_kind(self) -> str:
        """Return the kind of store for logging."""
        return "sqlite"

    @property
    def write_lock(self) -> threading.Lock:
        """Return the write lock for serialization.

        Exposed for lifecycle/state modules that need to serialize writes.
        """
        return self._write_lock

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Context manager for getting a fresh SQLite connection.

        Each call creates a new connection. This avoids sharing connections
        across threads which causes sqlite3.ProgrammingError.

        The caller is responsible for acquiring _write_lock before using
        this connection for writes.

        Yields:
            A fresh configured SQLite connection
        """
        conn = _create_connection(self._path, self._journal_mode)
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _write_connection(self) -> Iterator[sqlite3.Connection]:
        """Context manager for getting a connection with write lock held.

        This combines _write_lock acquisition with _connect() to ensure
        thread-safe write operations.

        Yields:
            A fresh configured SQLite connection with write lock held

        Note:
            Prefer _write_context() for new code that also needs cache access.
            This method is kept for backward compatibility with existing code.
        """
        with self._write_lock:
            with self._connect() as conn:
                yield conn

    @contextmanager
    def _write_context(self) -> Iterator[SQLiteWriteContext]:
        """Context manager for acquiring a write capability.

        This is the preferred way to perform write operations on the store.
        It creates a SQLiteWriteContext that owns:
        - Event append authority
        - Cache read/write authority
        - Snapshot helper access

        The context is only valid inside this block. After the block exits,
        the context is closed and any further use will raise ContextClosedError.

        Yields:
            SQLiteWriteContext with write authority

        Example:
            with store._write_context() as ctx:
                ctx.append_event(...)
                ctx.put_cached_incident(updated)
                return ctx.snapshot_incident(updated)
        """
        with self._write_lock:
            with self._connect() as conn:
                ctx = SQLiteWriteContext(
                    conn=conn,
                    cache=self._incidents,
                    store=self,
                )
                try:
                    yield ctx
                finally:
                    ctx.close()

    def _load_from_projection(self) -> None:
        """Load incidents from incident_current projection into memory cache."""
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT incident_id, current_state_json, last_event_seq
                FROM incident_current
                ORDER BY incident_id
                """
            )

            for row in cursor.fetchall():
                incident_id = row[0]
                current_json = row[1]

                try:
                    state = json.loads(current_json)
                    incident = self._state_to_incident(state)
                    self._incidents[incident_id] = incident
                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    _logger.warning(
                        "Failed to deserialize incident %s from projection: %s",
                        incident_id,
                        e,
                    )

    def _state_to_incident(self, state: dict[str, Any]) -> Incident:
        """Convert a projection state dict to an Incident object.

        Uses Incident.from_dict() to preserve real typing and avoid drift
        between file-backed and SQLite deserialization.
        """
        # Use the canonical Incident.from_dict() method for proper typing
        return Incident.from_dict(state)

    # =========================================================================
    # Override IncidentStore Methods (delegated to lifecycle/state modules)
    # =========================================================================

    def promote_candidates(
        self,
        candidates: list[IncidentCandidate] | tuple[IncidentCandidate, ...],
        observed_at: datetime,
        snapshot_bundle_id: str | None = None,
    ) -> tuple[Incident, ...]:
        """Promote candidates to incidents with event sourcing."""
        return promote_candidates_impl(self, candidates, observed_at, snapshot_bundle_id)

    def add_incident(self, incident: Incident) -> None:
        """Add an incident by appending an OPENED event."""
        add_incident_impl(self, incident)

    def mark_collecting_evidence(self, incident_id: str, bundle_id: str) -> Incident | None:
        """Transition to COLLECTING_EVIDENCE."""
        return mark_collecting_evidence_impl(self, incident_id, bundle_id)

    def mark_ready_for_review(
        self,
        incident_id: str,
        reviewer_id: str | None = None,
    ) -> Incident | None:
        """Transition to READY_FOR_REVIEW."""
        # reviewer_id is required by impl, default to "unknown" if not provided
        reviewer = reviewer_id if reviewer_id else "unknown"
        return mark_ready_for_review_impl(self, incident_id, reviewer)

    def suppress(self, incident_id: str, reason: str) -> Incident | None:
        """Suppress incident."""
        return suppress_impl(self, incident_id, reason)

    def mark_duplicate(self, incident_id: str, duplicate_of: str) -> Incident | None:
        """Mark incident as duplicate."""
        return mark_duplicate_impl(self, incident_id, duplicate_of)

    def resolve(self, incident_id: str, resolution: str = "resolved") -> Incident | None:
        """Resolve incident."""
        return resolve_impl(self, incident_id, resolution)

    def mark_investigating(self, incident_id: str) -> Incident | None:
        """Transition to INVESTIGATING."""
        return mark_investigating_impl(self, incident_id)

    def attach_evidence(
        self,
        incident_id: str,
        artifact_id: str,
        role: EvidenceRole,
    ) -> Incident | None:
        """Attach evidence to incident."""
        return attach_evidence_impl(self, incident_id, artifact_id, role)

    def mark_diagnosis_loop_started(
        self,
        incident_id: str,
        run_id: str,
        collector_run_id: str,
    ) -> Incident | None:
        """Mark diagnosis loop started."""
        return mark_diagnosis_loop_started_impl(self, incident_id, run_id, collector_run_id)

    def mark_diagnosis_loop_completed(
        self,
        incident_id: str,
        run_id: str,
        collector_run_id: str,
        review_packet_name: str | None = None,
        checks_requested: int = 0,
        checks_run: int = 0,
        checks_rejected: int = 0,
        decision: str | None = None,
    ) -> Incident | None:
        """Mark diagnosis loop completed."""
        return mark_diagnosis_loop_completed_impl(
            self, incident_id, run_id, collector_run_id,
            review_packet_name, checks_requested, checks_run, checks_rejected, decision
        )

    def mark_diagnosis_loop_failed(
        self,
        incident_id: str,
        run_id: str | None = None,
        collector_run_id: str | None = None,
        unavailable_reason: str | None = None,
    ) -> Incident | None:
        """Mark diagnosis loop failed."""
        return mark_diagnosis_loop_failed_impl(self, incident_id, run_id, collector_run_id, unavailable_reason)

    # =========================================================================
    # Event History (for detail endpoint)
    # =========================================================================

    def get_incident_events(
        self,
        incident_id: str,
        limit: int = 100,
    ) -> list[StoredEvent]:
        """Get events for an incident."""
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT event_seq, event_id, incident_id, aggregate_version, event_type,
                       occurred_at, actor, actor_id, payload_json, payload_sha256,
                       previous_event_sha256, event_sha256, created_at
                FROM incident_events
                WHERE incident_id = ?
                ORDER BY event_seq DESC
                LIMIT ?
                """,
                (incident_id, limit),
            )

            events = []
            for row in cursor.fetchall():
                events.append(parse_stored_event(row))

            return events

    # =========================================================================
    # Diagnostics
    # =========================================================================

    def get_event_count(self) -> int:
        """Get total number of events in the store."""
        with self._connect() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM incident_events")
            row = cursor.fetchone()
            return row[0] if row else 0

    def get_incident_count(self) -> int:
        """Get total number of incidents in the store."""
        with self._connect() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM incident_current")
            row = cursor.fetchone()
            return row[0] if row else 0

    def rebuild_projection(self) -> int:
        """Rebuild the entire projection from events."""
        from .incident_store_sqlite_projection import rebuild_projection as _rebuild

        with self._write_connection() as conn:
            count = _rebuild(conn)

        self._incidents.clear()
        self._load_from_projection()

        return count

    def close(self) -> None:
        """Close the store (no-op, connections are per-operation)."""
        # Connections are per-operation, so no global connection to close
        pass

    def __len__(self) -> int:
        """Return the number of incidents in the store."""
        return len(self._incidents)

    def __repr__(self) -> str:
        """Return string representation for debugging."""
        return f"SQLiteIncidentStore(path={self._path}, incidents={len(self._incidents)})"


__all__ = [
    "SQLiteIncidentStore",
    "SQLiteConnectionConfig",
    "ENV_BACKEND",
    "ENV_SQLITE_PATH",
    "ENV_FILE_PATH",
    "ENV_JOURNAL_MODE",
    "DEFAULT_SQLITE_PATH",
    "DEFAULT_JOURNAL_MODE",
    "VALID_JOURNAL_MODES",
]
