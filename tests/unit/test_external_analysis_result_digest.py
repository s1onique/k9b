"""Tests for external analysis result_digest module.

Tests cover:
- ResultDigest class instantiation and properties
- Digest building with various artifact states
- Payload exit code parsing edge cases
- Serialization with digest_to_dict
- Missing field handling
- Default values
- Frozen dataclass behavior
"""

import unittest

from k8s_diag_agent.external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisStatus,
)
from k8s_diag_agent.external_analysis.result_digest import (
    ResultDigest,
    _classify_failure,
    _coerce_optional_int,
    _extract_signal_markers,
    build_result_digest,
    digest_to_dict,
)


class TestResultDigestClass(unittest.TestCase):
    """Tests for ResultDigest dataclass."""

    def test_result_digest_instantiation(self) -> None:
        """Test creating ResultDigest with all fields."""
        digest = ResultDigest(
            result_digest="OK (100B)",
            result_digest_lines=("line1", "line2", "line3"),
            stderr_digest="error message",
            stdout_digest="output message",
            signal_markers=("NotFound", "ErrorIndicator"),
            failure_class="not_found",
            exit_code=1,
            output_bytes_captured=100,
            stdout_truncated=False,
            stderr_truncated=True,
        )

        self.assertEqual(digest.result_digest, "OK (100B)")
        self.assertEqual(digest.result_digest_lines, ("line1", "line2", "line3"))
        self.assertEqual(digest.stderr_digest, "error message")
        self.assertEqual(digest.stdout_digest, "output message")
        self.assertEqual(digest.signal_markers, ("NotFound", "ErrorIndicator"))
        self.assertEqual(digest.failure_class, "not_found")
        self.assertEqual(digest.exit_code, 1)
        self.assertEqual(digest.output_bytes_captured, 100)
        self.assertFalse(digest.stdout_truncated)
        self.assertTrue(digest.stderr_truncated)

    def test_result_digest_with_none_optional_fields(self) -> None:
        """Test creating ResultDigest with None optional fields."""
        digest = ResultDigest(
            result_digest="OK",
            result_digest_lines=(),
            stderr_digest=None,
            stdout_digest=None,
            signal_markers=(),
            failure_class=None,
            exit_code=None,
            output_bytes_captured=None,
            stdout_truncated=None,
            stderr_truncated=None,
        )

        self.assertEqual(digest.result_digest, "OK")
        self.assertEqual(digest.result_digest_lines, ())
        self.assertIsNone(digest.stderr_digest)
        self.assertIsNone(digest.stdout_digest)
        self.assertEqual(digest.signal_markers, ())
        self.assertIsNone(digest.failure_class)
        self.assertIsNone(digest.exit_code)
        self.assertIsNone(digest.output_bytes_captured)
        self.assertIsNone(digest.stdout_truncated)
        self.assertIsNone(digest.stderr_truncated)

    def test_result_digest_is_frozen(self) -> None:
        """Test that ResultDigest is frozen and immutable."""
        digest = ResultDigest(
            result_digest="OK",
            result_digest_lines=(),
            stderr_digest=None,
            stdout_digest=None,
            signal_markers=(),
            failure_class=None,
            exit_code=None,
            output_bytes_captured=None,
            stdout_truncated=None,
            stderr_truncated=None,
        )

        with self.assertRaises(AttributeError):
            digest.result_digest = "CHANGED"  # type: ignore[misc]

    def test_result_digest_with_empty_tuples(self) -> None:
        """Test ResultDigest with empty tuple fields."""
        digest = ResultDigest(
            result_digest="FAILED",
            result_digest_lines=tuple(),
            stderr_digest=None,
            stdout_digest=None,
            signal_markers=tuple(),
            failure_class="exit_1",
            exit_code=1,
            output_bytes_captured=0,
            stdout_truncated=False,
            stderr_truncated=False,
        )

        self.assertEqual(digest.result_digest_lines, tuple())
        self.assertEqual(digest.signal_markers, tuple())


class TestCoerceOptionalInt(unittest.TestCase):
    """Tests for _coerce_optional_int helper function."""

    def test_returns_none_for_none_input(self) -> None:
        """Test that None input returns None."""
        result = _coerce_optional_int(None)
        self.assertIsNone(result)

    def test_returns_int_for_int_input(self) -> None:
        """Test that int input returns int."""
        result = _coerce_optional_int(42)
        self.assertEqual(result, 42)

    def test_returns_int_for_float_input(self) -> None:
        """Test that float input returns truncated int."""
        result = _coerce_optional_int(42.9)
        self.assertEqual(result, 42)

    def test_returns_int_for_numeric_string(self) -> None:
        """Test that valid numeric string is parsed."""
        result = _coerce_optional_int("123")
        self.assertEqual(result, 123)

    def test_returns_none_for_invalid_string(self) -> None:
        """Test that invalid string returns None."""
        result = _coerce_optional_int("not-a-number")
        self.assertIsNone(result)

    def test_coerces_boolean_to_int(self) -> None:
        """Test that boolean input is coerced to int (bool is subclass of int)."""
        # Note: In Python, bool is a subclass of int, so True becomes 1, False becomes 0
        result = _coerce_optional_int(True)
        self.assertEqual(result, 1)
        result = _coerce_optional_int(False)
        self.assertEqual(result, 0)

    def test_returns_none_for_list_input(self) -> None:
        """Test that list input returns None."""
        result = _coerce_optional_int([1, 2, 3])
        self.assertIsNone(result)

    def test_returns_none_for_dict_input(self) -> None:
        """Test that dict input returns None."""
        result = _coerce_optional_int({"key": "value"})
        self.assertIsNone(result)


class TestBuildResultDigestWithPayload(unittest.TestCase):
    """Tests for build_result_digest with various artifact configurations."""

    def test_extracts_exit_code_from_camelcase_payload(self) -> None:
        """Test that exitCode (camelCase) is extracted from payload."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-payload-camel",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.FAILED,
            payload={"exitCode": 137},
            error_summary="OOMKilled",
        )

        digest = build_result_digest(artifact)

        self.assertEqual(digest.exit_code, 137)

    def test_extracts_exit_code_from_snake_case_payload(self) -> None:
        """Test that exit_code (snake_case) is extracted from payload."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-payload-snake",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.FAILED,
            payload={"exit_code": 42},
            error_summary="error",
        )

        digest = build_result_digest(artifact)

        self.assertEqual(digest.exit_code, 42)

    def test_extracts_exit_code_from_string_payload(self) -> None:
        """Test that string exit code in payload is coerced to int."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-payload-string",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.FAILED,
            payload={"exitCode": "128"},
            error_summary="error",
        )

        digest = build_result_digest(artifact)

        self.assertEqual(digest.exit_code, 128)

    def test_handles_none_payload(self) -> None:
        """Test build_result_digest with None payload."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-no-payload",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.SUCCESS,
            payload=None,
        )

        digest = build_result_digest(artifact)

        self.assertIsNone(digest.exit_code)
        self.assertEqual(digest.result_digest, "OK")

    def test_handles_empty_payload(self) -> None:
        """Test build_result_digest with empty dict payload."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-empty-payload",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.SUCCESS,
            payload={},
        )

        digest = build_result_digest(artifact)

        self.assertIsNone(digest.exit_code)
        self.assertEqual(digest.result_digest, "OK")

    def test_payload_with_unrelated_keys(self) -> None:
        """Test that non-exit-code payload keys are ignored."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-unrelated-payload",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.SUCCESS,
            payload={"command": "kubectl", "timeout": 30},
        )

        digest = build_result_digest(artifact)

        self.assertIsNone(digest.exit_code)


class TestBuildResultDigestStatusScenarios(unittest.TestCase):
    """Tests for build_result_digest with different status scenarios."""

    def test_success_status_with_bytes(self) -> None:
        """Test success status with bytes captured."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-success",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.SUCCESS,
            output_bytes_captured=2048,
            raw_output="deployment.apps/nginx created",
        )

        digest = build_result_digest(artifact)

        self.assertEqual(digest.result_digest, "OK (2048B)")
        self.assertIsNone(digest.failure_class)

    def test_success_status_zero_bytes(self) -> None:
        """Test success status with zero bytes."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-zero",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.SUCCESS,
            output_bytes_captured=0,
        )

        digest = build_result_digest(artifact)

        self.assertEqual(digest.result_digest, "OK")

    def test_failed_status_with_error_summary(self) -> None:
        """Test failed status with error summary truncates at 80 chars."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-fail-err",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.FAILED,
            error_summary="This is a very long error message that definitely exceeds the 80 character limit and will be truncated by the digest builder",
        )

        digest = build_result_digest(artifact)

        self.assertEqual(len(digest.result_digest), 81)
        self.assertTrue(digest.result_digest.endswith("…"))

    def test_failed_status_with_exit_code_only(self) -> None:
        """Test failed status with only exit code (no error summary)."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-fail-code",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.FAILED,
            error_summary=None,
            payload={"exitCode": 1},
        )

        digest = build_result_digest(artifact)

        self.assertEqual(digest.result_digest, "FAILED: exit_code=1")

    def test_skipped_status(self) -> None:
        """Test skipped status returns SKIPPED."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-skip",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.SKIPPED,
            skip_reason="resource not applicable",
        )

        digest = build_result_digest(artifact)

        self.assertEqual(digest.result_digest, "SKIPPED")

    def test_pending_status_returns_pending(self) -> None:
        """Test that PENDING status returns pending."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-pending-status",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.PENDING,
        )

        digest = build_result_digest(artifact)

        self.assertEqual(digest.result_digest, "pending")


class TestBuildResultDigestTimeoutHandling(unittest.TestCase):
    """Tests for timeout handling in build_result_digest."""

    def test_timed_out_overrides_failed_status(self) -> None:
        """Test that timed_out=True returns TIMED_OUT regardless of status."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-timed",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.FAILED,
            timed_out=True,
            error_summary="some error",
        )

        digest = build_result_digest(artifact)

        self.assertEqual(digest.result_digest, "TIMED_OUT")

    def test_timed_out_classifies_failure_as_timeout(self) -> None:
        """Test that timed_out=True sets failure_class to timeout."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-timed-class",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.FAILED,
            timed_out=True,
        )

        digest = build_result_digest(artifact)

        self.assertEqual(digest.failure_class, "timeout")


class TestBuildResultDigestSignalMarkers(unittest.TestCase):
    """Tests for signal marker extraction in build_result_digest."""

    def test_extracts_evicted_marker(self) -> None:
        """Test Evicted status marker extraction."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-evicted",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.FAILED,
            raw_output="Pod nginx-xyz has been evicted",
        )

        digest = build_result_digest(artifact)

        self.assertIn("Evicted", digest.signal_markers)

    def test_extracts_terminating_marker(self) -> None:
        """Test Terminating status marker extraction."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-term",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.FAILED,
            raw_output="Pod nginx is Terminating",
        )

        digest = build_result_digest(artifact)

        self.assertIn("Terminating", digest.signal_markers)

    def test_extracts_failed_scheduling_marker(self) -> None:
        """Test FailedScheduling marker extraction."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-sched",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.FAILED,
            raw_output="0/3 nodes are available: 3 Insufficient memory. FailedScheduling",
        )

        digest = build_result_digest(artifact)

        self.assertIn("FailedScheduling", digest.signal_markers)

    def test_extracts_unauthorized_marker(self) -> None:
        """Test Unauthorized marker extraction."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-unauth",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.FAILED,
            raw_output="Error: unauthorized: unable to list pods",
        )

        digest = build_result_digest(artifact)

        self.assertIn("Unauthorized", digest.signal_markers)

    def test_extracts_dns_error_marker(self) -> None:
        """Test DNSError marker extraction."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-dns",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.FAILED,
            raw_output="Error: no such host example.com",
        )

        digest = build_result_digest(artifact)

        self.assertIn("DNSError", digest.signal_markers)

    def test_extracts_resource_quota_marker(self) -> None:
        """Test ResourceQuota marker extraction."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-quota",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.FAILED,
            raw_output="insufficient quota for CPU",
        )

        digest = build_result_digest(artifact)

        self.assertIn("ResourceQuota", digest.signal_markers)

    def test_extracts_resource_limit_marker(self) -> None:
        """Test ResourceLimit marker extraction."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-limit",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.FAILED,
            raw_output="memory limit exceeded",
        )

        digest = build_result_digest(artifact)

        self.assertIn("ResourceLimit", digest.signal_markers)

    def test_case_insensitive_marker_extraction(self) -> None:
        """Test that marker extraction is case insensitive."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-case",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.FAILED,
            raw_output="CRASHLOOPBACKOFF detected",
        )

        digest = build_result_digest(artifact)

        self.assertIn("CrashLoopBackOff", digest.signal_markers)


class TestBuildResultDigestDigestLines(unittest.TestCase):
    """Tests for digest lines handling in build_result_digest."""

    def test_extracts_digest_lines_from_raw_output(self) -> None:
        """Test that digest lines are extracted from raw output."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-lines",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.SUCCESS,
            raw_output="line1\nline2\nline3\nline4\nline5",
        )

        digest = build_result_digest(artifact)

        self.assertEqual(digest.result_digest_lines, ("line1", "line2", "line3", "line4", "line5"))

    def test_adds_truncation_indicator_when_exceeds_limit(self) -> None:
        """Test that truncation indicator is added when lines exceed max_lines."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-trunc",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.SUCCESS,
            raw_output="line1\nline2\nline3\nline4\nline5\nline6\nline7",
        )

        digest = build_result_digest(artifact)

        self.assertEqual(len(digest.result_digest_lines), 6)  # 5 content + 1 indicator
        self.assertTrue(digest.result_digest_lines[-1].startswith("[+"))

    def test_filters_empty_lines_from_digest_lines(self) -> None:
        """Test that empty lines are filtered from digest lines."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-filter",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.SUCCESS,
            raw_output="line1\n\n  \nline2\n\nline3",
        )

        digest = build_result_digest(artifact)

        self.assertEqual(digest.result_digest_lines, ("line1", "line2", "line3"))


class TestBuildResultDigestStdioDigests(unittest.TestCase):
    """Tests for stdout/stderr digest extraction."""

    def test_extracts_stderr_digest_from_combined_output(self) -> None:
        """Test that stderr digest is extracted from combined output."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-stderr",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.FAILED,
            raw_output="some output\nError: permission denied\nmore output",
            stderr_truncated=False,
        )

        digest = build_result_digest(artifact)

        self.assertIsNotNone(digest.stderr_digest)
        assert digest.stderr_digest is not None
        self.assertIn("error", digest.stderr_digest.lower())

    def test_extracts_stdout_digest_from_combined_output(self) -> None:
        """Test that stdout digest is extracted from combined output."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-stdout",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.SUCCESS,
            raw_output="some output\nclean line\nmore output",
            stdout_truncated=False,
        )

        digest = build_result_digest(artifact)

        self.assertIsNotNone(digest.stdout_digest)
        assert digest.stdout_digest is not None
        stdout_digest: str = digest.stdout_digest
        self.assertNotIn("error", stdout_digest.lower())

    def test_stdout_digest_is_none_when_stderr_truncated_not_set(self) -> None:
        """Test that stdout_digest is None when stderr_truncated is not set."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-no-stderr-flag",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.SUCCESS,
            raw_output="some output",
            stderr_truncated=None,
        )

        digest = build_result_digest(artifact)

        self.assertIsNone(digest.stderr_digest)


class TestBuildResultDigestFailureClassification(unittest.TestCase):
    """Tests for failure classification in build_result_digest."""

    def test_classifies_not_found_from_error_summary(self) -> None:
        """Test that not_found is classified from error_summary."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-nf-class",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.FAILED,
            error_summary='pods "test" not found',
            payload={"exitCode": 1},
        )

        digest = build_result_digest(artifact)

        self.assertEqual(digest.failure_class, "not_found")

    def test_classifies_permission_denied_from_error_summary(self) -> None:
        """Test that permission_denied is classified from error_summary."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-perm-class",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.FAILED,
            error_summary="pods is forbidden: authorization",
        )

        digest = build_result_digest(artifact)

        self.assertEqual(digest.failure_class, "permission_denied")

    def test_classifies_connection_refused_from_error_summary(self) -> None:
        """Test that connection_refused is classified from error_summary."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-cr-class",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.FAILED,
            error_summary="connection refused to port 8080",
        )

        digest = build_result_digest(artifact)

        self.assertEqual(digest.failure_class, "connection_refused")

    def test_classifies_tls_error_from_error_summary(self) -> None:
        """Test that tls_error is classified from error_summary."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-tls-class",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.FAILED,
            error_summary="x509: certificate signed by unknown authority",
        )

        digest = build_result_digest(artifact)

        self.assertEqual(digest.failure_class, "tls_error")

    def test_classifies_command_error_from_error_summary(self) -> None:
        """Test that command_error is classified from generic error_summary."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-err-class",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.FAILED,
            error_summary="some generic error occurred",
        )

        digest = build_result_digest(artifact)

        self.assertEqual(digest.failure_class, "command_error")

    def test_classifies_exit_code_when_no_stderr(self) -> None:
        """Test that exit code is classified when no error_summary."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-exit-class",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.FAILED,
            error_summary=None,
            payload={"exitCode": 127},
        )

        digest = build_result_digest(artifact)

        self.assertEqual(digest.failure_class, "exit_127")


class TestDigestToDictSerialization(unittest.TestCase):
    """Tests for digest_to_dict serialization."""

    def test_serializes_all_fields(self) -> None:
        """Test that all fields are serialized to dict."""
        digest = ResultDigest(
            result_digest="OK (100B)",
            result_digest_lines=("line1", "line2"),
            stderr_digest="error",
            stdout_digest="output",
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
        self.assertEqual(result["stderr_digest"], "error")
        self.assertEqual(result["stdout_digest"], "output")
        self.assertEqual(result["signal_markers"], ["NotFound", "ErrorIndicator"])
        self.assertEqual(result["failure_class"], "not_found")
        self.assertEqual(result["exit_code"], 1)
        self.assertEqual(result["output_bytes_captured"], 100)
        self.assertFalse(result["stdout_truncated"])
        self.assertTrue(result["stderr_truncated"])

    def test_converts_tuples_to_lists(self) -> None:
        """Test that tuples are converted to lists for JSON serialization."""
        digest = ResultDigest(
            result_digest="TEST",
            result_digest_lines=("a", "b", "c"),
            stderr_digest=None,
            stdout_digest=None,
            signal_markers=("x", "y"),
            failure_class=None,
            exit_code=None,
            output_bytes_captured=None,
            stdout_truncated=None,
            stderr_truncated=None,
        )

        result = digest_to_dict(digest)

        self.assertIsInstance(result["result_digest_lines"], list)
        self.assertIsInstance(result["signal_markers"], list)
        self.assertEqual(result["result_digest_lines"], ["a", "b", "c"])
        self.assertEqual(result["signal_markers"], ["x", "y"])

    def test_includes_none_for_optional_fields(self) -> None:
        """Test that None values are included for optional fields."""
        digest = ResultDigest(
            result_digest="OK",
            result_digest_lines=(),
            stderr_digest=None,
            stdout_digest=None,
            signal_markers=(),
            failure_class=None,
            exit_code=None,
            output_bytes_captured=None,
            stdout_truncated=None,
            stderr_truncated=None,
        )

        result = digest_to_dict(digest)

        self.assertIn("stderr_digest", result)
        self.assertIn("stdout_digest", result)
        self.assertIn("signal_markers", result)
        self.assertIn("failure_class", result)
        self.assertIn("exit_code", result)
        self.assertIn("output_bytes_captured", result)
        self.assertIn("stdout_truncated", result)
        self.assertIn("stderr_truncated", result)
        self.assertIsNone(result["stderr_digest"])
        self.assertIsNone(result["stdout_digest"])


class TestBuildResultDigestMinimalArtifacts(unittest.TestCase):
    """Tests for build_result_digest with minimal artifacts."""

    def test_minimal_success_artifact(self) -> None:
        """Test build_result_digest with minimal success artifact."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test",
            run_id="run-min",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.SUCCESS,
        )

        digest = build_result_digest(artifact)

        self.assertEqual(digest.result_digest, "OK")
        self.assertEqual(digest.result_digest_lines, ())
        self.assertIsNone(digest.stderr_digest)
        self.assertIsNone(digest.stdout_digest)
        self.assertEqual(digest.signal_markers, ())
        self.assertIsNone(digest.failure_class)
        self.assertIsNone(digest.exit_code)
        self.assertIsNone(digest.output_bytes_captured)
        self.assertIsNone(digest.stdout_truncated)
        self.assertIsNone(digest.stderr_truncated)

    def test_minimal_failed_artifact(self) -> None:
        """Test build_result_digest with minimal failed artifact."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test",
            run_id="run-fail-min",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.FAILED,
            error_summary="generic error",
        )

        digest = build_result_digest(artifact)

        self.assertEqual(digest.result_digest, "generic error")
        self.assertEqual(digest.failure_class, "command_error")

    def test_artifact_with_only_status(self) -> None:
        """Test build_result_digest with only status field."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test",
            run_id="run-status-only",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.SKIPPED,
        )

        digest = build_result_digest(artifact)

        self.assertEqual(digest.result_digest, "SKIPPED")


class TestBuildResultDigestRoundtrip(unittest.TestCase):
    """Tests for roundtrip serialization of ResultDigest."""

    def test_digest_to_dict_and_back(self) -> None:
        """Test that digest can be serialized and the dict contains all data."""
        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-round",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.FAILED,
            raw_output="Error: not found\nsome output",
            error_summary="not found",
            stderr_truncated=True,
            stdout_truncated=False,
            output_bytes_captured=50,
            payload={"exitCode": 1},
        )

        digest = build_result_digest(artifact)
        serialized = digest_to_dict(digest)

        # Verify all expected fields are present
        expected_fields = [
            "result_digest",
            "result_digest_lines",
            "stderr_digest",
            "stdout_digest",
            "signal_markers",
            "failure_class",
            "exit_code",
            "output_bytes_captured",
            "stdout_truncated",
            "stderr_truncated",
        ]

        for field in expected_fields:
            self.assertIn(field, serialized)

    def test_result_digest_with_many_markers(self) -> None:
        """Test ResultDigest with many signal markers."""
        output_with_many_issues = """
        CrashLoopBackOff detected
        Error from server (Forbidden): pods is forbidden
        connection refused to port 8080
        OOMKilled: Exit Code 137
        """

        artifact = ExternalAnalysisArtifact(
            tool_name="test-tool",
            run_id="run-many",
            cluster_label="cluster",
            status=ExternalAnalysisStatus.FAILED,
            raw_output=output_with_many_issues,
            error_summary="multiple errors",
        )

        digest = build_result_digest(artifact)

        self.assertIn("CrashLoopBackOff", digest.signal_markers)
        self.assertIn("Forbidden", digest.signal_markers)
        self.assertIn("ConnectionRefused", digest.signal_markers)
        self.assertIn("OOMKilled", digest.signal_markers)


class TestClassifyFailureEdgeCases(unittest.TestCase):
    """Tests for _classify_failure edge cases."""

    def test_none_stderr_with_exit_code(self) -> None:
        """Test classification with None stderr but exit code."""
        result = _classify_failure(stderr=None, exit_code=42, timed_out=False)
        self.assertEqual(result, "exit_42")

    def test_zero_exit_code_returns_none(self) -> None:
        """Test that zero exit code returns None (no failure)."""
        result = _classify_failure(stderr=None, exit_code=0, timed_out=False)
        self.assertIsNone(result)

    def test_timeout_takes_precedence_over_stderr(self) -> None:
        """Test that timed_out=True takes precedence over stderr analysis."""
        result = _classify_failure(
            stderr="Error: not found",
            exit_code=None,
            timed_out=True,
        )
        self.assertEqual(result, "timeout")

    def test_no_failure_when_all_none(self) -> None:
        """Test that no failure is classified when all inputs are None/zero."""
        result = _classify_failure(stderr=None, exit_code=None, timed_out=False)
        self.assertIsNone(result)

    def test_tls_error_classification(self) -> None:
        """Test TLS error classification from stderr."""
        result = _classify_failure(
            stderr="x509: certificate has expired",
            exit_code=None,
            timed_out=False,
        )
        self.assertEqual(result, "tls_error")

    def test_connection_refused_classification(self) -> None:
        """Test connection refused classification from stderr."""
        result = _classify_failure(
            stderr="could not connect: connection refused",
            exit_code=None,
            timed_out=False,
        )
        self.assertEqual(result, "connection_refused")


class TestExtractSignalMarkersEdgeCases(unittest.TestCase):
    """Edge case tests for _extract_signal_markers."""

    def test_doesnt_find_signal_in_non_matching_output(self) -> None:
        """Test that no markers are found in clean output."""
        clean_output = "NAME       READY   STATUS    RESTARTS   AGE\npod-xyz    1/1     Running   0          2d"
        markers = _extract_signal_markers(clean_output)
        self.assertEqual(markers, ())

    def test_marker_not_duplicated_when_multiple_matches(self) -> None:
        """Test that same marker is not duplicated when found multiple times."""
        output = "error not found\nanother not found error"
        markers = _extract_signal_markers(output)
        # NotFound should appear once, not twice
        self.assertEqual(markers.count("NotFound"), 1)

    def test_whitespace_only_output(self) -> None:
        """Test that whitespace-only output returns empty markers."""
        markers = _extract_signal_markers("   \n\t\n   ")
        self.assertEqual(markers, ())

    def test_markers_are_case_insensitive(self) -> None:
        """Test that signal markers are detected case-insensitively."""
        output = "FORBIDDEN error detected"
        markers = _extract_signal_markers(output)
        self.assertIn("Forbidden", markers)

    def test_all_marker_types_detected(self) -> None:
        """Test that all marker types can be detected."""
        output = """
        CrashLoopBackOff
        ImagePullBackOff
        ErrImagePull
        Evicted
        OOMKilled
        Terminating
        FailedScheduling
        ReadinessProbeFailed
        LivenessProbeFailed
        StartupProbeFailed
        probe fail detected
        forbidden
        unauthorized
        permission denied
        not found
        doesn't exist
        no such host
        connection refused
        TLS error
        timeout occurred
        insufficient resources
        memory limit exceeded
        """

        markers = _extract_signal_markers(output)

        expected_markers = [
            "CrashLoopBackOff",
            "ImagePullBackOff",
            "ErrImagePull",
            "Evicted",
            "OOMKilled",
            "Terminating",
            "FailedScheduling",
            "ReadinessProbeFailed",
            "LivenessProbeFailed",
            "StartupProbeFailed",
            "ProbeFailed",
            "Forbidden",
            "Unauthorized",
            "PermissionDenied",
            "NotFound",
            "DNSError",
            "ConnectionRefused",
            "TLSCertError",
            "Timeout",
            "ResourceQuota",
            "ResourceLimit",
        ]

        for marker in expected_markers:
            self.assertIn(marker, markers, f"Missing marker: {marker}")


if __name__ == "__main__":
    unittest.main()
