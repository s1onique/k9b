"""Tests for gate_checks - pre-execution check rejection.

These tests prove that:
1. Mutating checks are rejected before execution
2. Sensitive reads are rejected before execution
3. Duplicate checks are rejected across passes
"""
from __future__ import annotations

import pytest

from k8s_diag_agent.collect.incident_diagnosis_loop_policy import DiagnosisLoopPolicy
from k8s_diag_agent.collect.runtime_gating import gate_checks

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_policy() -> DiagnosisLoopPolicy:
    """Default policy for testing."""
    return DiagnosisLoopPolicy.live_lab_default()


@pytest.fixture
def permissive_policy() -> DiagnosisLoopPolicy:
    """Permissive policy that allows mutating and sensitive checks."""
    return DiagnosisLoopPolicy(
        max_passes=5,
        max_checks_per_pass=5,
        max_total_checks=15,
        max_model_calls=10,
        max_wall_clock_seconds=300,
        allow_mutating_checks=True,
        allow_sensitive_reads=True,
    )


# =============================================================================
# Mutating Check Rejection Tests
# =============================================================================


class TestMutatingCheckRejection:
    """Tests for mutating check rejection."""

    def test_mutating_check_is_rejected_by_gate(self, sample_policy: DiagnosisLoopPolicy) -> None:
        """Mutating checks are rejected at the gate, before execution."""
        proposed_checks = [
            {"check_id": "kubectl_apply"},
            {"check_id": "kubectl_delete"},
        ]

        seen_fingerprints: set[str] = set()
        gate_summary, accepted_fps = gate_checks(proposed_checks, sample_policy, seen_fingerprints)

        # All mutating checks should be rejected
        assert gate_summary.rejected_mutating == 2
        assert gate_summary.accepted == 0
        assert gate_summary.rejected_duplicate == 0
        assert len(gate_summary.accepted_checks) == 0
        assert len(gate_summary.rejected_checks) == 2

        # Verify the rejected checks have the correct reason
        for rejected in gate_summary.rejected_checks:
            assert rejected.get("rejection_reason") == "mutating_check_rejected"
            assert rejected.get("is_unsafe") is True

    def test_mutating_check_is_not_executed(self, sample_policy: DiagnosisLoopPolicy) -> None:
        """A check that looks mutating is never passed to execution."""
        proposed_checks = [
            {"check_id": "kubectl_apply", "action": "apply"},
        ]

        seen_fingerprints: set[str] = set()
        gate_summary, accepted_fps = gate_checks(proposed_checks, sample_policy, seen_fingerprints)

        # The accepted list should be empty - check never reaches execution
        assert len(gate_summary.accepted_checks) == 0
        assert "kubectl_apply" not in [c.get("check_id") for c in gate_summary.accepted_checks]

    def test_mutating_check_allowed_when_policy_permissive(
        self, permissive_policy: DiagnosisLoopPolicy
    ) -> None:
        """Mutating checks pass gate when policy allows them."""
        proposed_checks = [
            {"check_id": "kubectl_apply"},
        ]

        seen_fingerprints: set[str] = set()
        gate_summary, accepted_fps = gate_checks(proposed_checks, permissive_policy, seen_fingerprints)

        # With permissive policy, mutating checks are accepted
        assert gate_summary.accepted == 1
        assert gate_summary.rejected_mutating == 0
        assert len(gate_summary.accepted_checks) == 1


# =============================================================================
# Sensitive Read Rejection Tests
# =============================================================================


class TestSensitiveReadRejection:
    """Tests for sensitive read check rejection."""

    def test_secret_read_is_rejected_by_gate(self, sample_policy: DiagnosisLoopPolicy) -> None:
        """Secret reads are rejected at the gate, before execution."""
        proposed_checks = [
            {"check_id": "kubectl_get_secrets"},
            {"check_id": "kubectl describe secret"},
        ]

        seen_fingerprints: set[str] = set()
        gate_summary, accepted_fps = gate_checks(proposed_checks, sample_policy, seen_fingerprints)

        # All sensitive reads should be rejected
        assert gate_summary.rejected_sensitive == 2
        assert gate_summary.accepted == 0
        assert len(gate_summary.accepted_checks) == 0
        assert len(gate_summary.rejected_checks) == 2

        # Verify the rejected checks have the correct reason
        for rejected in gate_summary.rejected_checks:
            assert rejected.get("rejection_reason") == "sensitive_read_denied"
            assert rejected.get("is_sensitive") is True

    def test_secret_read_is_not_executed(self, sample_policy: DiagnosisLoopPolicy) -> None:
        """A check that reads secrets is never passed to execution."""
        proposed_checks = [
            {"check_id": "kubectl_get_secrets", "resource": "secrets"},
        ]

        seen_fingerprints: set[str] = set()
        gate_summary, accepted_fps = gate_checks(proposed_checks, sample_policy, seen_fingerprints)

        # The accepted list should be empty - check never reaches execution
        assert len(gate_summary.accepted_checks) == 0
        assert "kubectl_get_secrets" not in [c.get("check_id") for c in gate_summary.accepted_checks]


# =============================================================================
# Duplicate Check Rejection Tests
# =============================================================================


class TestDuplicateCheckRejection:
    """Tests for duplicate check rejection across passes."""

    def test_duplicate_check_is_rejected_on_second_pass(self, sample_policy: DiagnosisLoopPolicy) -> None:
        """Same check fingerprint is rejected on subsequent passes."""
        proposed_checks = [
            {"check_id": "check_1", "title": "Check 1"},
        ]

        # Simulate first pass - check is accepted
        seen_fingerprints: set[str] = set()
        gate_summary_pass1, accepted_fps_pass1 = gate_checks(proposed_checks, sample_policy, seen_fingerprints)

        assert gate_summary_pass1.accepted == 1
        assert len(accepted_fps_pass1) == 1

        # Simulate second pass - same check should be rejected
        gate_summary_pass2, accepted_fps_pass2 = gate_checks(proposed_checks, sample_policy, seen_fingerprints)

        assert gate_summary_pass2.rejected_duplicate == 1
        assert gate_summary_pass2.accepted == 0
        assert len(gate_summary_pass2.accepted_checks) == 0

    def test_seen_fingerprints_persist_across_passes(self, sample_policy: DiagnosisLoopPolicy) -> None:
        """Fingerprints from previous passes persist and cause rejection."""
        # Pass 1
        checks_pass1 = [
            {"check_id": "check_1"},
            {"check_id": "check_2"},
        ]

        seen_fingerprints: set[str] = set()
        gate_summary_pass1, _ = gate_checks(checks_pass1, sample_policy, seen_fingerprints)

        assert gate_summary_pass1.accepted == 2
        assert len(seen_fingerprints) == 2

        # Pass 2
        checks_pass2 = [
            {"check_id": "check_1"},  # Duplicate!
            {"check_id": "check_3"},
        ]

        gate_summary_pass2, _ = gate_checks(checks_pass2, sample_policy, seen_fingerprints)

        assert gate_summary_pass2.accepted == 1  # Only check_3
        assert gate_summary_pass2.rejected_duplicate == 1  # check_1 rejected

        # Pass 3 - verify fingerprints still persisted
        checks_pass3 = [
            {"check_id": "check_1"},  # Still duplicate!
            {"check_id": "check_2"},  # Still duplicate!
            {"check_id": "check_4"},
        ]

        gate_summary_pass3, _ = gate_checks(checks_pass3, sample_policy, seen_fingerprints)

        assert gate_summary_pass3.accepted == 1  # Only check_4
        assert gate_summary_pass3.rejected_duplicate == 2  # check_1 and check_2

    def test_accepted_fingerprints_are_added_to_seen_set(self, sample_policy: DiagnosisLoopPolicy) -> None:
        """Accepted fingerprints are immediately added to seen_fingerprints."""
        proposed_checks = [
            {"check_id": "check_1"},
            {"check_id": "check_2"},
        ]

        seen_fingerprints: set[str] = set()
        gate_summary, accepted_fps = gate_checks(proposed_checks, sample_policy, seen_fingerprints)

        # The seen_fingerprints should be updated immediately
        assert len(seen_fingerprints) == 2
        # Compare as sets since order may vary
        assert set(accepted_fps) == seen_fingerprints


# =============================================================================
# Rejection Reason Documentation
# =============================================================================


class TestRejectionReasons:
    """Tests for documented rejection reasons."""

    def test_all_rejection_reasons_are_documented(self) -> None:
        """All rejection reasons are properly documented."""
        proposed_checks = [
            {"check_id": "kubectl_apply"},  # Mutating
            {"check_id": "kubectl_get_secrets"},  # Sensitive
            {"check_id": "check_1"},  # Duplicate of itself? No, but let's test
        ]

        policy = DiagnosisLoopPolicy(
            allow_mutating_checks=False,
            allow_sensitive_reads=False,
        )

        # First pass - accept check_1
        seen_fingerprints: set[str] = set()
        gate_summary1, _ = gate_checks([proposed_checks[2]], policy, seen_fingerprints)
        assert gate_summary1.accepted == 1

        # Second pass - check_1 is now duplicate
        gate_summary2, _ = gate_checks(proposed_checks, policy, seen_fingerprints)

        # Should have all three rejection types
        rejection_reasons = set()
        for rejected in gate_summary2.rejected_checks:
            rejection_reasons.add(rejected.get("rejection_reason"))

        assert "mutating_check_rejected" in rejection_reasons
        assert "sensitive_read_denied" in rejection_reasons
        assert "duplicate_check_fingerprint" in rejection_reasons

    def test_rejected_checks_never_reach_execution(self) -> None:
        """When a check is rejected by the gate, it never reaches execution."""
        proposed_checks = [
            {"check_id": "kubectl_apply"},  # Mutating - should be rejected
            {"check_id": "check_1"},  # OK - should be accepted
        ]

        policy = DiagnosisLoopPolicy(allow_mutating_checks=False)

        seen_fingerprints: set[str] = set()
        gate_summary, accepted_fps = gate_checks(proposed_checks, policy, seen_fingerprints)

        # The execution list contains ONLY accepted checks
        execution_list = gate_summary.accepted_checks
        
        # kubectl_apply should NOT be in the execution list
        execution_ids = [c.get("check_id") for c in execution_list]
        assert "kubectl_apply" not in execution_ids
        assert "check_1" in execution_ids
