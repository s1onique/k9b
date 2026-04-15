"""Tests for result digest generation.

Tests cover:
- Successful logs command with useful output
- Failed command with meaningful stderr
- Broad/verbose output with truncation
- Empty/minimal output
- Marker extraction
- Deterministic digest generation
"""

import unittest
from datetime import UTC, datetime

from k8s_diag_agent.external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisPurpose,
    ExternalAnalysisStatus,
)
from k8s_diag_agent.external_analysis.result_digest import (
    _build_digest_lines,
    _build_result_digest,
    _classify_failure,
    _extract_signal_markers,
    build_result_digest,
    digest_to_dict,
)


class TestSignalMarkerExtraction(unittest.TestCase):
    """Tests for signal marker extraction from output."""

    def test_extracts_crashloop_marker(self) -> None:
        """Test that CrashLoopBackOff is detected."""
        output = "Warning: BackOff restarting pod nginx-xyz\nCrashLoopBackOff: restarts=5"
        markers = _extract_signal_markers(output)
        self.assertIn("CrashLoopBackOff", markers)

    def test_extracts_imagepull_marker(self) -> None:
        """Test that ImagePullBackOff is detected."""
        output = "ImagePullBackOff: failed to pull image gcr.io/myapp:v1"
        markers = _extract_signal_markers(output)
        self.assertIn("ImagePullBackOff", markers)

    def test_extracts_oom_marker(self) -> None:
        """Test that OOMKilled is detected."""
        output = "Last State: Terminated\nExit Code: 137\nReason: OOMKilled"
        markers = _extract_signal_markers(output)
        self.assertIn("OOMKilled", markers)

    def test_extracts_probe_failure_marker(self) -> None:
        """Test that probe failure is detected."""
        output = "Liveness probe failed: HTTP probe failed"
        markers = _extract_signal_markers(output)
        self.assertIn("ProbeFailed", markers)

    def test_extracts_permission_marker(self) -> None:
        """Test that forbidden/permission issues are detected."""
        output = "Error from server (Forbidden): pods is forbidden"
        markers = _extract_signal_markers(output)
        self.assertIn("Forbidden", markers)

    def test_extracts_not_found_marker(self) -> None:
        """Test that not found issues are detected."""
        output = "Error from server (NotFound): pods \"nginx\" not found"
        markers = _extract_signal_markers(output)
        self.assertIn("NotFound", markers)

    def test_extracts_connection_refused_marker(self) -> None:
        """Test that connection refused is detected."""
        output = "could not connect: connection refused to port 8080"
        markers = _extract_signal_markers(output)
        self.assertIn("ConnectionRefused", markers)

    def test_extracts_tls_marker(self) -> None:
        """Test that TLS/certificate errors are detected."""
        output = "x509: certificate has expired"
        markers = _extract_signal_markers(output)
        self.assertIn("TLSCertError", markers)

    def test_extracts_timeout_marker(self) -> None:
        """Test that timeout is detected."""
        output = "command timed out after 45s"
        markers = _extract_signal_markers(output)
        self.assertIn("Timeout", markers)

    def test_no_markers_on_clean_output(self) -> None:
        """Test that no markers are extracted from clean output."""
        output = "NAME       READY   STATUS    RESTARTS   AGE\nnginx-pod  1/1     Running   0          2d"
        markers = _extract_signal_markers(output)
        self.assertEqual(markers, ())

    def test_empty_output_returns_empty_tuple(self) -> None:
        """Test that empty output returns empty markers."""
        markers = _extract_signal_markers(None)
        self.assertEqual(markers, ())

    def test_multiple_markers_deduplicated(self) -> None:
        """Test that multiple detected markers are deduplicated."""
        output = "CrashLoopBackOff and ImagePullBackOff detected"
        markers = _extract_signal_markers(output)
        self.assertIn("CrashLoopBackOff", markers)
        self.assertIn("ImagePullBackOff", markers)


class TestFailureClassification(unittest.TestCase):
    """Tests for failure classification."""

    def test_timeout_classification(self) -> None:
        """Test that timed out commands are classified as timeout."""
        result = _classify_failure(stderr=None, exit_code=None, timed_out=True)
        self.assertEqual(result, "timeout")

    def test_not_found_classification(self) -> None:
        """Test that not found errors are classified correctly."""
        result = _classify_failure(stderr="pods \"test\" not found", exit_code=None, timed_out=False)
        self.assertEqual(result, "not_found")

    def test_permission_denied_classification(self) -> None:
        """Test that forbidden errors are classified correctly."""
        result = _classify_failure(stderr="pods is forbidden", exit_code=None, timed_out=False)
        self.assertEqual(result, "permission_denied")

    def test_exit_code_classification(self) -> None:
        """Test that non-zero exit codes are classified."""
        result = _classify_failure(stderr=None, exit_code=1, timed_out=False)
        self.assertEqual(result, "exit_1")

    def test_no_failure_on_clean(self) -> None:
        """Test that clean output returns None."""
        result = _classify_failure(stderr=None, exit_code=0, timed_out=False)
        self.assertIsNone(result)


class TestResultDigestBuild(unittest.TestCase):
    """Tests for result digest string building."""

    def test_success_with_bytes(self) -> None:
        """Test success digest includes bytes captured."""
        result = _build_result_digest(
            status="success",
            error_summary=None,
            timed_out=False,
            exit_code=None,
            output_bytes_captured=1234,
        )
        self.assertEqual(result, "OK (1234B)")

    def test_success_without_bytes(self) -> None:
        """Test success digest without bytes captured."""
        result = _build_result_digest(
            status="success",
            error_summary=None,
            timed_out=False,
            exit_code=None,
            output_bytes_captured=None,
        )
        self.assertEqual(result, "OK")

    def test_timed_out(self) -> None:
        """Test timed out returns TIMED_OUT."""
        result = _build_result_digest(
            status="failed",
            error_summary=None,
            timed_out=True,
            exit_code=None,
            output_bytes_captured=None,
        )
        self.assertEqual(result, "TIMED_OUT")

    def test_failed_with_error_summary(self) -> None:
        """Test failed command with error summary."""
        result = _build_result_digest(
            status="failed",
            error_summary="pods \"test\" not found",
            timed_out=False,
            exit_code=None,
            output_bytes_captured=None,
        )
        self.assertEqual(result, "pods \"test\" not found")

    def test_failed_truncates_long_error(self) -> None:
        """Test that long error summaries are truncated."""
        long_error = "this is a very long error message that exceeds 80 characters and should be truncated"
        result = _build_result_digest(
            status="failed",
            error_summary=long_error,
            timed_out=False,
            exit_code=None,
            output_bytes_captured=None,
        )
        self.assertEqual(len(result), 81)  # 80 chars + "…"
        self.assertTrue(result.endswith("…"))

    def test_failed_with_exit_code(self) -> None:
        """Test failed with exit code when no error summary."""
        result = _build_result_digest(
            status="failed",
            error_summary=None,
            timed_out=False,
            exit_code=2,
            output_bytes_captured=None,
        )
        self.assertEqual(result, "FAILED: exit_code=2")

    def test_skipped(self) -> None:
        """Test skipped status."""
        result = _build_result_digest(
            status="skipped",
            error_summary=None,
            timed_out=False,
            exit_code=None,
            output_bytes_captured=None,
        )
        self.assertEqual(result, "SKIPPED")


class TestDigestLinesBuild(unittest.TestCase):
    """Tests for digest lines extraction."""

    def test_extracts_first_lines(self) -> None:
        """Test that first few lines are extracted without truncation indicator when within limit."""
        output = "line1\nline2\nline3\nline4"
        lines = _build_digest_lines(output, max_lines=5)
        self.assertEqual(lines, ("line1", "line2", "line3", "line4"))

    def test_adds_truncation_indicator(self) -> None:
        """Test that truncation indicator is added when lines exceed max."""
        output = "line1\nline2\nline3\nline4\nline5\nline6"
        lines = _build_digest_lines(output, max_lines=3)
        self.assertEqual(len(lines), 4)  # 3 content + 1 truncation indicator
        self.assertEqual(lines[-1], "[+3 more lines]")

    def test_filters_empty_lines(self) -> None:
        """Test that empty lines are filtered."""
        output = "line1\n\n\nline2\n\n"
        lines = _build_digest_lines(output, max_lines=5)
        self.assertEqual(lines, ("line1", "line2"))

    def test_empty_output_returns_empty_tuple(self) -> None:
        """Test that empty output returns empty tuple."""
        lines = _build_digest_lines(None, max_lines=5)
        self.assertEqual(lines, ())


class TestBuildResultDigest(unittest.TestCase):
    """Tests for full ResultDigest building."""

    def test_digest_from_success_artifact(self) -> None:
        """Test digest from successful execution artifact."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-runner",
            run_id="run-1",
            cluster_label="test-cluster",
            run_label="Test Run",
            status=ExternalAnalysisStatus.SUCCESS,
            raw_output="pod-xyz   1/1   Running   0   2d",
            output_bytes_captured=50,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION,
            timestamp=datetime.now(UTC),
        )

        digest = build_result_digest(artifact)

        self.assertEqual(digest.result_digest, "OK (50B)")
        self.assertEqual(len(digest.result_digest_lines), 1)
        self.assertEqual(digest.signal_markers, ())
        self.assertIsNone(digest.failure_class)
        self.assertIsNone(digest.exit_code)

    def test_digest_from_failed_artifact(self) -> None:
        """Test digest from failed execution artifact."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-runner",
            run_id="run-1",
            cluster_label="test-cluster",
            run_label="Test Run",
            status=ExternalAnalysisStatus.FAILED,
            raw_output="Error from server (NotFound): pods \"test\" not found",
            error_summary="pods \"test\" not found",
            output_bytes_captured=60,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION,
            timestamp=datetime.now(UTC),
        )

        digest = build_result_digest(artifact)

        self.assertEqual(digest.result_digest, "pods \"test\" not found")
        self.assertEqual(digest.failure_class, "not_found")
        self.assertIn("NotFound", digest.signal_markers)

    def test_digest_from_timed_out_artifact(self) -> None:
        """Test digest from timed-out artifact."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-runner",
            run_id="run-1",
            cluster_label="test-cluster",
            run_label="Test Run",
            status=ExternalAnalysisStatus.FAILED,
            timed_out=True,
            output_bytes_captured=100,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION,
            timestamp=datetime.now(UTC),
        )

        digest = build_result_digest(artifact)

        self.assertEqual(digest.result_digest, "TIMED_OUT")
        self.assertEqual(digest.failure_class, "timeout")
        # stdout_truncated follows artifact value (None if not set)
        self.assertIsNone(digest.stdout_truncated)

    def test_digest_with_crashloop_output(self) -> None:
        """Test digest extracts CrashLoopBackOff marker."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-runner",
            run_id="run-1",
            cluster_label="test-cluster",
            run_label="Test Run",
            status=ExternalAnalysisStatus.SUCCESS,
            raw_output="Warning: BackOff restarting\nCrashLoopBackOff: restarts=5",
            output_bytes_captured=80,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION,
            timestamp=datetime.now(UTC),
        )

        digest = build_result_digest(artifact)

        self.assertIn("CrashLoopBackOff", digest.signal_markers)

    def test_digest_with_empty_raw_output(self) -> None:
        """Test digest handles empty raw output."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-runner",
            run_id="run-1",
            cluster_label="test-cluster",
            run_label="Test Run",
            status=ExternalAnalysisStatus.SUCCESS,
            raw_output=None,
            output_bytes_captured=0,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION,
            timestamp=datetime.now(UTC),
        )

        digest = build_result_digest(artifact)

        self.assertEqual(digest.result_digest, "OK")
        self.assertEqual(digest.result_digest_lines, ())
        self.assertEqual(digest.signal_markers, ())


class TestDigestToDict(unittest.TestCase):
    """Tests for digest_to_dict conversion."""

    def test_converts_all_fields(self) -> None:
        """Test that all fields are converted to dict."""
        from k8s_diag_agent.external_analysis.result_digest import ResultDigest

        digest = ResultDigest(
            result_digest="OK (100B)",
            result_digest_lines=("line1", "line2"),
            stderr_digest="some error",
            stdout_digest="some output",
            signal_markers=("NotFound", "ErrorIndicator"),
            failure_class="not_found",
            exit_code=1,
            output_bytes_captured=100,
            stdout_truncated=False,
            stderr_truncated=True,
        )

        result = digest_to_dict(digest)

        self.assertEqual(result["result_digest"], "OK (100B)")
        self.assertEqual(result["result_digest_lines"], ["line1", "line2"])
        self.assertEqual(result["stderr_digest"], "some error")
        self.assertEqual(result["stdout_digest"], "some output")
        self.assertEqual(result["signal_markers"], ["NotFound", "ErrorIndicator"])
        self.assertEqual(result["failure_class"], "not_found")
        self.assertEqual(result["exit_code"], 1)
        self.assertEqual(result["output_bytes_captured"], 100)
        self.assertFalse(result["stdout_truncated"])
        self.assertTrue(result["stderr_truncated"])


class TestDeterminism(unittest.TestCase):
    """Tests for deterministic digest generation."""

    def test_same_artifact_produces_same_digest(self) -> None:
        """Test that the same artifact always produces the same digest."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-runner",
            run_id="run-1",
            cluster_label="test-cluster",
            run_label="Test Run",
            status=ExternalAnalysisStatus.SUCCESS,
            raw_output="line1\nline2\nline3",
            output_bytes_captured=50,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION,
            timestamp=datetime.now(UTC),
        )

        digest1 = build_result_digest(artifact)
        digest2 = build_result_digest(artifact)

        self.assertEqual(digest1.result_digest, digest2.result_digest)
        self.assertEqual(digest1.result_digest_lines, digest2.result_digest_lines)
        self.assertEqual(digest1.signal_markers, digest2.signal_markers)


if __name__ == "__main__":
    unittest.main()
