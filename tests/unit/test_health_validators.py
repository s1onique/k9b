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


class HealthAssessmentValidatorEdgeCasesTest(unittest.TestCase):
    def test_rejects_non_mapping_input(self) -> None:
        for invalid in [None, "string", [], 42]:  # type: ignore
            with self.assertRaises(ArtifactValidationError) as ctx:
                HealthAssessmentValidator.validate(invalid)
            self.assertIn("must be a mapping", str(ctx.exception))

    def test_rejects_wrong_types_for_string_fields(self) -> None:
        valid_base = {
            "run_label": "run-1",
            "run_id": "run-1-123",
            "timestamp": "2026-01-01T00:00:00Z",
            "context": "cluster-alpha",
            "label": "cluster-alpha",
            "cluster_id": "alpha",
            "snapshot_path": "runs/health/snapshots/run-1.json",
            "assessment": {"findings": []},
            "health_rating": "healthy",
        }
        string_fields = ["run_label", "run_id", "context", "label", "cluster_id", "snapshot_path", "health_rating"]
        for field in string_fields:
            data: dict[str, object] = dict(valid_base)
            data[field] = 123
            with self.assertRaises(ArtifactValidationError) as ctx:
                HealthAssessmentValidator.validate(data)
            self.assertIn(field, str(ctx.exception))
            self.assertIn("must be a string", str(ctx.exception))

    def test_rejects_assessment_not_mapping(self) -> None:
        data = {
            "run_label": "run-1",
            "run_id": "run-1-123",
            "timestamp": "2026-01-01T00:00:00Z",
            "context": "cluster-alpha",
            "label": "cluster-alpha",
            "cluster_id": "alpha",
            "snapshot_path": "runs/health/snapshots/run-1.json",
            "assessment": "not-a-mapping",
            "health_rating": "healthy",
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            HealthAssessmentValidator.validate(data)
        self.assertIn("assessment", str(ctx.exception))
        self.assertIn("must be an object", str(ctx.exception))

    def test_rejects_missing_evidence_not_list(self) -> None:
        data = {
            "run_label": "run-1",
            "run_id": "run-1-123",
            "timestamp": "2026-01-01T00:00:00Z",
            "context": "cluster-alpha",
            "label": "cluster-alpha",
            "cluster_id": "alpha",
            "snapshot_path": "runs/health/snapshots/run-1.json",
            "assessment": {"findings": []},
            "missing_evidence": "not-a-list",
            "health_rating": "healthy",
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            HealthAssessmentValidator.validate(data)
        self.assertIn("missing_evidence", str(ctx.exception))
        self.assertIn("must be a list", str(ctx.exception))

    def test_accepts_omitted_optional_missing_evidence(self) -> None:
        data = {
            "run_label": "run-1",
            "run_id": "run-1-123",
            "timestamp": "2026-01-01T00:00:00Z",
            "context": "cluster-alpha",
            "label": "cluster-alpha",
            "cluster_id": "alpha",
            "snapshot_path": "runs/health/snapshots/run-1.json",
            "assessment": {"findings": []},
            "health_rating": "healthy",
        }
        HealthAssessmentValidator.validate(data)

    def test_missing_keys_reports_all(self) -> None:
        with self.assertRaises(ArtifactValidationError) as ctx:
            HealthAssessmentValidator.validate({})
        error_msg = str(ctx.exception)
        self.assertIn("Missing keys", error_msg)
        for key in ["run_label", "run_id", "timestamp", "context", "label", "cluster_id", "snapshot_path", "assessment", "health_rating"]:
            self.assertIn(key, error_msg)


class DrilldownArtifactValidatorEdgeCasesTest(unittest.TestCase):
    def test_rejects_non_mapping_input(self) -> None:
        for invalid in [None, "string", [], 42]:  # type: ignore[var-annotated]
            with self.assertRaises(ArtifactValidationError) as ctx:
                DrilldownArtifactValidator.validate(invalid)
            self.assertIn("must be a mapping", str(ctx.exception))

    def test_rejects_missing_required_timestamp(self) -> None:
        data = {
            "run_label": "run-1",
            "run_id": "run-1",
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
            "collection_timestamps": {},
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            DrilldownArtifactValidator.validate(data)
        self.assertIn("timestamp", str(ctx.exception).lower())

    def test_rejects_invalid_timestamp_format(self) -> None:
        data = {
            "run_label": "run-1",
            "run_id": "run-1",
            "timestamp": "not-a-valid-timestamp",
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
            "collection_timestamps": {},
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            DrilldownArtifactValidator.validate(data)
        self.assertIn("timestamp", str(ctx.exception).lower())

    def test_accepts_valid_with_all_fields(self) -> None:
        data = {
            "run_label": "run-1",
            "run_id": "run-1",
            "timestamp": "2026-01-01T00:00:00Z",
            "snapshot_timestamp": "2026-01-01T00:00:00Z",
            "context": "cluster-alpha",
            "label": "cluster-alpha",
            "cluster_id": "alpha",
            "trigger_reasons": ["warning_event_threshold"],
            "missing_evidence": ["events"],
            "evidence_summary": {"warning_events": 5},
            "affected_namespaces": ["default"],
            "affected_workloads": [{"kind": "Pod", "namespace": "default", "name": "test-pod"}],
            "warning_events": [
                {
                    "namespace": "default",
                    "reason": "BackOff",
                    "message": "Container restarting",
                    "count": 3,
                    "last_seen": "2026-01-01T00:00:00Z",
                }
            ],
            "non_running_pods": [
                {"namespace": "default", "name": "failing-pod", "phase": "Pending", "reason": "Pending"},
            ],
            "pod_descriptions": {"default/failing-pod": "Container creating..."},
            "rollout_status": [],
            "collection_timestamps": {
                "warning_events": "2026-01-01T00:00:00Z",
                "pods": "2026-01-01T00:00:00Z",
            },
            "pattern_details": {"probe_failure": "kubectl describe pods"},
        }
        DrilldownArtifactValidator.validate(data)


class HealthProposalValidatorEdgeCasesTest(unittest.TestCase):
    def test_rejects_non_mapping_input(self) -> None:
        for invalid in [None, "string", [], 42]:  # type: ignore[var-annotated]
            with self.assertRaises(ArtifactValidationError) as ctx:
                HealthProposalValidator.validate(invalid)
            self.assertIn("Proposal must be a mapping", str(ctx.exception))

    def test_rejects_promotion_payload_not_mapping(self) -> None:
        data = {
            "proposal_id": "p1",
            "source_run_id": "run-1",
            "target": "health.trigger_policy.warning_event_threshold",
            "proposed_change": "Adjust threshold.",
            "rationale": "Noise.",
            "confidence": "medium",
            "expected_benefit": "Less noise.",
            "rollback_note": "Revert if needed.",
            "promotion_payload": "not-a-mapping",
            "lifecycle_history": [
                {"status": "proposed", "timestamp": "2026-01-01T00:00:00Z"}
            ],
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            HealthProposalValidator.validate(data)
        self.assertIn("promotion_payload", str(ctx.exception))

    def test_rejects_lifecycle_history_not_list(self) -> None:
        data = {
            "proposal_id": "p1",
            "source_run_id": "run-1",
            "target": "health.trigger_policy.warning_event_threshold",
            "proposed_change": "Adjust threshold.",
            "rationale": "Noise.",
            "confidence": "medium",
            "expected_benefit": "Less noise.",
            "rollback_note": "Revert if needed.",
            "promotion_payload": {},
            "lifecycle_history": "not-a-list",
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            HealthProposalValidator.validate(data)
        self.assertIn("lifecycle_history", str(ctx.exception))
        self.assertIn("must be a list", str(ctx.exception))

    def test_rejects_lifecycle_entry_not_mapping(self) -> None:
        data = {
            "proposal_id": "p1",
            "source_run_id": "run-1",
            "target": "health.trigger_policy.warning_event_threshold",
            "proposed_change": "Adjust threshold.",
            "rationale": "Noise.",
            "confidence": "medium",
            "expected_benefit": "Less noise.",
            "rollback_note": "Revert if needed.",
            "promotion_payload": {},
            "lifecycle_history": ["not-a-mapping"],
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            HealthProposalValidator.validate(data)
        self.assertIn("lifecycle entries", str(ctx.exception))
        self.assertIn("must be mappings", str(ctx.exception))

    def test_rejects_lifecycle_entry_missing_status(self) -> None:
        data = {
            "proposal_id": "p1",
            "source_run_id": "run-1",
            "target": "health.trigger_policy.warning_event_threshold",
            "proposed_change": "Adjust threshold.",
            "rationale": "Noise.",
            "confidence": "medium",
            "expected_benefit": "Less noise.",
            "rollback_note": "Revert if needed.",
            "promotion_payload": {},
            "lifecycle_history": [{"timestamp": "2026-01-01T00:00:00Z"}],
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            HealthProposalValidator.validate(data)
        self.assertIn("status", str(ctx.exception))

    def test_rejects_lifecycle_entry_missing_timestamp(self) -> None:
        data = {
            "proposal_id": "p1",
            "source_run_id": "run-1",
            "target": "health.trigger_policy.warning_event_threshold",
            "proposed_change": "Adjust threshold.",
            "rationale": "Noise.",
            "confidence": "medium",
            "expected_benefit": "Less noise.",
            "rollback_note": "Revert if needed.",
            "promotion_payload": {},
            "lifecycle_history": [{"status": "proposed"}],
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            HealthProposalValidator.validate(data)
        self.assertIn("timestamp", str(ctx.exception))

    def test_accepts_omitted_optional_promotion_evaluation(self) -> None:
        data = {
            "proposal_id": "p1",
            "source_run_id": "run-1",
            "target": "health.trigger_policy.warning_event_threshold",
            "proposed_change": "Adjust threshold.",
            "rationale": "Noise.",
            "confidence": "medium",
            "expected_benefit": "Less noise.",
            "rollback_note": "Revert if needed.",
            "promotion_payload": {},
            "lifecycle_history": [{"status": "proposed", "timestamp": "2026-01-01T00:00:00Z"}],
        }
        HealthProposalValidator.validate(data)

    def test_rejects_promotion_evaluation_not_mapping(self) -> None:
        data = {
            "proposal_id": "p1",
            "source_run_id": "run-1",
            "target": "health.trigger_policy.warning_event_threshold",
            "proposed_change": "Adjust threshold.",
            "rationale": "Noise.",
            "confidence": "medium",
            "expected_benefit": "Less noise.",
            "rollback_note": "Revert if needed.",
            "promotion_payload": {},
            "lifecycle_history": [{"status": "proposed", "timestamp": "2026-01-01T00:00:00Z"}],
            "promotion_evaluation": "not-a-mapping",
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            HealthProposalValidator.validate(data)
        self.assertIn("promotion_evaluation", str(ctx.exception))

    def test_rejects_promotion_evaluation_missing_keys(self) -> None:
        data = {
            "proposal_id": "p1",
            "source_run_id": "run-1",
            "target": "health.trigger_policy.warning_event_threshold",
            "proposed_change": "Adjust threshold.",
            "rationale": "Noise.",
            "confidence": "medium",
            "expected_benefit": "Less noise.",
            "rollback_note": "Revert if needed.",
            "promotion_payload": {},
            "lifecycle_history": [{"status": "proposed", "timestamp": "2026-01-01T00:00:00Z"}],
            "promotion_evaluation": {
                "proposal_id": "p1",
                "noise_reduction": "~50%",
            },
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            HealthProposalValidator.validate(data)
        error_msg = str(ctx.exception)
        self.assertIn("promotion_evaluation", error_msg)
        # Validator reports first missing key only
        self.assertIn("signal_loss", error_msg)


class ComparisonDecisionValidatorEdgeCasesTest(unittest.TestCase):
    def test_rejects_non_mapping_input(self) -> None:
        for invalid in [None, "string", [], 42]:  # type: ignore[var-annotated]
            with self.assertRaises(ArtifactValidationError) as ctx:
                ComparisonDecisionValidator.validate(invalid)
            self.assertIn("Comparison decision must be a mapping", str(ctx.exception))

    def test_rejects_policy_eligible_not_boolean(self) -> None:
        data = {
            "primary_label": "a",
            "secondary_label": "b",
            "policy_eligible": "yes",
            "triggered": False,
            "comparison_intent": "suspicious drift",
            "reason": "manual",
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            ComparisonDecisionValidator.validate(data)
        self.assertIn("policy_eligible", str(ctx.exception))
        self.assertIn("must be a boolean", str(ctx.exception))

    def test_rejects_triggered_not_boolean(self) -> None:
        data = {
            "primary_label": "a",
            "secondary_label": "b",
            "policy_eligible": True,
            "triggered": "yes",
            "comparison_intent": "suspicious drift",
            "reason": "manual",
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            ComparisonDecisionValidator.validate(data)
        self.assertIn("triggered", str(ctx.exception))
        self.assertIn("must be a boolean", str(ctx.exception))

    def test_rejects_expected_drift_categories_not_list(self) -> None:
        data = {
            "primary_label": "a",
            "secondary_label": "b",
            "policy_eligible": True,
            "triggered": False,
            "comparison_intent": "suspicious drift",
            "reason": "manual",
            "expected_drift_categories": "not-a-list",
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            ComparisonDecisionValidator.validate(data)
        self.assertIn("expected_drift_categories", str(ctx.exception))
        self.assertIn("must be a list", str(ctx.exception))

    def test_rejects_ignored_drift_categories_not_list(self) -> None:
        data = {
            "primary_label": "a",
            "secondary_label": "b",
            "policy_eligible": True,
            "triggered": False,
            "comparison_intent": "suspicious drift",
            "reason": "manual",
            "ignored_drift_categories": "not-a-list",
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            ComparisonDecisionValidator.validate(data)
        self.assertIn("ignored_drift_categories", str(ctx.exception))
        self.assertIn("must be a list", str(ctx.exception))

    def test_accepts_omitted_optional_drift_fields(self) -> None:
        data = {
            "primary_label": "a",
            "secondary_label": "b",
            "policy_eligible": True,
            "triggered": False,
            "comparison_intent": "suspicious drift",
            "reason": "manual",
        }
        ComparisonDecisionValidator.validate(data)

    def test_missing_keys_reports_all(self) -> None:
        with self.assertRaises(ArtifactValidationError) as ctx:
            ComparisonDecisionValidator.validate({})
        error_msg = str(ctx.exception)
        self.assertIn("Missing keys", error_msg)
        for key in ["primary_label", "secondary_label", "policy_eligible", "triggered", "comparison_intent", "reason"]:
            self.assertIn(key, error_msg)


class ArtifactValidationErrorTest(unittest.TestCase):
    def test_is_value_error_subclass(self) -> None:
        error = ArtifactValidationError("test message")
        self.assertIsInstance(error, ValueError)
        self.assertIsInstance(error, Exception)

    def test_error_message_accessible(self) -> None:
        msg = "Custom validation failure"
        error = ArtifactValidationError(msg)
        self.assertEqual(str(error), msg)

    def test_can_be_caught_as_value_error(self) -> None:
        with self.assertRaises(ValueError):
            HealthAssessmentValidator.validate({})

    def test_can_be_caught_as_artifact_error(self) -> None:
        with self.assertRaises(ArtifactValidationError):
            HealthAssessmentValidator.validate({})


if __name__ == "__main__":
    unittest.main()
