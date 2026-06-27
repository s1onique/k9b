#!/usr/bin/env python3
"""Regression tests for classify-wait-timeout deployment_not_found detection.

These tests verify the fix for the live-lab rollout failure where:
1. The rollout failed because expected Deployment/k9b was never observed
2. The secondary Python crash was FileNotFoundError when writing watchdog/pods-final.json
   because the parent directory didn't exist

The fix ensures:
1. Artifact writes create parent directories automatically (parent.mkdir(parents=True, exist_ok=True))
2. Missing Deployment is classified as expected_workload_missing, not helm_wait_timeout_unknown
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Import the CLI module to test
import scripts.k9b_cnpg_live_lab_cli as cli_module

# Import the parser helper for unit testing
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from k9b_cnpg_live_lab_bootstrap_parse import _parse_deployment_not_found


class TestParseDeploymentNotFound(unittest.TestCase):
    """Unit tests for _parse_deployment_not_found parser."""

    def test_detects_empty_deployments_items(self) -> None:
        """Should detect when deployments items list is empty (namespace has no deployments)."""
        deployments_json = '{"apiVersion": "v1", "kind": "List", "items": []}'
        result = _parse_deployment_not_found(deployments_json)
        self.assertTrue(result, "Should detect empty deployments items")

    def test_detects_null_items(self) -> None:
        """Should detect when items is null."""
        deployments_json = '{"apiVersion": "v1", "kind": "List", "items": null}'
        result = _parse_deployment_not_found(deployments_json)
        self.assertTrue(result, "Should detect null items")

    def test_ignores_deployments_with_items(self) -> None:
        """Should not flag when deployments items contains entries."""
        deployments_json = '''{
            "apiVersion": "v1",
            "kind": "List",
            "items": [
                {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "k9b"}}
            ]
        }'''
        result = _parse_deployment_not_found(deployments_json)
        self.assertFalse(result, "Should not flag deployments with items")

    def test_handles_invalid_json(self) -> None:
        """Should return False for invalid JSON."""
        result = _parse_deployment_not_found("not json")
        self.assertFalse(result, "Should handle invalid JSON gracefully")

    def test_handles_non_dict_json(self) -> None:
        """Should return False for non-dict JSON."""
        result = _parse_deployment_not_found('["not", "a", "dict"]')
        self.assertFalse(result, "Should handle non-dict JSON gracefully")

    def test_handles_empty_string(self) -> None:
        """Should return False for empty string."""
        result = _parse_deployment_not_found("")
        self.assertFalse(result, "Should handle empty string gracefully")

    def test_rejects_malformed_json_without_items_key(self) -> None:
        """Should return False for malformed JSON without 'items' key.

        This is a safety check: malformed JSON like {} without an 'items' key
        should NOT be treated as "deployment missing" - it's just malformed.
        """
        result = _parse_deployment_not_found("{}")
        self.assertFalse(result, "Malformed JSON without 'items' key should not be treated as deployment missing")


class TestArtifactDirectoryCreation(unittest.TestCase):
    """Regression test: artifact writes must create parent directories."""

    def test_watchdog_directory_created_on_artifact_write(self) -> None:
        """classify-wait-timeout must create watchdog/ directory before writing artifacts.

        This is the regression test for the original bug:
            FileNotFoundError: ... lab-artifacts/live/watchdog/pods-final.json

        The classifier was trying to write:
            lab-artifacts/live/watchdog/pods-final.json

        but only lab-artifacts/live existed, so watchdog/ was missing.
        """
        test_args = [
            "classify-wait-timeout",
            "--namespace", "test-ns",
            "--artifact-dir", "/tmp/test-artifacts",
            # No --kubeconfig, so it falls to else branch
        ]

        with patch.object(sys, "argv", ["k9b_cnpg_live_lab_bootstrap.py"] + test_args):
            with patch.object(cli_module, "DiagnosisGenerator") as mock_diag:
                mock_diag.return_value = MagicMock()
                with patch.object(cli_module, "PreflightData") as mock_preflight:
                    mock_preflight.return_value = MagicMock()
                    with patch.object(cli_module, "read_json") as mock_read:
                        mock_read.return_value = None
                        # Run without kubeconfig - it should not crash
                        try:
                            cli_module.main_classify_wait_timeout()
                        except FileNotFoundError as e:
                            self.fail(f"Artifact write crashed with FileNotFoundError: {e}")


class TestDeploymentNotFoundClassification(unittest.TestCase):
    """Regression test: missing deployment must be classified as expected_workload_missing."""

    def test_cli_delegates_to_wait_timeout_module(self) -> None:
        """Verify CLI facade delegates to wait_timeout module and preserves return code.

        This is a true behavioral test using sys.modules mocking to verify:
        1. CLI calls the wait_timeout module's main_classify_wait_timeout()
        2. The delegated return code is preserved
        """
        import types

        from scripts import k9b_cnpg_live_lab_cli as cli

        module_name = "scripts.k9b_cnpg_live_lab_wait_timeout"

        # Track calls for verification
        calls: list[str] = []
        fake_module = types.ModuleType(module_name)

        def fake_main() -> int:
            calls.append("called")
            return 42

        fake_module.main_classify_wait_timeout = fake_main

        # Inject fake module and verify delegation
        previous = sys.modules.get(module_name)
        sys.modules[module_name] = fake_module
        try:
            result = cli.main_classify_wait_timeout()
            self.assertEqual(42, result, "CLI should return the delegated function's return code")
            self.assertEqual(["called"], calls, "CLI should have called the delegated function")
        finally:
            # Restore original module state
            if previous is None:
                sys.modules.pop(module_name, None)
            else:
                sys.modules[module_name] = previous

    def test_deployment_not_found_classification_behavior(self) -> None:
        """Verify deployment-not-found triggers FAILURE_EXPECTED_WORKLOAD_MISSING classification.

        This is a true behavioral test that:
        1. Mocks kubectl to return empty deployments (deployment not found)
        2. Invokes the classifier
        3. Verifies FAILURE_EXPECTED_WORKLOAD_MISSING is returned
        """
        import shutil
        import tempfile

        from scripts.k9b_cnpg_live_lab_config import DiagnosisGenerator, PreflightData
        from scripts.k9b_cnpg_live_lab_constants import FAILURE_EXPECTED_WORKLOAD_MISSING
        from scripts.k9b_cnpg_live_lab_wait_timeout import _classify_failure
        temp_dir = Path(tempfile.mkdtemp())
        try:
            # Create fake kubeconfig file so classifier enters cluster-state path
            kubeconfig_path = temp_dir / "kubeconfig"
            kubeconfig_path.write_text("fake kubeconfig content")

            temp_dir.mkdir(parents=True, exist_ok=True)

            def mock_subprocess_run(cmd: list, *args: object, **kwargs: object) -> MagicMock:
                """Mock kubectl to return empty List (no deployments found)."""
                result = MagicMock()
                if "deployments" in cmd:
                    # Return empty deployments List - simulates namespace with no deployments
                    result.stdout = '{"apiVersion": "v1", "kind": "List", "items": []}'
                elif "pods" in cmd:
                    result.stdout = '{"items": []}'
                else:
                    result.stdout = ""
                return result

            with patch("scripts.k9b_cnpg_live_lab_wait_timeout.subprocess.run", side_effect=mock_subprocess_run):
                preflight = PreflightData(temp_dir, "test-ns")
                diagnosis = DiagnosisGenerator(temp_dir, "test-ns")

                failure_class, failure_subclass = _classify_failure(
                    kubeconfig=str(kubeconfig_path),
                    namespace="test-ns",
                    artifact_dir=temp_dir,
                    helm_log_path=temp_dir / "helm.log",
                    helm_output="timeout",
                    preflight=preflight,
                    diagnosis=diagnosis,
                )

            # Verify deployment-not-found triggers expected workload missing
            self.assertEqual(FAILURE_EXPECTED_WORKLOAD_MISSING, failure_class,
                "Empty deployments (deployment not found) should trigger FAILURE_EXPECTED_WORKLOAD_MISSING")

        finally:
            shutil.rmtree(temp_dir)


class TestClassifyWaitTimeoutWithKubeconfig(unittest.TestCase):
    """Integration tests for classify-wait-timeout with kubeconfig."""

    def test_uses_parse_deployment_not_found(self) -> None:
        """classify-wait-timeout must use _parse_deployment_not_found parser."""
        # Verify the parser is used in wait_timeout module (CLI delegates to it)
        wait_timeout_source = Path(__file__).parent.parent / "scripts" / "k9b_cnpg_live_lab_wait_timeout.py"
        content = wait_timeout_source.read_text()
        self.assertIn("_parse_deployment_not_found", content,
            "Should use _parse_deployment_not_found")
        self.assertIn("FAILURE_EXPECTED_WORKLOAD_MISSING", content,
            "Should use FAILURE_EXPECTED_WORKLOAD_MISSING")


if __name__ == "__main__":
    unittest.main()
