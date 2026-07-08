"""Tests for apply_event_to_state function.

Tests the event-to-state projection for each event type.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from k8s_diag_agent.collect.incident_store_sqlite_events import (
    IncidentEventActor,
    IncidentEventType,
    StoredEvent,
    compute_event_sha256,
    compute_payload_sha256,
)
from k8s_diag_agent.collect.incident_store_sqlite_projection import apply_event_to_state


@pytest.fixture
def temp_db_path() -> Generator[Path, None, None]:
    """Provide a temporary database path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test_incidents.sqlite3"


@pytest.fixture
def temp_db_conn(temp_db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    """Provide a configured SQLite connection with schema."""
    from k8s_diag_agent.collect.incident_store_sqlite_migrations import run_migrations

    conn = sqlite3.connect(str(temp_db_path))
    conn.row_factory = sqlite3.Row
    run_migrations(conn)
    yield conn
    conn.close()


def create_test_event(
    incident_id: str,
    event_type: str,
    aggregate_version: int,
    payload: dict[str, Any],
    occurred_at: datetime | None = None,
    event_id: str | None = None,
    previous_event_sha256: str | None = None,
) -> StoredEvent:
    """Helper to create a test StoredEvent."""
    if occurred_at is None:
        occurred_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

    if event_id is None:
        event_id = f"{incident_id}-{event_type}-{aggregate_version}"

    payload_sha256 = compute_payload_sha256(payload)

    event_sha256 = compute_event_sha256(
        event_id=event_id,
        incident_id=incident_id,
        aggregate_version=aggregate_version,
        event_type=event_type,
        occurred_at=occurred_at,
        actor=IncidentEventActor.SYSTEM.value,
        actor_id=None,
        payload_sha256=payload_sha256,
        previous_event_sha256=previous_event_sha256,
    )

    return StoredEvent(
        event_seq=aggregate_version,
        event_id=event_id,
        incident_id=incident_id,
        aggregate_version=aggregate_version,
        event_type=event_type,
        occurred_at=occurred_at,
        actor=IncidentEventActor.SYSTEM.value,
        actor_id=None,
        payload_json=json.dumps(payload),
        payload_sha256=payload_sha256,
        previous_event_sha256=previous_event_sha256,
        event_sha256=event_sha256,
        created_at=datetime.now(UTC),
    )


class TestApplyOpened:
    """Tests for incident.opened event."""

    def test_opened_sets_initial_state(self) -> None:
        """OPENED event sets initial incident state."""
        state: dict[str, Any] = {}
        event = create_test_event(
            incident_id="test-inc-1",
            event_type=IncidentEventType.OPENED,
            aggregate_version=1,
            payload={
                "source_candidate_id": "candidate-123",
                "namespace": "default",
                "object_kind": "Pod",
                "object_name": "test-pod",
                "candidate_class": "crash_loop",
                "severity": "error",
                "first_observed_at": "2024-01-01T10:00:00+00:00",
                "last_observed_at": "2024-01-01T10:00:00+00:00",
                "signals": [{"source": "pod", "reason": "CrashLoopBackOff"}],
            },
        )

        result = apply_event_to_state(state, event)

        assert result is state
        assert state["incident_id"] == "test-inc-1"
        assert state["status"] == "open"
        assert state["namespace"] == "default"
        assert state["object_kind"] == "Pod"
        assert state["signal_count"] == 1
        assert state["evidence_count"] == 0
        assert state["suppressed_reason"] is None
        assert state["duplicate_of"] is None
        assert state["resolved_at"] is None


class TestApplySignalObserved:
    """Tests for incident.signal_observed event."""

    def test_signal_observed_increments_count(self) -> None:
        """SIGNAL_OBSERVED increments signal count."""
        state: dict[str, Any] = {"signal_count": 1}
        event = create_test_event(
            incident_id="test-inc-1",
            event_type=IncidentEventType.SIGNAL_OBSERVED,
            aggregate_version=2,
            payload={
                "signal_count": 2,
                "last_observed_at": "2024-01-01T11:00:00+00:00",
            },
        )

        apply_event_to_state(state, event)

        assert state["signal_count"] == 2
        assert state["last_observed_at"] == "2024-01-01T11:00:00+00:00"


class TestApplyUpdated:
    """Tests for incident.updated event."""

    def test_updated_changes_severity(self) -> None:
        """UPDATED event can change severity."""
        state: dict[str, Any] = {"severity": "warning"}
        event = create_test_event(
            incident_id="test-inc-1",
            event_type=IncidentEventType.UPDATED,
            aggregate_version=2,
            payload={"severity": "error"},
        )

        apply_event_to_state(state, event)

        assert state["severity"] == "error"

    def test_updated_changes_status(self) -> None:
        """UPDATED event can change status."""
        state: dict[str, Any] = {"status": "open"}
        event = create_test_event(
            incident_id="test-inc-1",
            event_type=IncidentEventType.UPDATED,
            aggregate_version=2,
            payload={"status": "investigating"},
        )

        apply_event_to_state(state, event)

        assert state["status"] == "investigating"


class TestApplyCollectingEvidenceStarted:
    """Tests for incident.collecting_evidence_started event."""

    def test_collecting_evidence_sets_status(self) -> None:
        """COLLECTING_EVIDENCE_STARTED sets status to collecting_evidence."""
        state: dict[str, Any] = {"status": "open"}
        event = create_test_event(
            incident_id="test-inc-1",
            event_type=IncidentEventType.COLLECTING_EVIDENCE_STARTED,
            aggregate_version=2,
            payload={
                "bundle_id": "bundle-123",
                "evidence_count": 5,
            },
        )

        apply_event_to_state(state, event)

        assert state["status"] == "collecting_evidence"
        assert state["latest_snapshot_bundle_id"] == "bundle-123"
        assert state["evidence_count"] == 5


class TestApplyReadyForReview:
    """Tests for incident.ready_for_review event."""

    def test_ready_for_review_sets_status(self) -> None:
        """READY_FOR_REVIEW sets status to ready_for_review."""
        state: dict[str, Any] = {"status": "collecting_evidence"}
        event = create_test_event(
            incident_id="test-inc-1",
            event_type=IncidentEventType.READY_FOR_REVIEW,
            aggregate_version=3,
            payload={"review_packet_id": "review-123"},
        )

        apply_event_to_state(state, event)

        assert state["status"] == "ready_for_review"
        assert state["review_packet"]["status"] == "generated"
        assert state["review_packet"]["id"] == "review-123"


class TestApplyInvestigationStarted:
    """Tests for incident.investigation_started event."""

    def test_investigation_started_sets_status(self) -> None:
        """INVESTIGATION_STARTED sets status to investigating."""
        state: dict[str, Any] = {"status": "ready_for_review"}
        event = create_test_event(
            incident_id="test-inc-1",
            event_type=IncidentEventType.INVESTIGATION_STARTED,
            aggregate_version=4,
            payload={},
        )

        apply_event_to_state(state, event)

        assert state["status"] == "investigating"


class TestApplySuppressed:
    """Tests for incident.suppressed event."""

    def test_suppressed_sets_status_and_reason(self) -> None:
        """SUPPRESSED event sets status to suppressed with reason."""
        state: dict[str, Any] = {"status": "open"}
        event = create_test_event(
            incident_id="test-inc-1",
            event_type=IncidentEventType.SUPPRESSED,
            aggregate_version=2,
            payload={"reason": "noise_reduction"},
        )

        apply_event_to_state(state, event)

        assert state["status"] == "suppressed"
        assert state["suppressed_reason"] == "noise_reduction"


class TestApplyMarkedDuplicate:
    """Tests for incident.marked_duplicate event."""

    def test_marked_duplicate_sets_status_and_duplicate_of(self) -> None:
        """MARKED_DUPLICATE event sets status to duplicate."""
        state: dict[str, Any] = {"status": "open"}
        event = create_test_event(
            incident_id="test-inc-1",
            event_type=IncidentEventType.MARKED_DUPLICATE,
            aggregate_version=2,
            payload={"duplicate_of": "test-inc-other"},
        )

        apply_event_to_state(state, event)

        assert state["status"] == "duplicate"
        assert state["duplicate_of"] == "test-inc-other"


class TestApplyResolved:
    """Tests for incident.resolved event."""

    def test_resolved_sets_status_and_resolved_at(self) -> None:
        """RESOLVED event sets status to resolved."""
        occurred_at = datetime(2024, 1, 1, 15, 0, 0, tzinfo=UTC)
        state: dict[str, Any] = {"status": "investigating"}
        event = create_test_event(
            incident_id="test-inc-1",
            event_type=IncidentEventType.RESOLVED,
            aggregate_version=5,
            payload={"notes": "Fixed by restarting pod"},
            occurred_at=occurred_at,
        )

        apply_event_to_state(state, event)

        assert state["status"] == "resolved"
        assert state["resolved_at"] == "2024-01-01T15:00:00+00:00"
        assert state["resolution_notes"] == "Fixed by restarting pod"


class TestApplyEvidenceAttached:
    """Tests for incident.evidence_attached event."""

    def test_evidence_attached_increments_count(self) -> None:
        """EVIDENCE_ATTACHED increments evidence count."""
        state: dict[str, Any] = {"evidence_count": 1, "evidence_links": []}
        event = create_test_event(
            incident_id="test-inc-1",
            event_type=IncidentEventType.EVIDENCE_ATTACHED,
            aggregate_version=3,
            payload={
                "evidence_count": 2,
                "evidence_links": [
                    {"incident_id": "test-inc-1", "artifact_id": "art-1", "role": "snapshot"}
                ],
            },
        )

        apply_event_to_state(state, event)

        assert state["evidence_count"] == 2
        assert len(state["evidence_links"]) == 1


class TestApplyDiagnosisLoopStarted:
    """Tests for incident.diagnosis_loop_started event."""

    def test_diagnosis_loop_started_sets_diagnosis_loop(self) -> None:
        """DIAGNOSIS_LOOP_STARTED sets diagnosis_loop status to running."""
        occurred_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        state: dict[str, Any] = {}
        event = create_test_event(
            incident_id="test-inc-1",
            event_type=IncidentEventType.DIAGNOSIS_LOOP_STARTED,
            aggregate_version=2,
            payload={
                "run_id": "run-123",
                "collector_run_id": "collector-456",
            },
            occurred_at=occurred_at,
        )

        apply_event_to_state(state, event)

        assert state["diagnosis_loop"]["status"] == "running"
        assert state["diagnosis_loop"]["run_id"] == "run-123"
        assert state["diagnosis_loop"]["collector_run_id"] == "collector-456"
        assert state["diagnosis_loop"]["started_at"] == "2024-01-01T12:00:00+00:00"


class TestApplyDiagnosisLoopCompleted:
    """Tests for incident.diagnosis_loop_completed event."""

    def test_diagnosis_loop_completed_sets_diagnosis_loop(self) -> None:
        """DIAGNOSIS_LOOP_COMPLETED sets diagnosis_loop status to completed."""
        occurred_at = datetime(2024, 1, 1, 12, 30, 0, tzinfo=UTC)
        state: dict[str, Any] = {}
        event = create_test_event(
            incident_id="test-inc-1",
            event_type=IncidentEventType.DIAGNOSIS_LOOP_COMPLETED,
            aggregate_version=3,
            payload={
                "run_id": "run-123",
                "collector_run_id": "collector-456",
                "review_packet_name": "review-packet-1",
                "checks_requested": 5,
                "checks_run": 4,
                "checks_rejected": 1,
                "decision": "run_allowed_read_only_checks",
            },
            occurred_at=occurred_at,
        )

        apply_event_to_state(state, event)

        assert state["diagnosis_loop"]["status"] == "completed"
        assert state["diagnosis_loop"]["run_id"] == "run-123"
        assert state["diagnosis_loop"]["completed_at"] == "2024-01-01T12:30:00+00:00"
        assert state["diagnosis_loop"]["review_packet_name"] == "review-packet-1"
        assert state["diagnosis_loop"]["checks_requested"] == 5
        assert state["diagnosis_loop"]["checks_run"] == 4


class TestApplyDiagnosisLoopFailed:
    """Tests for incident.diagnosis_loop_failed event."""

    def test_diagnosis_loop_failed_sets_diagnosis_loop(self) -> None:
        """DIAGNOSIS_LOOP_FAILED sets diagnosis_loop status to failed."""
        occurred_at = datetime(2024, 1, 1, 12, 30, 0, tzinfo=UTC)
        state: dict[str, Any] = {}
        event = create_test_event(
            incident_id="test-inc-1",
            event_type=IncidentEventType.DIAGNOSIS_LOOP_FAILED,
            aggregate_version=3,
            payload={
                "run_id": "run-123",
                "collector_run_id": "collector-456",
                "unavailable_reason": "cluster_unreachable",
            },
            occurred_at=occurred_at,
        )

        apply_event_to_state(state, event)

        assert state["diagnosis_loop"]["status"] == "failed"
        assert state["diagnosis_loop"]["run_id"] == "run-123"
        assert state["diagnosis_loop"]["failed_at"] == "2024-01-01T12:30:00+00:00"
        assert state["diagnosis_loop"]["unavailable_reason"] == "cluster_unreachable"


class TestApplyImported:
    """Tests for incident.imported event."""

    def test_imported_restores_state(self) -> None:
        """IMPORTED event restores full state from imported incident."""
        state: dict[str, Any] = {}
        event = create_test_event(
            incident_id="test-inc-1",
            event_type=IncidentEventType.IMPORTED,
            aggregate_version=1,
            payload={
                "incident_id": "test-inc-1",
                "namespace": "default",
                "object_kind": "Pod",
                "object_name": "imported-pod",
                "severity": "warning",
                "status": "investigating",
                "signal_count": 3,
                "evidence_count": 2,
            },
        )

        apply_event_to_state(state, event)

        assert state["incident_id"] == "test-inc-1"
        assert state["namespace"] == "default"
        assert state["object_kind"] == "Pod"
        assert state["object_name"] == "imported-pod"
        assert state["severity"] == "warning"
        assert state["status"] == "investigating"
        assert state["signal_count"] == 3
        assert state["evidence_count"] == 2
