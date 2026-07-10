"""Unit tests for incident_diagnosis_auto_loop run behavior.

Tests cover:
- Run tests (collector behavior, orchestrator wiring)
- Safety tests (no forbidden imports)
- Event emission integration tests

These tests do NOT:
- Execute real Kubernetes collectors
- Call kubectl/helm/subprocess/shell (properly mocked)
- Perform remediation or mutation

Architecture note:
    After ACT-K9B-K8S-CLIENT-TEST-HARNESS-UPDATE01, these tests mock
    get_cached_kubernetes_client() instead of subprocess.run since production
    code now uses the Kubernetes Python client boundary.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from k8s_diag_agent.collect.incident_diagnosis_auto_loop import (
    AutomaticDiagnosisLoopConfig,
    collect_automatic_diagnosis_evidence,
    run_automatic_diagnosis_loop_evidence_collection,
)
from tests.unit.k8s_fake_client import FakeKubernetesReadClient

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def temp_external_dir():
    """Provide a temporary directory for artifact writing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


# =============================================================================
# Run Tests
# =============================================================================


class TestCollectorRun:
    """Tests for collector run behavior."""

    def test_disabled_collector_returns_early(
        self, temp_external_dir, monkeypatch: pytest.MonkeyPatch
    ):
        """Prove disabled collector returns without processing."""
        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            if "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]

            # Mock k8s client to return None (env var not in deployment)
            fake_client = FakeKubernetesReadClient()

            monkeypatch.setattr(
                "k8s_diag_agent.collect.incident_diagnosis_loop_gate.get_cached_kubernetes_client",
                lambda **kwargs: fake_client,
            )

            result = run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=temp_external_dir,
            )
            assert result.enabled is False
            assert result.incidents_processed == 0
            assert len(result.incident_results) == 1
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup

    def test_disabled_collector_does_not_run_checks(
        self, temp_external_dir, monkeypatch: pytest.MonkeyPatch
    ):
        """Prove disabled collector does not run checks."""
        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            # Ensure env is false or not set
            if "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]

            # Mock k8s client to return None (env var not in deployment)
            fake_client = FakeKubernetesReadClient()

            monkeypatch.setattr(
                "k8s_diag_agent.collect.incident_diagnosis_loop_gate.get_cached_kubernetes_client",
                lambda **kwargs: fake_client,
            )

            result = run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=temp_external_dir,
            )
            assert result.enabled is False
            assert result.incidents_processed == 0
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup

    def test_disabled_collector_does_not_write_packets(
        self, temp_external_dir, monkeypatch: pytest.MonkeyPatch
    ):
        """Prove disabled collector does not write evidence packets."""
        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            # Ensure env is false or not set
            if "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]

            # Mock k8s client to return None (env var not in deployment)
            fake_client = FakeKubernetesReadClient()

            monkeypatch.setattr(
                "k8s_diag_agent.collect.incident_diagnosis_loop_gate.get_cached_kubernetes_client",
                lambda **kwargs: fake_client,
            )

            result = run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=temp_external_dir,
            )
            assert result.total_review_packets_written == 0
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup

    def test_enabled_collector_with_no_incidents(
        self, temp_external_dir, monkeypatch: pytest.MonkeyPatch
    ):
        """Prove enabled collector handles no incidents gracefully."""
        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            # Mock k8s client to return None (env var not in deployment)
            fake_client = FakeKubernetesReadClient()

            monkeypatch.setattr(
                "k8s_diag_agent.collect.incident_diagnosis_loop_gate.get_cached_kubernetes_client",
                lambda **kwargs: fake_client,
            )

            os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = "true"

            result = run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=temp_external_dir,
            )
            assert result.enabled is True
            assert result.incidents_processed == 0
            assert result.incidents_eligible == 0
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup
            elif "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]

    def test_enabled_collector_processes_specific_incidents(
        self, temp_external_dir, monkeypatch: pytest.MonkeyPatch
    ):
        """Prove enabled collector processes specific incident IDs."""
        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            # Mock k8s client to return None (env var not in deployment)
            fake_client = FakeKubernetesReadClient()

            monkeypatch.setattr(
                "k8s_diag_agent.collect.incident_diagnosis_loop_gate.get_cached_kubernetes_client",
                lambda **kwargs: fake_client,
            )

            os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = "true"

            result = run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=temp_external_dir,
                incident_ids=["test-incident"],
            )
            assert result.enabled is True
            assert result.incidents_processed == 1
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup
            elif "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]

    def test_collector_respects_max_incidents(
        self, temp_external_dir, monkeypatch: pytest.MonkeyPatch
    ):
        """Prove collector respects max_incidents_per_run bound for explicit IDs.

        Regression test for explicit-ID path honoring max_incidents_per_run.
        When incident_ids are explicitly provided, the loop should process
        at most max_incidents_per_run, not scan_bound (3x for starvation fix).
        """
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_models import (
            AutoLoopIncidentResult,
        )

        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            # Mock k8s client to return None (env var not in deployment)
            fake_client = FakeKubernetesReadClient()

            monkeypatch.setattr(
                "k8s_diag_agent.collect.incident_diagnosis_loop_gate.get_cached_kubernetes_client",
                lambda **kwargs: fake_client,
            )

            os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = "true"

            # Track actual processed IDs to verify the bound is respected
            processed_ids: list[str] = []

            def fake_process_incident(**kwargs):
                processed_ids.append(kwargs["incident_id"])
                return AutoLoopIncidentResult(
                    incident_id=kwargs["incident_id"],
                    eligible=False,
                    eligibility_reason="not_found",
                    skipped=True,
                    skip_reason="incident_not_found",
                )

            monkeypatch.setattr(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection._process_incident",
                fake_process_incident,
            )

            config = AutomaticDiagnosisLoopConfig(max_incidents_per_run=1)
            result = run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=temp_external_dir,
                incident_ids=["inc1", "inc2", "inc3"],  # 3 incidents
                config=config,
            )
            # Explicit IDs should be bounded by max_incidents_per_run, not scan_bound
            assert processed_ids == ["inc1"], f"Expected only inc1, got {processed_ids}"
            assert result.incidents_processed == 1, f"Expected 1 processed, got {result.incidents_processed}"
            assert result.incidents_skipped == 1, f"Expected 1 skipped, got {result.incidents_skipped}"
            assert len(result.incident_results) == 1, f"Expected 1 result, got {len(result.incident_results)}"
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup
            elif "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]


class TestCollectAutomaticDiagnosisEvidence:
    """Tests for single-incident convenience function."""

    def test_disabled_collector_returns_skipped(
        self, temp_external_dir, monkeypatch: pytest.MonkeyPatch
    ):
        """Prove convenience function respects disabled state."""
        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            if "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]

            # Mock k8s client to return None (env var not in deployment)
            fake_client = FakeKubernetesReadClient()

            monkeypatch.setattr(
                "k8s_diag_agent.collect.incident_diagnosis_loop_gate.get_cached_kubernetes_client",
                lambda **kwargs: fake_client,
            )

            result = collect_automatic_diagnosis_evidence(
                incident_id="test-incident",
                external_analysis_dir=temp_external_dir,
            )
            assert result.skipped is True
            assert "not set to true" in result.skip_reason or "disabled" in result.skip_reason
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup


# =============================================================================
# Safety Tests
# =============================================================================


class TestSafetyMetadata:
    """Tests for safety metadata in results."""

    def test_collector_result_has_safety_metadata(
        self, temp_external_dir
    ):
        """Prove collector result includes safety metadata."""
        result = run_automatic_diagnosis_loop_evidence_collection(
            external_analysis_dir=temp_external_dir,
        )
        assert "read_only" in result.safety_metadata
        assert result.safety_metadata["read_only"] is True
        assert "no_kubectl" in result.safety_metadata
        assert result.safety_metadata["no_kubectl"] is True
        assert "no_shell" in result.safety_metadata
        assert result.safety_metadata["no_shell"] is True
        assert "no_remediation" in result.safety_metadata
        assert result.safety_metadata["no_remediation"] is True

    def test_incident_result_has_no_action_fields(
        self, temp_external_dir
    ):
        """Prove incident result does not contain action-control fields."""
        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = "true"

            result = run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=temp_external_dir,
                incident_ids=["test-incident"],
            )

            if result.incident_results:
                for ir in result.incident_results:
                    assert "run" not in ir
                    assert "execute" not in ir
                    assert "remediate" not in ir
                    assert "mutate" not in ir
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup
            elif "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]


# =============================================================================
# Event Emission Integration Tests
# =============================================================================


class TestDiagnosisLoopEventEmission:
    """Tests proving diagnosis loop events are emitted by the auto loop."""

    def test_eligible_incident_emits_started_event(
        self, temp_external_dir
    ):
        """Prove eligible incident causes DIAGNOSIS_LOOP_STARTED event."""
        from datetime import UTC, datetime

        from k8s_diag_agent.collect.incident_events import IncidentEventType
        from k8s_diag_agent.collect.incident_store import IncidentStore
        from k8s_diag_agent.collect.incident_store_provider import set_incident_store
        from tests.unit.incident_store_fixtures import make_candidate

        # Create a test incident via promote_candidates (standard pattern)
        store = IncidentStore()
        candidate = make_candidate(name="test-pod")
        incidents = store.promote_candidates([candidate], datetime.now(UTC))
        assert len(incidents) == 1
        incident_id = incidents[0].incident_id

        # Ensure incident has evidence link (so it's eligible for auto loop)
        # Use store method to transition to COLLECTING_EVIDENCE
        store.mark_collecting_evidence(incident_id, bundle_id="test-bundle-001")

        set_incident_store(store)

        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = "true"

            # Run the auto loop
            _result = run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=temp_external_dir,
                incident_ids=[incident_id],
            )

            # Verify events were emitted
            updated = store.get_incident(incident_id)
            assert updated is not None

            event_types = [e.event_type for e in updated.events]
            assert IncidentEventType.DIAGNOSIS_LOOP_STARTED in event_types, (
                f"Expected DIAGNOSIS_LOOP_STARTED event, got events: {event_types}"
            )
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup
            elif "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]
            # Reset store
            set_incident_store(None)

    def test_eligible_incident_emits_completed_event(
        self, temp_external_dir
    ):
        """Prove eligible incident causes DIAGNOSIS_LOOP_COMPLETED event."""
        from datetime import UTC, datetime

        from k8s_diag_agent.collect.incident_events import IncidentEventType
        from k8s_diag_agent.collect.incident_store import IncidentStore
        from k8s_diag_agent.collect.incident_store_provider import set_incident_store
        from tests.unit.incident_store_fixtures import make_candidate

        # Create a test incident via promote_candidates (eligible per system criteria)
        store = IncidentStore()
        candidate = make_candidate(name="test-pod")
        incidents = store.promote_candidates([candidate], datetime.now(UTC))
        assert len(incidents) == 1
        incident_id = incidents[0].incident_id

        # Ensure incident has evidence link (so it's eligible for auto loop)
        # Use store method to transition to COLLECTING_EVIDENCE
        store.mark_collecting_evidence(incident_id, bundle_id="test-bundle-001")

        set_incident_store(store)

        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = "true"

            # Run the auto loop
            _result = run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=temp_external_dir,
                incident_ids=[incident_id],
            )

            # Verify events were emitted including COMPLETED
            updated = store.get_incident(incident_id)
            assert updated is not None

            event_types = [e.event_type for e in updated.events]
            assert IncidentEventType.DIAGNOSIS_LOOP_STARTED in event_types
            assert IncidentEventType.DIAGNOSIS_LOOP_COMPLETED in event_types
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup
            elif "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]
            # Reset store
            set_incident_store(None)
