"""Regression tests for Alertmanager structured Forbidden discovery errors.

These tests verify that Kubernetes RBAC Forbidden errors in Alertmanager
discovery are represented as structured WARNING events, never as raw subprocess
text leaked to stdout/stderr.

See: Child Epic CI Verification - Gate health-loop logs as structured JSON
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# --- Alertmanager CRD Strategy Tests ---


class TestAlertmanagerCRDStrategyForbiddenErrors:
    """Test that Alertmanager CRD discovery emits structured errors for Forbidden."""

    def test_alertmanager_crd_strategy_returns_forbidden_error_on_rbac_denial(self):
        """CRD strategy should return Forbidden error with structured prefix."""
        from k8s_diag_agent.external_analysis.alertmanager_discovery_crd_strategy import (
            CRDDiscoveryStrategy,
        )

        strategy = CRDDiscoveryStrategy()

        # Mock subprocess to return a Forbidden error
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Error from server (Forbidden): alertmanagers.monitoring.coreos.com is forbidden: cannot list resource 'alertmanagers' in API group 'monitoring.coreos.com' in the namespace 'default'"

        with patch("subprocess.run", return_value=mock_result):
            result = strategy.discover(context="test-context")

        # Verify error is marked as Forbidden
        assert len(result.errors) == 1
        assert "Forbidden" in result.errors[0]
        assert result.strategy == "alertmanager-crd"

    def test_alertmanager_crd_strategy_continues_on_not_found(self):
        """CRD strategy should return empty result on CRD not installed."""
        from k8s_diag_agent.external_analysis.alertmanager_discovery_crd_strategy import (
            CRDDiscoveryStrategy,
        )

        strategy = CRDDiscoveryStrategy()

        # Mock subprocess to return "not found" error - must match "not found" or "no resources" pattern
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = 'error: the server could not find the requested resource (NotFound); alertmanagers.monitoring.coreos.com "alertmanagers" not found'

        with patch("subprocess.run", return_value=mock_result):
            result = strategy.discover(context="test-context")

        # Verify no errors (CRD not installed, not a failure)
        assert len(result.errors) == 0
        assert len(result.sources) == 0


# --- Prometheus CRD Config Strategy Tests ---


class TestPrometheusCRDConfigStrategyForbiddenErrors:
    """Test that Prometheus CRD config discovery emits structured errors for Forbidden."""

    def test_prometheus_crd_config_strategy_returns_forbidden_error_on_rbac_denial(self):
        """Prometheus CRD config strategy should return Forbidden error with structured prefix."""
        from k8s_diag_agent.external_analysis.alertmanager_discovery_crd_strategy import (
            PrometheusCRDConfigDiscoveryStrategy,
        )

        strategy = PrometheusCRDConfigDiscoveryStrategy()

        # Mock subprocess to return a Forbidden error
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Error from server (Forbidden): prometheuses.monitoring.coreos.com is forbidden: cannot list resource 'prometheuses' in API group 'monitoring.coreos.com' in the namespace 'default'"

        with patch("subprocess.run", return_value=mock_result):
            result = strategy.discover(context="test-context")

        # Verify error is marked as Forbidden
        assert len(result.errors) == 1
        assert "Forbidden" in result.errors[0]
        assert result.strategy == "prometheus-crd-config"

    def test_prometheus_crd_config_strategy_continues_on_not_found(self):
        """Prometheus CRD config strategy should return empty result on CRD not installed."""
        from k8s_diag_agent.external_analysis.alertmanager_discovery_crd_strategy import (
            PrometheusCRDConfigDiscoveryStrategy,
        )

        strategy = PrometheusCRDConfigDiscoveryStrategy()

        # Mock subprocess to return "no resources" error - must match "not found" or "no resources" pattern
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "error: no prometheuses found - no resources found in project"

        with patch("subprocess.run", return_value=mock_result):
            result = strategy.discover(context="test-context")

        # Verify no errors (CRD not installed, not a failure)
        assert len(result.errors) == 0
        assert len(result.sources) == 0


# --- Orchestrator Structured Logging Tests ---


class TestAlertmanagerDiscoveryOrchestratorStructuredLogs:
    """Test that Alertmanager discovery orchestrator emits structured events."""

    @pytest.mark.mock_kubectl
    def test_alertmanager_orchestrator_emits_structured_warning_on_strategy_failure(self):
        """Orchestrator should emit structured WARNING event when strategy fails."""
        from k8s_diag_agent.external_analysis.alertmanager_discovery import (
            DiscoveryResult,
        )

        # Track emitted structured logs
        emitted_logs: list[dict[str, Any]] = []

        def mock_emit_fn(**kwargs: Any) -> dict[str, Any]:
            emitted_logs.append(kwargs)
            return {}

        # Mock the strategy to return a Forbidden error
        # Patch where the name is used in the orchestration module, not where the class is defined.
        # The orchestration does: from .alertmanager_discovery_strategies import CRDDiscoveryStrategy
        # So we need to patch alertmanager_discovery_orchestration.CRDDiscoveryStrategy
        with patch(
            "k8s_diag_agent.external_analysis.alertmanager_discovery_orchestration.CRDDiscoveryStrategy"
        ) as MockStrategy:
            mock_instance = MagicMock()
            mock_instance.discover.return_value = DiscoveryResult(
                sources=(),
                errors=("kubectl failed: Forbidden - Error from server (Forbidden): ...",),
                strategy="alertmanager-crd",
            )
            MockStrategy.return_value = mock_instance

            # Patch the shared emit_discovery_strategy_failure
            with patch(
                "k8s_diag_agent.external_analysis.discovery_structured_logging._get_emit_fn",
                return_value=mock_emit_fn,
            ):
                from k8s_diag_agent.external_analysis.alertmanager_discovery import (
                    discover_alertmanagers,
                )

                discover_alertmanagers(context="test-context")

        # Verify structured log was emitted
        assert len(emitted_logs) >= 1
        forbidden_log = None
        for log in emitted_logs:
            if "forbidden" in log.get("metadata", {}).get("reason", "").lower():
                forbidden_log = log
                break

        assert forbidden_log is not None
        assert forbidden_log["component"] == "alertmanager-discovery"
        assert forbidden_log["severity"] == "WARNING"
        assert "strategy" in forbidden_log["metadata"]
        assert forbidden_log["metadata"]["reason"] == "forbidden"


# --- Regression Tests: No Unstructured Logs in Alertmanager Discovery ---


class TestNoUnstructuredLogsInAlertmanagerDiscovery:
    """Regression tests for Alertmanager discovery.

    Verifies that when discovery strategies fail with Forbidden errors,
    the output is structured (or empty) with no raw kubectl error text leaking.
    """

    def test_alertmanager_discovery_no_raw_forbidden_on_rbac_denial(self, caplog):
        """Alertmanager discovery should not emit raw Forbidden text to logs."""
        import logging

        from k8s_diag_agent.external_analysis.alertmanager_discovery import (
            DiscoveryResult,
            discover_alertmanagers,
        )

        # Set log level to capture warnings
        caplog.set_level(logging.WARNING)

        # Mock the CRD strategy to return a Forbidden error
        # Patch where the name is used in the orchestration module.
        with patch(
            "k8s_diag_agent.external_analysis.alertmanager_discovery_orchestration.CRDDiscoveryStrategy"
        ) as MockCRD:
            mock_crd_instance = MagicMock()
            mock_crd_instance.discover.return_value = DiscoveryResult(
                sources=(),
                errors=("kubectl failed: Forbidden - Error from server (Forbidden): ...",),
                strategy="alertmanager-crd",
            )
            MockCRD.return_value = mock_crd_instance

            # Mock PrometheusCRDConfigDiscoveryStrategy to return empty
            with patch(
                "k8s_diag_agent.external_analysis.alertmanager_discovery_orchestration.PrometheusCRDConfigDiscoveryStrategy"
            ) as MockProm:
                mock_prom_instance = MagicMock()
                mock_prom_instance.discover.return_value = DiscoveryResult(
                    sources=(), errors=(), strategy="prometheus-crd-config"
                )
                MockProm.return_value = mock_prom_instance

                # Mock ServiceHeuristicDiscoveryStrategy to return empty
                with patch(
                    "k8s_diag_agent.external_analysis.alertmanager_discovery_orchestration.ServiceHeuristicDiscoveryStrategy"
                ) as MockService:
                    mock_service_instance = MagicMock()
                    mock_service_instance.discover.return_value = DiscoveryResult(
                        sources=(), errors=(), strategy="service-heuristic"
                    )
                    MockService.return_value = mock_service_instance

                    # Run discovery
                    discover_alertmanagers(context="test-context")

        # Check that no raw Forbidden error text appears in logs
        # The structured event should be emitted instead
        for record in caplog.records:
            if record.levelno >= logging.WARNING:
                # Should not contain raw kubectl Forbidden error text
                assert "Error from server (Forbidden):" not in record.message, (
                    f"Found raw Forbidden error in log: {record.message}"
                )

    def test_alertmanager_discovery_orchestrator_emits_structured_on_strategy_error(
        self, caplog
    ):
        """Alertmanager orchestrator should emit structured WARNING for strategy failures."""
        import logging

        from k8s_diag_agent.external_analysis.alertmanager_discovery import (
            DiscoveryResult,
            discover_alertmanagers,
        )

        # Track structured log emissions
        structured_logs: list[dict[str, Any]] = []

        def mock_emit_fn(**kwargs: Any) -> dict[str, Any]:
            structured_logs.append(kwargs)
            return {}

        # Set log level
        caplog.set_level(logging.DEBUG)

        # Mock the CRD strategy to return a Forbidden error
        # Patch where the name is used in the orchestration module.
        with patch(
            "k8s_diag_agent.external_analysis.alertmanager_discovery_orchestration.CRDDiscoveryStrategy"
        ) as MockCRD:
            mock_crd_instance = MagicMock()
            mock_crd_instance.discover.return_value = DiscoveryResult(
                sources=(),
                errors=("kubectl failed: Forbidden - Error from server (Forbidden): ...",),
                strategy="alertmanager-crd",
            )
            MockCRD.return_value = mock_crd_instance

            # Mock other strategies to return empty
            with patch(
                "k8s_diag_agent.external_analysis.alertmanager_discovery_orchestration.PrometheusCRDConfigDiscoveryStrategy"
            ) as MockProm:
                mock_prom_instance = MagicMock()
                mock_prom_instance.discover.return_value = DiscoveryResult(
                    sources=(), errors=(), strategy="prometheus-crd-config"
                )
                MockProm.return_value = mock_prom_instance

                with patch(
                    "k8s_diag_agent.external_analysis.alertmanager_discovery_orchestration.ServiceHeuristicDiscoveryStrategy"
                ) as MockService:
                    mock_service_instance = MagicMock()
                    mock_service_instance.discover.return_value = DiscoveryResult(
                        sources=(), errors=(), strategy="service-heuristic"
                    )
                    MockService.return_value = mock_service_instance

                    # Patch the emit function
                    with patch(
                        "k8s_diag_agent.external_analysis.discovery_structured_logging._get_emit_fn",
                        return_value=mock_emit_fn,
                    ):
                        # Run discovery
                        discover_alertmanagers(context="test-context")

        # Verify structured event was emitted
        assert len(structured_logs) >= 1, "Expected at least one structured log event"

        # Find the Forbidden event
        forbidden_event = None
        for log in structured_logs:
            if log.get("metadata", {}).get("reason") == "forbidden":
                forbidden_event = log
                break

        assert forbidden_event is not None, "Expected 'forbidden' reason in structured event"
        assert forbidden_event["severity"] == "WARNING"
        assert forbidden_event["component"] == "alertmanager-discovery"
