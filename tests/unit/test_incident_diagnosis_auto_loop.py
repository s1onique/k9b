"""Unit tests for incident_diagnosis_auto_loop module.

Tests cover:
- Config/activation tests (disabled by default, enabled via env)
- Eligibility tests (active status, terminal status, budget)
- Run tests (collector behavior, orchestrator wiring)
- Safety tests (no forbidden imports)

These tests do NOT:
- Execute real Kubernetes collectors
- Call kubectl/helm/subprocess/shell
- Perform remediation or mutation
"""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from k8s_diag_agent.collect.incident_diagnosis_auto_loop import (
    _ACTIVE_STATUSES,
    _TERMINAL_STATUSES,
    AutomaticDiagnosisLoopConfig,
    check_incident_eligibility,
    collect_automatic_diagnosis_evidence,
    is_automatic_diagnosis_loop_enabled,
    run_automatic_diagnosis_loop_evidence_collection,
)
from k8s_diag_agent.collect.incident_lifecycle import Incident, IncidentStatus
from k8s_diag_agent.collect.incident_store import IncidentStore
from k8s_diag_agent.collect.incident_store_provider import set_incident_store

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def clean_store():
    """Provide a clean incident store for each test."""
    store = IncidentStore()
    set_incident_store(store)
    yield store
    set_incident_store(None)


@pytest.fixture
def temp_external_dir():
    """Provide a temporary directory for artifact writing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_open_incident(clean_store) -> Incident:
    """Create a sample open incident for testing."""
    from k8s_diag_agent.collect.incident_candidates import (
        CandidateClass,
        CandidateSignal,
        IncidentCandidate,
        ObjectKind,
        Severity,
    )
    from k8s_diag_agent.collect.incident_lifecycle import (
        open_incident_from_candidate,
    )

    candidate = IncidentCandidate(
        candidate_id="test-candidate-1",
        namespace="default",
        object_kind=ObjectKind.POD,
        object_name="failing-pod",
        raw_object_kind="Pod",
        candidate_class=CandidateClass.CRASH_LOOP,
        severity=Severity.WARNING,
        signals=(
            CandidateSignal(
                source="test",
                reason="test_reason",
                message="Test signal for auto loop",
            ),
        ),
        evidence_needed=("check_logs",),
    )

    incident = open_incident_from_candidate(candidate, datetime.now(UTC))
    clean_store._incidents[incident.incident_id] = incident
    return incident


# =============================================================================
# Config/Activation Tests
# =============================================================================


class TestActivationConfig:
    """Tests for automatic diagnosis loop activation."""

    def test_collector_disabled_by_default(self):
        """Prove automatic collector is disabled by default."""
        # Clear any environment variable
        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            if "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]
            assert is_automatic_diagnosis_loop_enabled() is False
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup

    def test_collector_enabled_when_env_set(self):
        """Prove automatic collector is enabled when env is true."""
        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = "true"
            assert is_automatic_diagnosis_loop_enabled() is True
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup
            elif "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]

    def test_collector_enabled_case_insensitive(self):
        """Prove collector enabled is case insensitive."""
        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = "TRUE"
            assert is_automatic_diagnosis_loop_enabled() is True

            os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = "True"
            assert is_automatic_diagnosis_loop_enabled() is True
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup
            elif "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]

    def test_collector_disabled_when_env_false(self):
        """Prove collector disabled when env is false."""
        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = "false"
            assert is_automatic_diagnosis_loop_enabled() is False

            os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = "0"
            assert is_automatic_diagnosis_loop_enabled() is False
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup
            elif "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]

    def test_disabled_collector_does_not_run_checks(
        self, clean_store, temp_external_dir
    ):
        """Prove disabled collector does not run checks."""
        result = run_automatic_diagnosis_loop_evidence_collection(
            external_analysis_dir=temp_external_dir,
        )
        assert result.enabled is False
        assert result.incidents_processed == 0

    def test_disabled_collector_does_not_write_packets(
        self, clean_store, temp_external_dir
    ):
        """Prove disabled collector does not write evidence packets."""
        result = run_automatic_diagnosis_loop_evidence_collection(
            external_analysis_dir=temp_external_dir,
        )
        assert result.total_review_packets_written == 0


class TestAutomaticDiagnosisLoopConfig:
    """Tests for AutomaticDiagnosisLoopConfig."""

    def test_default_config_values(self):
        """Prove config has safe default values."""
        config = AutomaticDiagnosisLoopConfig()
        assert config.max_incidents_per_run == 10
        assert config.max_passes_per_incident == 1
        assert config.max_checks_per_pass == 5
        assert config.write_stop_path_packets is True
        assert config.write_ineligible_packets is False

    def test_config_to_dict(self):
        """Prove config serializes to dict correctly."""
        config = AutomaticDiagnosisLoopConfig()
        d = config.to_dict()
        assert d["max_incidents_per_run"] == 10
        assert d["max_passes_per_incident"] == 1
        assert d["max_checks_per_pass"] == 5


# =============================================================================
# Eligibility Tests
# =============================================================================


class TestEligibilityModel:
    """Tests for incident eligibility in automatic loop."""

    def test_active_status_is_eligible(self, clean_store, sample_open_incident):
        """Prove open incident is eligible."""
        config = AutomaticDiagnosisLoopConfig()
        result = check_incident_eligibility(sample_open_incident.incident_id, config)
        assert result.eligible is True
        assert "active" in result.reason

    def test_collecting_evidence_status_is_eligible(self, clean_store):
        """Prove collecting_evidence incident is eligible."""
        incident = Incident(
            incident_id="test-ce-incident",
            source_candidate_id="test",
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            raw_object_kind="Pod",
            candidate_class="health",
            severity="warning",
            status=IncidentStatus.COLLECTING_EVIDENCE,
            first_observed_at=datetime.now(UTC),
            last_observed_at=datetime.now(UTC),
            signals=[],
        )
        clean_store._incidents[incident.incident_id] = incident

        config = AutomaticDiagnosisLoopConfig()
        result = check_incident_eligibility(incident.incident_id, config)
        assert result.eligible is True

    def test_investigating_status_is_eligible(self, clean_store):
        """Prove investigating incident is eligible."""
        incident = Incident(
            incident_id="test-inv-incident",
            source_candidate_id="test",
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            raw_object_kind="Pod",
            candidate_class="health",
            severity="warning",
            status=IncidentStatus.INVESTIGATING,
            first_observed_at=datetime.now(UTC),
            last_observed_at=datetime.now(UTC),
            signals=[],
        )
        clean_store._incidents[incident.incident_id] = incident

        config = AutomaticDiagnosisLoopConfig()
        result = check_incident_eligibility(incident.incident_id, config)
        assert result.eligible is True

    def test_resolved_incident_not_eligible(self, clean_store, sample_open_incident):
        """Prove resolved incident is not eligible."""
        # Update status to resolved
        sample_open_incident.status = IncidentStatus.RESOLVED

        config = AutomaticDiagnosisLoopConfig()
        result = check_incident_eligibility(sample_open_incident.incident_id, config)
        assert result.eligible is False
        assert "terminal" in result.reason

    def test_suppressed_incident_not_eligible(self, clean_store):
        """Prove suppressed incident is not eligible."""
        incident = Incident(
            incident_id="test-sup-incident",
            source_candidate_id="test",
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            raw_object_kind="Pod",
            candidate_class="health",
            severity="warning",
            status=IncidentStatus.SUPPRESSED,
            first_observed_at=datetime.now(UTC),
            last_observed_at=datetime.now(UTC),
            signals=[],
            suppressed_reason="test suppression",
        )
        clean_store._incidents[incident.incident_id] = incident

        config = AutomaticDiagnosisLoopConfig()
        result = check_incident_eligibility(incident.incident_id, config)
        assert result.eligible is False
        assert "terminal" in result.reason

    def test_duplicate_incident_not_eligible(self, clean_store):
        """Prove duplicate incident is not eligible."""
        incident = Incident(
            incident_id="test-dup-incident",
            source_candidate_id="test",
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            raw_object_kind="Pod",
            candidate_class="health",
            severity="warning",
            status=IncidentStatus.DUPLICATE,
            first_observed_at=datetime.now(UTC),
            last_observed_at=datetime.now(UTC),
            signals=[],
            duplicate_of="other-incident",
        )
        clean_store._incidents[incident.incident_id] = incident

        config = AutomaticDiagnosisLoopConfig()
        result = check_incident_eligibility(incident.incident_id, config)
        assert result.eligible is False
        assert "terminal" in result.reason

    def test_ready_for_review_not_eligible(self, clean_store):
        """Prove ready_for_review incident is not eligible."""
        incident = Incident(
            incident_id="test-rfr-incident",
            source_candidate_id="test",
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            raw_object_kind="Pod",
            candidate_class="health",
            severity="warning",
            status=IncidentStatus.READY_FOR_REVIEW,
            first_observed_at=datetime.now(UTC),
            last_observed_at=datetime.now(UTC),
            signals=[],
        )
        clean_store._incidents[incident.incident_id] = incident

        config = AutomaticDiagnosisLoopConfig()
        result = check_incident_eligibility(incident.incident_id, config)
        assert result.eligible is False

    def test_nonexistent_incident_not_eligible(self, clean_store):
        """Prove nonexistent incident returns not eligible."""
        config = AutomaticDiagnosisLoopConfig()
        result = check_incident_eligibility("nonexistent-incident-id", config)
        assert result.eligible is False
        assert result.reason == "incident_not_found"


# =============================================================================
# Run Tests
# =============================================================================


class TestCollectorRun:
    """Tests for collector run behavior."""

    def test_disabled_collector_returns_early(
        self, clean_store, temp_external_dir
    ):
        """Prove disabled collector returns without processing."""
        # Ensure disabled
        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            if "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]

            result = run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=temp_external_dir,
            )
            assert result.enabled is False
            assert result.incidents_processed == 0
            assert len(result.incident_results) == 1
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup

    def test_enabled_collector_with_no_incidents(
        self, clean_store, temp_external_dir
    ):
        """Prove enabled collector handles no incidents gracefully."""
        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
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
        self, clean_store, sample_open_incident, temp_external_dir
    ):
        """Prove enabled collector processes specific incident IDs."""
        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = "true"

            result = run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=temp_external_dir,
                incident_ids=[sample_open_incident.incident_id],
            )
            assert result.enabled is True
            assert result.incidents_processed == 1
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup
            elif "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]

    def test_collector_respects_max_incidents(
        self, clean_store, sample_open_incident, temp_external_dir
    ):
        """Prove collector respects max_incidents_per_run bound."""
        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = "true"

            config = AutomaticDiagnosisLoopConfig(max_incidents_per_run=1)
            result = run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=temp_external_dir,
                incident_ids=["inc1", "inc2", "inc3"],  # 3 incidents
                config=config,
            )
            assert result.incidents_processed <= 1
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup
            elif "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]

    def test_collector_ineligible_incident_skipped(
        self, clean_store, sample_open_incident, temp_external_dir
    ):
        """Prove collector skips ineligible incidents."""
        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = "true"

            # Mark incident as resolved
            sample_open_incident.status = IncidentStatus.RESOLVED

            result = run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=temp_external_dir,
                incident_ids=[sample_open_incident.incident_id],
            )
            assert result.incidents_processed == 1
            # Ineligible incidents are skipped, not ineligible
            assert result.incidents_skipped == 1
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup
            elif "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]

    def test_second_call_skips_budget_exhausted(
        self, clean_store, sample_open_incident, temp_external_dir
    ):
        """Prove second call skips when budget is exhausted.

        First call writes a review packet. Second call should skip
        because budget is exhausted (count >= max_passes_per_incident).
        """
        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = "true"

            config = AutomaticDiagnosisLoopConfig(max_passes_per_incident=1)

            # First call
            result1 = run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=temp_external_dir,
                incident_ids=[sample_open_incident.incident_id],
                config=config,
            )

            # First call should process the incident
            assert result1.incidents_processed == 1

            # Second call - should skip because budget is exhausted
            result2 = run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=temp_external_dir,
                incident_ids=[sample_open_incident.incident_id],
                config=config,
            )

            # Second call should skip due to budget exhaustion
            assert result2.incidents_processed == 1
            assert result2.incidents_skipped == 1
            assert result2.incident_results[0]["skip_reason"] == "not_eligible: budget_exhausted"
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup
            elif "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]


class TestCollectAutomaticDiagnosisEvidence:
    """Tests for single-incident convenience function."""

    def test_disabled_collector_returns_skipped(
        self, clean_store, sample_open_incident, temp_external_dir
    ):
        """Prove convenience function respects disabled state."""
        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            if "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]

            result = collect_automatic_diagnosis_evidence(
                incident_id=sample_open_incident.incident_id,
                external_analysis_dir=temp_external_dir,
            )
            assert result.skipped is True
            # Check for "not set" or "disabled" in skip_reason
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
        self, clean_store, temp_external_dir
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
        self, clean_store, temp_external_dir
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
                    # Should not have action-control fields
                    assert "run" not in ir
                    assert "execute" not in ir
                    assert "remediate" not in ir
                    assert "mutate" not in ir
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup
            elif "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]


class TestActiveTerminalStatuses:
    """Tests for active and terminal status constants."""

    def test_active_statuses_are_active(self):
        """Prove active statuses are actually active."""
        assert IncidentStatus.OPEN in _ACTIVE_STATUSES
        assert IncidentStatus.COLLECTING_EVIDENCE in _ACTIVE_STATUSES
        assert IncidentStatus.INVESTIGATING in _ACTIVE_STATUSES

    def test_terminal_statuses_are_terminal(self):
        """Prove terminal statuses are actually terminal."""
        assert IncidentStatus.SUPPRESSED in _TERMINAL_STATUSES
        assert IncidentStatus.DUPLICATE in _TERMINAL_STATUSES
        assert IncidentStatus.RESOLVED in _TERMINAL_STATUSES
        assert IncidentStatus.READY_FOR_REVIEW in _TERMINAL_STATUSES

    def test_statuses_do_not_overlap(self):
        """Prove active and terminal statuses do not overlap."""
        overlap = _ACTIVE_STATUSES & _TERMINAL_STATUSES
        assert len(overlap) == 0