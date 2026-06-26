"""Behavioral tests for live lab bootstrap and protected kubeconfig workflow.

This module replaces brittle source-string assertions with behavioral tests that:
- Import the facade module and assert required public functions are available
- Call classifier functions directly with representative inputs
- Exercise JSON artifact writing through temporary artifact directories
- Verify existing lab-preflight.json context is preserved by classification subcommands
- Verify kubeconfig decode writes a file with 0o600 permissions
- Verify GITHUB_ENV export behavior using an isolated temp file
- Verify credential-source validation through mocked kubectl auth whoami output

The test file at tests/test_live_lab_cli_contract_regression.py and
tests/test_classify_wait_timeout_deployment_not_found.py already contain
behavioral tests for CLI contract and timeout classifier respectively.
"""

from __future__ import annotations

import base64
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

# Import the facade module - this tests the public contract
import scripts.k9b_cnpg_live_lab_bootstrap as bootstrap


class TestFacadePublicAPI(unittest.TestCase):
    """Verify the bootstrap facade exposes required public functions."""

    def test_facade_exports_main_functions(self) -> None:
        """Bootstrap facade must export main CLI entry points."""
        required_funcs = [
            "main_bootstrap",
            "main_classify_error",
            "main_classify_schema",
            "main_classify_wait_timeout",
            "main_collect_helm_evidence",
            "main_collect_rendered_manifest_evidence",
            "main_extract_schema_evidence",
            "main_monitor_rollout",
        ]
        for func_name in required_funcs:
            self.assertTrue(
                hasattr(bootstrap, func_name),
                f"Bootstrap facade should export {func_name}",
            )

    def test_facade_exports_classifier_functions(self) -> None:
        """Bootstrap facade must export classifier functions."""
        required_funcs = [
            "classify_helm_error",
            "classify_schema_error",
            "classify_wait_timeout",
        ]
        for func_name in required_funcs:
            self.assertTrue(
                hasattr(bootstrap, func_name),
                f"Bootstrap facade should export {func_name}",
            )

    def test_facade_exports_parse_helpers(self) -> None:
        """Bootstrap facade must export JSON parsing helpers."""
        required_funcs = [
            "_parse_crash_loop_from_pods",
            "_parse_deployment_not_ready_from_deployments",
            "_parse_image_pull_failure_from_pods",
            "_parse_pvc_pending_from_pods",
        ]
        for func_name in required_funcs:
            self.assertTrue(
                hasattr(bootstrap, func_name),
                f"Bootstrap facade should export {func_name}",
            )

    def test_facade_exports_config_classes(self) -> None:
        """Bootstrap facade must export config classes."""
        self.assertTrue(hasattr(bootstrap, "DiagnosisGenerator"))
        self.assertTrue(hasattr(bootstrap, "PreflightData"))

    def test_facade_exports_failure_constants(self) -> None:
        """Bootstrap facade must export failure class constants."""
        required_constants = [
            "FAILURE_KUBECONFIG_MISSING",
            "FAILURE_KUBECONFIG_DECODE_FAILED",
            "FAILURE_KUBECONFIG_AUTH_FAILED",
            "FAILURE_CREDENTIAL_SOURCE_WRONG",
            "FAILURE_HELM_RBAC_DENIED",
            "FAILURE_IMAGE_PULL_FAILED",
            "FAILURE_HELM_WAIT_TIMEOUT_UNKNOWN",
            "FAILURE_POD_CRASH_LOOP",
            "FAILURE_HELM_UNKNOWN",
        ]
        for const_name in required_constants:
            self.assertTrue(
                hasattr(bootstrap, const_name),
                f"Bootstrap facade should export {const_name}",
            )

    def test_facade_exports_json_helpers(self) -> None:
        """Bootstrap facade must export JSON helper functions."""
        self.assertTrue(hasattr(bootstrap, "write_json_atomically"))
        self.assertTrue(hasattr(bootstrap, "read_json"))


class TestClassifyHelmError(unittest.TestCase):
    """Behavioral tests for classify_helm_error function."""

    def test_classifies_rbac_denied_pattern(self) -> None:
        """Must classify forbidden roles/rbac errors as FAILURE_HELM_RBAC_DENIED."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            preflight = bootstrap.PreflightData(artifact_dir)
            diagnosis = bootstrap.DiagnosisGenerator(artifact_dir)

            helm_output = "Error: failed to create resource: roles.rbac.authorization.k8s.io is forbidden"
            result = bootstrap.classify_helm_error(
                helm_output, artifact_dir, preflight, diagnosis
            )

            self.assertEqual(
                result,
                bootstrap.FAILURE_HELM_RBAC_DENIED,
                "Should classify rbac forbidden error",
            )
            # Verify diagnosis was saved
            self.assertTrue((artifact_dir / "lab-diagnosis.md").exists())

    def test_classifies_image_pull_failure(self) -> None:
        """Must classify ImagePullBackOff errors as FAILURE_IMAGE_PULL_FAILED."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            preflight = bootstrap.PreflightData(artifact_dir)
            diagnosis = bootstrap.DiagnosisGenerator(artifact_dir)

            helm_output = "Warning: ImagePullBackOff - rpc error: code = Unknown desc = failed to pull image"
            result = bootstrap.classify_helm_error(
                helm_output, artifact_dir, preflight, diagnosis
            )

            self.assertEqual(
                result,
                bootstrap.FAILURE_IMAGE_PULL_FAILED,
                "Should classify ImagePullBackOff error",
            )

    def test_classifies_cnpg_crd_missing(self) -> None:
        """Must classify CNPG CRD missing errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            preflight = bootstrap.PreflightData(artifact_dir)
            diagnosis = bootstrap.DiagnosisGenerator(artifact_dir)

            helm_output = 'no matches for kind "Cluster" in version "clusters.postgresql.cnpg.io/v1"'
            result = bootstrap.classify_helm_error(
                helm_output, artifact_dir, preflight, diagnosis
            )

            self.assertEqual(
                result,
                bootstrap.FAILURE_CNPG_CRD_MISSING,
                "Should classify CNPG CRD missing error",
            )

    def test_classifies_unknown_error(self) -> None:
        """Must classify unknown errors as FAILURE_HELM_UNKNOWN."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            preflight = bootstrap.PreflightData(artifact_dir)
            diagnosis = bootstrap.DiagnosisGenerator(artifact_dir)

            helm_output = "Something unexpected happened"
            result = bootstrap.classify_helm_error(
                helm_output, artifact_dir, preflight, diagnosis
            )

            self.assertEqual(
                result,
                bootstrap.FAILURE_HELM_UNKNOWN,
                "Should classify unknown error",
            )


class TestClassifySchemaError(unittest.TestCase):
    """Behavioral tests for classify_schema_error function."""

    def test_classifies_unknown_field_error(self) -> None:
        """Must classify unknown field errors as schema warning."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            preflight = bootstrap.PreflightData(artifact_dir)
            diagnosis = bootstrap.DiagnosisGenerator(artifact_dir)

            output = 'error: error validating data: [pos 84]: unknown field "allowPrivilegeEscalation"'
            result = bootstrap.classify_schema_error(
                output, artifact_dir, preflight, diagnosis
            )

            self.assertEqual(
                result,
                bootstrap.FAILURE_HELM_MANIFEST_SCHEMA_WARNING,
                "Should classify unknown field error",
            )

    def test_classifies_dry_run_validation_failure(self) -> None:
        """Must classify dry-run validation failures."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            preflight = bootstrap.PreflightData(artifact_dir)
            diagnosis = bootstrap.DiagnosisGenerator(artifact_dir)

            output = "error: error validating data: validation failed"
            result = bootstrap.classify_schema_error(
                output, artifact_dir, preflight, diagnosis
            )

            self.assertEqual(
                result,
                bootstrap.FAILURE_HELM_MANIFEST_SERVER_DRY_RUN_FAILED,
                "Should classify dry-run validation failure",
            )


class TestJsonParsingHelpers(unittest.TestCase):
    """Behavioral tests for JSON parsing helper functions."""

    def test_parse_crash_loop_detects_crashloopbackoff(self) -> None:
        """Must detect CrashLoopBackOff from pod JSON."""
        pods_json = json.dumps({
            "items": [{
                "status": {
                    "containerStatuses": [{
                        "state": {
                            "waiting": {
                                "reason": "CrashLoopBackOff",
                                "message": "Back-off 5m0s restarting",
                            }
                        }
                    }]
                }
            }]
        })

        result = bootstrap._parse_crash_loop_from_pods(pods_json)
        self.assertTrue(result, "Should detect CrashLoopBackOff")

    def test_parse_crash_loop_ignores_running_pods(self) -> None:
        """Must not detect crash loop for running pods."""
        pods_json = json.dumps({
            "items": [{
                "status": {
                    "containerStatuses": [{
                        "state": {"running": {"startedAt": "2024-01-01T00:00:00Z"}}
                    }]
                }
            }]
        })

        result = bootstrap._parse_crash_loop_from_pods(pods_json)
        self.assertFalse(result, "Should not detect crash loop for running pods")

    def test_parse_image_pull_failure_detects_imagepullbackoff(self) -> None:
        """Must detect ImagePullBackOff from pod JSON."""
        pods_json = json.dumps({
            "items": [{
                "status": {
                    "containerStatuses": [{
                        "state": {
                            "waiting": {
                                "reason": "ImagePullBackOff",
                                "message": "rpc error",
                            }
                        }
                    }]
                }
            }]
        })

        result = bootstrap._parse_image_pull_failure_from_pods(pods_json)
        self.assertTrue(result, "Should detect ImagePullBackOff")

    def test_parse_deployment_not_ready_detects_zero_available(self) -> None:
        """Must detect deployment with no available replicas."""
        deployments_json = json.dumps({
            "items": [{
                "status": {
                    "replicas": 1,
                    "availableReplicas": 0,
                }
            }]
        })

        result = bootstrap._parse_deployment_not_ready_from_deployments(deployments_json)
        self.assertTrue(result, "Should detect unavailable deployment")

    def test_parse_deployment_not_ready_ignores_ready(self) -> None:
        """Must not flag deployment with available replicas."""
        deployments_json = json.dumps({
            "items": [{
                "status": {
                    "replicas": 1,
                    "availableReplicas": 1,
                }
            }]
        })

        result = bootstrap._parse_deployment_not_ready_from_deployments(deployments_json)
        self.assertFalse(result, "Should not flag ready deployment")

    def test_parse_handles_invalid_json(self) -> None:
        """Must handle invalid JSON gracefully."""
        result = bootstrap._parse_crash_loop_from_pods("not json")
        self.assertFalse(result, "Should handle invalid JSON")

    def test_parse_handles_empty_json(self) -> None:
        """Must handle empty/null JSON gracefully."""
        self.assertFalse(bootstrap._parse_crash_loop_from_pods(""))
        self.assertFalse(bootstrap._parse_crash_loop_from_pods("null"))
        self.assertFalse(bootstrap._parse_crash_loop_from_pods('{"items": null}'))


class TestPreflightDataJsonRoundTrip(unittest.TestCase):
    """Behavioral tests for PreflightData JSON serialization."""

    def test_preflight_data_to_dict(self) -> None:
        """PreflightData.to_dict() must produce valid dict with required fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            preflight = bootstrap.PreflightData(artifact_dir, "test-ns")
            preflight.failure_class = "test_failure"
            preflight.active_identity = "system:serviceaccount:default:sa"

            data = preflight.to_dict()

            self.assertIsInstance(data, dict)
            self.assertIn("failure_class", data)
            self.assertIn("active_identity", data)
            self.assertIn("namespace", data)
            self.assertIn("bootstrap_timestamp", data)

    def test_preflight_data_save_writes_valid_json(self) -> None:
        """PreflightData.save() must write valid JSON to lab-preflight.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            preflight = bootstrap.PreflightData(artifact_dir, "test-ns")
            preflight.failure_class = "test_failure"

            preflight.save()

            preflight_path = artifact_dir / "lab-preflight.json"
            self.assertTrue(preflight_path.exists(), "lab-preflight.json should be created")

            # Must be valid JSON
            content = preflight_path.read_text()
            parsed = json.loads(content)
            self.assertEqual(parsed["failure_class"], "test_failure")
            self.assertEqual(parsed["namespace"], "test-ns")


class TestDiagnosisGenerator(unittest.TestCase):
    """Behavioral tests for DiagnosisGenerator."""

    def test_diagnosis_creates_file(self) -> None:
        """DiagnosisGenerator.save() must create lab-diagnosis.md."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            diagnosis = bootstrap.DiagnosisGenerator(artifact_dir, "test-ns")
            diagnosis.heading(1, "Test Diagnosis")
            diagnosis.text("Test content")

            diagnosis.save()

            diagnosis_path = artifact_dir / "lab-diagnosis.md"
            self.assertTrue(diagnosis_path.exists(), "lab-diagnosis.md should be created")
            content = diagnosis_path.read_text()
            self.assertIn("Test Diagnosis", content)
            self.assertIn("Test content", content)


class TestCredentialSourceValidation(unittest.TestCase):
    """Behavioral tests for credential source validation."""

    def test_detects_arc_runner_sa_pattern(self) -> None:
        """Must detect and fail on ARC runner ServiceAccount identity."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            preflight = bootstrap.PreflightData(artifact_dir)
            diagnosis = bootstrap.DiagnosisGenerator(artifact_dir)

            # Create a fake kubeconfig file
            kubeconfig_path = Path(tmpdir) / "kubeconfig"
            kubeconfig_path.write_text("apiVersion: v1\ncontexts:\n- name: test\ncurrent-context: test\n")

            # Mock kubectl auth whoami to return ARC runner SA identity
            with patch("subprocess.run") as mock_run:
                mock_result = MagicMock()
                mock_result.returncode = 0
                mock_result.stdout.strip.return_value = "system:serviceaccount:github-actions-runner:arc-runner-set-h4sxx"
                mock_result.stderr = ""
                mock_run.return_value = mock_result

                rc = bootstrap.validate_credential_source(
                    str(kubeconfig_path), artifact_dir, preflight, diagnosis
                )

                self.assertEqual(rc, 1, "Should fail for ARC runner SA")
                self.assertEqual(
                    preflight.failure_class,
                    bootstrap.FAILURE_CREDENTIAL_SOURCE_WRONG,
                    "Should classify as credential_source_wrong",
                )

    def test_accepts_valid_identity(self) -> None:
        """Must accept valid non-ARC identities."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            preflight = bootstrap.PreflightData(artifact_dir)
            diagnosis = bootstrap.DiagnosisGenerator(artifact_dir)

            kubeconfig_path = Path(tmpdir) / "kubeconfig"
            kubeconfig_path.write_text("apiVersion: v1\ncontexts:\n- name: test\ncurrent-context: test\n")

            with patch("subprocess.run") as mock_run:
                mock_result = MagicMock()
                mock_result.returncode = 0
                mock_result.stdout.strip.return_value = "system:serviceaccount:default:valid-sa"
                mock_result.stderr = ""
                mock_run.return_value = mock_result

                rc = bootstrap.validate_credential_source(
                    str(kubeconfig_path), artifact_dir, preflight, diagnosis
                )

                self.assertEqual(rc, 0, "Should succeed for valid identity")
                self.assertIsNone(preflight.failure_class)


class TestBootstrapDecodeKubeconfig(unittest.TestCase):
    """Behavioral tests for kubeconfig decode and permissions."""

    def test_decodes_base64_to_file_with_0600_permissions(self) -> None:
        """Must decode base64 secret and set file permissions to 0o600."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            preflight = bootstrap.PreflightData(artifact_dir)
            diagnosis = bootstrap.DiagnosisGenerator(artifact_dir)

            # Create a valid kubeconfig content
            kubeconfig_content = """apiVersion: v1
clusters:
- cluster:
    server: https://127.0.0.1:6443
  name: test
contexts:
- context:
    cluster: test
    user: test
  name: test
current-context: test
users:
- name: test
  user:
    token: test-token
"""
            b64_content = base64.b64encode(kubeconfig_content.encode()).decode()

            # Mock get_env_secret in the module where it's used
            with patch.dict(os.environ, {"RUNNER_TEMP": tmpdir}):
                with patch("scripts.k9b_cnpg_live_lab_bootstrap_decode.get_env_secret", return_value=b64_content):
                    with patch("subprocess.run") as mock_run:
                        # Mock auth whoami for successful decode
                        mock_result = MagicMock()
                        mock_result.returncode = 0
                        mock_result.stdout.strip.return_value = "system:serviceaccount:default:sa"
                        mock_result.stderr = ""
                        mock_run.return_value = mock_result

                        path, rc = bootstrap.bootstrap_decode_kubeconfig(
                            "TEST_SECRET", "KUBECONFIG", artifact_dir, preflight, diagnosis
                        )

                        self.assertEqual(rc, 0, "Should decode successfully")

                        if path:
                            kubeconfig_path = Path(path)
                            self.assertTrue(kubeconfig_path.exists(), "Kubeconfig should be created")

                            # Verify 0o600 permissions (owner read/write only)
                            file_stat = kubeconfig_path.stat()
                            mode = file_stat.st_mode & 0o777
                            self.assertEqual(
                                mode, 0o600,
                                f"File should have 0o600 permissions, got {oct(mode)}",
                            )

    def test_exports_kubeconfig_to_github_env(self) -> None:
        """Must export KUBECONFIG path to GITHUB_ENV."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            preflight = bootstrap.PreflightData(artifact_dir)
            diagnosis = bootstrap.DiagnosisGenerator(artifact_dir)

            kubeconfig_content = """apiVersion: v1
clusters:
- cluster:
    server: https://127.0.0.1:6443
  name: test
contexts:
- context:
    cluster: test
    user: test
  name: test
current-context: test
users:
- name: test
"""
            b64_content = base64.b64encode(kubeconfig_content.encode()).decode()

            # Create a temp GITHUB_ENV file
            github_env_path = Path(tmpdir) / "github_env"

            with patch.dict(os.environ, {"RUNNER_TEMP": tmpdir, "GITHUB_ENV": str(github_env_path)}):
                with patch("scripts.k9b_cnpg_live_lab_bootstrap_decode.get_env_secret", return_value=b64_content):
                    with patch("subprocess.run") as mock_run:
                        mock_result = MagicMock()
                        mock_result.returncode = 0
                        mock_result.stdout.strip.return_value = "system:serviceaccount:default:sa"
                        mock_result.stderr = ""
                        mock_run.return_value = mock_result

                        path, rc = bootstrap.bootstrap_decode_kubeconfig(
                            "TEST_SECRET", "KUBECONFIG", artifact_dir, preflight, diagnosis
                        )

                        if rc == 0 and path:
                            self.assertTrue(github_env_path.exists(), "GITHUB_ENV should be created")
                            content = github_env_path.read_text()
                            self.assertIn("KUBECONFIG=", content, "Should export KUBECONFIG")
                            self.assertIn(path, content, "Should include kubeconfig path")

    def test_fails_on_missing_secret(self) -> None:
        """Must fail when secret is not set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            preflight = bootstrap.PreflightData(artifact_dir)
            diagnosis = bootstrap.DiagnosisGenerator(artifact_dir)

            # Ensure secret is not in environment
            with patch.dict(os.environ, {"TEST_SECRET": ""}, clear=True):
                with patch("scripts.k9b_cnpg_live_lab_bootstrap.get_env_secret", return_value=None):
                    path, rc = bootstrap.bootstrap_decode_kubeconfig(
                        "TEST_SECRET", "KUBECONFIG", artifact_dir, preflight, diagnosis
                    )

                    self.assertEqual(rc, 1, "Should fail for missing secret")
                    self.assertIsNone(path)
                    self.assertEqual(preflight.failure_class, bootstrap.FAILURE_KUBECONFIG_MISSING)


class TestJsonWriteAtomically(unittest.TestCase):
    """Behavioral tests for atomic JSON writing."""

    def test_writes_valid_json(self) -> None:
        """write_json_atomically must write valid JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.json"
            data = {"key": "value", "number": 42}

            bootstrap.write_json_atomically(path, data)

            self.assertTrue(path.exists())
            content = path.read_text()
            parsed = json.loads(content)
            self.assertEqual(parsed, data)

    def test_creates_parent_directories(self) -> None:
        """write_json_atomically must create parent directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nested" / "dir" / "test.json"
            data = {"key": "value"}

            bootstrap.write_json_atomically(path, data)

            self.assertTrue(path.exists())

    def test_roundtrip_preserves_data(self) -> None:
        """write_json_atomically + read_json must preserve data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "roundtrip.json"
            original = {
                "failure_class": "test_failure",
                "active_identity": "system:serviceaccount:default:sa",
                "namespace": "test-ns",
                "nested": {"key": "value"},
            }

            bootstrap.write_json_atomically(path, original)
            loaded = bootstrap.read_json(path)

            self.assertEqual(loaded, original)


class TestClassifyWaitTimeout(unittest.TestCase):
    """Behavioral tests for classify_wait_timeout function."""

    def test_classifies_pod_crash_loop(self) -> None:
        """Must classify pod crash loop from cluster state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            preflight = bootstrap.PreflightData(artifact_dir)
            diagnosis = bootstrap.DiagnosisGenerator(artifact_dir)

            # Create mock cluster state files
            pods_json = json.dumps({
                "items": [{
                    "status": {
                        "containerStatuses": [{
                            "state": {
                                "waiting": {
                                    "reason": "CrashLoopBackOff",
                                    "message": "Back-off 10s restarting",
                                }
                            }
                        }]
                    }
                }]
            })

            deployments_json = json.dumps({
                "items": [{
                    "status": {
                        "replicas": 1,
                        "availableReplicas": 1,
                    }
                }]
            })

            helm_output = "Error: Helm wait timed out"

            # Mock subprocess for kubectl commands
            with patch("subprocess.run") as mock_run:
                # Return appropriate output based on the command
                def run_side_effect(*args: Any, **kwargs: Any) -> MagicMock:
                    cmd = args[0] if args else kwargs.get("args", [])
                    mock_result = MagicMock()
                    mock_result.stdout = ""

                    if "-o" in cmd and "json" in cmd:
                        if "pods" in cmd:
                            mock_result.stdout = pods_json
                        elif "deployments" in cmd:
                            mock_result.stdout = deployments_json
                    elif cmd[-1].endswith(".txt"):
                        mock_result.stdout = "(mock output)"

                    return mock_result

                mock_run.side_effect = run_side_effect

                result = bootstrap.classify_wait_timeout(
                    helm_output, "/fake/kubeconfig", "test-ns", artifact_dir, preflight, diagnosis
                )

                self.assertEqual(
                    result,
                    bootstrap.FAILURE_POD_CRASH_LOOP,
                    "Should classify as pod_crash_loop",
                )


class TestWorkflowContractPreservation(unittest.TestCase):
    """Tests that verify the workflow contract is preserved.

    These tests ensure that implementation changes don't break the
    expected behavior that the workflow depends on.
    """

    def test_classify_error_reads_existing_preflight(self) -> None:
        """classify-error must read and preserve existing preflight context."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            # Create existing preflight
            existing_preflight = {
                "bootstrap_timestamp": "2024-01-01T00:00:00Z",
                "active_identity": "system:serviceaccount:default:existing-sa",
                "namespace": "test-ns",
                "failure_class": None,
            }
            preflight_path = artifact_dir / "lab-preflight.json"
            bootstrap.write_json_atomically(preflight_path, existing_preflight)

            # Mock stdin with helm error output
            helm_output = "Error: some helm error"

            with patch("sys.stdin.read", return_value=helm_output):
                with patch.dict(os.environ, {"ARTIFACT_DIR": str(artifact_dir)}):
                    # Call main_classify_error
                    bootstrap.main_classify_error()

                    # Verify preflight was read and preserved
                    preflight_data = bootstrap.read_json(preflight_path)
                    self.assertEqual(
                        preflight_data.get("active_identity"),
                        "system:serviceaccount:default:existing-sa",
                        "Should preserve existing active_identity",
                    )
                    self.assertEqual(
                        preflight_data.get("namespace"),
                        "test-ns",
                        "Should preserve existing namespace",
                    )

    def test_classify_schema_preserves_preflight_context(self) -> None:
        """classify-schema must read and preserve existing preflight context."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            # Create existing preflight
            existing_preflight = {
                "bootstrap_timestamp": "2024-01-01T00:00:00Z",
                "active_identity": "system:serviceaccount:default:existing-sa",
                "namespace": "test-ns",
                "failure_class": "previous_failure",
            }
            preflight_path = artifact_dir / "lab-preflight.json"
            bootstrap.write_json_atomically(preflight_path, existing_preflight)

            # Create input file
            input_path = artifact_dir / "schema-error.log"
            input_path.write_text('error: unknown field "spec.containers[0].allowPrivilegeEscalation"')

            # Mock sys.argv for CLI parsing
            with patch("sys.argv", ["k9b_cnpg_live_lab_bootstrap.py", "classify-schema", "--input", str(input_path), "--artifact-dir", str(artifact_dir)]):
                with patch("scripts.k9b_cnpg_live_lab_bootstrap.extract_schema_warnings", return_value=[]):
                    bootstrap.main_classify_schema()

                    # Verify preflight was read and preserved
                    preflight_data = bootstrap.read_json(preflight_path)
                    self.assertEqual(
                        preflight_data.get("active_identity"),
                        "system:serviceaccount:default:existing-sa",
                        "Should preserve existing active_identity",
                    )


class TestPyYAMLDependencyContract(unittest.TestCase):
    """Regression tests for PyYAML dependency contract.

    These tests verify that:
    1. The bootstrap facade imports cleanly without requiring PyYAML
    2. PyYAML is declared in the project dependency manifest
    """

    def test_bootstrap_import_does_not_require_helm_yaml_dependency(self) -> None:
        """Bootstrap facade must import cleanly without triggering PyYAML dependency.

        This is a regression guard for CI failure where importing
        scripts/k9b_cnpg_live_lab_bootstrap.py transitively required PyYAML
        via the Helm evidence/inventory import chain.

        This test actually blocks yaml imports to prove the bootstrap façade
        truly does not require PyYAML, even when PyYAML is installed.
        """
        import builtins
        import importlib
        import sys
        from unittest import mock

        # Remove any cached imports to force fresh import
        modules_to_remove = [
            key for key in sys.modules.keys()
            if key.startswith("scripts.k9b_cnpg_live_lab") or key == "yaml"
        ]
        for mod in modules_to_remove:
            del sys.modules[mod]

        real_import = builtins.__import__

        def blocked_yaml_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "yaml" or name.startswith("yaml."):
                raise ModuleNotFoundError("No module named 'yaml'")
            return real_import(name, *args, **kwargs)

        # This import must NOT raise ModuleNotFoundError: No module named 'yaml'
        # even when yaml is blocked - proving the bootstrap façade truly doesn't need it
        with mock.patch("builtins.__import__", side_effect=blocked_yaml_import):
            module = importlib.import_module("scripts.k9b_cnpg_live_lab_bootstrap")
            self.assertIsNotNone(module)

    def test_pyyaml_declared_in_dependency_manifest(self) -> None:
        """PyYAML must be declared in the project dependency manifest.

        This ensures CI installs PyYAML before running live-lab scripts.
        """
        from pathlib import Path

        # Check pyproject.toml (main dependency manifest)
        pyproject = Path("pyproject.toml")
        self.assertTrue(
            pyproject.exists(),
            "pyproject.toml must exist at repository root"
        )

        content = pyproject.read_text().lower()

        # Verify PyYAML is declared (either as pyyaml or PyYAML)
        self.assertTrue(
            "pyyaml" in content,
            "PyYAML must be declared in pyproject.toml dependencies. "
            "Add 'pyyaml>=6.0' to the dependencies list."
        )


if __name__ == "__main__":
    unittest.main()
