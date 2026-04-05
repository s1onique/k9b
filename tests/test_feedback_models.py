import unittest

from tests.path_helper import ensure_src_in_path


ensure_src_in_path()

from k8s_diag_agent.feedback import FailureMode
from k8s_diag_agent.feedback.validators import ArtifactValidationError, RunArtifactValidator


class FeedbackModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base_run = {
            "run_id": "run-123",
            "timestamp": "2026-04-05T00:00:00+00:00",
            "context_name": "fixture-alpha",
            "collector_version": "v0.1",
            "collection_status": "complete",
            "comparison_summary": {"added": 1, "removed": 0, "changed": 2},
            "missing_evidence": ["events"],
            "snapshot_pair": {
                "primary_snapshot_id": "snap-a",
                "primary_snapshot_path": "runs/snapshots/snap-a.json",
                "secondary_snapshot_id": "snap-b",
                "secondary_snapshot_path": "runs/snapshots/snap-b.json",
                "comparison_summary": {"deployment": 1},
                "status": "complete",
                "missing_evidence": ["logs"],
                "start_time": "2026-04-05T00:00:00+00:00",
                "end_time": "2026-04-05T00:05:00+00:00",
            },
            "assessment": {
                "assessment_id": "assessment-1",
                "schema_version": "assessment-schema:v1",
                "assessment": {"observed_signals": []},
                "overall_confidence": "low",
            },
            "validation_results": [
                {
                    "name": "schema-check",
                    "passed": False,
                    "errors": ["missing_signals"],
                    "checked_at": "2026-04-05T00:00:01+00:00",
                    "failure_mode": "validation_failure",
                }
            ],
            "failure_modes": ["missing_evidence"],
            "proposed_improvements": [
                {
                    "id": "impr-1",
                    "description": "Document partial snapshot handling",
                    "target": "docs/schemas/run-artifact-layout.md",
                    "confidence": "medium",
                    "related_failure_modes": ["missing_evidence"],
                }
            ],
            "notes": "Baseline fixture run",
        }

    def test_run_artifact_validator_builds_artifact(self) -> None:
        artifact = RunArtifactValidator.from_dict(self.base_run)
        self.assertEqual(artifact.run_id, "run-123")
        self.assertEqual(artifact.context_name, "fixture-alpha")
        self.assertEqual(artifact.collection_status, "complete")
        self.assertEqual(artifact.snapshot_pair.primary_snapshot_id, "snap-a")
        self.assertEqual(artifact.snapshot_pair.comparison_summary, {"deployment": 1})
        self.assertEqual(artifact.failure_modes, [FailureMode.MISSING_EVIDENCE])
        self.assertEqual(artifact.missing_evidence, ["events"])
        self.assertEqual(len(artifact.validation_results), 1)
        validation = artifact.validation_results[0]
        self.assertFalse(validation.passed)
        self.assertEqual(validation.failure_mode, FailureMode.VALIDATION_FAILURE)
        self.assertEqual(len(artifact.proposed_improvements), 1)
        improvement = artifact.proposed_improvements[0]
        self.assertEqual(improvement.id, "impr-1")
        self.assertEqual(improvement.target, "docs/schemas/run-artifact-layout.md")
        self.assertEqual(improvement.related_failure_modes, [FailureMode.MISSING_EVIDENCE])

    def test_run_artifact_validator_requires_snapshot_pair(self) -> None:
        incomplete = {
            "run_id": "run-456",
            "timestamp": "2026-04-05T00:00:00+00:00",
        }
        with self.assertRaises(ArtifactValidationError):
            RunArtifactValidator.from_dict(incomplete)
