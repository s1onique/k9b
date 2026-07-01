"""Regression tests for P4c backend retry constants.

These tests verify:
- P4C_BACKEND_RETRY_* constants are defined correctly
- Exponential backoff sequence matches requirements
- Failure constants are properly defined
"""

from __future__ import annotations


class TestBackendRetryConstants:
    """Tests for P4c backend retry constants."""

    def test_retry_constants_exist(self) -> None:
        """P4c backend retry constants should be defined."""
        from scripts.lab_common.constants import (
            P4C_BACKEND_RETRY_DEADLINE_SECONDS,
            P4C_BACKEND_RETRY_INITIAL_SLEEP_SECONDS,
            P4C_BACKEND_RETRY_MAX_SLEEP_SECONDS,
        )

        assert P4C_BACKEND_RETRY_DEADLINE_SECONDS == 60
        assert P4C_BACKEND_RETRY_INITIAL_SLEEP_SECONDS == 0.25
        assert P4C_BACKEND_RETRY_MAX_SLEEP_SECONDS == 8

    def test_exponential_backoff_sequence(self) -> None:
        """Verify exponential backoff sequence matches requirements."""
        from scripts.lab_common.constants import (
            P4C_BACKEND_RETRY_INITIAL_SLEEP_SECONDS,
            P4C_BACKEND_RETRY_MAX_SLEEP_SECONDS,
        )

        # Expected backoff sequence: 0.25, 0.5, 1.0, 2.0, 4.0, 8.0
        backoff_sequence = []
        current = float(P4C_BACKEND_RETRY_INITIAL_SLEEP_SECONDS)
        max_sleep = float(P4C_BACKEND_RETRY_MAX_SLEEP_SECONDS)

        while current <= max_sleep * 2:  # Generate a few iterations
            backoff_sequence.append(current)
            current = min(current * 2, max_sleep)
            if current >= max_sleep:
                break

        expected_sequence = [0.25, 0.5, 1.0, 2.0, 4.0, 8.0]
        assert backoff_sequence == expected_sequence[:len(backoff_sequence)]


class TestBackendFailureConstants:
    """Tests for backend failure constants."""

    def test_dns_resolution_failed_constant(self) -> None:
        """FAILURE_BACKEND_DNS_RESOLUTION_FAILED should be defined."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
            FAILURE_BACKEND_DNS_RESOLUTION_FAILED,
        )

        assert FAILURE_BACKEND_DNS_RESOLUTION_FAILED == "backend_dns_resolution_failed"

    def test_endpoint_not_ready_constant(self) -> None:
        """FAILURE_BACKEND_ENDPOINT_NOT_READY should be defined."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
            FAILURE_BACKEND_ENDPOINT_NOT_READY,
        )

        assert FAILURE_BACKEND_ENDPOINT_NOT_READY == "backend_endpoint_not_ready"
