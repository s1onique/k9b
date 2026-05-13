"""Unit tests for artifact filtering in incident report and worklist provenance.

Coverage goals (per epic BETA-G7):
- Skipped artifacts are filtered out of sourceArtifactRefs
- Placeholder artifacts (adapter-not-registered) are filtered
- Useful/partial artifacts remain visible
- Empty/no-content artifacts are filtered
- Mixed refs: only non-useful ones are filtered
- No fake/unknown placeholder paths are introduced
- Filtering does not remove all provenance from a claim
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from k8s_diag_agent.external_analysis.artifact import ExternalAnalysisArtifact, ExternalAnalysisStatus
from k8s_diag_agent.ui.api_incident_report_filtering import (
    _is_placeholder_artifact,
    _has_useful_evidence,
    _should_filter_artifact,
    filter_artifact_links,
    filter_artifact_refs_preserving_minimum,
)


class SkippedArtifactFilteringTests(unittest.TestCase):
    """Tests for filtering skipped artifacts from provenance."""

    def test_skipped_artifact_is_filtered(self) -> None:
        """Artifacts with status=skipped should be filtered."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-1",
            cluster_label="cluster-a",
            status=ExternalAnalysisStatus.SKIPPED,
            skip_reason="Adapter not configured for this purpose",
        )
        self.assertTrue(_should_filter_artifact(artifact))

    def test_skipped_artifact_with_skip_reason_only_is_filtered(self) -> None:
        """Skipped artifacts with only skip_reason and no evidence are filtered."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-1",
            cluster_label="cluster-a",
            status=ExternalAnalysisStatus.SKIPPED,
            skip_reason="Resource budget exhausted",
        )
        self.assertTrue(_should_filter_artifact(artifact))

    def test_skipped_artifact_preserved_in_mixed_refs(self) -> None:
        """When mixed refs include a skipped artifact, only the skipped one is filtered."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)

            # Create a successful artifact
            success_artifact = ExternalAnalysisArtifact(
                tool_name="test-tool",
                run_id="run-1",
                cluster_label="cluster-a",
                status=ExternalAnalysisStatus.SUCCESS,
                summary="Found important diagnostic data",
                raw_output="key=value\ncount=5",
            )
            success_path = runs_dir / "runs/run-1/external-analysis/success-artifact.json"
            success_path.parent.mkdir(parents=True, exist_ok=True)
            success_path.write_text(json.dumps(success_artifact.to_dict()))

            # Create a skipped artifact
            skipped_artifact = ExternalAnalysisArtifact(
                tool_name="test-tool",
                run_id="run-1",
                cluster_label="cluster-a",
                status=ExternalAnalysisStatus.SKIPPED,
                skip_reason="Skipped for testing",
            )
            skipped_path = runs_dir / "runs/run-1/external-analysis/skipped-artifact.json"
            skipped_path.parent.mkdir(parents=True, exist_ok=True)
            skipped_path.write_text(json.dumps(skipped_artifact.to_dict()))

            links = [
                {"label": "Success Ref", "path": str(success_path.relative_to(runs_dir))},
                {"label": "Skipped Ref", "path": str(skipped_path.relative_to(runs_dir))},
            ]

            result = filter_artifact_links(links, runs_dir)

            # Only the successful artifact should remain
            self.assertEqual(len(result.filtered_links), 1)
            self.assertEqual(result.filtered_links[0]["label"], "Success Ref")
            self.assertTrue(result.had_filtered_refs)


class PlaceholderArtifactFilteringTests(unittest.TestCase):
    """Tests for filtering placeholder artifacts (adapter-not-registered, etc.)."""

    def test_adapter_not_registered_placeholder_is_filtered(self) -> None:
        """Artifacts with 'adapter is not registered' summary are filtered."""
        artifact = ExternalAnalysisArtifact(
            tool_name="review-enrichment",
            run_id="run-1",
            cluster_label="cluster-a",
            status=ExternalAnalysisStatus.SKIPPED,
            summary="Adapter is not registered for review enrichment",
            skip_reason="Adapter is not registered",
        )
        self.assertTrue(_should_filter_artifact(artifact))
        self.assertTrue(_is_placeholder_artifact(artifact))

    def test_adapter_not_configured_placeholder_is_filtered(self) -> None:
        """Artifacts with 'adapter is not configured' summary are filtered."""
        artifact = ExternalAnalysisArtifact(
            tool_name="k8sgpt",
            run_id="run-1",
            cluster_label="cluster-a",
            status=ExternalAnalysisStatus.SKIPPED,
            summary="Adapter is not configured",
            skip_reason="Provider not configured in settings",
        )
        self.assertTrue(_should_filter_artifact(artifact))
        self.assertTrue(_is_placeholder_artifact(artifact))

    def test_error_summary_placeholder_is_filtered(self) -> None:
        """Artifacts with placeholder error_summary are filtered."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-1",
            cluster_label="cluster-a",
            status=ExternalAnalysisStatus.FAILED,
            error_summary="Adapter is not registered for this operation",
        )
        self.assertTrue(_is_placeholder_artifact(artifact))
        self.assertTrue(_should_filter_artifact(artifact))

    def test_skip_reason_not_registered_is_filtered(self) -> None:
        """Artifacts with 'not registered' in skip_reason are filtered."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-1",
            cluster_label="cluster-a",
            status=ExternalAnalysisStatus.SKIPPED,
            skip_reason="The provider is not registered for external analysis",
        )
        self.assertTrue(_is_placeholder_artifact(artifact))
        self.assertTrue(_should_filter_artifact(artifact))

    def test_meaningful_error_summary_preserved(self) -> None:
        """Artifacts with meaningful error_summary are preserved."""
        artifact = ExternalAnalysisArtifact(
            tool_name="kubectl-logs",
            run_id="run-1",
            cluster_label="cluster-a",
            status=ExternalAnalysisStatus.FAILED,
            error_summary="Connection timeout after 30s; namespace default unreachable",
        )
        self.assertFalse(_is_placeholder_artifact(artifact))
        self.assertTrue(_has_useful_evidence(artifact))
        self.assertFalse(_should_filter_artifact(artifact))


class UsefulArtifactPreservationTests(unittest.TestCase):
    """Tests for preserving useful/partial artifacts."""

    def test_successful_artifact_with_output_is_preserved(self) -> None:
        """Successful artifacts with actual output are preserved."""
        artifact = ExternalAnalysisArtifact(
            tool_name="kubectl-logs",
            run_id="run-1",
            cluster_label="cluster-a",
            status=ExternalAnalysisStatus.SUCCESS,
            summary="Collected 15 pod log entries",
            raw_output="2026-01-01 10:00:00 Pod started\n2026-01-01 10:00:05 Crash detected",
        )
        self.assertFalse(_should_filter_artifact(artifact))
        self.assertTrue(_has_useful_evidence(artifact))

    def test_successful_artifact_with_payload_is_preserved(self) -> None:
        """Successful artifacts with payload content are preserved."""
        artifact = ExternalAnalysisArtifact(
            tool_name="kubectl-top",
            run_id="run-1",
            cluster_label="cluster-a",
            status=ExternalAnalysisStatus.SUCCESS,
            summary="Resource metrics collected",
            payload={"cpu_usage_millicores": 450, "memory_usage_mb": 1024},
        )
        self.assertFalse(_should_filter_artifact(artifact))
        self.assertTrue(_has_useful_evidence(artifact))

    def test_failed_artifact_with_failure_metadata_is_preserved(self) -> None:
        """Failed artifacts with failure_metadata contain diagnostic context."""
        artifact = ExternalAnalysisArtifact(
            tool_name="kubectl-top",
            run_id="run-1",
            cluster_label="cluster-a",
            status=ExternalAnalysisStatus.FAILED,
            error_summary="Metrics server unavailable",
            failure_metadata={
                "failure_class": "upstream_timeout",
                "suggested_next_move": "Check metrics-server pod health",
            },
        )
        self.assertFalse(_should_filter_artifact(artifact))
        self.assertTrue(_has_useful_evidence(artifact))

    def test_failed_artifact_with_meaningful_error_is_preserved(self) -> None:
        """Failed artifacts with meaningful error_summary provide diagnostic value."""
        artifact = ExternalAnalysisArtifact(
            tool_name="kubectl-logs",
            run_id="run-1",
            cluster_label="cluster-a",
            status=ExternalAnalysisStatus.FAILED,
            error_summary="Pod not found in namespace production",
        )
        self.assertFalse(_should_filter_artifact(artifact))
        self.assertTrue(_has_useful_evidence(artifact))


class EmptyArtifactFilteringTests(unittest.TestCase):
    """Tests for filtering empty/no-content artifacts."""

    def test_empty_failed_artifact_is_filtered(self) -> None:
        """Failed artifacts with no content are filtered."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-1",
            cluster_label="cluster-a",
            status=ExternalAnalysisStatus.FAILED,
        )
        self.assertFalse(_has_useful_evidence(artifact))
        self.assertTrue(_should_filter_artifact(artifact))

    def test_empty_success_artifact_is_filtered(self) -> None:
        """Successful artifacts with no content are filtered."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-1",
            cluster_label="cluster-a",
            status=ExternalAnalysisStatus.SUCCESS,
        )
        self.assertFalse(_has_useful_evidence(artifact))
        self.assertTrue(_should_filter_artifact(artifact))

    def test_skipped_with_only_skip_reason_is_filtered(self) -> None:
        """Skipped artifacts with only skip_reason and no other content are filtered."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-1",
            cluster_label="cluster-a",
            status=ExternalAnalysisStatus.SKIPPED,
            skip_reason="Skipped due to configuration",
        )
        self.assertFalse(_has_useful_evidence(artifact))
        self.assertTrue(_should_filter_artifact(artifact))


class MixedRefsFilteringTests(unittest.TestCase):
    """Tests for mixed refs where only some should be filtered."""

    def test_mixed_refs_preserves_successful_filters_skipped(self) -> None:
        """Mixed refs: successful preserved, skipped filtered."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)

            # Create successful artifact with useful content
            success_artifact = ExternalAnalysisArtifact(
                tool_name="kubectl-logs",
                run_id="run-1",
                cluster_label="cluster-a",
                status=ExternalAnalysisStatus.SUCCESS,
                summary="Found CrashLoopBackOff pattern",
                raw_output="CrashLoopBackOff: Exit code 1",
            )
            success_path = runs_dir / "runs/run-1/external-analysis/useful-logs.json"
            success_path.parent.mkdir(parents=True, exist_ok=True)
            success_path.write_text(json.dumps(success_artifact.to_dict()))

            # Create skipped artifact
            skipped_artifact = ExternalAnalysisArtifact(
                tool_name="k8sgpt",
                run_id="run-1",
                cluster_label="cluster-a",
                status=ExternalAnalysisStatus.SKIPPED,
                skip_reason="Adapter not configured",
            )
            skipped_path = runs_dir / "runs/run-1/external-analysis/skipped-k8sgpt.json"
            skipped_path.parent.mkdir(parents=True, exist_ok=True)
            skipped_path.write_text(json.dumps(skipped_artifact.to_dict()))

            # Create placeholder artifact
            placeholder_artifact = ExternalAnalysisArtifact(
                tool_name="review-enrichment",
                run_id="run-1",
                cluster_label="cluster-a",
                status=ExternalAnalysisStatus.SKIPPED,
                summary="Adapter is not registered",
            )
            placeholder_path = runs_dir / "runs/run-1/external-analysis/placeholder-enrichment.json"
            placeholder_path.parent.mkdir(parents=True, exist_ok=True)
            placeholder_path.write_text(json.dumps(placeholder_artifact.to_dict()))

            links = [
                {"label": "Useful Logs", "path": str(success_path.relative_to(runs_dir))},
                {"label": "Skipped K8sGPT", "path": str(skipped_path.relative_to(runs_dir))},
                {"label": "Placeholder Enrichment", "path": str(placeholder_path.relative_to(runs_dir))},
            ]

            result = filter_artifact_links(links, runs_dir)

            # Only the useful artifact should remain
            self.assertEqual(len(result.filtered_links), 1)
            self.assertEqual(result.filtered_links[0]["label"], "Useful Logs")
            self.assertTrue(result.had_filtered_refs)
            self.assertEqual(result.original_count, 3)

    def test_multiple_preserved_refs_all_survive(self) -> None:
        """Multiple useful refs all survive filtering."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)

            # Create two successful artifacts
            for i, label in enumerate(["Assessment", "Drilldown"]):
                artifact = ExternalAnalysisArtifact(
                    tool_name="test-tool",
                    run_id="run-1",
                    cluster_label="cluster-a",
                    status=ExternalAnalysisStatus.SUCCESS,
                    summary=f"Useful {label} data",
                    raw_output=f"Content for {label}",
                )
                path = runs_dir / f"runs/run-1/{label.lower()}.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(artifact.to_dict()))

            links = [
                {"label": "Assessment", "path": "runs/run-1/assessment.json"},
                {"label": "Drilldown", "path": "runs/run-1/drilldown.json"},
            ]

            result = filter_artifact_links(links, runs_dir)

            # Both useful artifacts should remain
            self.assertEqual(len(result.filtered_links), 2)
            self.assertFalse(result.had_filtered_refs)


class PreservingMinimumTests(unittest.TestCase):
    """Tests for preserving minimum provenance when filtering would remove all refs."""

    def test_filtering_all_would_remove_preserves_original(self) -> None:
        """When filtering would remove all refs, original list is preserved."""
        links = [
            {"label": "Unknown Ref", "path": "runs/run-1/unknown.json"},
        ]

        # This would filter everything, but we preserve minimum
        result = filter_artifact_refs_preserving_minimum(links)
        self.assertEqual(result, links)

    def test_filtering_some_preserves_filtered(self) -> None:
        """When filtering removes only some refs, filtered list is returned."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)

            # Create one useful artifact
            artifact = ExternalAnalysisArtifact(
                tool_name="test-tool",
                run_id="run-1",
                cluster_label="cluster-a",
                status=ExternalAnalysisStatus.SUCCESS,
                summary="Useful data",
                raw_output="content",
            )
            path = runs_dir / "runs/run-1/useful.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(artifact.to_dict()))

            links = [
                {"label": "Useful", "path": "runs/run-1/useful.json"},
            ]

            result = filter_artifact_refs_preserving_minimum(links, runs_dir)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["label"], "Useful")


class NoFakeUnknownTests(unittest.TestCase):
    """Tests ensuring no fake/unknown placeholder paths are introduced."""

    def test_no_unknown_label_in_filtered(self) -> None:
        """Filtered results should not contain 'unknown' labels."""
        links = [
            {"label": "Assessment", "path": "runs/run-1/assessment.json"},
            {"label": "Skipped", "path": "runs/run-1/skipped.json"},
        ]

        result = filter_artifact_links(links)
        labels = [ref.get("label") for ref in result.filtered_links]
        self.assertNotIn("unknown", labels)
        self.assertNotIn("Unknown", labels)

    def test_no_unknown_path_in_filtered(self) -> None:
        """Filtered results should not contain 'unknown' paths."""
        links = [
            {"label": "Assessment", "path": "assessments/cluster-a.json"},
            {"label": "Skipped", "path": "runs/run-1/skipped.json"},
        ]

        result = filter_artifact_links(links)
        paths = [ref.get("path") for ref in result.filtered_links]
        self.assertNotIn("unknown", paths)


class EmptyLinksTests(unittest.TestCase):
    """Tests for empty/edge case inputs."""

    def test_empty_links_returns_empty(self) -> None:
        """Empty links list returns empty result."""
        result = filter_artifact_links([])
        self.assertEqual(result.filtered_links, [])
        self.assertFalse(result.had_filtered_refs)
        self.assertEqual(result.original_count, 0)

    def test_none_path_skipped(self) -> None:
        """Links with None path are skipped during filtering."""
        links = [
            {"label": "Valid Ref", "path": "runs/run-1/valid.json"},
            {"label": "Missing Path", "path": None},  # type: ignore
        ]

        result = filter_artifact_links(links)
        # Should not crash, should return valid ref
        self.assertLessEqual(len(result.filtered_links), 1)


if __name__ == "__main__":
    unittest.main()