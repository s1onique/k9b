"""File-backed incident store with atomic writes for cross-process durability.

This module provides a file-backed incident store that:
- Persists incidents to a JSON file
- Uses atomic writes to prevent corruption
- Supports shared access between scheduler and backend pods
- Loads existing incidents on startup

Hard constraints enforced:
- NO remediation actions
- NO Kubernetes resource mutation
- NO LLM calls
- NO external tool invocation

Usage:
    # Set via environment variable
    K9B_INCIDENT_STORE_PATH=/app/runs/incidents/incident-store.json

    # Or configure directly
    store = FileBackedIncidentStore(Path("/app/runs/incidents/incident-store.json"))
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .incident_lifecycle import Incident, IncidentStatus
from .incident_store import IncidentStore

if TYPE_CHECKING:
    pass

_logger = logging.getLogger(__name__)

# Schema version for the incident store file format
SCHEMA_VERSION = "k9b.incident-store.v1"

# Default directory for incident store
DEFAULT_INCIDENT_STORE_DIR = "/app/runs/incidents"


def _serialize_incident(incident: Incident) -> dict[str, Any]:
    """Serialize an incident to a dict for JSON storage."""
    return incident.to_dict()


def _deserialize_incident(data: dict[str, Any]) -> Incident:
    """Deserialize an incident from a dict stored in JSON."""
    return Incident.from_dict(data)


class FileBackedIncidentStore(IncidentStore):
    """File-backed incident store that persists incidents to JSON.

    This store extends the in-memory IncidentStore with file persistence.
    It:
    - Loads existing incidents from file on initialization
    - Persists incidents after each write operation using atomic writes
    - Supports shared access between scheduler and backend pods
    - Reloads from file before reads to see other process's writes
    - Merges before writes to avoid clobbering concurrent updates

    Atomic write strategy:
    1. Write to temp file with .tmp suffix
    2. Use os.replace() to atomically rename temp to target
    3. This prevents corruption if process crashes during write

    Refresh-on-read pattern:
    - list_incidents() and get_incident() reload from file before returning
    - Ensures already-running backend sees scheduler's new incidents

    Merge-before-write pattern:
    - add_incident() and all transition methods reload before mutating
    - Prevents stale process from overwriting newer data from another process
    """

    def __init__(
        self,
        path: Path | str,
        create_dirs: bool = True,
    ) -> None:
        """Initialize file-backed incident store.

        Args:
            path: Path to the incident store JSON file.
            create_dirs: If True, create parent directories if they don't exist.
        """
        super().__init__()
        self._path = Path(path)

        # Create parent directories if needed
        if create_dirs:
            self._path.parent.mkdir(parents=True, exist_ok=True)

        # Load existing incidents from file
        self._load_from_file()

    @property
    def path(self) -> Path:
        """Return the path to the incident store file."""
        return self._path

    @property
    def store_kind(self) -> str:
        """Return the kind of store for logging."""
        return "file"

    def _reload_from_file(self) -> None:
        """Reload incidents from file, replacing in-memory state.

        This is called before reads to see other process's writes,
        and before writes to merge concurrent updates.
        """
        self._incidents.clear()
        self._load_from_file()

    def _mutate_and_save(self, fn: Any) -> Any:
        """Execute mutation function with merge-before-write pattern.

        Reloads from file first, applies the mutation, then saves.
        This prevents stale processes from overwriting newer data.

        Args:
            fn: Mutation function to execute. Note: avoid capturing self or super
                in lambdas - use direct method calls instead.

        Returns:
            The result of the mutation function
        """
        self._reload_from_file()
        result = fn()
        self._save_to_file()
        return result

    def _load_from_file(self) -> None:
        """Load incidents from the file into memory.

        If the file doesn't exist or is corrupted, starts with empty store.
        """
        if not self._path.exists():
            _logger.debug("No incident store file at %s, starting fresh", self._path)
            return

        try:
            content = self._path.read_text(encoding="utf-8")
            data = json.loads(content)

            # Validate schema version
            schema_version = data.get("schema_version")
            if schema_version != SCHEMA_VERSION:
                _logger.warning(
                    "Unexpected schema version %s, expected %s. Starting fresh.",
                    schema_version,
                    SCHEMA_VERSION,
                )
                return

            # Load incidents
            incidents_data = data.get("incidents", [])
            loaded_count = 0
            for inc_data in incidents_data:
                try:
                    incident = _deserialize_incident(inc_data)
                    self._incidents[incident.incident_id] = incident
                    loaded_count += 1
                except (KeyError, ValueError, TypeError) as e:
                    _logger.warning("Failed to deserialize incident: %s", e)

            _logger.info(
                "Loaded %d incidents from %s",
                loaded_count,
                self._path,
            )

        except (json.JSONDecodeError, OSError) as e:
            _logger.warning(
                "Failed to load incident store from %s: %s. Starting fresh.",
                self._path,
                e,
            )

    def _save_to_file(self) -> None:
        """Persist current incidents to file using atomic write."""
        # Build payload
        updated_at = datetime.now(UTC).isoformat()
        incidents_data = [
            _serialize_incident(inc) for inc in self._incidents.values()
        ]
        payload = {
            "schema_version": SCHEMA_VERSION,
            "updated_at": updated_at,
            "incidents": incidents_data,
        }

        # Atomic write: write to temp file, then rename
        tmp_path = self._path.with_suffix(".json.tmp")
        try:
            tmp_path.write_text(
                json.dumps(payload, indent=2, default=str, ensure_ascii=False),
                encoding="utf-8",
            )
            os.replace(tmp_path, self._path)
            _logger.debug(
                "Persisted %d incidents to %s",
                len(self._incidents),
                self._path,
            )
        except OSError as e:
            _logger.error(
                "Failed to persist incident store to %s: %s",
                self._path,
                e,
            )
            # Clean up temp file if it exists
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            raise

    # Override read methods to reload before returning (refresh-on-read)

    def list_incidents(
        self,
        status: IncidentStatus | None = None,
    ) -> tuple[Incident, ...]:
        """List incidents, reloading from file first to see other process's writes."""
        self._reload_from_file()
        return super().list_incidents(status=status)

    def get_incident(self, incident_id: str) -> Incident | None:
        """Get incident by ID, reloading from file first."""
        self._reload_from_file()
        return super().get_incident(incident_id)

    # Override mutation methods to use merge-before-write pattern

    def promote_candidates(
        self,
        candidates: list[Any] | tuple[Any, ...],
        observed_at: datetime,
        snapshot_bundle_id: str | None = None,
    ) -> tuple[Incident, ...]:
        """Promote candidates and persist to file."""
        self._reload_from_file()
        result = IncidentStore.promote_candidates(
            self, candidates, observed_at, snapshot_bundle_id
        )
        self._save_to_file()
        return result

    def add_incident(self, incident: Incident) -> None:
        """Add incident and persist to file."""
        self._reload_from_file()
        IncidentStore.add_incident(self, incident)
        self._save_to_file()

    def mark_collecting_evidence(self, incident_id: str, bundle_id: str) -> Incident | None:
        """Transition to COLLECTING_EVIDENCE and persist."""
        self._reload_from_file()
        result = IncidentStore.mark_collecting_evidence(self, incident_id, bundle_id)
        self._save_to_file()
        return result

    def mark_ready_for_review(
        self,
        incident_id: str,
        review_packet_id: str | None = None,
    ) -> Incident | None:
        """Transition to READY_FOR_REVIEW and persist."""
        self._reload_from_file()
        result = IncidentStore.mark_ready_for_review(self, incident_id, review_packet_id)
        self._save_to_file()
        return result

    def suppress(self, incident_id: str, reason: str) -> Incident | None:
        """Suppress incident and persist."""
        self._reload_from_file()
        result = IncidentStore.suppress(self, incident_id, reason)
        self._save_to_file()
        return result

    def mark_duplicate(self, incident_id: str, duplicate_of: str) -> Incident | None:
        """Mark as duplicate and persist."""
        self._reload_from_file()
        result = IncidentStore.mark_duplicate(self, incident_id, duplicate_of)
        self._save_to_file()
        return result

    def resolve(self, incident_id: str) -> Incident | None:
        """Resolve incident and persist."""
        self._reload_from_file()
        result = IncidentStore.resolve(self, incident_id)
        self._save_to_file()
        return result

    def mark_investigating(self, incident_id: str) -> Incident | None:
        """Mark investigating and persist."""
        self._reload_from_file()
        result = IncidentStore.mark_investigating(self, incident_id)
        self._save_to_file()
        return result

    def attach_evidence(
        self,
        incident_id: str,
        artifact_id: str,
        role: Any,  # EvidenceRole
    ) -> Incident | None:
        """Attach evidence and persist."""
        self._reload_from_file()
        result = IncidentStore.attach_evidence(self, incident_id, artifact_id, role)
        self._save_to_file()
        return result

    def mark_ready_for_review_by_bundle_id(
        self,
        snapshot_bundle_id: str,
        review_packet_id: str | None = None,
    ) -> tuple[Incident, ...]:
        """Mark by bundle ID and persist."""
        self._reload_from_file()
        result = IncidentStore.mark_ready_for_review_by_bundle_id(
            self, snapshot_bundle_id, review_packet_id
        )
        self._save_to_file()
        return result

    def mark_diagnosis_loop_started(
        self,
        incident_id: str,
        run_id: str,
        collector_run_id: str,
    ) -> Incident | None:
        """Mark diagnosis started and persist."""
        self._reload_from_file()
        result = IncidentStore.mark_diagnosis_loop_started(
            self, incident_id, run_id, collector_run_id
        )
        self._save_to_file()
        return result

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
        """Mark diagnosis completed and persist."""
        self._reload_from_file()
        result = IncidentStore.mark_diagnosis_loop_completed(
            self,
            incident_id,
            run_id,
            collector_run_id,
            review_packet_name,
            checks_requested,
            checks_run,
            checks_rejected,
            decision,
        )
        self._save_to_file()
        return result

    def mark_diagnosis_loop_failed(
        self,
        incident_id: str,
        run_id: str | None = None,
        collector_run_id: str | None = None,
        unavailable_reason: str | None = None,
    ) -> Incident | None:
        """Mark diagnosis failed and persist."""
        self._reload_from_file()
        result = IncidentStore.mark_diagnosis_loop_failed(
            self, incident_id, run_id, collector_run_id, unavailable_reason
        )
        self._save_to_file()
        return result

    def __repr__(self) -> str:
        """Return string representation for debugging."""
        return f"FileBackedIncidentStore(path={self._path}, incidents={len(self._incidents)})"


__all__ = [
    "FileBackedIncidentStore",
    "SCHEMA_VERSION",
    "DEFAULT_INCIDENT_STORE_DIR",
]
