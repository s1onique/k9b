"""Tests for scheduler pod selector derivation from deployment.

These tests verify that:
1. app.kubernetes.io/name=k9b-scheduler is NOT used as the hard-coded selector
2. Selector is correctly derived from deployment/k9b-scheduler.spec.selector.matchLabels
3. Fallback works when deployment cannot be read
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch


class TestSchedulerSelectorNotHardcoded:
    """Verify hard-coded scheduler selector is not used in production code."""

    def test_no_hardcoded_scheduler_selector_in_collect_module(self) -> None:
        """The collect_scheduler_logs function must not use app.kubernetes.io/name=k9b-scheduler."""
        from scripts.incident_discovery_gate.collect import collect_scheduler_logs

        # Mock the get_scheduler_pod_selector to return a correct selector
        fake_selector = "app.kubernetes.io/component=scheduler,app.kubernetes.io/name=k9b"

        with patch(
            "scripts.incident_discovery_gate.collect.get_scheduler_pod_selector",
            return_value=fake_selector,
        ), patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=json.dumps({"items": [{"metadata": {"name": "k9b-scheduler-abc"}}]}),
                stderr="",
            )

            collect_scheduler_logs("/tmp/kubeconfig", "k9b")

            # Verify subprocess.run was called
            assert mock_run.called

            # Check that kubectl get pods was called with the derived selector
            calls = mock_run.call_args_list
            pod_call = [c for c in calls if "get" in str(c) and "pods" in str(c)][0]
            args = pod_call[0][0]
            selector_index = args.index("-l") + 1
            used_selector = args[selector_index]

            # Must NOT be the hard-coded wrong selector
            assert used_selector != "app.kubernetes.io/name=k9b-scheduler", (
                "collect_scheduler_logs must not use hard-coded 'app.kubernetes.io/name=k9b-scheduler'"
            )

    def test_no_hardcoded_scheduler_selector_in_k8s_diagnostics(self) -> None:
        """The _collect_scheduler_diagnostics function must not use hard-coded selector."""
        from scripts.backend_health_gate.k8s_diagnostics import _collect_scheduler_diagnostics

        # Mock the get_scheduler_pod_selector to return a correct selector
        fake_selector = "app.kubernetes.io/component=scheduler,app.kubernetes.io/name=k9b"

        with patch(
            "scripts.incident_discovery_gate.collect.get_scheduler_pod_selector",
            return_value=fake_selector,
        ), patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=json.dumps({"items": [{"metadata": {"name": "k9b-scheduler-abc"}}]}),
                stderr="",
            )

            _collect_scheduler_diagnostics("/tmp/kubeconfig", "k9b")

            # Verify subprocess.run was called
            assert mock_run.called

            # Check that kubectl get pods was called with the derived selector
            calls = mock_run.call_args_list
            pod_call = [c for c in calls if "get" in str(c) and "pods" in str(c)][0]
            args = pod_call[0][0]
            selector_index = args.index("-l") + 1
            used_selector = args[selector_index]

            # Must NOT be the hard-coded wrong selector
            assert used_selector != "app.kubernetes.io/name=k9b-scheduler", (
                "_collect_scheduler_diagnostics must not use hard-coded selector"
            )


class TestSchedulerSelectorDerivation:
    """Test scheduler pod selector derivation from deployment."""

    def test_get_scheduler_pod_selector_derives_from_deployment(self) -> None:
        """get_scheduler_pod_selector must derive selector from deployment spec."""
        from scripts.incident_discovery_gate.collect import get_scheduler_pod_selector

        # Mock deployment with correct matchLabels
        fake_deployment = {
            "spec": {
                "selector": {
                    "matchLabels": {
                        "app.kubernetes.io/name": "k9b",
                        "app.kubernetes.io/component": "scheduler",
                    }
                }
            }
        }

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=json.dumps(fake_deployment),
                stderr="",
            )

            selector = get_scheduler_pod_selector("/tmp/kubeconfig", "k9b")

            assert selector is not None
            # Selector should contain both labels
            assert "app.kubernetes.io/name=k9b" in selector
            assert "app.kubernetes.io/component=scheduler" in selector
            # Selector must NOT contain the wrong label
            assert "app.kubernetes.io/name=k9b-scheduler" not in selector

    def test_get_scheduler_pod_selector_returns_none_on_failure(self) -> None:
        """get_scheduler_pod_selector returns None when deployment not found."""
        from scripts.incident_discovery_gate.collect import get_scheduler_pod_selector

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="NotFound",
            )

            selector = get_scheduler_pod_selector("/tmp/kubeconfig", "k9b")

            assert selector is None


class TestSchedulerSelectorUsage:
    """Test that functions handle selector unavailability gracefully."""

    def test_collect_scheduler_logs_handles_missing_selector(self) -> None:
        """collect_scheduler_logs returns empty string when selector unavailable."""
        from scripts.incident_discovery_gate.collect import collect_scheduler_logs

        with patch(
            "scripts.incident_discovery_gate.collect.get_scheduler_pod_selector",
            return_value=None,
        ):
            result = collect_scheduler_logs("/tmp/kubeconfig", "k9b")

            assert result == ""

    def test_collect_scheduler_diagnostics_handles_missing_selector(self) -> None:
        """_collect_scheduler_diagnostics handles missing selector gracefully."""
        from scripts.backend_health_gate.k8s_diagnostics import _collect_scheduler_diagnostics

        with patch(
            "scripts.incident_discovery_gate.collect.get_scheduler_pod_selector",
            return_value=None,
        ):
            result = _collect_scheduler_diagnostics("/tmp/kubeconfig", "k9b")

            assert result.get("error") == "scheduler_selector_unavailable"


class TestContractsBackwardCompatibility:
    """Verify contracts module backward compatibility."""

    def test_scheduler_pod_selector_constant_exists(self) -> None:
        """SCHEDULER_POD_SELECTOR constant must still exist for backward compat."""
        from scripts.scheduler_health_gate.contracts import SCHEDULER_POD_SELECTOR

        # Must still exist for backward compatibility
        assert SCHEDULER_POD_SELECTOR is not None

    def test_scheduler_pod_selector_fallback_marked(self) -> None:
        """SCHEDULER_POD_SELECTOR_FALLBACK documents the deprecated value."""
        from scripts.scheduler_health_gate.contracts import (
            SCHEDULER_POD_SELECTOR,
            SCHEDULER_POD_SELECTOR_FALLBACK,
        )

        assert SCHEDULER_POD_SELECTOR == SCHEDULER_POD_SELECTOR_FALLBACK
