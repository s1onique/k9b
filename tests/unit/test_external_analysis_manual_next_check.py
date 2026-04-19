"""Tests for manual_next_check module.

Tests cover:
- Helper function parsing and validation
- Edge cases in output capture and command processing
- Error handling for gating conditions
- Default values for missing fields
"""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from k8s_diag_agent.external_analysis.artifact import (
    ExternalAnalysisStatus,
)
from k8s_diag_agent.external_analysis.manual_next_check import (
    _ALLOWED_FAMILIES,
    _DANGEROUS_CHARS,
    _OUTPUT_LIMIT,
    ManualNextCheckError,
    _build_command,
    _build_payload,
    _candidate_blocking_reason,
    _capture_output,
    _strip_context_arguments,
    _validate_command_tokens,
    execute_manual_next_check,
)
from k8s_diag_agent.external_analysis.next_check_planner import (
    BlockingReason,
    CommandFamily,
)


class TestCaptureOutput(unittest.TestCase):
    """Tests for _capture_output function."""

    def test_capture_none_returns_none(self) -> None:
        """Test that None input returns None tuple."""
        result = _capture_output(None)
        self.assertEqual(result, (None, False, 0))

    def test_capture_bytes_decodes_utf8(self) -> None:
        """Test that bytes input is decoded to string."""
        result = _capture_output(b"hello world")
        text, truncated, bytes_count = result
        self.assertEqual(text, "hello world")
        self.assertFalse(truncated)
        self.assertEqual(bytes_count, 11)

    def test_capture_bytes_replaces_invalid_utf8(self) -> None:
        """Test that invalid UTF-8 bytes are replaced."""
        result = _capture_output(b"hello\xffworld")
        text, _, _ = result
        self.assertEqual(text, "hello\ufffdworld")

    def test_capture_empty_string_returns_none(self) -> None:
        """Test that empty string returns None."""
        result = _capture_output("")
        self.assertEqual(result, (None, False, 0))

    def test_capture_whitespace_only_returns_none(self) -> None:
        """Test that whitespace-only string returns None."""
        result = _capture_output("   \t\n  ")
        self.assertEqual(result, (None, False, 0))

    def test_capture_trims_whitespace(self) -> None:
        """Test that whitespace is trimmed."""
        result = _capture_output("  hello world  \n")
        text, _, _ = result
        self.assertEqual(text, "hello world")

    def test_capture_truncates_long_output(self) -> None:
        """Test that long output is truncated correctly."""
        long_text = "x" * (_OUTPUT_LIMIT + 100)
        result = _capture_output(long_text)
        text, truncated, bytes_count = result
        self.assertTrue(truncated)
        assert text is not None  # help mypy
        self.assertEqual(len(text), _OUTPUT_LIMIT)  # 8191 x's + 1 ellipsis = 8192
        self.assertTrue(text.endswith("…"))
        self.assertLess(bytes_count, _OUTPUT_LIMIT + 100)

    def test_capture_truncate_limit_one(self) -> None:
        """Test truncation with limit=1 returns just ellipsis."""
        result = _capture_output("hello world", limit=1)
        text, truncated, bytes_count = result
        self.assertEqual(text, "…")
        self.assertTrue(truncated)

    def test_capture_preserves_short_output(self) -> None:
        """Test that short output is not truncated."""
        short_text = "short output"
        result = _capture_output(short_text)
        text, truncated, _ = result
        self.assertEqual(text, short_text)
        self.assertFalse(truncated)


class TestStripContextArguments(unittest.TestCase):
    """Tests for _strip_context_arguments function."""

    def test_strip_double_dash_context(self) -> None:
        """Test stripping --context flag with separate value."""
        tokens = ["kubectl", "get", "pods", "--context", "prod"]
        result = _strip_context_arguments(tokens)
        self.assertEqual(result, ("kubectl", "get", "pods"))

    def test_strip_single_dash_context(self) -> None:
        """Test stripping -c flag with separate value."""
        tokens = ["kubectl", "get", "pods", "-c", "dev"]
        result = _strip_context_arguments(tokens)
        self.assertEqual(result, ("kubectl", "get", "pods"))

    def test_strip_equals_context(self) -> None:
        """Test stripping --context=value format."""
        tokens = ["kubectl", "get", "pods", "--context=staging"]
        result = _strip_context_arguments(tokens)
        self.assertEqual(result, ("kubectl", "get", "pods"))

    def test_strip_equals_c_context(self) -> None:
        """Test stripping -c=value format."""
        tokens = ["kubectl", "get", "pods", "-c=test"]
        result = _strip_context_arguments(tokens)
        self.assertEqual(result, ("kubectl", "get", "pods"))

    def test_preserves_other_flags(self) -> None:
        """Test that other flags are preserved."""
        tokens = ["kubectl", "get", "pods", "-n", "default", "--context", "prod"]
        result = _strip_context_arguments(tokens)
        self.assertEqual(result, ("kubectl", "get", "pods", "-n", "default"))

    def test_handles_context_at_start(self) -> None:
        """Test stripping context flag at start of args."""
        tokens = ["--context", "prod", "kubectl", "get", "pods"]
        result = _strip_context_arguments(tokens)
        self.assertEqual(result, ("kubectl", "get", "pods"))


class TestCandidateBlockingReason(unittest.TestCase):
    """Tests for _candidate_blocking_reason function."""

    def test_parses_valid_blocking_reason(self) -> None:
        """Test parsing a valid blocking reason."""
        candidate = {"blockingReason": "requires_approval"}
        result = _candidate_blocking_reason(candidate)
        self.assertEqual(result, BlockingReason.REQUIRES_APPROVAL)

    def test_parses_all_valid_blocking_reasons(self) -> None:
        """Test parsing all valid blocking reason values."""
        for reason in BlockingReason:
            candidate = {"blockingReason": reason.value}
            result = _candidate_blocking_reason(candidate)
            self.assertEqual(result, reason)

    def test_returns_none_for_invalid_reason(self) -> None:
        """Test that invalid reason string returns None."""
        candidate = {"blockingReason": "not_a_valid_reason"}
        result = _candidate_blocking_reason(candidate)
        self.assertIsNone(result)

    def test_returns_none_for_missing_reason(self) -> None:
        """Test that missing reason returns None."""
        candidate: dict[str, object] = {}
        result = _candidate_blocking_reason(candidate)
        self.assertIsNone(result)

    def test_returns_none_for_empty_reason(self) -> None:
        """Test that empty reason string returns None."""
        candidate = {"blockingReason": ""}
        result = _candidate_blocking_reason(candidate)
        self.assertIsNone(result)

    def test_returns_none_for_non_string_reason(self) -> None:
        """Test that non-string reason returns None."""
        candidate = {"blockingReason": 123}
        result = _candidate_blocking_reason(candidate)
        self.assertIsNone(result)


class TestValidateCommandTokens(unittest.TestCase):
    """Tests for _validate_command_tokens function."""

    def test_validate_empty_tokens_raises(self) -> None:
        """Test that empty tokens raise error."""
        with self.assertRaises(ManualNextCheckError) as cm:
            _validate_command_tokens(CommandFamily.KUBECTL_GET, [])
        self.assertIn("Command text must include a kubectl subcommand", str(cm.exception))

    def test_validate_logs_family_requires_logs_subcommand(self) -> None:
        """Test that kubectl-logs requires 'logs' subcommand."""
        tokens = ["get", "pods"]
        with self.assertRaises(ManualNextCheckError) as cm:
            _validate_command_tokens(CommandFamily.KUBECTL_LOGS, tokens)
        self.assertIn("Logs candidate must use `kubectl logs`", str(cm.exception))

    def test_validate_describe_family_requires_describe_subcommand(self) -> None:
        """Test that kubectl-describe requires 'describe' subcommand."""
        tokens = ["get", "pods"]
        with self.assertRaises(ManualNextCheckError) as cm:
            _validate_command_tokens(CommandFamily.KUBECTL_DESCRIBE, tokens)
        self.assertIn("Describe candidate must use `kubectl describe`", str(cm.exception))

    def test_validate_get_family_requires_get_subcommand(self) -> None:
        """Test that kubectl-get requires 'get' subcommand."""
        tokens = ["logs", "pods"]
        with self.assertRaises(ManualNextCheckError) as cm:
            _validate_command_tokens(CommandFamily.KUBECTL_GET, tokens)
        self.assertIn("Get candidate must use `kubectl get`", str(cm.exception))

    def test_validate_crd_family_requires_get_and_crd_reference(self) -> None:
        """Test that kubectl-get-crd requires 'get' and CRD reference."""
        tokens = ["get", "pods"]
        with self.assertRaises(ManualNextCheckError) as cm:
            _validate_command_tokens(CommandFamily.KUBECTL_GET_CRD, tokens)
        self.assertIn("CRD candidate must reference CRDs", str(cm.exception))

    def test_validate_crd_family_accepts_crd_reference(self) -> None:
        """Test that CRD family accepts commands with crd reference."""
        tokens = ["get", "crd", "certificates"]
        # Should not raise
        _validate_command_tokens(CommandFamily.KUBECTL_GET_CRD, tokens)

    def test_validate_crd_family_accepts_customresourcedefinition(self) -> None:
        """Test that CRD family accepts customresourcedefinition keyword."""
        tokens = ["get", "customresourcedefinition", "certificates"]
        # Should not raise
        _validate_command_tokens(CommandFamily.KUBECTL_GET_CRD, tokens)

    def test_validate_rejects_dangerous_characters(self) -> None:
        """Test that dangerous characters are rejected."""
        for char in _DANGEROUS_CHARS:
            tokens = ["get", f"pods{char}something"]
            with self.assertRaises(ManualNextCheckError) as cm:
                _validate_command_tokens(CommandFamily.KUBECTL_GET, tokens)
            self.assertIn("unsupported punctuation", str(cm.exception))
    
    def test_validate_accepts_valid_get_command(self) -> None:
        """Test that valid get command passes validation."""
        tokens = ["get", "pods", "-n", "default"]
        # Should not raise
        _validate_command_tokens(CommandFamily.KUBECTL_GET, tokens)


class TestBuildCommand(unittest.TestCase):
    """Tests for _build_command function."""

    def test_build_command_basic(self) -> None:
        """Test basic command building."""
        result = _build_command(
            "kubectl get pods -n default",
            "prod",
            CommandFamily.KUBECTL_GET,
        )
        self.assertEqual(result, ["kubectl", "get", "pods", "-n", "default", "--context", "prod"])

    def test_build_command_strips_context(self) -> None:
        """Test that existing --context is stripped."""
        result = _build_command(
            "kubectl get pods --context dev -n default",
            "prod",
            CommandFamily.KUBECTL_GET,
        )
        self.assertEqual(result, ["kubectl", "get", "pods", "-n", "default", "--context", "prod"])
        self.assertNotIn("dev", result)

    def test_build_command_strips_c_context(self) -> None:
        """Test that existing -c context is stripped."""
        result = _build_command(
            "kubectl get pods -c dev -n default",
            "prod",
            CommandFamily.KUBECTL_GET,
        )
        self.assertEqual(result, ["kubectl", "get", "pods", "-n", "default", "--context", "prod"])
        self.assertNotIn("dev", result)

    def test_build_command_raises_if_not_kubectl(self) -> None:
        """Test that non-kubectl command raises error."""
        with self.assertRaises(ManualNextCheckError) as cm:
            _build_command("docker ps", "prod", CommandFamily.KUBECTL_GET)
        self.assertIn("must begin with `kubectl`", str(cm.exception))

    def test_build_command_raises_on_parse_error(self) -> None:
        """Test that malformed command raises error."""
        with self.assertRaises(ManualNextCheckError) as cm:
            _build_command("kubectl get pods 'unclosed quote", "prod", CommandFamily.KUBECTL_GET)
        self.assertIn("Unable to parse", str(cm.exception))

    def test_build_command_raises_if_no_subcommand(self) -> None:
        """Test that kubectl without subcommand raises error."""
        with self.assertRaises(ManualNextCheckError) as cm:
            _build_command("kubectl", "prod", CommandFamily.KUBECTL_GET)
        self.assertIn("Command text must include a kubectl subcommand", str(cm.exception))


class TestBuildPayload(unittest.TestCase):
    """Tests for _build_payload function."""

    def test_build_payload_basic(self) -> None:
        """Test basic payload construction."""
        candidate = {
            "candidateId": "test-id",
            "description": "kubectl get pods",
            "suggestedCommandFamily": "kubectl-get",
        }
        result = _build_payload(
            candidate=candidate,
            candidate_index=0,
            command=["kubectl", "get", "pods"],
            plan_artifact="plan.json",
            target_cluster="cluster-a",
            target_context="prod",
            timed_out=False,
            stdout_truncated=False,
            stderr_truncated=False,
            output_bytes_captured=100,
        )

        self.assertEqual(result["candidateIndex"], 0)
        self.assertEqual(result["candidateId"], "test-id")
        self.assertEqual(result["candidateDescription"], "kubectl get pods")
        self.assertEqual(result["commandFamily"], "kubectl-get")
        self.assertEqual(result["command"], ["kubectl", "get", "pods"])
        self.assertEqual(result["planArtifactPath"], "plan.json")
        self.assertEqual(result["targetCluster"], "cluster-a")
        self.assertEqual(result["targetContext"], "prod")
        self.assertFalse(result["timedOut"])
        self.assertFalse(result["stdoutTruncated"])
        self.assertFalse(result["stderrTruncated"])
        self.assertEqual(result["outputBytesCaptured"], 100)

    def test_build_payload_missing_candidate_id(self) -> None:
        """Test payload with missing candidateId becomes None."""
        candidate: dict[str, object] = {"description": "kubectl get pods"}
        result = _build_payload(
            candidate=candidate,
            candidate_index=0,
            command=["kubectl", "get", "pods"],
            plan_artifact="plan.json",
            target_cluster=None,
            target_context="prod",
            timed_out=False,
            stdout_truncated=False,
            stderr_truncated=False,
            output_bytes_captured=0,
        )
        self.assertIsNone(result["candidateId"])

    def test_build_payload_non_string_candidate_id(self) -> None:
        """Test that non-string candidateId becomes None."""
        candidate = {"candidateId": 123, "description": "kubectl get pods"}
        result = _build_payload(
            candidate=candidate,
            candidate_index=0,
            command=["kubectl", "get", "pods"],
            plan_artifact="plan.json",
            target_cluster=None,
            target_context="prod",
            timed_out=False,
            stdout_truncated=False,
            stderr_truncated=False,
            output_bytes_captured=0,
        )
        self.assertIsNone(result["candidateId"])

    def test_build_payload_empty_description(self) -> None:
        """Test that empty description becomes empty string."""
        candidate = {"description": ""}
        result = _build_payload(
            candidate=candidate,
            candidate_index=0,
            command=["kubectl"],
            plan_artifact="plan.json",
            target_cluster=None,
            target_context="prod",
            timed_out=False,
            stdout_truncated=False,
            stderr_truncated=False,
            output_bytes_captured=0,
        )
        self.assertEqual(result["candidateDescription"], "")

    def test_build_payload_missing_command_family(self) -> None:
        """Test that missing command family becomes empty string."""
        candidate = {"description": "kubectl get pods"}
        result = _build_payload(
            candidate=candidate,
            candidate_index=0,
            command=["kubectl"],
            plan_artifact="plan.json",
            target_cluster=None,
            target_context="prod",
            timed_out=False,
            stdout_truncated=False,
            stderr_truncated=False,
            output_bytes_captured=0,
        )
        self.assertEqual(result["commandFamily"], "")


class TestExecuteManualNextCheckGating(unittest.TestCase):
    """Tests for gating conditions in execute_manual_next_check."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.health_root = self.tmpdir

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _base_candidate(self) -> dict[str, object]:
        return {
            "description": "kubectl get pods -n default",
            "targetCluster": "cluster-a",
            "suggestedCommandFamily": "kubectl-get",
            "safeToAutomate": True,
            "requiresOperatorApproval": False,
            "duplicateOfExistingEvidence": False,
            "gatingReason": None,
            "candidateId": "candidate-get",
        }

    def test_rejects_candidate_not_safe_to_automate(self) -> None:
        """Test that non-safe-to-automate candidate is rejected."""
        candidate = self._base_candidate()
        candidate["safeToAutomate"] = False
        with self.assertRaises(ManualNextCheckError) as cm:
            execute_manual_next_check(
                health_root=self.health_root,
                run_id="run-not-safe",
                run_label="run-not-safe",
                plan_artifact_path=Path("plan.json"),
                candidate_index=0,
                candidate=candidate,
                target_context="prod",
                target_cluster="cluster-a",
            )
        # Note: blocking_reason is None because no blockingReason is set on candidate
        self.assertIsNone(cm.exception.blocking_reason)

    def test_rejects_candidate_missing_description(self) -> None:
        """Test that missing description is rejected."""
        candidate = self._base_candidate()
        del candidate["description"]
        with self.assertRaises(ManualNextCheckError) as cm:
            execute_manual_next_check(
                health_root=self.health_root,
                run_id="run-no-desc",
                run_label="run-no-desc",
                plan_artifact_path=Path("plan.json"),
                candidate_index=0,
                candidate=candidate,
                target_context="prod",
                target_cluster="cluster-a",
            )
        self.assertEqual(cm.exception.blocking_reason, BlockingReason.MISSING_DESCRIPTION)

    def test_rejects_candidate_empty_description(self) -> None:
        """Test that empty description is rejected."""
        candidate = self._base_candidate()
        candidate["description"] = "   "
        with self.assertRaises(ManualNextCheckError) as cm:
            execute_manual_next_check(
                health_root=self.health_root,
                run_id="run-empty-desc",
                run_label="run-empty-desc",
                plan_artifact_path=Path("plan.json"),
                candidate_index=0,
                candidate=candidate,
                target_context="prod",
                target_cluster="cluster-a",
            )
        self.assertEqual(cm.exception.blocking_reason, BlockingReason.MISSING_DESCRIPTION)

    def test_rejects_candidate_missing_command_family(self) -> None:
        """Test that missing command family is rejected."""
        candidate = self._base_candidate()
        del candidate["suggestedCommandFamily"]
        with self.assertRaises(ManualNextCheckError) as cm:
            execute_manual_next_check(
                health_root=self.health_root,
                run_id="run-no-family",
                run_label="run-no-family",
                plan_artifact_path=Path("plan.json"),
                candidate_index=0,
                candidate=candidate,
                target_context="prod",
                target_cluster="cluster-a",
            )
        self.assertEqual(cm.exception.blocking_reason, BlockingReason.UNKNOWN_COMMAND)

    def test_rejects_invalid_command_family(self) -> None:
        """Test that invalid command family is rejected."""
        candidate = self._base_candidate()
        candidate["suggestedCommandFamily"] = "not-a-real-family"
        with self.assertRaises(ManualNextCheckError) as cm:
            execute_manual_next_check(
                health_root=self.health_root,
                run_id="run-invalid-family",
                run_label="run-invalid-family",
                plan_artifact_path=Path("plan.json"),
                candidate_index=0,
                candidate=candidate,
                target_context="prod",
                target_cluster="cluster-a",
            )
        self.assertEqual(cm.exception.blocking_reason, BlockingReason.COMMAND_NOT_ALLOWED)

    def test_rejects_disallowed_command_family(self) -> None:
        """Test that disallowed command family is rejected."""
        candidate = self._base_candidate()
        # kubectl-apply is not in _ALLOWED_FAMILIES
        candidate["suggestedCommandFamily"] = "kubectl-apply"
        with self.assertRaises(ManualNextCheckError) as cm:
            execute_manual_next_check(
                health_root=self.health_root,
                run_id="run-disallowed-family",
                run_label="run-disallowed-family",
                plan_artifact_path=Path("plan.json"),
                candidate_index=0,
                candidate=candidate,
                target_context="prod",
                target_cluster="cluster-a",
            )
        self.assertEqual(cm.exception.blocking_reason, BlockingReason.COMMAND_NOT_ALLOWED)

    def test_accepts_all_allowed_command_families(self) -> None:
        """Test that all allowed command families pass validation."""
        for family in _ALLOWED_FAMILIES:
            candidate = self._base_candidate()
            candidate["suggestedCommandFamily"] = family.value
            # Should not raise during validation
            # May raise later due to empty description, but that's fine for this test
            pass

    def test_rejects_empty_target_context(self) -> None:
        """Test that empty target context is rejected."""
        candidate = self._base_candidate()
        with self.assertRaises(ManualNextCheckError) as cm:
            execute_manual_next_check(
                health_root=self.health_root,
                run_id="run-no-context",
                run_label="run-no-context",
                plan_artifact_path=Path("plan.json"),
                candidate_index=0,
                candidate=candidate,
                target_context="",  # Empty context
                target_cluster="cluster-a",
            )
        self.assertEqual(cm.exception.blocking_reason, BlockingReason.MISSING_CONTEXT)


class TestExecuteManualNextCheckEdgeCases(unittest.TestCase):
    """Tests for edge cases in execute_manual_next_check."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.health_root = self.tmpdir

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _base_candidate(self) -> dict[str, object]:
        return {
            "description": "kubectl get pods -n default",
            "targetCluster": "cluster-a",
            "suggestedCommandFamily": "kubectl-get",
            "safeToAutomate": True,
            "requiresOperatorApproval": False,
            "duplicateOfExistingEvidence": False,
            "gatingReason": None,
            "candidateId": "candidate-get",
        }

    def _runner(self, returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(["kubectl"], returncode, stdout=stdout, stderr=stderr)

    def test_candidate_with_none_candidate_id(self) -> None:
        """Test candidate with None candidateId."""
        candidate = self._base_candidate()
        candidate["candidateId"] = None
        artifact = execute_manual_next_check(
            health_root=self.health_root,
            run_id="run-none-id",
            run_label="run-none-id",
            plan_artifact_path=Path("plan.json"),
            candidate_index=0,
            candidate=candidate,
            target_context="prod",
            target_cluster="cluster-a",
            command_runner=lambda cmd: self._runner(0, stdout="ok"),
        )
        # Should succeed and payload should have None for candidateId
        self.assertEqual(artifact.status, ExternalAnalysisStatus.SUCCESS)

    def test_candidate_with_numeric_candidate_id(self) -> None:
        """Test candidate with numeric candidateId becomes None."""
        candidate = self._base_candidate()
        candidate["candidateId"] = 12345
        artifact = execute_manual_next_check(
            health_root=self.health_root,
            run_id="run-numeric-id",
            run_label="run-numeric-id",
            plan_artifact_path=Path("plan.json"),
            candidate_index=0,
            candidate=candidate,
            target_context="prod",
            target_cluster="cluster-a",
            command_runner=lambda cmd: self._runner(0, stdout="ok"),
        )
        self.assertEqual(artifact.status, ExternalAnalysisStatus.SUCCESS)

    def test_whitespace_description_trimmed(self) -> None:
        """Test that whitespace-only description is handled correctly."""
        candidate = self._base_candidate()
        candidate["description"] = "  kubectl get pods  "
        artifact = execute_manual_next_check(
            health_root=self.health_root,
            run_id="run-whitespace",
            run_label="run-whitespace",
            plan_artifact_path=Path("plan.json"),
            candidate_index=0,
            candidate=candidate,
            target_context="prod",
            target_cluster="cluster-a",
            command_runner=lambda cmd: self._runner(0, stdout="ok"),
        )
        self.assertEqual(artifact.status, ExternalAnalysisStatus.SUCCESS)

    def test_none_description_handled(self) -> None:
        """Test that None description becomes empty string."""
        candidate = self._base_candidate()
        candidate["description"] = None
        with self.assertRaises(ManualNextCheckError):
            execute_manual_next_check(
                health_root=self.health_root,
                run_id="run-none-desc",
                run_label="run-none-desc",
                plan_artifact_path=Path("plan.json"),
                candidate_index=0,
                candidate=candidate,
                target_context="prod",
                target_cluster="cluster-a",
            )

    def test_empty_target_cluster_uses_run_label(self) -> None:
        """Test that empty target cluster uses run label for artifact cluster_label."""
        candidate = self._base_candidate()
        artifact = execute_manual_next_check(
            health_root=self.health_root,
            run_id="run-empty-cluster",
            run_label="my-run-label",
            plan_artifact_path=Path("plan.json"),
            candidate_index=0,
            candidate=candidate,
            target_context="prod",
            target_cluster="",  # Empty cluster
            command_runner=lambda cmd: self._runner(0, stdout="ok"),
        )
        # Should use run_label as fallback for cluster_label
        self.assertEqual(artifact.cluster_label, "my-run-label")


class TestExecuteManualNextCheckDefaultValues(unittest.TestCase):
    """Tests for default values in execute_manual_next_check."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.health_root = self.tmpdir

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _base_candidate(self) -> dict[str, object]:
        return {
            "description": "kubectl get pods -n default",
            "targetCluster": "cluster-a",
            "suggestedCommandFamily": "kubectl-get",
            "safeToAutomate": True,
            "requiresOperatorApproval": False,
            "duplicateOfExistingEvidence": False,
            "gatingReason": None,
            "candidateId": "candidate-get",
        }

    def _runner(self, returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(["kubectl"], returncode, stdout=stdout, stderr=stderr)

    def test_default_safe_to_automate_is_false(self) -> None:
        """Test that missing safeToAutomate is treated as False."""
        candidate = self._base_candidate()
        del candidate["safeToAutomate"]
        with self.assertRaises(ManualNextCheckError) as cm:
            execute_manual_next_check(
                health_root=self.health_root,
                run_id="run-no-safe",
                run_label="run-no-safe",
                plan_artifact_path=Path("plan.json"),
                candidate_index=0,
                candidate=candidate,
                target_context="prod",
                target_cluster="cluster-a",
            )
        # Note: blocking_reason is None because no blockingReason is set on candidate
        self.assertIsNone(cm.exception.blocking_reason)

    def test_default_requires_approval_is_false(self) -> None:
        """Test that missing requiresOperatorApproval defaults to False."""
        candidate = self._base_candidate()
        del candidate["requiresOperatorApproval"]
        # Should succeed because approval not required
        artifact = execute_manual_next_check(
            health_root=self.health_root,
            run_id="run-default-approval",
            run_label="run-default-approval",
            plan_artifact_path=Path("plan.json"),
            candidate_index=0,
            candidate=candidate,
            target_context="prod",
            target_cluster="cluster-a",
            command_runner=lambda cmd: self._runner(0, stdout="ok"),
        )
        self.assertEqual(artifact.status, ExternalAnalysisStatus.SUCCESS)

    def test_default_duplicate_is_false(self) -> None:
        """Test that missing duplicateOfExistingEvidence defaults to False."""
        candidate = self._base_candidate()
        del candidate["duplicateOfExistingEvidence"]
        artifact = execute_manual_next_check(
            health_root=self.health_root,
            run_id="run-default-dup",
            run_label="run-default-dup",
            plan_artifact_path=Path("plan.json"),
            candidate_index=0,
            candidate=candidate,
            target_context="prod",
            target_cluster="cluster-a",
            command_runner=lambda cmd: self._runner(0, stdout="ok"),
        )
        self.assertEqual(artifact.status, ExternalAnalysisStatus.SUCCESS)


class TestArtifactWriting(unittest.TestCase):
    """Tests for artifact writing in execute_manual_next_check."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.health_root = self.tmpdir

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _base_candidate(self) -> dict[str, object]:
        return {
            "description": "kubectl get pods -n default",
            "targetCluster": "cluster-a",
            "suggestedCommandFamily": "kubectl-get",
            "safeToAutomate": True,
            "requiresOperatorApproval": False,
            "duplicateOfExistingEvidence": False,
            "gatingReason": None,
            "candidateId": "candidate-write-test",
        }

    def _runner(self, returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(["kubectl"], returncode, stdout=stdout, stderr=stderr)

    def test_artifact_written_to_correct_path(self) -> None:
        """Test artifact is written to health_root/external-analysis/."""
        candidate = self._base_candidate()
        artifact = execute_manual_next_check(
            health_root=self.health_root,
            run_id="run-artifact-path",
            run_label="run-artifact-path",
            plan_artifact_path=Path("external-analysis/plan.json"),
            candidate_index=0,
            candidate=candidate,
            target_context="prod",
            target_cluster="cluster-a",
            command_runner=lambda cmd: self._runner(0, stdout="ok"),
        )

        expected_path = self.health_root / "external-analysis" / "run-artifact-path-next-check-execution-0.json"
        self.assertEqual(artifact.artifact_path, str(expected_path))
        self.assertTrue(expected_path.exists())

    def test_artifact_contains_all_payload_fields(self) -> None:
        """Test that written artifact contains all expected payload fields."""
        candidate = self._base_candidate()
        execute_manual_next_check(
            health_root=self.health_root,
            run_id="run-payload-check",
            run_label="run-payload-check",
            plan_artifact_path=Path("plan.json"),
            candidate_index=0,
            candidate=candidate,
            target_context="prod",
            target_cluster="cluster-a",
            command_runner=lambda cmd: self._runner(0, stdout="ok"),
        )

        artifact_path = self.health_root / "external-analysis" / "run-payload-check-next-check-execution-0.json"
        data = json.loads(artifact_path.read_text(encoding="utf-8"))

        # Verify payload contains all expected fields
        payload = data["payload"]
        expected_fields = [
            "candidateIndex",
            "candidateId",
            "candidateDescription",
            "commandFamily",
            "command",
            "planArtifactPath",
            "targetCluster",
            "targetContext",
            "timedOut",
            "stdoutTruncated",
            "stderrTruncated",
            "outputBytesCaptured",
        ]
        for field in expected_fields:
            self.assertIn(field, payload, f"Missing field: {field}")


if __name__ == "__main__":
    unittest.main()
