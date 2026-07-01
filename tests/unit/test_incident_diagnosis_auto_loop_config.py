"""Unit tests for incident_diagnosis_auto_loop config and activation.

Tests cover:
- Config/activation tests (disabled by default, enabled via env)
- Eligibility tests (active status, terminal status, budget)

These tests do NOT:
- Execute real Kubernetes collectors
- Call kubectl/helm/subprocess/shell (properly mocked)
- Perform remediation or mutation
"""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
    _ACTIVE_STATUSES,
    _TERMINAL_STATUSES,
    AutomaticDiagnosisLoopConfig,
    check_incident_eligibility,
    is_automatic_diagnosis_loop_enabled,
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
        """Prove automatic collector is disabled by default when cluster read fails and env not set."""
        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            if "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]

            # Mock kubectl to fail (simulating no cluster access)
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = type(
                    "MockResult",
                    (),
                    {"returncode": 1, "stderr": "connection refused"},
                )()
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

            # Mock kubectl to fail (simulating no cluster access)
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = type(
                    "MockResult",
                    (),
                    {"returncode": 1, "stderr": "connection refused"},
                )()
                assert is_automatic_diagnosis_loop_enabled() is False

            os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = "0"

            with patch("subprocess.run") as mock_run:
                mock_run.return_value = type(
                    "MockResult",
                    (),
                    {"returncode": 1, "stderr": "connection refused"},
                )()
                assert is_automatic_diagnosis_loop_enabled() is False
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup
            elif "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]


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


class TestBudgetDiscoveryParity:
    """Regression tests for budget artifact discovery parity between backend and lab helper.
    
    Bug: Backend used iterdir() to count review packets, missing artifacts in nested paths.
    Lab helper used rglob(). This caused backend to report budget_exhausted while lab reset
    reported 0 artifacts, leading to contradictory state.
    
    Fix: Backend now uses rglob() to match lab helper behavior.
    """

    def test_eligibility_discovers_nested_review_packets(
        self,
        clean_store: None,
        sample_open_incident: Incident,
        temp_external_dir: Path,
    ) -> None:
        """Prove eligibility check discovers review packets in nested directories.
        
        This is the regression test for the iterdir() vs rglob() bug.
        The backend must use rglob to find artifacts in nested paths like:
        - phase4-diagnosis/p4c-k8s-multipass-diagnosis/auto-{incident_id}-*-review-packet.json
        """
        incident_id = sample_open_incident.incident_id
        
        # Create nested artifact structure like P4c writes
        nested_dir = temp_external_dir / 'phase4-diagnosis' / 'p4c-k8s-multipass-diagnosis'
        nested_dir.mkdir(parents=True, exist_ok=True)
        
        # Create artifact in nested path (simulates P4c behavior)
        artifact_name = f'auto-{incident_id}-20260107-123456-abc123-diagnosis-review-packet.json'
        (nested_dir / artifact_name).write_text('{"test": true}')
        
        # Check eligibility - must find nested artifact
        config = AutomaticDiagnosisLoopConfig()
        result = check_incident_eligibility(incident_id, config, temp_external_dir)
        
        assert result.eligible is False, (
            'Expected ineligible due to budget exhaustion, got eligible. '
            'Backend must use rglob to find nested review packets.'
        )
        assert result.reason == 'budget_exhausted', (
            f'Expected budget_exhausted, got {result.reason}'
        )
        assert result.auto_pass_count == 1, (
            f'Expected 1 auto_pass_count (nested artifact), got {result.auto_pass_count}. '
            f'Backend must use rglob to find nested review packets.'
        )
        
        # Verify budget diagnostics show correct count
        assert len(result.budget_diagnostics) == 1
        diag = result.budget_diagnostics[0]
        assert diag.name == 'review_packet_budget'
        assert diag.used == 1
        assert diag.limit == 1
        assert diag.exhausted is True
        assert diag.source == 'review_packet_artifacts'
        assert diag.resettable is True

    def test_eligibility_counts_all_review_packets_including_top_level(
        self,
        clean_store: None,
        sample_open_incident: Incident,
        temp_external_dir: Path,
    ) -> None:
        """Prove eligibility counts both nested and top-level review packets."""
        incident_id = sample_open_incident.incident_id
        
        # Create both nested and top-level artifacts
        nested_dir = temp_external_dir / 'phase4-diagnosis' / 'p4c-k8s-multipass-diagnosis'
        nested_dir.mkdir(parents=True, exist_ok=True)
        
        (nested_dir / f'auto-{incident_id}-20260107-001-diagnosis-review-packet.json').write_text('{}')
        (temp_external_dir / f'auto-{incident_id}-20260107-002-diagnosis-review-packet.json').write_text('{}')
        
        config = AutomaticDiagnosisLoopConfig()
        result = check_incident_eligibility(incident_id, config, temp_external_dir)
        
        assert result.auto_pass_count == 2, (
            f'Expected 2 artifacts (nested + top-level), got {result.auto_pass_count}'
        )
        assert result.budget_diagnostics[0].used == 2




    def test_backend_counts_what_lab_reset_removes(
        self,
        clean_store: None,
        sample_open_incident: Incident,
        temp_external_dir: Path,
    ) -> None:
        """End-to-end parity test: backend counts == lab reset removes.
        
        This is the critical regression test that proves the core invariant:
        - write artifact in P4c nested layout
        - check_incident_eligibility() => budget_exhausted used=1
        - reset_diagnosis_loop_budget()
        - check_incident_eligibility() => eligible / used=0
        
        This catches the class of bug where backend and lab helper disagree
        on what constitutes a budget artifact.
        """
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_budget_reset import (
            get_budget_status,
            reset_diagnosis_loop_budget,
        )
        
        incident_id = sample_open_incident.incident_id
        
        # Create nested artifact structure like P4c writes
        nested_dir = temp_external_dir / 'phase4-diagnosis' / 'p4c-k8s-multipass-diagnosis'
        nested_dir.mkdir(parents=True, exist_ok=True)
        
        # Write artifact in P4c nested layout
        artifact_name = f'auto-{incident_id}-20260107-123456-abc123-diagnosis-review-packet.json'
        (nested_dir / artifact_name).write_text('{"test": true}')
        
        # Step 1: Backend eligibility should report budget_exhausted
        config = AutomaticDiagnosisLoopConfig()
        result_before = check_incident_eligibility(incident_id, config, temp_external_dir)
        assert result_before.eligible is False, (
            'Backend should report budget_exhausted for nested artifact'
        )
        assert result_before.reason == 'budget_exhausted'
        assert result_before.auto_pass_count == 1
        
        # Step 2: Lab helper status should also see the artifact
        status_before = get_budget_status(temp_external_dir, incident_id)
        assert status_before['review_packet_count'] == 1, (
            'Lab helper should see the nested artifact'
        )
        
        # Step 3: Lab reset should remove the artifact
        removed = reset_diagnosis_loop_budget(temp_external_dir, incident_id)
        assert removed == 1, f'Lab reset should remove 1 artifact, got {removed}'
        
        # Step 4: Backend eligibility should now be eligible
        result_after = check_incident_eligibility(incident_id, config, temp_external_dir)
        assert result_after.eligible is True, (
            'Backend should report eligible after reset'
        )
        assert result_after.auto_pass_count == 0
        
        # Step 5: Lab helper status should also be clean
        status_after = get_budget_status(temp_external_dir, incident_id)
        assert status_after['review_packet_count'] == 0, (
            'Lab helper should see 0 artifacts after reset'
        )

