"""SQLite-backed incident store with event sourcing.

This module provides a production-grade incident store backed by SQLite:
- Append-only incident_events table (immutable source of truth)
- incident_current projection (rebuildable cache)
- Atomic transactions for event append + projection update
- Hash chain for tamper evidence
- Trigger-protected immutability

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
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

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
    create_connection,
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

        config = SQLiteConnectionConfig(
            path=self._path,
            journal_mode=journal_mode,
        )
        self._conn: sqlite3.Connection = create_connection(config)

        self._schema_version = run_migrations(self._conn)
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

    def _load_from_projection(self) -> None:
        """Load incidents from incident_current projection into memory cache."""
        cursor = self._conn.execute(
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
        cursor = self._conn.execute(
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
        cursor = self._conn.execute("SELECT COUNT(*) FROM incident_events")
        row = cursor.fetchone()
        return row[0] if row else 0

    def get_incident_count(self) -> int:
        """Get total number of incidents in the store."""
        cursor = self._conn.execute("SELECT COUNT(*) FROM incident_current")
        row = cursor.fetchone()
        return row[0] if row else 0

    def rebuild_projection(self) -> int:
        """Rebuild the entire projection from events."""
        from .incident_store_sqlite_projection import rebuild_projection as _rebuild

        with self._conn:
            count = _rebuild(self._conn)

        self._incidents.clear()
        self._load_from_projection()

        return count

    def close(self) -> None:
        """Close the SQLite connection."""
        conn = self._conn
        if conn:
            conn.close()

    def __len__(self) -> int:
        """Return the number of incidents in the store."""
        return len(self._incidents)

    def __repr__(self) -> str:
        """Return string representation for debugging."""
        return f"SQLiteIncidentStore(path={self._path}, incidents={len(self._incidents)})"


__all__ = [
    "SQLiteIncidentStore",
    "SQLiteConnectionConfig",
    "create_connection",
    "ENV_BACKEND",
    "ENV_SQLITE_PATH",
    "ENV_FILE_PATH",
    "ENV_JOURNAL_MODE",
    "DEFAULT_SQLITE_PATH",
    "DEFAULT_JOURNAL_MODE",
    "VALID_JOURNAL_MODES",
]
