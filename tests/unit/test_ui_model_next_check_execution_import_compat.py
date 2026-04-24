"""Import compatibility tests for model_next_check_execution modularization.

These tests verify that NextCheckExecutionHistoryEntryView and its builder function
remain importable from k8s_diag_agent.ui.model after extraction to model_next_check_execution.py.
"""

from __future__ import annotations

import unittest


class TestExecutionHistoryImportsReExportedFromModel(unittest.TestCase):
    """Verify execution history symbols are importable from model.py (re-export compatibility)."""

    def test_next_check_execution_history_entry_view_importable(self) -> None:
        """NextCheckExecutionHistoryEntryView should be importable from model."""
        from k8s_diag_agent.ui.model import NextCheckExecutionHistoryEntryView  # noqa: F401

    def test_build_execution_history_view_importable(self) -> None:
        """_build_execution_history_view should be importable from model."""
        from k8s_diag_agent.ui.model import _build_execution_history_view  # noqa: F401

    def test_next_check_execution_history_entry_view_instantiation(self) -> None:
        """NextCheckExecutionHistoryEntryView should be instantiable."""
        from k8s_diag_agent.ui.model import NextCheckExecutionHistoryEntryView

        view = NextCheckExecutionHistoryEntryView(
            timestamp="2024-01-01T00:00:00Z",
            cluster_label="test-cluster",
            candidate_description="Test check",
            command_family="kubectl",
            status="success",
            duration_ms=100,
            artifact_path="/path/to/artifact",
            timed_out=False,
            stdout_truncated=False,
            stderr_truncated=False,
            output_bytes_captured=1024,
        )
        self.assertEqual(view.timestamp, "2024-01-01T00:00:00Z")
        self.assertEqual(view.cluster_label, "test-cluster")
        self.assertEqual(view.candidate_description, "Test check")
        self.assertEqual(view.command_family, "kubectl")
        self.assertEqual(view.status, "success")
        self.assertEqual(view.duration_ms, 100)
        self.assertEqual(view.artifact_path, "/path/to/artifact")
        self.assertEqual(view.timed_out, False)
        self.assertEqual(view.stdout_truncated, False)
        self.assertEqual(view.stderr_truncated, False)
        self.assertEqual(view.output_bytes_captured, 1024)

    def test_build_execution_history_view_null_input(self) -> None:
        """_build_execution_history_view should return empty tuple for non-Sequence input."""
        from k8s_diag_agent.ui.model import _build_execution_history_view

        result = _build_execution_history_view(None)
        self.assertEqual(result, ())

        result = _build_execution_history_view("not a sequence")
        self.assertEqual(result, ())

    def test_build_execution_history_view_valid_input(self) -> None:
        """_build_execution_history_view should build correct view from raw data."""
        from k8s_diag_agent.ui.model import NextCheckExecutionHistoryEntryView, _build_execution_history_view

        raw = [
            {
                "timestamp": "2024-01-01T00:00:00Z",
                "clusterLabel": "prod-cluster",
                "candidateDescription": "Check pod logs",
                "commandFamily": "kubectl",
                "status": "success",
                "durationMs": 150,
                "artifactPath": "/runs/run-1/exec-1",
            }
        ]
        result = _build_execution_history_view(raw)
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], NextCheckExecutionHistoryEntryView)
        self.assertEqual(result[0].timestamp, "2024-01-01T00:00:00Z")
        self.assertEqual(result[0].cluster_label, "prod-cluster")
        self.assertEqual(result[0].candidate_description, "Check pod logs")
        self.assertEqual(result[0].command_family, "kubectl")
        self.assertEqual(result[0].status, "success")
        self.assertEqual(result[0].duration_ms, 150)
        self.assertEqual(result[0].artifact_path, "/runs/run-1/exec-1")

    def test_build_execution_history_view_with_provenance(self) -> None:
        """_build_execution_history_view should correctly build alertmanager_provenance field."""
        from k8s_diag_agent.ui.model import _build_execution_history_view

        raw = [
            {
                "timestamp": "2024-01-01T00:00:00Z",
                "status": "success",
                "alertmanagerProvenance": {
                    "matched_dimensions": ["namespace"],
                    "matched_values": {"namespace": ["monitoring"]},
                    "applied_bonus": 10,
                },
            }
        ]
        result = _build_execution_history_view(raw)
        self.assertEqual(len(result), 1)
        self.assertIsNotNone(result[0].alertmanager_provenance)
        self.assertEqual(result[0].alertmanager_provenance.matched_dimensions, ("namespace",))
        self.assertEqual(result[0].alertmanager_provenance.applied_bonus, 10)


class TestExecutionHistoryImportsDirectlyFromModule(unittest.TestCase):
    """Verify execution history symbols are importable directly from model_next_check_execution.py."""

    def test_next_check_execution_history_entry_view_importable_from_module(self) -> None:
        """NextCheckExecutionHistoryEntryView should be importable from model_next_check_execution."""
        from k8s_diag_agent.ui.model_next_check_execution import NextCheckExecutionHistoryEntryView

        assert NextCheckExecutionHistoryEntryView is not None

    def test_build_execution_history_view_importable_from_module(self) -> None:
        """_build_execution_history_view should be importable from model_next_check_execution."""
        from k8s_diag_agent.ui.model_next_check_execution import _build_execution_history_view

        assert _build_execution_history_view is not None
        assert callable(_build_execution_history_view)


class TestExecutionHistoryProvenanceFields(unittest.TestCase):
    """Verify Alertmanager provenance and usefulness fields are correctly preserved in execution history."""

    def test_execution_history_with_alertmanager_relevance(self) -> None:
        """Execution history entries should correctly store alertmanager_relevance fields."""
        from k8s_diag_agent.ui.model import _build_execution_history_view

        raw = [
            {
                "timestamp": "2024-01-01T00:00:00Z",
                "status": "success",
                "alertmanagerRelevance": "relevant",
                "alertmanagerRelevanceSummary": "Matched alert criteria",
            }
        ]
        result = _build_execution_history_view(raw)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].alertmanager_relevance, "relevant")
        self.assertEqual(result[0].alertmanager_relevance_summary, "Matched alert criteria")

    def test_execution_history_with_usefulness_review(self) -> None:
        """Execution history entries should correctly store usefulness review fields."""
        from k8s_diag_agent.ui.model import _build_execution_history_view

        raw = [
            {
                "timestamp": "2024-01-01T00:00:00Z",
                "status": "success",
                "usefulnessClass": "useful",
                "usefulnessSummary": "Found relevant data",
                "usefulnessArtifactId": "art-123",
                "usefulnessArtifactPath": "/runs/run-1/use-1",
                "usefulnessReviewedAt": "2024-01-01T01:00:00Z",
            }
        ]
        result = _build_execution_history_view(raw)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].usefulness_class, "useful")
        self.assertEqual(result[0].usefulness_summary, "Found relevant data")
        self.assertEqual(result[0].usefulness_artifact_id, "art-123")
        self.assertEqual(result[0].usefulness_artifact_path, "/runs/run-1/use-1")
        self.assertEqual(result[0].usefulness_reviewed_at, "2024-01-01T01:00:00Z")

    def test_execution_history_with_candidate_identity(self) -> None:
        """Execution history entries should correctly store candidate identity fields."""
        from k8s_diag_agent.ui.model import _build_execution_history_view

        raw = [
            {
                "timestamp": "2024-01-01T00:00:00Z",
                "status": "success",
                "candidateId": "cand-456",
                "candidateIndex": 3,
                "artifactId": "art-789",
            }
        ]
        result = _build_execution_history_view(raw)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].candidate_id, "cand-456")
        self.assertEqual(result[0].candidate_index, 3)
        self.assertEqual(result[0].artifact_id, "art-789")


if __name__ == "__main__":
    unittest.main()
