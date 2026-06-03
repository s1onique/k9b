"""Tests for signal marker extraction in ExecutionResultDigest."""

import unittest

from k8s_diag_agent.external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisStatus,
)
from k8s_diag_agent.external_analysis.result_digest import (
    build_execution_result_digest,
)


class TestExecutionResultDigestSignalExtraction(unittest.TestCase):
    """Tests for signal marker extraction in ExecutionResultDigest."""

    def test_extracts_multiple_signal_markers(self) -> None:
        """Test that multiple signal markers are extracted."""
        artifact = ExternalAnalysisArtifact(
            tool_name="executor",
            run_id="run-signals",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.FAILED,
            raw_output="""
            Pod nginx-0 is in CrashLoopBackOff state
            Error: ImagePullBackOff detected
            Warning: OOMKilled memory limit exceeded
            """,
        )

        digest = build_execution_result_digest(artifact)

        self.assertIn("CrashLoopBackOff", digest.signals)
        self.assertIn("ImagePullBackOff", digest.signals)
        self.assertIn("OOMKilled", digest.signals)

    def test_deduplicates_signal_markers(self) -> None:
        """Test that duplicate signal markers are not repeated."""
        artifact = ExternalAnalysisArtifact(
            tool_name="executor",
            run_id="run-dedup",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.FAILED,
            raw_output="CrashLoopBackOff detected again CrashLoopBackOff and again",
        )

        digest = build_execution_result_digest(artifact)

        self.assertEqual(digest.signals.count("CrashLoopBackOff"), 1)

    def test_handles_no_signals_in_output(self) -> None:
        """Test that empty signals tuple is returned for clean output."""
        artifact = ExternalAnalysisArtifact(
            tool_name="executor",
            run_id="run-clean",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.SUCCESS,
            raw_output="NAME READY STATUS RESTARTS AGE\npod-xyz 1/1 Running 0 2d",
        )

        digest = build_execution_result_digest(artifact)

        self.assertEqual(digest.signals, ())

    def test_truncation_flags_preserved(self) -> None:
        """Test that truncation flags are preserved from artifact."""
        artifact = ExternalAnalysisArtifact(
            tool_name="executor",
            run_id="run-trunc",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.SUCCESS,
            stdout_truncated=True,
            stderr_truncated=False,
        )

        digest = build_execution_result_digest(artifact)

        self.assertTrue(digest.stdout_truncated)
        self.assertFalse(digest.stderr_truncated)

    def test_extracts_forbidden_signal(self) -> None:
        """Test that Forbidden signal is extracted."""
        artifact = ExternalAnalysisArtifact(
            tool_name="executor",
            run_id="run-forbidden",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.FAILED,
            raw_output="Error: forbidden: pods \"nginx\" is forbidden",
        )

        digest = build_execution_result_digest(artifact)

        self.assertIn("Forbidden", digest.signals)

    def test_extracts_not_found_signal(self) -> None:
        """Test that NotFound signal is extracted."""
        artifact = ExternalAnalysisArtifact(
            tool_name="executor",
            run_id="run-notfound",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.FAILED,
            raw_output="Error from server (NotFound): pods \"nginx\" not found",
        )

        digest = build_execution_result_digest(artifact)

        self.assertIn("NotFound", digest.signals)

    def test_extracts_timeout_signal(self) -> None:
        """Test that Timeout signal is extracted."""
        artifact = ExternalAnalysisArtifact(
            tool_name="executor",
            run_id="run-timeout",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.FAILED,
            raw_output="Error: command timed out after 30s",
        )

        digest = build_execution_result_digest(artifact)

        self.assertIn("Timeout", digest.signals)

    def test_extracts_connection_refused_signal(self) -> None:
        """Test that ConnectionRefused signal is extracted."""
        artifact = ExternalAnalysisArtifact(
            tool_name="executor",
            run_id="run-refused",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.FAILED,
            raw_output="Error: connection refused",
        )

        digest = build_execution_result_digest(artifact)

        self.assertIn("ConnectionRefused", digest.signals)


if __name__ == "__main__":
    unittest.main()