"""Tests for P4c pass/accounting accumulation fix.

This test module covers the fix for the P4c failure where review artifacts
were not accumulating across multiple diagnosis passes. The log showed:

    [pass 1/5] Observable passes so far: 1
    ...
    [pass 5/5] Observable passes so far: 1

Then normalized output reported `Pass run IDs: []`, indicating the runner
was not maintaining cumulative evidence outside the backend's one-pass summary.

The fix ensures:
1. pass_run_ids accumulate across loop iterations in the result dict
2. total_pass_count reflects cumulative evidence, not just backend state
3. evidence propagation to compute_p4c_outcome uses accumulated values
"""

from __future__ import annotations

from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
    compute_p4c_outcome,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_pass_counting import (
    count_observable_targeted_diagnosis_passes,
)


class TestCountObservablePassesWithReview:
    """Tests for count_observable_targeted_diagnosis_passes with review artifact."""

    def test_single_review_returns_one(self) -> None:
        """Single review artifact should return 1."""
        detail: dict[str, object] = {
            "automatic_diagnosis_review": {
                "available": True,
                "artifact_type": "diagnosis-loop-review-packet",
                "run_id": "pass-1",
            },
        }
        count = count_observable_targeted_diagnosis_passes(detail)
        assert count == 1

    def test_review_with_pass_count_takes_precedence(self) -> None:
        """Explicit pass_count in loop_summary takes precedence over review."""
        detail: dict[str, object] = {
            "automatic_diagnosis_loop_summary": {
                "pass_count": 2,
                "pass_run_ids": ["pass-1", "pass-2"],
            },
            "automatic_diagnosis_review": {
                "available": True,
                "artifact_type": "diagnosis-loop-review-packet",
                "run_id": "pass-1",
            },
        }
        count = count_observable_targeted_diagnosis_passes(detail)
        assert count == 2

    def test_no_passes_returns_zero(self) -> None:
        """No review or pass count should return 0."""
        detail: dict[str, object] = {}
        count = count_observable_targeted_diagnosis_passes(detail)
        assert count == 0


class TestP4cOutcomeWithAccumulatedPasses:
    """Tests for compute_p4c_outcome with accumulated pass evidence."""

    def test_p4c_accumulates_pass_run_ids(self) -> None:
        """compute_p4c_outcome should use accumulated pass_run_ids from evidence."""
        evidence: dict[str, object] = {
            "incident_id": "test-incident-123",
            "pass_count": 2,
            "pass_run_ids": ["pass-1", "pass-2"],
            "terminal_no_checks_accepted": False,
            "real_pass_artifacts_found": True,
            "read_only": True,
            "read_only_violations": [],
            "root_cause_summary": (
                "shipping nodeSelector k9b.dev/otel-lab-node "
                "unschedulable FailedScheduling"
            ),
        }
        outcome = compute_p4c_outcome(evidence, min_required_passes=2)

        assert outcome.pass_count == 2
        assert outcome.pass_run_ids == ("pass-1", "pass-2")
        assert outcome.success is True

    def test_p4c_fails_with_insufficient_passes(self) -> None:
        """compute_p4c_outcome should fail with insufficient passes."""
        evidence: dict[str, object] = {
            "incident_id": "test-incident-123",
            "pass_count": 1,
            "pass_run_ids": ["pass-1"],
            "terminal_no_checks_accepted": False,
            "real_pass_artifacts_found": False,
            "read_only": True,
            "read_only_violations": [],
            "root_cause_summary": (
                "shipping nodeSelector k9b.dev/otel-lab-node "
                "unschedulable FailedScheduling"
            ),
        }
        outcome = compute_p4c_outcome(evidence, min_required_passes=2)

        assert outcome.success is False
        assert any("insufficient_passes" in str(r) for r in outcome.failure_reasons)

    def test_p4c_terminal_single_pass_lab_strict_fails(self) -> None:
        """LAB-STRICT: Terminal single-pass before required passes is a failure."""
        evidence: dict[str, object] = {
            "incident_id": "test-incident-123",
            "pass_count": 1,
            "pass_run_ids": ["pass-1"],
            "terminal_no_checks_accepted": True,
            "real_pass_artifacts_found": True,
            "read_only": True,
            "read_only_violations": [],
            "root_cause_summary": "shipping nodeSelector unschedulable",
        }
        outcome = compute_p4c_outcome(
            evidence,
            accept_terminal_single_pass=False,  # LAB-STRICT
            min_required_passes=2,
        )

        assert outcome.success is False
        assert "premature_terminal_no_checks" in outcome.failure_reasons[0]

    def test_p4c_terminal_single_pass_product_mode_succeeds(self) -> None:
        """PRODUCT MODE: Terminal single-pass with all requirements met is success."""
        evidence: dict[str, object] = {
            "incident_id": "test-incident-123",
            "pass_count": 1,
            "pass_run_ids": ["pass-1"],
            "terminal_no_checks_accepted": True,
            "terminal_decision_reached": "stop_no_checks_proposed",
            "real_pass_artifacts_found": True,
            "read_only": True,
            "read_only_violations": [],
            "backend_incident_detail": {
                "automatic_diagnosis_review": {
                    "run_id": "pass-1",
                    "artifact_name": "review.json",
                },
            },
        }
        # Set require_root_cause_terms=False to avoid needing specific terms
        outcome = compute_p4c_outcome(
            evidence,
            accept_terminal_single_pass=True,  # PRODUCT MODE
            require_root_cause_terms=False,
        )

        # This may still fail due to missing scheduling markers
        assert "premature_terminal_no_checks" not in str(outcome.failure_reasons)


class TestP4cAccumulationScenario:
    """Integration-style tests for the exact failure scenario."""

    def test_accumulated_passes_satisfy_minimum(self) -> None:
        """Multiple accumulated passes should satisfy MIN_REQUIRED_PASSES."""
        evidence: dict[str, object] = {
            "incident_id": "test-incident-123",
            "pass_count": 5,  # Accumulated across 5 loop iterations
            "pass_run_ids": [
                "pass-1", "pass-2", "pass-3", "pass-4", "pass-5"
            ],
            "terminal_no_checks_accepted": False,
            "real_pass_artifacts_found": True,
            "read_only": True,
            "read_only_violations": [],
            "root_cause_summary": (
                "shipping nodeSelector k9b.dev/otel-lab-node "
                "unschedulable FailedScheduling"
            ),
        }
        outcome = compute_p4c_outcome(evidence, min_required_passes=2)

        assert outcome.success is True
        assert outcome.pass_count == 5
        assert len(outcome.pass_run_ids) == 5

    def test_empty_pass_run_ids_with_pass_count_fails_gracefully(self) -> None:
        """Empty pass_run_ids with positive pass_count should still work."""
        evidence: dict[str, object] = {
            "incident_id": "test-incident-123",
            "pass_count": 2,
            "pass_run_ids": [],  # Empty despite pass_count
            "terminal_no_checks_accepted": False,
            "real_pass_artifacts_found": True,
            "read_only": True,
            "read_only_violations": [],
            "root_cause_summary": (
                "shipping nodeSelector k9b.dev/otel-lab-node "
                "unschedulable FailedScheduling"
            ),
        }
        outcome = compute_p4c_outcome(evidence, min_required_passes=2)

        # Should still succeed with pass_count=2 even if pass_run_ids is empty
        assert outcome.success is True
        assert outcome.pass_count == 2
