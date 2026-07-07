"""Regression tests for VMAlert structured Forbidden discovery errors.

These tests verify that Kubernetes RBAC Forbidden errors in VMAlert
discovery are represented as structured WARNING events, never as raw subprocess
text leaked to stdout/stderr.

See: Child Epic CI Verification - Gate health-loop logs as structured JSON
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

# --- VMAlert CRD Strategy Tests ---


class TestVMAlertCRDStrategyForbiddenErrors:
    """Test that VMAlert CRD discovery emits structured errors for Forbidden."""

    def test_vmalert_crd_strategy_returns_forbidden_error_on_rbac_denial(self):
        """VMAlert CRD strategy should return Forbidden error with structured prefix."""
        from k8s_diag_agent.external_analysis.vmalert_discovery_crd_strategy import (
            VMAlertCRDDiscoveryStrategy,
        )

        strategy = VMAlertCRDDiscoveryStrategy()

        # Mock subprocess to return a Forbidden error
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Error from server (Forbidden): vmalerts.operator.victoriametrics.com is forbidden: cannot list resource 'vmalerts' in API group 'operator.victoriametrics.com' in the namespace 'default'"

        with patch("subprocess.run", return_value=mock_result):
            result = strategy.discover(context="test-context")

        # Verify error is marked as Forbidden
        assert len(result.errors) == 1
        assert "Forbidden" in result.errors[0]
        assert result.strategy == "vmalert-crd"

    def test_vmalert_crd_strategy_continues_on_not_found(self):
        """VMAlert CRD strategy should return empty result on CRD not installed."""
        from k8s_diag_agent.external_analysis.vmalert_discovery_crd_strategy import (
            VMAlertCRDDiscoveryStrategy,
        )

        strategy = VMAlertCRDDiscoveryStrategy()

        # Mock subprocess to return "not found" error
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "error: no resources found"

        with patch("subprocess.run", return_value=mock_result):
            result = strategy.discover(context="test-context")

        # Verify no errors (CRD not installed, not a failure)
        assert len(result.errors) == 0
        assert len(result.sources) == 0


# --- Orchestrator Structured Logging Tests ---


class TestVMAlertDiscoveryOrchestratorStructuredLogs:
    """Test that VMAlert discovery orchestrator emits structured events."""

    def test_vmalert_orchestrator_emits_structured_warning_on_strategy_failure(self):
        """Orchestrator should emit structured WARNING event when strategy fails."""
        from k8s_diag_agent.external_analysis.vmalert_discovery import (
            DiscoveryResult,
        )

        # Track emitted structured logs
        emitted_logs: list[dict[str, Any]] = []

        def mock_emit_fn(**kwargs: Any) -> dict[str, Any]:
            emitted_logs.append(kwargs)
            return {}

        # Mock the CRD strategy to return a Forbidden error
        with patch(
            "k8s_diag_agent.external_analysis.vmalert_discovery.VMAlertCRDDiscoveryStrategy"
        ) as MockCRDStrategy:
            mock_crd_instance = MagicMock()
            mock_crd_instance.discover.return_value = DiscoveryResult(
                sources=(),
                errors=("kubectl failed: Forbidden - Error from server (Forbidden): ...",),
                strategy="vmalert-crd",
            )
            MockCRDStrategy.return_value = mock_crd_instance

            # Mock the service heuristic strategy to return empty (fallback behavior)
            with patch(
                "k8s_diag_agent.external_analysis.vmalert_discovery.ServiceHeuristicDiscoveryStrategy"
            ) as MockServiceStrategy:
                mock_service_instance = MagicMock()
                mock_service_instance.discover.return_value = DiscoveryResult(
                    sources=(),
                    errors=(),
                    strategy="service-heuristic",
                )
                MockServiceStrategy.return_value = mock_service_instance

                # Patch the shared emit_discovery_strategy_failure
                with patch(
                    "k8s_diag_agent.external_analysis.discovery_structured_logging._get_emit_fn",
                    return_value=mock_emit_fn,
                ):
                    from k8s_diag_agent.external_analysis.vmalert_discovery import (
                        discover_vmalerts,
                    )

                    discover_vmalerts(context="test-context")

        # Verify structured log was emitted
        assert len(emitted_logs) >= 1
        forbidden_log = None
        for log in emitted_logs:
            if "forbidden" in log.get("metadata", {}).get("reason", "").lower():
                forbidden_log = log
                break

        assert forbidden_log is not None
        assert forbidden_log["component"] == "vmalert-discovery"
        assert forbidden_log["severity"] == "WARNING"
        assert "strategy" in forbidden_log["metadata"]
        assert forbidden_log["metadata"]["reason"] == "forbidden"


# --- Regression Tests: No Unstructured Logs in VMAlert Discovery ---


class TestNoUnstructuredLogsInVMAlertDiscovery:
    """Regression tests for VMAlert discovery.

    Verifies that when VMAlert discovery strategies fail with Forbidden errors,
    the output is structured (or empty) with no raw kubectl error text leaking.
    """

    def test_vmalert_discovery_no_raw_forbidden_on_rbac_denial(self, caplog):
        """VMAlert discovery should not emit raw Forbidden text to logs."""
        import logging

        from k8s_diag_agent.external_analysis.vmalert_discovery import (
            DiscoveryResult,
            discover_vmalerts,
        )

        # Set log level to capture warnings
        caplog.set_level(logging.WARNING)

        # Mock the CRD strategy to return a Forbidden error
        with patch(
            "k8s_diag_agent.external_analysis.vmalert_discovery.VMAlertCRDDiscoveryStrategy"
        ) as MockCRD:
            mock_crd_instance = MagicMock()
            mock_crd_instance.discover.return_value = DiscoveryResult(
                sources=(),
                errors=("kubectl failed: Forbidden - Error from server (Forbidden): ...",),
                strategy="vmalert-crd",
            )
            MockCRD.return_value = mock_crd_instance

            # Mock ServiceHeuristicDiscoveryStrategy to return empty
            with patch(
                "k8s_diag_agent.external_analysis.vmalert_discovery.ServiceHeuristicDiscoveryStrategy"
            ) as MockService:
                mock_service_instance = MagicMock()
                mock_service_instance.discover.return_value = DiscoveryResult(
                    sources=(), errors=(), strategy="service-heuristic"
                )
                MockService.return_value = mock_service_instance

                # Run discovery
                discover_vmalerts(context="test-context")

        # Check that no raw Forbidden error text appears in logs
        for record in caplog.records:
            if record.levelno >= logging.WARNING:
                # Should not contain raw kubectl Forbidden error text
                assert "Error from server (Forbidden):" not in record.message, (
                    f"Found raw Forbidden error in log: {record.message}"
                )
