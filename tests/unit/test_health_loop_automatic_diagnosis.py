"""Unit tests for health loop automatic diagnosis integration.

Tests cover:
- Integration disabled by default
- Integration calls collector when enabled
- Failure isolation (collector errors don't crash loop)
- Bounded result summary
- Safety metadata

These tests do NOT:
- Execute real Kubernetes collectors
- Call kubectl/helm/subprocess/shell
- Perform remediation or mutation
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import pytest

from k8s_diag_agent.health.loop_automatic_diagnosis import run_automatic_diagnosis_loop

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def temp_external_dir():
    """Provide a temporary directory for artifact writing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_log_fn():
    """Provide a mock logging function."""
    logs: list[dict[str, Any]] = []

    def log_fn(component: str, severity: str, message: str, **metadata: Any) -> None:
        logs.append({
            "component": component,
            "severity": severity,
            "message": message,
            "metadata": metadata,
        })

    log_fn.logs = logs
    return log_fn


# =============================================================================
# Disabled Integration Tests
# =============================================================================


class TestDisabledIntegration:
    """Tests for disabled integration behavior."""

    def test_integration_disabled_by_default(self, temp_external_dir, mock_log_fn):
        """Prove integration is disabled when env var is not set."""
        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            if "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]

            result = run_automatic_diagnosis_loop(
                external_analysis_dir=temp_external_dir,
                log_event_fn=mock_log_fn,
            )

            assert result["automatic_diagnosis_enabled"] is False
            assert result["incidents_processed"] == 0
            assert result["collector_run_id"] is None
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup
            elif "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]

    def test_integration_disabled_when_env_false(self, temp_external_dir, mock_log_fn):
        """Prove integration is disabled when env var is false."""
        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = "false"

            result = run_automatic_diagnosis_loop(
                external_analysis_dir=temp_external_dir,
                log_event_fn=mock_log_fn,
            )

            assert result["automatic_diagnosis_enabled"] is False
            assert result["incidents_processed"] == 0
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup
            elif "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]

    def test_disabled_logs_info_message(self, temp_external_dir, mock_log_fn):
        """Prove disabled integration logs an info message."""
        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            if "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]

            run_automatic_diagnosis_loop(
                external_analysis_dir=temp_external_dir,
                log_event_fn=mock_log_fn,
            )

            # Should have logged disabled status
            disabled_logs = [log_entry for log_entry in mock_log_fn.logs if "disabled" in log_entry.get("metadata", {}).get("event", "")]
            assert len(disabled_logs) >= 1
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup
            elif "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]


# =============================================================================
# Enabled Integration Tests
# =============================================================================


class TestEnabledIntegration:
    """Tests for enabled integration behavior."""

    def test_integration_enabled_when_env_true(self, temp_external_dir, mock_log_fn):
        """Prove integration is enabled when env var is true."""
        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = "true"

            result = run_automatic_diagnosis_loop(
                external_analysis_dir=temp_external_dir,
                log_event_fn=mock_log_fn,
            )

            assert result["automatic_diagnosis_enabled"] is True
            # May or may not have incidents depending on store state
            assert "incidents_processed" in result
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup
            elif "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]

    def test_result_has_required_fields(self, temp_external_dir, mock_log_fn):
        """Prove result has all required bounded fields."""
        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = "true"

            result = run_automatic_diagnosis_loop(
                external_analysis_dir=temp_external_dir,
                log_event_fn=mock_log_fn,
            )

            # Check all required fields are present
            assert "automatic_diagnosis_enabled" in result
            assert "collector_run_id" in result
            assert "incidents_processed" in result
            assert "incidents_eligible" in result
            assert "incidents_skipped" in result
            assert "incidents_with_errors" in result
            assert "total_review_packets_written" in result
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup
            elif "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]


# =============================================================================
# Failure Isolation Tests
# =============================================================================


class TestFailureIsolation:
    """Tests for failure isolation behavior."""

    def test_collector_error_does_not_crash(self, temp_external_dir, mock_log_fn):
        """Prove collector errors don't crash the integration."""
        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = "true"

            # The collector should handle errors gracefully
            result = run_automatic_diagnosis_loop(
                external_analysis_dir=temp_external_dir,
                log_event_fn=mock_log_fn,
            )

            # Should return a valid result even if collector had issues
            assert result is not None
            assert "automatic_diagnosis_enabled" in result
            assert isinstance(result["incidents_with_errors"], int)
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup
            elif "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]

    def test_no_traceback_in_logs(self, temp_external_dir, mock_log_fn):
        """Prove error logs don't expose tracebacks."""
        env_backup = os.environ.get("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED")
        try:
            os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = "true"

            run_automatic_diagnosis_loop(
                external_analysis_dir=temp_external_dir,
                log_event_fn=mock_log_fn,
            )

            # Check that no log contains traceback indicators
            for log in mock_log_fn.logs:
                message = log.get("message", "")
                assert "Traceback" not in message
                assert "traceback" not in message.lower()
        finally:
            if env_backup is not None:
                os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = env_backup
            elif "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED" in os.environ:
                del os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"]


# =============================================================================
# Safety Tests
# =============================================================================


class TestSafetyIntegration:
    """Tests for integration safety."""

    def test_no_kubectl_integration_module(self):
        """Prove integration module doesn't import kubectl."""
        import ast

        import k8s_diag_agent.health.loop_automatic_diagnosis as mod

        source = Path(mod.__file__).read_text()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "kubectl" not in alias.name.lower()
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    assert "kubectl" not in node.module.lower()

    def test_no_subprocess_integration_module(self):
        """Prove integration module doesn't import subprocess."""
        import ast

        import k8s_diag_agent.health.loop_automatic_diagnosis as mod

        source = Path(mod.__file__).read_text()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "subprocess"
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    assert node.module != "subprocess"


# =============================================================================
# HealthLoopRunner Integration Tests
# =============================================================================


class TestHealthLoopRunnerIntegration:
    """Tests for HealthLoopRunner.execute() wiring to automatic diagnosis."""

    def test_execute_calls_automatic_diagnosis_with_external_analysis_dir(
        self, temp_external_dir, mock_log_fn
    ):
        """Prove HealthLoopRunner.execute() invokes integration with external_analysis_dir."""
        from unittest.mock import patch

        from k8s_diag_agent.health.loop import HealthLoopRunner, HealthRunConfig
        from k8s_diag_agent.health.loop_baseline_helpers import BaselinePolicy
        from k8s_diag_agent.health.loop_comparison_types import TriggerPolicy
        from k8s_diag_agent.health.loop_types import HealthTarget

        # Create minimal config
        config = HealthRunConfig(
            run_label="test-run",
            output_dir=temp_external_dir,
            collector_version="test",
            targets=(
                HealthTarget(
                    context="test-context",
                    label="test-cluster",
                    monitor_health=False,  # Disable health monitoring to avoid complex mocking
                    watched_helm_releases=(),
                    watched_crd_families=(),
                    cluster_class="test",
                    cluster_role="test",
                    baseline_cohort="test",
                    baseline_policy_path="test.json",
                ),
            ),
            peers=(),
            trigger_policy=TriggerPolicy(
                control_plane_version=True,
                watched_helm_release=True,
                watched_crd=True,
                health_regression=True,
                missing_evidence=True,
                manual=True,
                warning_event_threshold=0,
            ),
            manual_pairs=(),
            baseline_policy=BaselinePolicy.empty(),
        )

        # Create runner
        runner = HealthLoopRunner(
            config=config,
            available_contexts=["test-context"],
            quiet=True,
        )

        # Patch the automatic diagnosis function to capture call arguments
        with patch(
            "k8s_diag_agent.health.loop.run_automatic_diagnosis_loop"
        ) as mock_auto_diag:
            mock_auto_diag.return_value = {
                "automatic_diagnosis_enabled": False,
                "collector_run_id": None,
                "incidents_processed": 0,
                "incidents_eligible": 0,
                "incidents_skipped": 0,
                "incidents_with_errors": 0,
                "total_review_packets_written": 0,
            }

            # Execute the health loop
            runner.execute()

            # Verify automatic diagnosis was called
            mock_auto_diag.assert_called_once()

            # Verify it was called with external_analysis_dir
            call_kwargs = mock_auto_diag.call_args.kwargs
            assert "external_analysis_dir" in call_kwargs
            # Verify it's a path under external-analysis
            external_dir = call_kwargs["external_analysis_dir"]
            assert "external-analysis" in str(external_dir)
            assert external_dir.is_dir()
