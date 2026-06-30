"""Tests for next-check planner command rejection (unknown commands, vague suggestions)."""

from __future__ import annotations

from pathlib import Path

from k8s_diag_agent.external_analysis.next_check_planner import (
    ApprovalReason,
    BlockingReason,
    CommandFamily,
    SafetyReason,
    plan_next_checks,
)
from tests.helpers.next_check_planner_helpers import _build_enrichment_artifact, _write_review


def test_vague_check_is_rejected(tmp_path: Path) -> None:
    """Test that vague/unrecognized checks are rejected."""
    run_id = "run-vague"
    root = tmp_path / "runs" / "health"
    review_path = _write_review(
        root,
        run_id,
        [{"label": "cluster-b", "context": "cluster-b", "reasons": ["missing_metrics"]}],
    )
    artifact = _build_enrichment_artifact(run_id, ("Investigate cluster signals",))
    plan = plan_next_checks(review_path, run_id, artifact)
    assert plan is not None
    candidate = plan.candidates[0]
    assert not candidate.safe_to_automate
    assert candidate.requires_operator_approval
    assert "Command not recognized" in (candidate.gating_reason or "")
    assert candidate.safe_to_automate is False
    assert candidate.safety_reason == SafetyReason.UNKNOWN_COMMAND.value
    assert candidate.approval_reason == ApprovalReason.UNKNOWN_COMMAND.value
    assert candidate.blocking_reason == BlockingReason.UNKNOWN_COMMAND.value


def test_multi_cluster_suggestion_rejected(tmp_path: Path) -> None:
    """Test that multi-cluster suggestions are rejected as too vague."""
    run_id = "run-multi"
    root = tmp_path / "runs" / "health"
    review_path = _write_review(
        root,
        run_id,
        [
            {
                "label": "cluster-a",
                "context": "cluster-a",
                "reasons": ["warning_event_threshold"],
            }
        ],
    )
    # This targets "all three clusters" - should be rejected
    artifact = _build_enrichment_artifact(
        run_id, ("Validate Helm release versions against baseline policy for all three clusters.",)
    )
    plan = plan_next_checks(review_path, run_id, artifact)
    assert plan is not None
    candidate = plan.candidates[0]
    assert not candidate.safe_to_automate
    assert candidate.requires_operator_approval
    assert candidate.suggested_command_family == CommandFamily.UNKNOWN
    assert candidate.safety_reason == SafetyReason.UNKNOWN_COMMAND.value
    assert "Command not recognized" in (candidate.gating_reason or "")


def test_vague_validate_check_rejected(tmp_path: Path) -> None:
    """Test that vague 'validate' suggestions are rejected."""
    run_id = "run-validate"
    root = tmp_path / "runs" / "health"
    review_path = _write_review(
        root,
        run_id,
        [
            {
                "label": "cluster-x",
                "context": "cluster-x",
                "reasons": ["baseline_drift"],
            }
        ],
    )
    artifact = _build_enrichment_artifact(
        run_id, ("Validate baseline policy compliance for all workloads",)
    )
    plan = plan_next_checks(review_path, run_id, artifact)
    assert plan is not None
    candidate = plan.candidates[0]
    assert not candidate.safe_to_automate
    assert candidate.suggested_command_family == CommandFamily.UNKNOWN
    assert candidate.requires_operator_approval
    assert "Command not recognized" in (candidate.gating_reason or "")


def test_validate_phrase_rejected(tmp_path: Path) -> None:
    """Test that suggestions with 'validate' are rejected as unknown_command."""
    run_id = "run-validate-phrase"
    root = tmp_path / "runs" / "health"
    review_path = _write_review(
        root,
        run_id,
        [
            {
                "label": "cluster1",
                "context": "cluster1",
                "reasons": ["CrashLoopBackOff"],
            }
        ],
    )
    # This is the exact phrase from the problematic run
    artifact = _build_enrichment_artifact(
        run_id, ("Validate image pull secrets (regcred, docker-registry) in cluster1 and cluster2 kube-system.",)
    )
    plan = plan_next_checks(review_path, run_id, artifact)
    assert plan is not None
    candidate = plan.candidates[0]
    assert not candidate.safe_to_automate
    assert candidate.requires_operator_approval
    assert candidate.suggested_command_family == CommandFamily.UNKNOWN
    assert candidate.safety_reason == SafetyReason.UNKNOWN_COMMAND.value
    assert "Command not recognized" in (candidate.gating_reason or "")


def test_investigate_phrase_rejected(tmp_path: Path) -> None:
    """Test that suggestions with 'investigate' are rejected as unknown_command."""
    run_id = "run-investigate-phrase"
    root = tmp_path / "runs" / "health"
    review_path = _write_review(
        root,
        run_id,
        [
            {
                "label": "cluster3",
                "context": "cluster3",
                "reasons": ["warning_event_threshold"],
            }
        ],
    )
    # This is the exact phrase from the problematic run
    artifact = _build_enrichment_artifact(
        run_id, ("Investigate liveness probe failures in cluster3 import-service and cluster2 redis-redis-ha.",)
    )
    plan = plan_next_checks(review_path, run_id, artifact)
    assert plan is not None
    candidate = plan.candidates[0]
    assert not candidate.safe_to_automate
    assert candidate.requires_operator_approval
    assert candidate.suggested_command_family == CommandFamily.UNKNOWN
    assert candidate.safety_reason == SafetyReason.UNKNOWN_COMMAND.value


def test_review_phrase_rejected(tmp_path: Path) -> None:
    """Test that suggestions with 'review' are rejected as unknown_command."""
    run_id = "run-review-phrase"
    root = tmp_path / "runs" / "health"
    review_path = _write_review(
        root,
        run_id,
        [
            {
                "label": "cluster1",
                "context": "cluster1",
                "reasons": ["CrashLoopBackOff"],
            }
        ],
    )
    # This is the exact phrase from the problematic run
    artifact = _build_enrichment_artifact(
        run_id, ("Review Helm release versions for cert-manager and ingress-nginx against baseline policies.",)
    )
    plan = plan_next_checks(review_path, run_id, artifact)
    assert plan is not None
    candidate = plan.candidates[0]
    assert not candidate.safe_to_automate
    assert candidate.requires_operator_approval
    assert candidate.suggested_command_family == CommandFamily.UNKNOWN
    assert candidate.safety_reason == SafetyReason.UNKNOWN_COMMAND.value


def test_confirm_phrase_rejected(tmp_path: Path) -> None:
    """Test that suggestions with 'confirm' are rejected as unknown_command."""
    run_id = "run-confirm-phrase"
    root = tmp_path / "runs" / "health"
    review_path = _write_review(
        root,
        run_id,
        [
            {
                "label": "cluster1",
                "context": "cluster1",
                "reasons": ["warning_event_threshold"],
            }
        ],
    )
    # This is the exact phrase from the problematic run - has 'Confirm' but also 'all clusters'
    artifact = _build_enrichment_artifact(
        run_id, ("Confirm existence of required CRDs (cilium.io, monitoring.coreos.com) across all clusters.",)
    )
    plan = plan_next_checks(review_path, run_id, artifact)
    assert plan is not None
    candidate = plan.candidates[0]
    assert not candidate.safe_to_automate
    assert candidate.requires_operator_approval
    assert candidate.suggested_command_family == CommandFamily.UNKNOWN
    assert candidate.safety_reason == SafetyReason.UNKNOWN_COMMAND.value


def test_inspect_phrase_rejected(tmp_path: Path) -> None:
    """Test that suggestions with 'Inspect' (no kubectl prefix) are rejected as unknown_command."""
    run_id = "run-inspect-phrase"
    root = tmp_path / "runs" / "health"
    review_path = _write_review(
        root,
        run_id,
        [
            {
                "label": "cluster1",
                "context": "cluster1",
                "reasons": ["CrashLoopBackOff"],
            }
        ],
    )
    # This is the exact phrase from the problematic run - starts with 'Inspect' not 'kubectl'
    artifact = _build_enrichment_artifact(
        run_id, ("Inspect node taints and pod affinity rules in cluster1 to resolve scheduling blocks.",)
    )
    plan = plan_next_checks(review_path, run_id, artifact)
    assert plan is not None
    candidate = plan.candidates[0]
    assert not candidate.safe_to_automate
    assert candidate.requires_operator_approval
    assert candidate.suggested_command_family == CommandFamily.UNKNOWN
    assert candidate.safety_reason == SafetyReason.UNKNOWN_COMMAND.value
