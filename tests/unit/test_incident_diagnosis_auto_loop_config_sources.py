"""Unit tests for incident_diagnosis_auto_loop config - budget discovery parity.

Tests cover:
- Budget artifact discovery parity between backend and lab helper
- Nested path artifact handling
- Backend/lab helper consistency

These tests do NOT:
- Execute real Kubernetes collectors
- Call kubectl/helm/subprocess/shell (properly mocked)
- Perform remediation or mutation
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
    AutomaticDiagnosisLoopConfig,
    check_incident_eligibility,
)
from k8s_diag_agent.collect.incident_lifecycle import Incident
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
# Budget Discovery Parity Tests
# =============================================================================


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
