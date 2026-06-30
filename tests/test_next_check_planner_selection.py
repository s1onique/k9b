"""Tests for next-check planner candidate selection, deduplication, and prioritization."""

from __future__ import annotations

from pathlib import Path

from k8s_diag_agent.external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisStatus,
)
from k8s_diag_agent.external_analysis.next_check_planner import (
    DuplicateReason,
    SafetyReason,
    plan_next_checks,
)
from tests.helpers.next_check_planner_helpers import (
    _build_enrichment_artifact,
    _copy_fixture_set,
    _write_assessment,
    _write_review,
)


def test_duplicate_check_is_flagged(tmp_path: Path) -> None:
    """Test that duplicate checks are flagged."""
    from k8s_diag_agent.external_analysis.next_check_planner import (
        ApprovalReason,
        BlockingReason,
    )

    run_id = "run-duplicate"
    root = tmp_path / "runs" / "health"
    review_path = _write_review(
        root,
        run_id,
        [{"label": "cluster-d", "context": "cluster-d", "reasons": ["warning_event"]}],
    )
    _write_assessment(
        root,
        run_id,
        "cluster-d",
        [{"description": "Inspect ingress logs"}],
    )
    artifact = _build_enrichment_artifact(run_id, ("Inspect ingress logs",))
    plan = plan_next_checks(review_path, run_id, artifact)
    assert plan is not None
    candidate = plan.candidates[0]
    assert candidate.duplicate_of_existing_evidence
    assert "Matches deterministic next check" in (candidate.gating_reason or "")
    assert candidate.duplicate_reason == DuplicateReason.EXACT_MATCH.value
    assert candidate.blocking_reason == BlockingReason.DUPLICATE.value
    assert candidate.safety_reason == SafetyReason.DUPLICATE_EVIDENCE.value
    assert candidate.approval_reason == ApprovalReason.DUPLICATE_EVIDENCE.value


def test_fixture_duplicate_detection_handles_variations(tmp_path: Path) -> None:
    """Test that duplicate detection handles semantic variations."""
    run_id = "fixture-run"
    root = _copy_fixture_set(tmp_path)
    review_path = root / "reviews" / f"{run_id}-review.json"
    artifact = _build_enrichment_artifact(
        run_id,
        ("Inspect ingress logs for authentication errors",),
    )
    plan = plan_next_checks(review_path, run_id, artifact)
    assert plan is not None
    candidate = plan.candidates[0]
    assert candidate.duplicate_of_existing_evidence
    assert "Matches deterministic next check" in (candidate.gating_reason or "")


def test_specific_candidate_preferred_over_generic(tmp_path: Path) -> None:
    """Test that specific candidates are preferred over generic ones."""
    run_id = "run-ranking"
    root = tmp_path / "runs" / "health"
    review_path = _write_review(
        root,
        run_id,
        [
            {
                "label": "cluster-ranking",
                "context": "cluster-ranking",
                "reasons": ["warning_event_threshold"],
            }
        ],
    )
    artifact = _build_enrichment_artifact(
        run_id,
        (
            "Investigate flagged resources",
            "kubectl logs -n default deployment/alpha",
        ),
    )
    plan = plan_next_checks(review_path, run_id, artifact)
    assert plan is not None
    assert len(plan.candidates) == 2
    assert plan.candidates[0].description.startswith("kubectl logs")
    assert plan.candidates[0].priority_label == "primary"
    assert plan.candidates[1].priority_label == "fallback"


def test_generic_candidate_preserved_when_no_specific_suggestions(tmp_path: Path) -> None:
    """Test that generic candidates are preserved when no specific suggestions exist."""
    run_id = "run-generic"
    root = tmp_path / "runs" / "health"
    review_path = _write_review(
        root,
        run_id,
        [
            {
                "label": "cluster-generic",
                "context": "cluster-generic",
                "reasons": ["cluster_health"],
            }
        ],
    )
    artifact = _build_enrichment_artifact(run_id, ("Review cluster status and signals",))
    plan = plan_next_checks(review_path, run_id, artifact)
    assert plan is not None
    assert len(plan.candidates) == 1
    assert plan.candidates[0].priority_label == "fallback"


def test_repeated_helm_suggestions_are_collapsed(tmp_path: Path) -> None:
    """Test that repeated Helm suggestions are collapsed to one."""
    run_id = "run-helm"
    root = tmp_path / "runs" / "health"
    review_path = _write_review(
        root,
        run_id,
        [
            {
                "label": "cluster-helm",
                "context": "cluster-helm",
                "reasons": ["helm_release"],
            }
        ],
    )
    artifact = _build_enrichment_artifact(
        run_id,
        (
            "Validate Helm release nginx",
            "Validate Helm release nginx version 2.1",
            "Validate Helm release nginx (status check)",
        ),
    )
    plan = plan_next_checks(review_path, run_id, artifact)
    assert plan is not None
    assert len(plan.candidates) == 1
    assert plan.candidates[0].description == "Validate Helm release nginx"


def test_planner_skips_when_enrichment_missing(tmp_path: Path) -> None:
    """Test that planner returns None when enrichment is missing/skipped."""

    run_id = "run-missing"
    root = tmp_path / "runs" / "health"
    review_path = _write_review(
        root,
        run_id,
        [{"label": "cluster-e", "context": "cluster-e", "reasons": ["warning_event"]}],
    )
    artifact = ExternalAnalysisArtifact(
        tool_name="llamacpp",
        run_id=run_id,
        cluster_label="cluster-e",
        summary="missing",
        status=ExternalAnalysisStatus.SKIPPED,
        suggested_next_checks=("kubectl get pods",),
    )
    assert plan_next_checks(review_path, run_id, artifact) is None


def test_fixture_safe_command_classification(tmp_path: Path) -> None:
    """Test that safe commands are classified correctly from fixtures."""
    run_id = "fixture-run"
    root = _copy_fixture_set(tmp_path)
    review_path = root / "reviews" / f"{run_id}-review.json"
    artifact = _build_enrichment_artifact(run_id, ("kubectl get pods -n default",))
    plan = plan_next_checks(review_path, run_id, artifact)
    assert plan is not None
    candidate = plan.candidates[0]
    assert candidate.target_cluster == "cluster-fixture"
    assert candidate.safe_to_automate
    assert not candidate.requires_operator_approval
