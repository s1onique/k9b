"""Tests for discovery structured logging fallback exception handling.

These tests verify that emit_discovery_strategy_failure() returns bool
and exposes failure safely without leaking raw Forbidden text.

See: ACT: Harden discovery structured logging fallback exception handling
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock, patch


class TestEmitDiscoveryStrategyFailureReturnValue:
    """Tests for emit_discovery_strategy_failure return value behavior.

    Verifies that the function returns bool and exposes failure safely.
    See: ACT: Harden discovery structured logging fallback exception handling
    """

    def test_returns_true_when_emit_fn_succeeds(self):
        """emit_discovery_strategy_failure returns True when emit_fn succeeds."""
        from k8s_diag_agent.external_analysis.discovery_structured_logging import (
            emit_discovery_strategy_failure,
        )

        mock_emit = MagicMock(return_value={"status": "ok"})

        with patch(
            "k8s_diag_agent.external_analysis.discovery_structured_logging._get_emit_fn",
            return_value=mock_emit,
        ):
            result = emit_discovery_strategy_failure(
                component="test-discovery",
                strategy_name="test-strategy",
                errors=("Forbidden error",),
            )

        assert result is True
        mock_emit.assert_called_once()

    def test_returns_false_when_emit_fn_raises(self, caplog):
        """emit_discovery_strategy_failure returns False when emit_fn raises."""
        from k8s_diag_agent.external_analysis.discovery_structured_logging import (
            emit_discovery_strategy_failure,
        )

        caplog.set_level(logging.DEBUG)

        def mock_emit_raises(**kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("Structured logging unavailable")

        with patch(
            "k8s_diag_agent.external_analysis.discovery_structured_logging._get_emit_fn",
            return_value=mock_emit_raises,
        ):
            result = emit_discovery_strategy_failure(
                component="test-discovery",
                strategy_name="test-strategy",
                errors=("Forbidden error",),
            )

        assert result is False

    def test_returns_false_when_get_emit_fn_raises(self, caplog):
        """emit_discovery_strategy_failure returns False when _get_emit_fn raises."""
        from k8s_diag_agent.external_analysis.discovery_structured_logging import (
            emit_discovery_strategy_failure,
        )

        caplog.set_level(logging.DEBUG)

        with patch(
            "k8s_diag_agent.external_analysis.discovery_structured_logging._get_emit_fn",
            side_effect=ImportError("Cannot load emit_structured_log"),
        ):
            result = emit_discovery_strategy_failure(
                component="test-discovery",
                strategy_name="test-strategy",
                errors=("Forbidden error",),
            )

        assert result is False

    def test_returns_false_for_empty_errors(self):
        """emit_discovery_strategy_failure returns False when errors is empty."""
        from k8s_diag_agent.external_analysis.discovery_structured_logging import (
            emit_discovery_strategy_failure,
        )

        result = emit_discovery_strategy_failure(
            component="test-discovery",
            strategy_name="test-strategy",
            errors=(),
        )

        assert result is False

    def test_fallback_emits_sanitized_debug_diagnostic(self, caplog):
        """Fallback path emits sanitized DEBUG diagnostic without raw error text."""
        from k8s_diag_agent.external_analysis.discovery_structured_logging import (
            emit_discovery_strategy_failure,
        )

        caplog.set_level(logging.DEBUG)

        def mock_emit_with_sensitive(**kwargs: Any) -> dict[str, Any]:
            raise RuntimeError(
                "Error from server (Forbidden): cannot list resource 'alertmanagers'"
            )

        with patch(
            "k8s_diag_agent.external_analysis.discovery_structured_logging._get_emit_fn",
            return_value=mock_emit_with_sensitive,
        ):
            emit_discovery_strategy_failure(
                component="alertmanager-discovery",
                strategy_name="alertmanager-crd",
                errors=("Forbidden error",),
            )

        # Verify sanitized DEBUG diagnostic was emitted
        debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert len(debug_records) >= 1

        # Verify diagnostic contains safe fields but NOT raw error text
        log_text = "\n".join(r.message for r in caplog.records)
        assert "component=alertmanager-discovery" in log_text
        assert "strategy=alertmanager-crd" in log_text
        assert "exception_type=RuntimeError" in log_text

        # Verify NO raw forbidden text in any log
        assert "Forbidden" not in log_text
        assert "cannot list resource" not in log_text
        assert "alertmanagers" not in log_text

    def test_no_exception_escapes_when_emit_fn_raises(self):
        """No exception escapes when emit_fn raises."""
        from k8s_diag_agent.external_analysis.discovery_structured_logging import (
            emit_discovery_strategy_failure,
        )

        def mock_emit_raises(**kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("Structured logging unavailable")

        with patch(
            "k8s_diag_agent.external_analysis.discovery_structured_logging._get_emit_fn",
            return_value=mock_emit_raises,
        ):
            # Should not raise
            result = emit_discovery_strategy_failure(
                component="test-discovery",
                strategy_name="test-strategy",
                errors=("Forbidden error",),
            )
            assert result is False

    def test_no_exception_escapes_when_get_emit_fn_raises(self):
        """No exception escapes when _get_emit_fn raises."""
        from k8s_diag_agent.external_analysis.discovery_structured_logging import (
            emit_discovery_strategy_failure,
        )

        with patch(
            "k8s_diag_agent.external_analysis.discovery_structured_logging._get_emit_fn",
            side_effect=ImportError("Cannot load emit_structured_log"),
        ):
            # Should not raise
            result = emit_discovery_strategy_failure(
                component="test-discovery",
                strategy_name="test-strategy",
                errors=("Forbidden error",),
            )
            assert result is False


class TestSafeEmitDiscoveryFailure:
    """Regression tests for safe discovery structured logging fallback.

    Verifies that when structured emitter raises with a sensitive message,
    the captured logs do NOT contain forbidden/kubectl/cluster error text.

    See: ACT: Harden discovery structured logging fallback exception handling
    """

    def test_emit_discovery_event_suppresses_emitter_exception_without_raw_message(
        self, caplog
    ):
        """Structured emitter exceptions should be suppressed without leaking exception text."""
        from k8s_diag_agent.external_analysis.discovery_structured_logging import (
            emit_discovery_strategy_failure,
        )

        caplog.set_level(logging.DEBUG)

        # Mock the emit function to raise with a sensitive message
        def mock_emit_with_sensitive(**kwargs: Any) -> dict[str, Any]:
            raise RuntimeError(
                "Error from server (Forbidden): users 'system:serviceaccount:...' "
                "cannot list resource 'alertmanagers'"
            )

        with patch(
            "k8s_diag_agent.external_analysis.discovery_structured_logging._get_emit_fn",
            return_value=mock_emit_with_sensitive,
        ):
            # Should not raise
            emit_discovery_strategy_failure(
                component="test-discovery",
                strategy_name="test-strategy",
                errors=("Forbidden error",),
            )

        # Check that no sensitive text appears in any log
        for record in caplog.records:
            assert "Forbidden" not in record.message, (
                f"Found raw Forbidden error in fallback log: {record.message}"
            )
            assert "system:serviceaccount" not in record.message, (
                f"Found serviceaccount in fallback log: {record.message}"
            )
            assert "cannot list resource" not in record.message, (
                f"Found kubectl error in fallback log: {record.message}"
            )

    def test_emit_discovery_event_does_not_log_forbidden_exception_text(
        self, caplog
    ):
        """When emitter raises, the exception text should not be logged anywhere."""
        from k8s_diag_agent.external_analysis.discovery_structured_logging import (
            emit_discovery_strategy_failure,
        )

        caplog.set_level(logging.DEBUG)

        # Mock the emit function to raise with forbidden kubectl error
        sensitive_error = (
            "Error from server (Forbidden): "
            "users \"system:serviceaccount:kube-system:...\" "
            "cannot list resource ... in API group \"monitoring.coreos.com\""
        )

        def mock_emit_with_sensitive(**kwargs: Any) -> dict[str, Any]:
            raise RuntimeError(sensitive_error)

        with patch(
            "k8s_diag_agent.external_analysis.discovery_structured_logging._get_emit_fn",
            return_value=mock_emit_with_sensitive,
        ):
            emit_discovery_strategy_failure(
                component="alertmanager-discovery",
                strategy_name="alertmanager-crd",
                errors=(f"kubectl failed: Forbidden - {sensitive_error[:200]}",),
            )

        # Verify no raw forbidden text in any captured log
        log_text = "\n".join(r.message for r in caplog.records)
        assert "Forbidden" not in log_text, (
            f"Found Forbidden in fallback logs: {log_text}"
        )
        assert "system:serviceaccount" not in log_text
        assert "cannot list resource" not in log_text

    def test_safe_emit_discovery_failure_wraps_inner_failure(
        self, caplog
    ):
        """safe_emit_discovery_failure should wrap emit_discovery_strategy_failure safely."""
        from k8s_diag_agent.external_analysis.discovery_structured_logging import (
            safe_emit_discovery_failure,
        )

        caplog.set_level(logging.DEBUG)

        # Mock the inner emit function to raise with a sensitive message
        def mock_emit_with_sensitive(**kwargs: Any) -> dict[str, Any]:
            raise RuntimeError(
                "Error from server (Forbidden): cannot list resource 'vmalerts'"
            )

        with patch(
            "k8s_diag_agent.external_analysis.discovery_structured_logging._get_emit_fn",
            return_value=mock_emit_with_sensitive,
        ):
            # Should not raise
            safe_emit_discovery_failure(
                component="vmalert-discovery",
                strategy_name="vmalert-crd",
                errors=("kubectl failed: Forbidden - Error from server (Forbidden): ...",),
            )

        # Verify no sensitive text in logs
        for record in caplog.records:
            assert "Forbidden" not in record.message
            assert "cannot list resource" not in record.message

    def test_emit_discovery_event_failure_preserves_discovery_result_flow(
        self, caplog
    ):
        """Emitter failure should not prevent the caller from continuing.

        This test verifies that when structured logging fails, the discovery
        result (error tuple) is still accessible to the caller.
        """
        from k8s_diag_agent.external_analysis.discovery_structured_logging import (
            emit_discovery_strategy_failure,
        )

        caplog.set_level(logging.WARNING)

        # Track calls to verify the function completes
        call_completed = False

        def mock_emit_with_error(**kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("Structured logging service unavailable")

        with patch(
            "k8s_diag_agent.external_analysis.discovery_structured_logging._get_emit_fn",
            return_value=mock_emit_with_error,
        ):
            # Should complete without raising
            emit_discovery_strategy_failure(
                component="test-discovery",
                strategy_name="test-crd",
                errors=("kubectl failed: Some error",),
            )
            call_completed = True

        assert call_completed, "emit_discovery_strategy_failure should complete without raising"

        # Verify no sensitive text leaked
        log_text = "\n".join(r.message for r in caplog.records)
        assert "Some error" not in log_text, (
            f"Found 'Some error' in fallback logs: {log_text}"
        )
        assert "kubectl failed" not in log_text, (
            f"Found 'kubectl failed' in fallback logs: {log_text}"
        )

    def test_metadata_preserved_on_success(self):
        """Success path preserves all expected metadata fields."""
        from k8s_diag_agent.external_analysis.discovery_structured_logging import (
            emit_discovery_strategy_failure,
        )

        captured_metadata: dict[str, Any] = {}

        def mock_emit(**kwargs: Any) -> dict[str, Any]:
            captured_metadata.update(kwargs)
            return {"status": "ok"}

        with patch(
            "k8s_diag_agent.external_analysis.discovery_structured_logging._get_emit_fn",
            return_value=mock_emit,
        ):
            result = emit_discovery_strategy_failure(
                component="alertmanager-discovery",
                strategy_name="alertmanager-crd",
                errors=("kubectl failed: Forbidden - some forbidden message",),
                cluster_context="kind-cluster",
            )

        assert result is True
        assert captured_metadata["component"] == "alertmanager-discovery"
        assert captured_metadata["severity"] == "WARNING"
        assert captured_metadata["metadata"]["event"] == "alertmanager-discovery-strategy-failed"
        assert captured_metadata["metadata"]["strategy"] == "alertmanager-crd"
        assert captured_metadata["metadata"]["error_count"] == 1
        assert captured_metadata["metadata"]["reason"] == "forbidden"
        assert captured_metadata["metadata"]["cluster_context"] == "kind-cluster"


class TestServiceStrategyNoRawLogs:
    """Regression tests verifying service strategies don't emit raw kubectl errors.

    These tests verify that when service heuristic strategies fail,
    they do not log raw error text containing forbidden/kubectl details.
    """

    def test_alertmanager_service_strategy_no_raw_forbidden_on_failure(
        self, caplog
    ):
        """Alertmanager service strategy should not log raw Forbidden text on failure."""
        from k8s_diag_agent.external_analysis.alertmanager_discovery_service_strategy import (
            ServiceHeuristicDiscoveryStrategy,
        )

        caplog.set_level(logging.WARNING)

        strategy = ServiceHeuristicDiscoveryStrategy()

        # Mock subprocess to return a Forbidden error
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = (
            "Error from server (Forbidden): services is forbidden: "
            "cannot list resource 'services' in API group '' in the namespace 'default'"
        )

        with patch("subprocess.run", return_value=mock_result):
            result = strategy.discover(context="test-context")

        # Verify error is captured in result
        assert len(result.errors) == 1
        assert "Forbidden" in result.errors[0]

        # Verify no raw Forbidden text in logs
        for record in caplog.records:
            if record.levelno >= logging.WARNING:
                assert "Error from server (Forbidden):" not in record.message
                assert "system:serviceaccount" not in record.message

    def test_vmalert_service_strategy_no_raw_forbidden_on_failure(self, caplog):
        """VMAlert service strategy should not log raw Forbidden text on failure."""
        from k8s_diag_agent.external_analysis.vmalert_discovery_service_strategy import (
            ServiceHeuristicDiscoveryStrategy,
        )

        caplog.set_level(logging.WARNING)

        strategy = ServiceHeuristicDiscoveryStrategy()

        # Mock subprocess to return a Forbidden error
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = (
            "Error from server (Forbidden): services is forbidden: "
            "cannot list resource 'services' in API group ''"
        )

        with patch("subprocess.run", return_value=mock_result):
            result = strategy.discover(context="test-context")

        # Verify error is captured in result
        assert len(result.errors) == 1
        assert "Forbidden" in result.errors[0]

        # Verify no raw Forbidden text in logs
        for record in caplog.records:
            if record.levelno >= logging.WARNING:
                assert "Error from server (Forbidden):" not in record.message
                assert "cannot list resource" not in record.message
