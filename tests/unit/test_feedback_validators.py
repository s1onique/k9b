"""Unit tests for feedback validators module."""

import unittest
from datetime import UTC, datetime

from k8s_diag_agent.feedback import models
from k8s_diag_agent.feedback.validators import (
    ArtifactValidationError,
    AssessmentArtifactValidator,
    ProposedImprovementValidator,
    RunArtifactValidator,
    SnapshotPairArtifactValidator,
    ValidationResultValidator,
)
from k8s_diag_agent.models import ConfidenceLevel


class SnapshotPairArtifactValidatorTest(unittest.TestCase):
    def test_validate_accepts_valid_data(self) -> None:
        data = {
            "primary_snapshot_id": "snap-1",
            "primary_snapshot_path": "/path/to/snap",
            "comparison_summary": {"nodes": 5, "namespaces": 10},
            "missing_evidence": ["events", "logs"],
        }
        SnapshotPairArtifactValidator.validate(data)

    def test_validate_accepts_minimal_data(self) -> None:
        data = {
            "primary_snapshot_id": "snap-1",
            "primary_snapshot_path": "/path/to/snap",
        }
        SnapshotPairArtifactValidator.validate(data)

    def test_validate_rejects_missing_primary_snapshot_id(self) -> None:
        data = {
            "primary_snapshot_path": "/path/to/snap",
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            SnapshotPairArtifactValidator.validate(data)
        self.assertIn("primary_snapshot_id", str(ctx.exception))

    def test_validate_rejects_missing_primary_snapshot_path(self) -> None:
        data = {
            "primary_snapshot_id": "snap-1",
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            SnapshotPairArtifactValidator.validate(data)
        self.assertIn("primary_snapshot_path", str(ctx.exception))

    def test_validate_rejects_missing_both_keys(self) -> None:
        data: dict[str, object] = {}
        with self.assertRaises(ArtifactValidationError) as ctx:
            SnapshotPairArtifactValidator.validate(data)
        self.assertIn("primary_snapshot_id", str(ctx.exception))
        self.assertIn("primary_snapshot_path", str(ctx.exception))

    def test_validate_rejects_wrong_comparison_summary_type(self) -> None:
        data = {
            "primary_snapshot_id": "snap-1",
            "primary_snapshot_path": "/path/to/snap",
            "comparison_summary": "not-a-dict",
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            SnapshotPairArtifactValidator.validate(data)
        self.assertIn("comparison_summary", str(ctx.exception))

    def test_validate_rejects_wrong_missing_evidence_type(self) -> None:
        data = {
            "primary_snapshot_id": "snap-1",
            "primary_snapshot_path": "/path/to/snap",
            "missing_evidence": "not-a-list",
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            SnapshotPairArtifactValidator.validate(data)
        self.assertIn("missing_evidence", str(ctx.exception))

    def test_from_dict_parses_valid_data(self) -> None:
        data = {
            "primary_snapshot_id": "snap-1",
            "primary_snapshot_path": "/path/to/snap",
            "comparison_summary": {"nodes": 5},
            "secondary_snapshot_id": "snap-2",
            "secondary_snapshot_path": "/path/to/snap2",
            "status": "pending",
            "start_time": "2024-01-01T10:00:00",
            "end_time": "2024-01-01T10:05:00",
            "missing_evidence": ["events"],
        }
        artifact = SnapshotPairArtifactValidator.from_dict(data)
        self.assertEqual(artifact.primary_snapshot_id, "snap-1")
        self.assertEqual(artifact.primary_snapshot_path, "/path/to/snap")
        self.assertEqual(artifact.comparison_summary, {"nodes": 5})
        self.assertEqual(artifact.secondary_snapshot_id, "snap-2")
        self.assertEqual(artifact.status, "pending")
        self.assertIsNotNone(artifact.start_time)
        self.assertIsNotNone(artifact.end_time)
        self.assertEqual(artifact.missing_evidence, ["events"])

    def test_from_dict_defaults_optional_fields(self) -> None:
        data = {
            "primary_snapshot_id": "snap-1",
            "primary_snapshot_path": "/path/to/snap",
        }
        artifact = SnapshotPairArtifactValidator.from_dict(data)
        self.assertIsNone(artifact.secondary_snapshot_id)
        self.assertEqual(artifact.status, "complete")
        self.assertIsNone(artifact.start_time)
        self.assertIsNone(artifact.end_time)
        self.assertEqual(artifact.missing_evidence, [])

    def test_from_dict_handles_datetime_objects(self) -> None:
        now = datetime.now(UTC)
        data = {
            "primary_snapshot_id": "snap-1",
            "primary_snapshot_path": "/path/to/snap",
            "start_time": now,
            "end_time": now,
        }
        artifact = SnapshotPairArtifactValidator.from_dict(data)
        self.assertEqual(artifact.start_time, now)
        self.assertEqual(artifact.end_time, now)

    def test_from_dict_rejects_invalid_timestamp(self) -> None:
        data = {
            "primary_snapshot_id": "snap-1",
            "primary_snapshot_path": "/path/to/snap",
            "start_time": "not-a-timestamp",
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            SnapshotPairArtifactValidator.from_dict(data)
        self.assertIn("Invalid timestamp", str(ctx.exception))

    def test_from_dict_converts_non_string_ids(self) -> None:
        data = {
            "primary_snapshot_id": 123,
            "primary_snapshot_path": "/path/to/snap",
        }
        artifact = SnapshotPairArtifactValidator.from_dict(data)
        self.assertEqual(artifact.primary_snapshot_id, "123")


class AssessmentArtifactValidatorTest(unittest.TestCase):
    def test_validate_accepts_valid_data(self) -> None:
        data = {
            "assessment_id": "assess-1",
            "schema_version": "1.0",
            "assessment": {"findings": []},
        }
        AssessmentArtifactValidator.validate(data)

    def test_validate_rejects_missing_assessment_id(self) -> None:
        data = {
            "schema_version": "1.0",
            "assessment": {},
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            AssessmentArtifactValidator.validate(data)
        self.assertIn("assessment_id", str(ctx.exception))

    def test_validate_rejects_missing_schema_version(self) -> None:
        data = {
            "assessment_id": "assess-1",
            "assessment": {},
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            AssessmentArtifactValidator.validate(data)
        self.assertIn("schema_version", str(ctx.exception))

    def test_validate_rejects_missing_assessment(self) -> None:
        data = {
            "assessment_id": "assess-1",
            "schema_version": "1.0",
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            AssessmentArtifactValidator.validate(data)
        self.assertIn("assessment", str(ctx.exception))

    def test_validate_rejects_wrong_assessment_type(self) -> None:
        data = {
            "assessment_id": "assess-1",
            "schema_version": "1.0",
            "assessment": "not-a-dict",
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            AssessmentArtifactValidator.validate(data)
        self.assertIn("assessment", str(ctx.exception))

    def test_from_dict_parses_valid_data(self) -> None:
        data = {
            "assessment_id": "assess-1",
            "schema_version": "1.0",
            "assessment": {"findings": [], "hypotheses": []},
            "overall_confidence": "high",
        }
        artifact = AssessmentArtifactValidator.from_dict(data)
        self.assertEqual(artifact.assessment_id, "assess-1")
        self.assertEqual(artifact.schema_version, "1.0")
        self.assertEqual(artifact.assessment["findings"], [])
        self.assertEqual(artifact.overall_confidence, "high")

    def test_from_dict_defaults_optional_fields(self) -> None:
        data = {
            "assessment_id": "assess-1",
            "schema_version": "1.0",
            "assessment": {},
        }
        artifact = AssessmentArtifactValidator.from_dict(data)
        self.assertIsNone(artifact.overall_confidence)


class ValidationResultValidatorTest(unittest.TestCase):
    def test_validate_accepts_valid_data(self) -> None:
        data = {
            "name": "schema-check",
            "passed": True,
            "errors": ["error1"],
        }
        ValidationResultValidator.validate(data)

    def test_validate_rejects_missing_name(self) -> None:
        data = {
            "passed": True,
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            ValidationResultValidator.validate(data)
        self.assertIn("name", str(ctx.exception))

    def test_validate_rejects_missing_passed(self) -> None:
        data = {
            "name": "schema-check",
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            ValidationResultValidator.validate(data)
        self.assertIn("passed", str(ctx.exception))

    def test_validate_rejects_wrong_passed_type(self) -> None:
        data = {
            "name": "schema-check",
            "passed": "yes",
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            ValidationResultValidator.validate(data)
        self.assertIn("passed", str(ctx.exception))

    def test_validate_rejects_wrong_errors_type(self) -> None:
        data = {
            "name": "schema-check",
            "passed": True,
            "errors": "not-a-list",
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            ValidationResultValidator.validate(data)
        self.assertIn("errors", str(ctx.exception))

    def test_validate_accepts_optional_failure_mode(self) -> None:
        data = {
            "name": "schema-check",
            "passed": False,
            "failure_mode": "missing_evidence",
        }
        ValidationResultValidator.validate(data)

    def test_from_dict_parses_valid_data(self) -> None:
        data = {
            "name": "schema-check",
            "passed": False,
            "errors": ["error1", "error2"],
            "checked_at": "2024-01-01T10:00:00",
            "failure_mode": "validation_failure",
        }
        artifact = ValidationResultValidator.from_dict(data)
        self.assertEqual(artifact.name, "schema-check")
        self.assertFalse(artifact.passed)
        self.assertEqual(artifact.errors, ["error1", "error2"])
        self.assertIsNotNone(artifact.checked_at)
        self.assertEqual(artifact.failure_mode, models.FailureMode.VALIDATION_FAILURE)

    def test_from_dict_defaults_optional_fields(self) -> None:
        data = {
            "name": "schema-check",
            "passed": True,
        }
        artifact = ValidationResultValidator.from_dict(data)
        self.assertEqual(artifact.errors, [])
        self.assertIsNone(artifact.failure_mode)

    def test_from_dict_accepts_failure_mode_enum(self) -> None:
        data = {
            "name": "schema-check",
            "passed": False,
            "failure_mode": models.FailureMode.LLM_ERROR,
        }
        artifact = ValidationResultValidator.from_dict(data)
        self.assertEqual(artifact.failure_mode, models.FailureMode.LLM_ERROR)

    def test_from_dict_rejects_invalid_failure_mode(self) -> None:
        data = {
            "name": "schema-check",
            "passed": True,
            "failure_mode": "not-a-failure-mode",
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            ValidationResultValidator.from_dict(data)
        self.assertIn("Unknown failure_mode", str(ctx.exception))


class ProposedImprovementValidatorTest(unittest.TestCase):
    def test_validate_accepts_valid_data(self) -> None:
        data = {
            "id": "imp-1",
            "description": "Add validation",
            "target": "schema-check",
        }
        ProposedImprovementValidator.validate(data)

    def test_validate_rejects_missing_id(self) -> None:
        data = {
            "description": "Add validation",
            "target": "schema-check",
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            ProposedImprovementValidator.validate(data)
        self.assertIn("id", str(ctx.exception))

    def test_validate_rejects_missing_description(self) -> None:
        data = {
            "id": "imp-1",
            "target": "schema-check",
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            ProposedImprovementValidator.validate(data)
        self.assertIn("description", str(ctx.exception))

    def test_validate_rejects_missing_target(self) -> None:
        data = {
            "id": "imp-1",
            "description": "Add validation",
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            ProposedImprovementValidator.validate(data)
        self.assertIn("target", str(ctx.exception))

    def test_validate_rejects_all_missing(self) -> None:
        data: dict[str, object] = {}
        with self.assertRaises(ArtifactValidationError) as ctx:
            ProposedImprovementValidator.validate(data)
        self.assertIn("id", str(ctx.exception))
        self.assertIn("description", str(ctx.exception))
        self.assertIn("target", str(ctx.exception))

    def test_from_dict_parses_valid_data(self) -> None:
        data = {
            "id": "imp-1",
            "description": "Add validation for logs",
            "target": "schema-check",
            "owner": "platform-team",
            "confidence": "medium",
            "rationale": "Current check is incomplete",
            "related_failure_modes": ["missing_evidence", "validation_failure"],
        }
        artifact = ProposedImprovementValidator.from_dict(data)
        self.assertEqual(artifact.id, "imp-1")
        self.assertEqual(artifact.description, "Add validation for logs")
        self.assertEqual(artifact.target, "schema-check")
        self.assertEqual(artifact.owner, "platform-team")
        self.assertEqual(artifact.confidence, ConfidenceLevel.MEDIUM)
        self.assertEqual(artifact.rationale, "Current check is incomplete")
        self.assertEqual(artifact.related_failure_modes, [
            models.FailureMode.MISSING_EVIDENCE,
            models.FailureMode.VALIDATION_FAILURE,
        ])

    def test_from_dict_defaults_optional_fields(self) -> None:
        data = {
            "id": "imp-1",
            "description": "Add validation",
            "target": "schema-check",
        }
        artifact = ProposedImprovementValidator.from_dict(data)
        self.assertIsNone(artifact.owner)
        self.assertIsNone(artifact.confidence)
        self.assertIsNone(artifact.rationale)
        self.assertEqual(artifact.related_failure_modes, [])

    def test_from_dict_accepts_confidence_enum(self) -> None:
        data = {
            "id": "imp-1",
            "description": "Add validation",
            "target": "schema-check",
            "confidence": ConfidenceLevel.HIGH,
        }
        artifact = ProposedImprovementValidator.from_dict(data)
        self.assertEqual(artifact.confidence, ConfidenceLevel.HIGH)

    def test_from_dict_rejects_invalid_confidence(self) -> None:
        data = {
            "id": "imp-1",
            "description": "Add validation",
            "target": "schema-check",
            "confidence": "super-high",
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            ProposedImprovementValidator.from_dict(data)
        self.assertIn("Unknown confidence level", str(ctx.exception))

    def test_from_dict_rejects_invalid_failure_mode_in_related(self) -> None:
        data = {
            "id": "imp-1",
            "description": "Add validation",
            "target": "schema-check",
            "related_failure_modes": ["invalid_mode"],
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            ProposedImprovementValidator.from_dict(data)
        self.assertIn("Unknown failure_mode", str(ctx.exception))

    def test_from_dict_handles_empty_related_failure_modes(self) -> None:
        data = {
            "id": "imp-1",
            "description": "Add validation",
            "target": "schema-check",
            "related_failure_modes": [],
        }
        artifact = ProposedImprovementValidator.from_dict(data)
        self.assertEqual(artifact.related_failure_modes, [])


class RunArtifactValidatorTest(unittest.TestCase):
    def _minimal_snapshot_pair(self) -> dict:
        return {
            "primary_snapshot_id": "snap-1",
            "primary_snapshot_path": "/path/to/snap",
        }

    def test_validate_accepts_valid_data(self) -> None:
        data = {
            "run_id": "run-1",
            "timestamp": "2024-01-01T10:00:00",
            "snapshot_pair": self._minimal_snapshot_pair(),
            "comparison_summary": {"nodes": 5},
            "failure_modes": ["missing_evidence"],
            "validation_results": [],
            "proposed_improvements": [],
        }
        RunArtifactValidator.validate(data)

    def test_validate_rejects_missing_run_id(self) -> None:
        data = {
            "timestamp": "2024-01-01T10:00:00",
            "snapshot_pair": self._minimal_snapshot_pair(),
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            RunArtifactValidator.validate(data)
        self.assertIn("run_id", str(ctx.exception))

    def test_validate_rejects_missing_timestamp(self) -> None:
        data = {
            "run_id": "run-1",
            "snapshot_pair": self._minimal_snapshot_pair(),
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            RunArtifactValidator.validate(data)
        self.assertIn("timestamp", str(ctx.exception))

    def test_validate_rejects_missing_snapshot_pair(self) -> None:
        data = {
            "run_id": "run-1",
            "timestamp": "2024-01-01T10:00:00",
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            RunArtifactValidator.validate(data)
        self.assertIn("snapshot_pair", str(ctx.exception))

    def test_validate_rejects_wrong_snapshot_pair_type(self) -> None:
        data = {
            "run_id": "run-1",
            "timestamp": "2024-01-01T10:00:00",
            "snapshot_pair": "not-a-dict",
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            RunArtifactValidator.validate(data)
        self.assertIn("snapshot_pair", str(ctx.exception))

    def test_validate_rejects_wrong_comparison_summary_type(self) -> None:
        data = {
            "run_id": "run-1",
            "timestamp": "2024-01-01T10:00:00",
            "snapshot_pair": self._minimal_snapshot_pair(),
            "comparison_summary": "not-a-dict",
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            RunArtifactValidator.validate(data)
        self.assertIn("comparison_summary", str(ctx.exception))

    def test_validate_rejects_wrong_failure_modes_type(self) -> None:
        data = {
            "run_id": "run-1",
            "timestamp": "2024-01-01T10:00:00",
            "snapshot_pair": self._minimal_snapshot_pair(),
            "failure_modes": "not-a-list",
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            RunArtifactValidator.validate(data)
        self.assertIn("failure_modes", str(ctx.exception))

    def test_validate_rejects_wrong_validation_results_type(self) -> None:
        data = {
            "run_id": "run-1",
            "timestamp": "2024-01-01T10:00:00",
            "snapshot_pair": self._minimal_snapshot_pair(),
            "validation_results": "not-a-list",
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            RunArtifactValidator.validate(data)
        self.assertIn("validation_results", str(ctx.exception))

    def test_validate_rejects_wrong_proposed_improvements_type(self) -> None:
        data = {
            "run_id": "run-1",
            "timestamp": "2024-01-01T10:00:00",
            "snapshot_pair": self._minimal_snapshot_pair(),
            "proposed_improvements": "not-a-list",
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            RunArtifactValidator.validate(data)
        self.assertIn("proposed_improvements", str(ctx.exception))

    def test_from_dict_parses_valid_data(self) -> None:
        data = {
            "run_id": "run-1",
            "timestamp": "2024-01-01T10:00:00",
            "context_name": "alpha-vs-beta",
            "comparison_intent": "prod-comparison",
            "comparison_notes": "Both production clusters",
            "collector_version": "1.0",
            "collection_status": "complete",
            "comparison_summary": {"nodes": 10, "namespaces": 20},
            "missing_evidence": ["logs"],
            "expected_drift_categories": ["helm_releases"],
            "unexpected_drift_categories": ["configmaps"],
            "snapshot_pair": {
                "primary_snapshot_id": "snap-1",
                "primary_snapshot_path": "/path/to/snap1",
                "secondary_snapshot_id": "snap-2",
                "secondary_snapshot_path": "/path/to/snap2",
            },
            "assessment": {
                "assessment_id": "assess-1",
                "schema_version": "1.0",
                "assessment": {"findings": []},
            },
            "validation_results": [
                {"name": "schema-check", "passed": True},
                {"name": "missing-evidence-check", "passed": False, "failure_mode": "missing_evidence"},
            ],
            "failure_modes": ["llm_error", "collection_error"],
            "proposed_improvements": [
                {"id": "imp-1", "description": "Add checks", "target": "schema-check"},
            ],
            "notes": "Test run",
        }
        artifact = RunArtifactValidator.from_dict(data)
        self.assertEqual(artifact.run_id, "run-1")
        self.assertEqual(artifact.context_name, "alpha-vs-beta")
        self.assertEqual(artifact.comparison_intent, "prod-comparison")
        self.assertEqual(artifact.comparison_notes, "Both production clusters")
        self.assertEqual(artifact.comparison_summary, {"nodes": 10, "namespaces": 20})
        self.assertEqual(artifact.missing_evidence, ["logs"])
        self.assertEqual(artifact.expected_drift_categories, ("helm_releases",))
        self.assertEqual(artifact.unexpected_drift_categories, ("configmaps",))

        self.assertIsNotNone(artifact.snapshot_pair)
        assert artifact.snapshot_pair is not None
        self.assertEqual(artifact.snapshot_pair.primary_snapshot_id, "snap-1")
        self.assertEqual(artifact.snapshot_pair.secondary_snapshot_id, "snap-2")

        self.assertIsNotNone(artifact.assessment)
        assert artifact.assessment is not None
        self.assertEqual(artifact.assessment.assessment_id, "assess-1")

        self.assertEqual(len(artifact.validation_results), 2)
        self.assertFalse(artifact.validation_results[1].passed)
        self.assertEqual(artifact.validation_results[1].failure_mode, models.FailureMode.MISSING_EVIDENCE)

        self.assertEqual(artifact.failure_modes, [models.FailureMode.LLM_ERROR, models.FailureMode.COLLECTION_ERROR])

        self.assertEqual(len(artifact.proposed_improvements), 1)
        self.assertEqual(artifact.proposed_improvements[0].id, "imp-1")

    def test_from_dict_handles_optional_assessment(self) -> None:
        data = {
            "run_id": "run-1",
            "timestamp": "2024-01-01T10:00:00",
            "snapshot_pair": self._minimal_snapshot_pair(),
        }
        artifact = RunArtifactValidator.from_dict(data)
        self.assertIsNone(artifact.assessment)

    def test_from_dict_handles_non_dict_assessment(self) -> None:
        data = {
            "run_id": "run-1",
            "timestamp": "2024-01-01T10:00:00",
            "snapshot_pair": self._minimal_snapshot_pair(),
            "assessment": None,
        }
        artifact = RunArtifactValidator.from_dict(data)
        self.assertIsNone(artifact.assessment)

    def test_from_dict_skips_non_dict_validation_results(self) -> None:
        data = {
            "run_id": "run-1",
            "timestamp": "2024-01-01T10:00:00",
            "snapshot_pair": self._minimal_snapshot_pair(),
            "validation_results": [
                {"name": "schema-check", "passed": True},
                "not-a-dict",
                {"name": "missing-check", "passed": False},
            ],
        }
        artifact = RunArtifactValidator.from_dict(data)
        self.assertEqual(len(artifact.validation_results), 2)

    def test_from_dict_skips_non_dict_proposed_improvements(self) -> None:
        data = {
            "run_id": "run-1",
            "timestamp": "2024-01-01T10:00:00",
            "snapshot_pair": self._minimal_snapshot_pair(),
            "proposed_improvements": [
                {"id": "imp-1", "description": "Add checks", "target": "schema-check"},
                "not-a-dict",
            ],
        }
        artifact = RunArtifactValidator.from_dict(data)
        self.assertEqual(len(artifact.proposed_improvements), 1)

    def test_from_dict_uses_defaults_for_optional_fields(self) -> None:
        data = {
            "run_id": "run-1",
            "timestamp": "2024-01-01T10:00:00",
            "snapshot_pair": self._minimal_snapshot_pair(),
        }
        artifact = RunArtifactValidator.from_dict(data)
        self.assertIsNone(artifact.context_name)
        self.assertIsNone(artifact.comparison_intent)
        self.assertEqual(artifact.comparison_summary, {})
        self.assertEqual(artifact.missing_evidence, [])
        self.assertEqual(artifact.validation_results, [])
        self.assertEqual(artifact.failure_modes, [])
        self.assertEqual(artifact.proposed_improvements, [])
        self.assertEqual(artifact.collector_version, "unknown")
        self.assertEqual(artifact.collection_status, "complete")

    def test_from_dict_rejects_invalid_timestamp(self) -> None:
        data = {
            "run_id": "run-1",
            "timestamp": "not-a-timestamp",
            "snapshot_pair": self._minimal_snapshot_pair(),
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            RunArtifactValidator.from_dict(data)
        self.assertIn("Invalid timestamp", str(ctx.exception))

    def test_from_dict_rejects_invalid_nested_snapshot_pair(self) -> None:
        data = {
            "run_id": "run-1",
            "timestamp": "2024-01-01T10:00:00",
            "snapshot_pair": {
                "primary_snapshot_id": "snap-1",
                # missing primary_snapshot_path
            },
        }
        with self.assertRaises(ArtifactValidationError) as ctx:
            RunArtifactValidator.from_dict(data)
        self.assertIn("primary_snapshot_path", str(ctx.exception))


class ArtifactValidationErrorTest(unittest.TestCase):
    def test_is_value_error(self) -> None:
        error = ArtifactValidationError("test message")
        self.assertIsInstance(error, ValueError)


if __name__ == "__main__":
    unittest.main()
