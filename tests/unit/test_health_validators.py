import unittest

from k8s_diag_agent.health.validators import (
    ArtifactValidationError,
    ComparisonDecisionValidator,
    DrilldownArtifactValidator,
    HealthAssessmentValidator,
    HealthProposalValidator,
)


class HealthValidatorsTest(unittest.TestCase):
    def test_assessment_validator_rejects_missing_keys(self) -> None:
        with self.assertRaises(ArtifactValidationError):
            HealthAssessmentValidator.validate({})

    def test_assessment_validator_accepts_valid_data(self) -> None:
        valid = {
            "run_label": "run-1",
            "run_id": "run-1-123",
            "timestamp": "2026-01-01T00:00:00Z",
            "context": "cluster-alpha",
            "label": "cluster-alpha",
            "cluster_id": "alpha",
            "snapshot_path": "runs/health/snapshots/run-1.json",
            "assessment": {"findings": []},
            "missing_evidence": [],
            "health_rating": "healthy",
        }
        HealthAssessmentValidator.validate(valid)

    def test_drilldown_validator_rejects_invalid_payload(self) -> None:
        with self.assertRaises(ArtifactValidationError):
            DrilldownArtifactValidator.validate({})

    def test_drilldown_validator_accepts_valid_payload(self) -> None:
        base = {
            "run_label": "run-1",
            "run_id": "run-1",
            "timestamp": "2026-01-01T00:00:00Z",
            "snapshot_timestamp": "2026-01-01T00:00:00Z",
            "context": "cluster-alpha",
            "label": "cluster-alpha",
            "cluster_id": "alpha",
            "trigger_reasons": [],
            "missing_evidence": [],
            "evidence_summary": {},
            "affected_namespaces": [],
            "affected_workloads": [],
            "warning_events": [],
            "non_running_pods": [],
            "pod_descriptions": {},
            "rollout_status": [],
            "collection_timestamps": {"warning_events": "2026-01-01T00:00:00Z"},
            "pattern_details": {},
        }
        DrilldownArtifactValidator.validate(base)

    def test_proposal_validator_rejects_missing_fields(self) -> None:
        with self.assertRaises(ArtifactValidationError):
            HealthProposalValidator.validate({})

    def test_proposal_validator_accepts_valid_data(self) -> None:
        data = {
            "proposal_id": "p1",
            "source_run_id": "run-1",
            "source_artifact_path": "runs/health/reviews/run-1-review.json",
            "target": "health.trigger_policy.warning_event_threshold",
            "proposed_change": "Adjust threshold.",
            "rationale": "Noise.",
            "confidence": "medium",
            "expected_benefit": "Less noise.",
            "rollback_note": "Revert if needed.",
            "promotion_payload": {"threshold": 5},
            "lifecycle_history": [
                {"status": "proposed", "timestamp": "2026-01-01T00:00:00Z"}
            ],
            "promotion_evaluation": {
                "proposal_id": "p1",
                "noise_reduction": "~50%",
                "signal_loss": "low",
                "test_outcome": "Fixture run 1",
            },
        }
        HealthProposalValidator.validate(data)

    def test_comparison_decision_validator_rejects_bad_entry(self) -> None:
        with self.assertRaises(ArtifactValidationError):
            ComparisonDecisionValidator.validate({})

    def test_comparison_decision_validator_accepts_valid_entry(self) -> None:
        valid = {
            "primary_label": "a",
            "secondary_label": "b",
            "policy_eligible": True,
            "triggered": False,
            "comparison_intent": "suspicious drift",
            "reason": "manual",
            "expected_drift_categories": [],
            "ignored_drift_categories": [],
        }
        ComparisonDecisionValidator.validate(valid)
