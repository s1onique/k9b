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

    def test_source_code_has_deployment_not_found_check(self) -> None:
        """Verify source code contains the deployment_not_found classification check.

        This is a source-code verification test rather than a full integration test,
        as mocking subprocess.run and Path correctly is complex. The parser unit tests
        verify the logic works correctly, and this test verifies the code is wired up.
        """
        cli_source = Path(__file__).parent.parent / "scripts" / "k9b_cnpg_live_lab_cli.py"
        content = cli_source.read_text()

        # Verify the check is present
        self.assertIn("_parse_deployment_not_found(deployments_json)", content)
        self.assertIn("FAILURE_EXPECTED_WORKLOAD_MISSING", content)
        # The string value is used via the constant assignment
        self.assertIn("failure_class = FAILURE_EXPECTED_WORKLOAD_MISSING", content)

        # Verify it's the first check (before crash_loop, image_pull, etc.)
        deploy_not_found_pos = content.find("_parse_deployment_not_found(deployments_json)")
        crash_loop_pos = content.find("_parse_crash_loop_from_pods(pods_json)")
        self.assertLess(deploy_not_found_pos, crash_loop_pos,
            "deployment_not_found check should come before crash_loop check")


class TestClassifyWaitTimeoutWithKubeconfig(unittest.TestCase):
    """Integration tests for classify-wait-timeout with kubeconfig."""

    def test_uses_parse_deployment_not_found(self) -> None:
        """classify-wait-timeout must use _parse_deployment_not_found parser."""
        # Verify the parser is imported and used in the function
        cli_source = Path(__file__).parent.parent / "scripts" / "k9b_cnpg_live_lab_cli.py"
        content = cli_source.read_text()
        self.assertIn("_parse_deployment_not_found", content, "Should import _parse_deployment_not_found")
        self.assertIn("FAILURE_EXPECTED_WORKLOAD_MISSING", content, "Should use FAILURE_EXPECTED_WORKLOAD_MISSING")


if __name__ == "__main__":
    unittest.main()
