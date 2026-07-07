"""Unit tests for incident_diagnosis_auto_loop config and activation.

Tests cover:
- Config/activation tests (disabled by default, enabled via env)
- Eligibility tests (active status, terminal status, budget)

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
from datetime import UTC, datetime

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
from tests.unit.k8s_fake_client import FakeKubernetesReadClient

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

    def test_collector_disabled_by_default(self, monkeypatch: pytest.MonkeyPatch):
        """Prove automatic collector is disabled by default when cluster read fails and env not set."""
        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            if "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]

            # Mock k8s client to raise error (simulating no cluster access)
            fake_client = FakeKubernetesReadClient()  # Returns None for all reads

            monkeypatch.setattr(
                "k8s_diag_agent.collect.incident_diagnosis_loop_gate.get_cached_kubernetes_client",
                lambda **kwargs: fake_client,
            )
            assert is_automatic_diagnosis_loop_enabled() is False
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup
            elif "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]

    def test_collector_enabled_when_env_set(self, monkeypatch: pytest.MonkeyPatch):
        """Prove automatic collector is enabled when env is true."""
        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            # Mock k8s client to return None (env var not in deployment)
            fake_client = FakeKubernetesReadClient()  # Returns None for all reads

            monkeypatch.setattr(
                "k8s_diag_agent.collect.incident_diagnosis_loop_gate.get_cached_kubernetes_client",
                lambda **kwargs: fake_client,
            )

            os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = "true"
            assert is_automatic_diagnosis_loop_enabled() is True
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup
            elif "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]

    def test_collector_enabled_case_insensitive(self, monkeypatch: pytest.MonkeyPatch):
        """Prove collector enabled is case insensitive."""
        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            # Mock k8s client to return None (env var not in deployment)
            fake_client = FakeKubernetesReadClient()

            monkeypatch.setattr(
                "k8s_diag_agent.collect.incident_diagnosis_loop_gate.get_cached_kubernetes_client",
                lambda **kwargs: fake_client,
            )

            os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = "TRUE"
            assert is_automatic_diagnosis_loop_enabled() is True

            os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = "True"
            assert is_automatic_diagnosis_loop_enabled() is True
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup
            elif "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]

    def test_collector_disabled_when_env_false(self, monkeypatch: pytest.MonkeyPatch):
        """Prove collector disabled when env is false."""
        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            # Mock k8s client to return None (env var not in deployment)
            fake_client = FakeKubernetesReadClient()

            monkeypatch.setattr(
                "k8s_diag_agent.collect.incident_diagnosis_loop_gate.get_cached_kubernetes_client",
                lambda **kwargs: fake_client,
            )

            os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = "false"
            assert is_automatic_diagnosis_loop_enabled() is False

            os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = "0"
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
