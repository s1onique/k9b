"""Regression tests for live lab CLI contract drift.

These tests verify backward compatibility between:
- GitHub Actions workflow (uses --deadline, --poll-interval, no --helm-log)
- Python CLI (expects --max-wait, --interval, required --helm-log)

The workflow was failing with:
    error: unrecognized arguments: --deadline 90 --poll-interval 8
    error: the following arguments are required: --helm-log

Fix: Add alias flags and make --helm-log optional with default.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Import the CLI module to test argument parsing
import scripts.k9b_cnpg_live_lab_cli as cli_module


class TestMonitorRolloutCliContract(unittest.TestCase):
    """Test that monitor-rollout accepts both canonical and legacy flag names."""

    def test_monitor_rollout_accepts_canonical_max_wait(self) -> None:
        """monitor-rollout must accept --max-wait flag."""
        test_args = [
            "monitor-rollout",
            "--kubeconfig", "/tmp/kubeconfig",
            "--namespace", "test-ns",
            "--max-wait", "90",
        ]
        # Patch sys.argv and _monitor_rollout to verify parsing
        with patch.object(sys, "argv", ["k9b_cnpg_live_lab_bootstrap.py"] + test_args):
            with patch.object(cli_module, "_monitor_rollout") as mock_monitor:
                mock_monitor.return_value = (True, "Ready", None)
                # Should not raise argparse error
                try:
                    cli_module.main_monitor_rollout()
                except SystemExit as e:
                    # argparse exits with 2 on parse error
                    if e.code == 2:
                        self.fail("Argument parsing failed: --max-wait not recognized")
                # Verify the mock was called with correct max_wait
                call_kwargs = mock_monitor.call_args
                self.assertEqual(call_kwargs[0][3], 90, "max_wait should be 90")

    def test_monitor_rollout_accepts_legacy_deadline_alias(self) -> None:
        """monitor-rollout must accept --deadline as alias for --max-wait.

        This is the regression test for the workflow failure:
            error: unrecognized arguments: --deadline 90
        """
        test_args = [
            "monitor-rollout",
            "--kubeconfig", "/tmp/kubeconfig",
            "--namespace", "test-ns",
            "--deadline", "90",  # Legacy alias from workflow
        ]
        with patch.object(sys, "argv", ["k9b_cnpg_live_lab_bootstrap.py"] + test_args):
            with patch.object(cli_module, "_monitor_rollout") as mock_monitor:
                mock_monitor.return_value = (True, "Ready", None)
                # Should not raise argparse error
                try:
                    cli_module.main_monitor_rollout()
                except SystemExit as e:
                    if e.code == 2:
                        self.fail("Argument parsing failed: --deadline not recognized as alias for --max-wait")
                # Verify the mock was called with correct max_wait
                call_kwargs = mock_monitor.call_args
                self.assertEqual(call_kwargs[0][3], 90, "--deadline should map to max_wait=90")

    def test_monitor_rollout_accepts_canonical_interval(self) -> None:
        """monitor-rollout must accept --interval flag."""
        test_args = [
            "monitor-rollout",
            "--kubeconfig", "/tmp/kubeconfig",
            "--namespace", "test-ns",
            "--interval", "8",
        ]
        with patch.object(sys, "argv", ["k9b_cnpg_live_lab_bootstrap.py"] + test_args):
            with patch.object(cli_module, "_monitor_rollout") as mock_monitor:
                mock_monitor.return_value = (True, "Ready", None)
                try:
                    cli_module.main_monitor_rollout()
                except SystemExit as e:
                    if e.code == 2:
                        self.fail("Argument parsing failed: --interval not recognized")
                call_kwargs = mock_monitor.call_args
                self.assertEqual(call_kwargs[0][4], 8, "interval should be 8")

    def test_monitor_rollout_accepts_legacy_poll_interval_alias(self) -> None:
        """monitor-rollout must accept --poll-interval as alias for --interval.

        This is the regression test for the workflow failure:
            error: unrecognized arguments: --poll-interval 8
        """
        test_args = [
            "monitor-rollout",
            "--kubeconfig", "/tmp/kubeconfig",
            "--namespace", "test-ns",
            "--poll-interval", "8",  # Legacy alias from workflow
        ]
        with patch.object(sys, "argv", ["k9b_cnpg_live_lab_bootstrap.py"] + test_args):
            with patch.object(cli_module, "_monitor_rollout") as mock_monitor:
                mock_monitor.return_value = (True, "Ready", None)
                try:
                    cli_module.main_monitor_rollout()
                except SystemExit as e:
                    if e.code == 2:
                        self.fail("Argument parsing failed: --poll-interval not recognized as alias for --interval")
                call_kwargs = mock_monitor.call_args
                self.assertEqual(call_kwargs[0][4], 8, "--poll-interval should map to interval=8")

    def test_monitor_rollout_accepts_workflow_flags_combined(self) -> None:
        """monitor-rollout must accept the exact workflow flag combination.

        This tests the exact failure case from the workflow:
            monitor-rollout --deadline 90 --poll-interval 8
        """
        test_args = [
            "monitor-rollout",
            "--kubeconfig", "/tmp/kubeconfig",
            "--namespace", "test-ns",
            "--artifact-dir", "/tmp/artifacts",
            "--deadline", "90",      # Legacy alias
            "--poll-interval", "8",  # Legacy alias
        ]
        with patch.object(sys, "argv", ["k9b_cnpg_live_lab_bootstrap.py"] + test_args):
            with patch.object(cli_module, "_monitor_rollout") as mock_monitor:
                mock_monitor.return_value = (True, "Ready", None)
                try:
                    cli_module.main_monitor_rollout()
                except SystemExit as e:
                    if e.code == 2:
                        self.fail("Argument parsing failed for workflow flags: --deadline 90 --poll-interval 8")
                call_kwargs = mock_monitor.call_args
                self.assertEqual(call_kwargs[0][3], 90, "max_wait should be 90")
                self.assertEqual(call_kwargs[0][4], 8, "interval should be 8")


class TestClassifyWaitTimeoutCliContract(unittest.TestCase):
    """Test that classify-wait-timeout handles missing --helm-log gracefully."""

    def test_classify_wait_timeout_requires_namespace(self) -> None:
        """classify-wait-timeout must still require --namespace."""
        test_args = [
            "classify-wait-timeout",
            # No --namespace - should fail
        ]
        with patch.object(sys, "argv", ["k9b_cnpg_live_lab_bootstrap.py"] + test_args):
            with patch.object(cli_module, "DiagnosisGenerator") as mock_diag:
                mock_diag.return_value = MagicMock()
                with patch.object(cli_module, "PreflightData") as mock_preflight:
                    mock_preflight.return_value = MagicMock()
                    with self.assertRaises(SystemExit) as context:
                        cli_module.main_classify_wait_timeout()
                    # Should exit with code 2 (argparse error), not crash
                    self.assertEqual(context.exception.code, 2)

    def test_classify_wait_timeout_works_without_helm_log(self) -> None:
        """classify-wait-timeout must not crash when --helm-log is omitted.

        This is the regression test for the workflow failure:
            error: the following arguments are required: --helm-log

        The workflow calls classify-wait-timeout without --helm-log, expecting
        the classifier to use a default path or skip gracefully.
        """
        test_args = [
            "classify-wait-timeout",
            "--namespace", "test-ns",
            # No --helm-log - should use default
        ]
        with patch.object(sys, "argv", ["k9b_cnpg_live_lab_bootstrap.py"] + test_args):
            with patch.object(cli_module, "DiagnosisGenerator") as mock_diag:
                mock_diag.return_value = MagicMock()
                with patch.object(cli_module, "PreflightData") as mock_preflight:
                    mock_preflight.return_value = MagicMock()
                    with patch.object(cli_module, "read_json") as mock_read:
                        mock_read.return_value = None  # No existing preflight
                        with patch.object(cli_module, "subprocess") as mock_subprocess:
                            mock_subprocess.run.return_value = MagicMock(stdout="")
                            # Should not raise argparse error
                            try:
                                cli_module.main_classify_wait_timeout()
                            except SystemExit as e:
                                if e.code == 2:
                                    self.fail("Argument parsing failed: --helm-log should not be required")

    def test_classify_wait_timeout_accepts_helm_log_when_provided(self) -> None:
        """classify-wait-timeout must still accept --helm-log when explicitly provided."""
        test_args = [
            "classify-wait-timeout",
            "--namespace", "test-ns",
            "--helm-log", "/tmp/helm-install.log",
        ]
        with patch.object(sys, "argv", ["k9b_cnpg_live_lab_bootstrap.py"] + test_args):
            with patch.object(cli_module, "DiagnosisGenerator") as mock_diag:
                mock_diag.return_value = MagicMock()
                with patch.object(cli_module, "PreflightData") as mock_preflight:
                    mock_preflight.return_value = MagicMock()
                    with patch.object(cli_module, "read_json") as mock_read:
                        mock_read.return_value = None
                        with patch.object(cli_module, "subprocess") as mock_subprocess:
                            mock_subprocess.run.return_value = MagicMock(stdout="")
                            # Should parse successfully
                            cli_module.main_classify_wait_timeout()

    def test_classify_wait_timeout_uses_helm_log_default_path(self) -> None:
        """classify-wait-timeout should default to ./lab-artifacts/live/logs/helm-install.log."""
        # Clear any env var that might affect the test
        old_helm_log = os.environ.pop("HELM_LOG", None)

        try:
            test_args = [
                "classify-wait-timeout",
                "--namespace", "test-ns",
                # No --helm-log
            ]

            # Test that parsing works without --helm-log
            with patch.object(sys, "argv", ["k9b_cnpg_live_lab_bootstrap.py"] + test_args):
                with patch.object(cli_module, "DiagnosisGenerator") as mock_diag:
                    mock_diag.return_value = MagicMock()
                    with patch.object(cli_module, "PreflightData") as mock_preflight:
                        mock_preflight.return_value = MagicMock()
                        with patch.object(cli_module, "read_json") as mock_read:
                            mock_read.return_value = None
                            with patch.object(cli_module, "subprocess") as mock_subprocess:
                                mock_subprocess.run.return_value = MagicMock(stdout="")
                                # This should NOT raise SystemExit with code 2
                                try:
                                    cli_module.main_classify_wait_timeout()
                                except SystemExit as e:
                                    if e.code == 2:
                                        self.fail("--helm-log should not be required, got argparse error")
                                    # Other exit codes are fine (e.g., 0 for success)

            # Now verify the default path is correct by checking the source
            # The HELM_LOG default is in the wait_timeout module (delegation pattern)
            wait_timeout_source = Path(__file__).parent.parent / "scripts" / "k9b_cnpg_live_lab_wait_timeout.py"
            source_content = wait_timeout_source.read_text()

            # The default should be set from environment or fallback to standard path
            self.assertIn("HELM_LOG", source_content, "Should have HELM_LOG env var support")
            self.assertIn("helm-install.log", source_content, "Should have helm-install.log in default")
        finally:
            # Restore environment
            if old_helm_log:
                os.environ["HELM_LOG"] = old_helm_log


class TestWorkflowContractIntegration(unittest.TestCase):
    """Integration tests for the complete workflow contract fix."""

    def test_workflow_failure_path_no_argparse_crash(self) -> None:
        """Simulate the workflow failure path - monitor fails then classifier runs.

        The original failure sequence was:
        1. monitor-rollout fails with argparse error (unrecognized --deadline, --poll-interval)
        2. classifier runs but also fails with argparse error (missing --helm-log)
        3. Classifier's argparse crash masks the original monitor failure

        After the fix:
        - monitor-rollout parses successfully
        - classifier parses successfully (helm-log has default)
        - Original monitor exit code is preserved
        """
        # Step 1: Simulate monitor-rollout with workflow flags (should succeed)
        monitor_args = [
            "monitor-rollout",
            "--kubeconfig", "/tmp/kubeconfig",
            "--namespace", "test-ns",
            "--artifact-dir", "/tmp/artifacts",
            "--deadline", "90",
            "--poll-interval", "8",
        ]

        with patch.object(sys, "argv", ["k9b_cnpg_live_lab_bootstrap.py"] + monitor_args):
            with patch.object(cli_module, "_monitor_rollout") as mock_monitor:
                mock_monitor.return_value = (False, "Timeout", None)  # Simulate failure
                with patch.object(cli_module, "write_json_atomically"):
                    # Should not raise argparse error
                    rc = cli_module.main_monitor_rollout()
                    # Should return 1 (failure) not exit code 2 (argparse error)
                    self.assertEqual(rc, 1, "Should return failure exit code, not argparse error")

        # Step 2: Simulate classifier call without --helm-log (should succeed)
        classifier_args = [
            "classify-wait-timeout",
            "--namespace", "test-ns",
            "--kubeconfig", "/tmp/kubeconfig",
            # Note: no --helm-log - workflow doesn't pass it
        ]

        with patch.object(sys, "argv", ["k9b_cnpg_live_lab_bootstrap.py"] + classifier_args):
            with patch.object(cli_module, "DiagnosisGenerator") as mock_diag:
                mock_diag.return_value = MagicMock()
                with patch.object(cli_module, "PreflightData") as mock_preflight:
                    mock_preflight.return_value = MagicMock()
                    with patch.object(cli_module, "read_json") as mock_read:
                        mock_read.return_value = None
                        with patch.object(cli_module, "subprocess") as mock_subprocess:
                            mock_subprocess.run.return_value = MagicMock(stdout="")
                            # Should not raise argparse error
                            try:
                                rc = cli_module.main_classify_wait_timeout()
                            except SystemExit as e:
                                self.fail(f"Classifier argparse failed: {e}. --helm-log should have default.")

        # Success: Both commands parse successfully, original monitor failure preserved

    def test_monitor_rollout_with_no_flags_uses_defaults(self) -> None:
        """When no timing flags provided, should use sensible defaults."""
        test_args = [
            "monitor-rollout",
            "--kubeconfig", "/tmp/kubeconfig",
            "--namespace", "test-ns",
        ]
        with patch.object(sys, "argv", ["k9b_cnpg_live_lab_bootstrap.py"] + test_args):
            with patch.object(cli_module, "_monitor_rollout") as mock_monitor:
                mock_monitor.return_value = (True, "Ready", None)
                cli_module.main_monitor_rollout()
                call_kwargs = mock_monitor.call_args
                # Default max_wait should be 300, interval should be 15
                self.assertEqual(call_kwargs[0][3], 300, "Default max_wait should be 300")
                self.assertEqual(call_kwargs[0][4], 15, "Default interval should be 15")


class TestCliImportTimeBehavior(unittest.TestCase):
    """Regression tests for CLI import-time behavior.

    These tests verify that the CLI can be imported and used for --help
    without triggering expensive/classifier-only imports that require PyYAML.

    Original failure: ModuleNotFoundError: No module named 'yaml'
    Root cause: Eager top-level import of wait_timeout module chain.
    Fix: Lazy import in main_classify_wait_timeout().
    """

    def test_cli_module_can_be_imported(self) -> None:
        """CLI module must be importable without errors."""
        # This test verifies the module loads correctly after lazy import fix
        import scripts.k9b_cnpg_live_lab_cli as cli
        self.assertTrue(hasattr(cli, "main_classify_wait_timeout"))
        self.assertTrue(hasattr(cli, "main_monitor_rollout"))

    def test_bootstrap_module_can_be_imported(self) -> None:
        """Bootstrap module must be importable without errors."""
        import scripts.k9b_cnpg_live_lab_bootstrap as bootstrap
        self.assertTrue(hasattr(bootstrap, "main_classify_wait_timeout"))
        self.assertTrue(hasattr(bootstrap, "main_monitor_rollout"))

    def test_main_classify_wait_timeout_uses_lazy_import(self) -> None:
        """Verify main_classify_wait_timeout uses lazy import pattern.

        This ensures that importing the CLI module does NOT trigger
        the full classifier stack import chain (which requires PyYAML).
        """
        cli_source = Path(__file__).parent.parent / "scripts" / "k9b_cnpg_live_lab_cli.py"
        cli_content = cli_source.read_text()

        # The function should use a lazy import pattern (from import inside function)
        # NOT a top-level import
        self.assertIn(
            "from scripts.k9b_cnpg_live_lab_wait_timeout import main_classify_wait_timeout",
            cli_content,
            "Should have lazy import inside main_classify_wait_timeout function"
        )


if __name__ == "__main__":
    unittest.main()
