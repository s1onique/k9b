import json
import shutil
from pathlib import Path

from k8s_diag_agent.external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisStatus,
)
from k8s_diag_agent.external_analysis.next_check_planner import (
    ApprovalReason,
    BlockingReason,
    CommandFamily,
    DuplicateReason,
    NormalizationReason,
    SafetyReason,
    plan_next_checks,
)


def _write_review(root: Path, run_id: str, selections: list[dict[str, object]]) -> Path:
    review_dir = root / "reviews"
    review_dir.mkdir(parents=True, exist_ok=True)
    path = review_dir / f"{run_id}-review.json"
    path.write_text(
        json.dumps({"run_id": run_id, "selected_drilldowns": selections}), encoding="utf-8"
    )
    return path


def _write_assessment(
    root: Path, run_id: str, label: str, next_checks: list[dict[str, str]]
) -> None:
    assessments_dir = root / "assessments"
    assessments_dir.mkdir(parents=True, exist_ok=True)
    path = assessments_dir / f"{run_id}-{label}-assessment.json"
    path.write_text(json.dumps({"next_evidence_to_collect": next_checks}), encoding="utf-8")


def _build_enrichment_artifact(run_id: str, hints: tuple[str, ...]) -> ExternalAnalysisArtifact:
    return ExternalAnalysisArtifact(
        tool_name="llamacpp",
        run_id=run_id,
        cluster_label="status-run",
        summary="enrichment",
        suggested_next_checks=hints,
        status=ExternalAnalysisStatus.SUCCESS,
        artifact_path="external-analysis/plan.json",
        provider="llamacpp",
    )


def _copy_fixture_set(tmp_path: Path) -> Path:
    fixture_root = Path(__file__).parent / "fixtures" / "next_check_planner"
    destination = tmp_path / "runs" / "health"
    shutil.copytree(fixture_root, destination)
    return destination


def test_safe_read_only_check(tmp_path: Path) -> None:
    run_id = "run-safe"
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
    artifact = _build_enrichment_artifact(run_id, ("kubectl logs -n default deployment/alpha",))
    plan = plan_next_checks(review_path, run_id, artifact)
    assert plan is not None
    candidate = plan.candidates[0]
    assert candidate.suggested_command_family == CommandFamily.KUBECTL_LOGS
    assert candidate.target_cluster == "cluster-a"
    assert candidate.safe_to_automate
    assert not candidate.requires_operator_approval
    assert candidate.normalization_reason == NormalizationReason.SELECTION_DEFAULT.value
    assert candidate.safety_reason == SafetyReason.KNOWN_COMMAND.value
    assert candidate.approval_reason is None
    assert candidate.duplicate_reason is None
    assert candidate.blocking_reason is None


def test_vague_check_is_rejected(tmp_path: Path) -> None:
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
    assert candidate.normalization_reason == NormalizationReason.SELECTION_DEFAULT.value


def test_mutation_like_check_is_rejected(tmp_path: Path) -> None:
    run_id = "run-mutate"
    root = tmp_path / "runs" / "health"
    review_path = _write_review(
        root,
        run_id,
        [{"label": "cluster-c", "context": "cluster-c", "reasons": ["warning"]}],
    )
    artifact = _build_enrichment_artifact(run_id, ("kubectl apply -f patch.yaml",))
    plan = plan_next_checks(review_path, run_id, artifact)
    assert plan is not None
    candidate = plan.candidates[0]
    assert not candidate.safe_to_automate
    assert "mutating" in (candidate.gating_reason or "").lower()
    assert candidate.safety_reason == SafetyReason.MUTATION_DETECTED.value
    assert candidate.approval_reason == ApprovalReason.MUTATION_DETECTED.value
    assert candidate.blocking_reason == BlockingReason.MUTATION_DETECTED.value


def test_duplicate_check_is_flagged(tmp_path: Path) -> None:
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


def test_candidate_id_is_stable(tmp_path: Path) -> None:
    run_id = "run-stable"
    root = tmp_path / "runs" / "health"
    review_path = _write_review(
        root,
        run_id,
        [
            {
                "label": "cluster-stable",
                "context": "cluster-stable",
                "reasons": ["missing_metrics"],
            }
        ],
    )
    artifact = _build_enrichment_artifact(run_id, ("kubectl logs deployment/stable",))
    ids: list[str | None] = []
    for _ in range(2):
        plan = plan_next_checks(review_path, run_id, artifact)
        assert plan is not None
        assert plan.candidates
        ids.append(plan.candidates[0].candidate_id)
    assert ids[0]
    assert all(candidate_id == ids[0] for candidate_id in ids)


def test_fixture_safe_command_classification(tmp_path: Path) -> None:
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


def test_fixture_duplicate_detection_handles_variations(tmp_path: Path) -> None:
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
