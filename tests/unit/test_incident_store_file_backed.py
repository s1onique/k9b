"""Unit tests for file-backed incident store.

These tests verify that FileBackedIncidentStore:
1. Persists incidents to JSON file
2. Loads incidents on initialization
3. Shares incidents between multiple store instances
4. Handles corruption gracefully
5. Uses atomic writes
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from k8s_diag_agent.collect.incident_lifecycle import Incident, IncidentStatus
from k8s_diag_agent.collect.incident_store_file import (
    DEFAULT_INCIDENT_STORE_DIR,
    SCHEMA_VERSION,
    FileBackedIncidentStore,
)


# Test fixtures
@pytest.fixture
def tmp_path(tmp_path: Path) -> Path:
    """Create a temporary path for incident store file."""
    store_path = tmp_path / "incident-store.json"
    return store_path


@pytest.fixture
def make_incident() -> Incident:
    """Factory for creating test incidents."""
    def _make_incident(
        incident_id: str,
        namespace: str = "default",
        object_kind: str = "Pod",
        object_name: str = "test-pod",
        status: IncidentStatus = IncidentStatus.OPEN,
    ) -> Incident:
        return Incident(
            incident_id=incident_id,
            source_candidate_id=f"{namespace}-{object_kind}-{object_name}-test",
            namespace=namespace,
            object_kind=object_kind,
            object_name=object_name,
            raw_object_kind=None,
            candidate_class="crash_loop",
            severity="error",
            status=status,
            first_observed_at=datetime.now(UTC),
            last_observed_at=datetime.now(UTC),
            signals=[],
            evidence_needed=[],
            evidence_links=[],
        )
    return _make_incident


class TestFileBackedIncidentStoreBasics:
    """Basic tests for FileBackedIncidentStore."""

    def test_initializes_with_empty_store(self, tmp_path: Path) -> None:
        """Store starts empty when file doesn't exist."""
        store = FileBackedIncidentStore(tmp_path)
        assert len(store) == 0
        assert len(store.list_incidents()) == 0

    def test_stores_incident_and_persists(self, tmp_path: Path, make_incident) -> None:
        """Adding incident persists to file."""
        store = FileBackedIncidentStore(tmp_path)
        incident = make_incident("test-incident-1")

        store.add_incident(incident)

        # File should exist
        assert tmp_path.exists()

        # Should be loadable by new store instance
        new_store = FileBackedIncidentStore(tmp_path)
        assert len(new_store) == 1
        assert new_store.get_incident("test-incident-1") is not None

    def test_lists_incidents(self, tmp_path: Path, make_incident) -> None:
        """List incidents returns all stored incidents."""
        store = FileBackedIncidentStore(tmp_path)
        inc1 = make_incident("inc-1")
        inc2 = make_incident("inc-2")

        store.add_incident(inc1)
        store.add_incident(inc2)

        incidents = store.list_incidents()
        assert len(incidents) == 2
        incident_ids = {i.incident_id for i in incidents}
        assert incident_ids == {"inc-1", "inc-2"}

    def test_gets_incident_by_id(self, tmp_path: Path, make_incident) -> None:
        """Get incident by ID returns correct incident."""
        store = FileBackedIncidentStore(tmp_path)
        incident = make_incident("test-incident-1")
        store.add_incident(incident)

        retrieved = store.get_incident("test-incident-1")
        assert retrieved is not None
        assert retrieved.incident_id == "test-incident-1"

    def test_gets_none_for_missing_incident(self, tmp_path: Path) -> None:
        """Get incident returns None for non-existent ID."""
        store = FileBackedIncidentStore(tmp_path)
        retrieved = store.get_incident("non-existent")
        assert retrieved is None


class TestTwoStoreInstancesShareFileBackedIncidents:
    """Tests for cross-process/file visibility."""

    def test_two_store_instances_share_file_backed_incidents(
        self, tmp_path: Path, make_incident
    ) -> None:
        """Two store instances share incidents via file."""
        # First store (simulates scheduler)
        scheduler_store = FileBackedIncidentStore(tmp_path)
        scheduler_store.add_incident(make_incident("inc-1"))

        # Second store (simulates backend)
        backend_store = FileBackedIncidentStore(tmp_path)

        # Backend can see incident created by scheduler
        assert backend_store.get_incident("inc-1") is not None
        assert len(backend_store.list_incidents()) == 1

    def test_incident_added_by_first_store_visible_to_second_after_reload(
        self, tmp_path: Path, make_incident
    ) -> None:
        """Incident added by first store is visible to second store after reload.

        This tests that when a new store instance is created, it loads incidents
        from the file (simulating backend pod restart or fresh startup).
        """
        store1 = FileBackedIncidentStore(tmp_path)
        store1.add_incident(make_incident("inc-visible"))

        # Simulate backend pod restart - new store instance reloads from file
        store2 = FileBackedIncidentStore(tmp_path)

        # store2 should see it (simulating backend reading scheduler's promotions)
        result = store2.get_incident("inc-visible")
        assert result is not None
        assert result.incident_id == "inc-visible"

    def test_incidents_survive_store_restart(self, tmp_path: Path, make_incident) -> None:
        """Incidents persist across store instance restarts."""
        # First instance
        store1 = FileBackedIncidentStore(tmp_path)
        store1.add_incident(make_incident("inc-persistent"))

        # Simulate restart by creating new instance
        store2 = FileBackedIncidentStore(tmp_path)

        assert store2.get_incident("inc-persistent") is not None
        assert len(store2.list_incidents()) == 1

    def test_new_promotions_merge_with_existing(self, tmp_path: Path, make_incident) -> None:
        """New promotions merge with existing incidents."""
        # First promotion
        store1 = FileBackedIncidentStore(tmp_path)
        store1.add_incident(make_incident("inc-existing"))

        # Simulate restart, then new promotion
        store2 = FileBackedIncidentStore(tmp_path)
        store2.add_incident(make_incident("inc-new"))

        # Both should be visible
        incidents = store2.list_incidents()
        assert len(incidents) == 2
        incident_ids = {i.incident_id for i in incidents}
        assert incident_ids == {"inc-existing", "inc-new"}


class TestAtomicWrites:
    """Tests for atomic write behavior."""

    def test_write_creates_temp_file_then_replaces(self, tmp_path: Path, make_incident) -> None:
        """Atomic write uses temp file pattern."""
        store = FileBackedIncidentStore(tmp_path)
        store.add_incident(make_incident("inc-1"))

        # Should have main file
        assert tmp_path.exists()

        # Should not have temp file
        tmp_file = tmp_path.with_suffix(".json.tmp")
        assert not tmp_file.exists()

    def test_file_content_is_valid_json(self, tmp_path: Path, make_incident) -> None:
        """File content is valid JSON with correct schema."""
        store = FileBackedIncidentStore(tmp_path)
        store.add_incident(make_incident("inc-1"))

        content = tmp_path.read_text(encoding="utf-8")
        data = json.loads(content)

        assert data["schema_version"] == SCHEMA_VERSION
        assert "updated_at" in data
        assert "incidents" in data
        assert len(data["incidents"]) == 1


class TestCorruptionHandling:
    """Tests for handling corrupted files."""

    def test_handles_missing_file_gracefully(self, tmp_path: Path) -> None:
        """Store starts fresh when file is missing."""
        store = FileBackedIncidentStore(tmp_path)
        assert len(store) == 0

    def test_handles_invalid_json_gracefully(self, tmp_path: Path) -> None:
        """Store starts fresh when file contains invalid JSON."""
        tmp_path.write_text("not valid json", encoding="utf-8")

        store = FileBackedIncidentStore(tmp_path)
        assert len(store) == 0

    def test_handles_wrong_schema_version_gracefully(self, tmp_path: Path) -> None:
        """Store starts fresh when schema version doesn't match."""
        data = {
            "schema_version": "wrong.version",
            "updated_at": "2024-01-01T00:00:00Z",
            "incidents": [],
        }
        tmp_path.write_text(json.dumps(data), encoding="utf-8")

        store = FileBackedIncidentStore(tmp_path)
        assert len(store) == 0


class TestFileBackedIncidentStoreMutation:
    """Tests for mutation methods persisting to file."""

    def test_mark_collecting_evidence_persists(self, tmp_path: Path, make_incident) -> None:
        """mark_collecting_evidence persists to file."""
        store = FileBackedIncidentStore(tmp_path)
        incident = make_incident("inc-1")
        store.add_incident(incident)

        store.mark_collecting_evidence("inc-1", "bundle-123")

        # Verify persisted
        new_store = FileBackedIncidentStore(tmp_path)
        retrieved = new_store.get_incident("inc-1")
        assert retrieved is not None
        assert retrieved.latest_snapshot_bundle_id == "bundle-123"

    def test_suppress_persists(self, tmp_path: Path, make_incident) -> None:
        """suppress persists to file."""
        store = FileBackedIncidentStore(tmp_path)
        incident = make_incident("inc-1")
        store.add_incident(incident)

        store.suppress("inc-1", "test suppression")

        # Verify persisted
        new_store = FileBackedIncidentStore(tmp_path)
        retrieved = new_store.get_incident("inc-1")
        assert retrieved is not None
        assert retrieved.status == IncidentStatus.SUPPRESSED
        assert retrieved.suppressed_reason == "test suppression"

    def test_resolve_persists(self, tmp_path: Path, make_incident) -> None:
        """resolve persists to file - requires transitioning through investigating first."""
        store = FileBackedIncidentStore(tmp_path)
        incident = make_incident("inc-1")
        store.add_incident(incident)

        # resolve is only valid from INVESTIGATING status
        # Full path: OPEN -> COLLECTING_EVIDENCE -> READY_FOR_REVIEW -> INVESTIGATING -> RESOLVED
        store.mark_collecting_evidence("inc-1", "bundle-123")
        store.mark_ready_for_review("inc-1")
        store.mark_investigating("inc-1")
        store.resolve("inc-1")

        # Verify persisted
        new_store = FileBackedIncidentStore(tmp_path)
        retrieved = new_store.get_incident("inc-1")
        assert retrieved is not None
        assert retrieved.status == IncidentStatus.RESOLVED
        assert retrieved.resolved_at is not None


class TestDefaultDirectory:
    """Tests for default directory constant."""

    def test_default_directory_is_set(self) -> None:
        """Default incident store directory is defined."""
        assert DEFAULT_INCIDENT_STORE_DIR == "/app/runs/incidents"


class TestStoreKind:
    """Tests for store kind property."""

    def test_store_kind_is_file(self, tmp_path: Path) -> None:
        """FileBackedIncidentStore reports correct store_kind."""
        store = FileBackedIncidentStore(tmp_path)
        assert store.store_kind == "file"


class TestIncidentFromDict:
    """Tests for Incident.from_dict deserialization."""

    def test_roundtrip_serialization(self, tmp_path: Path, make_incident) -> None:
        """Incident can be serialized and deserialized."""
        original = make_incident("roundtrip-test")
        original.signals = list(original.signals)  # Ensure mutable list
        original.evidence_needed = list(original.evidence_needed)

        # Store and reload
        store1 = FileBackedIncidentStore(tmp_path)
        store1.add_incident(original)

        store2 = FileBackedIncidentStore(tmp_path)
        retrieved = store2.get_incident("roundtrip-test")

        assert retrieved is not None
        assert retrieved.incident_id == original.incident_id
        assert retrieved.namespace == original.namespace
        assert retrieved.object_kind == original.object_kind
        assert retrieved.status == original.status


class TestRefreshOnRead:
    """Tests for refresh-on-read pattern (live visibility between processes)."""

    def test_existing_backend_instance_sees_scheduler_write_without_recreation(
        self, tmp_path: Path, make_incident
    ) -> None:
        """Backend store sees scheduler's write without restart.

        This is the critical test for scheduler -> existing backend visibility.
        FileBackedIncidentStore reloads on every read (list_incidents, get_incident),
        so an already-running backend process sees new incidents from scheduler.
        """
        path = tmp_path / "incident-store.json"

        # Backend starts first (simulates already-running backend pod)
        backend_store = FileBackedIncidentStore(path)

        # Scheduler starts later
        scheduler_store = FileBackedIncidentStore(path)

        # Scheduler adds incident
        scheduler_store.add_incident(make_incident("inc-live"))

        # Backend reads - should see scheduler's incident without restart
        result = backend_store.get_incident("inc-live")
        assert result is not None
        assert result.incident_id == "inc-live"

        incidents = backend_store.list_incidents()
        assert len(incidents) == 1
        assert incidents[0].incident_id == "inc-live"

    def test_stale_backend_instance_does_not_overwrite_scheduler_incidents(
        self, tmp_path: Path, make_incident
    ) -> None:
        """Stale backend instance does not overwrite scheduler's incidents.

        This tests merge-before-write pattern: when backend does a write,
        it reloads from file first, so scheduler's incidents are preserved.
        """
        path = tmp_path / "incident-store.json"

        # Backend loads empty (stale view)
        backend_store = FileBackedIncidentStore(path)

        # Scheduler adds incident
        scheduler_store = FileBackedIncidentStore(path)
        scheduler_store.add_incident(make_incident("inc-scheduler"))

        # Backend adds its own incident - should merge, not overwrite
        backend_store.add_incident(make_incident("inc-backend"))

        # Verify both incidents exist in file
        verifier = FileBackedIncidentStore(path)
        incident_ids = {i.incident_id for i in verifier.list_incidents()}
        assert incident_ids == {"inc-scheduler", "inc-backend"}

    def test_multiple_reads_see_latest_file_state(
        self, tmp_path: Path, make_incident
    ) -> None:
        """Multiple reads continue to see latest file state."""
        path = tmp_path / "incident-store.json"
        store = FileBackedIncidentStore(path)

        # Add incident via store1
        store1 = FileBackedIncidentStore(path)
        store1.add_incident(make_incident("inc-1"))

        # First read
        assert len(store.list_incidents()) == 1

        # Add another via store2
        store2 = FileBackedIncidentStore(path)
        store2.add_incident(make_incident("inc-2"))

        # Second read - should see both incidents
        assert len(store.list_incidents()) == 2
        incident_ids = {i.incident_id for i in store.list_incidents()}
        assert incident_ids == {"inc-1", "inc-2"}
