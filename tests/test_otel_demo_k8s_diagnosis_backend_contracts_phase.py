"""Unit tests for backend contracts - Phase-related tests.

Tests phase payload shape, diagnosis phase contract,
and status/reason/source contract assertions.
"""

from __future__ import annotations

# Import from the module under test
from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
    FAILURE_TARGETED_INSUFFICIENT_PASSES,
    FAILURE_TARGETED_INVOCATION_HTTP_ERROR,
    FAILURE_TARGETED_INVOCATION_INVALID_JSON,
    FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR,
    FAILURE_TARGETED_LOOP_NOT_COMPLETED,
    FAILURE_TARGETED_NO_PASS_ARTIFACTS,
    FAILURE_TARGETED_REVIEW_PACKET_MISSING,
)


class TestFailureReasonConstants:
    """Tests for failure reason constants."""

    def test_failure_constants_are_strings(self) -> None:
        """Test that all failure constants are non-empty strings."""
        constants = [
            FAILURE_TARGETED_INVOCATION_HTTP_ERROR,
            FAILURE_TARGETED_INVOCATION_INVALID_JSON,
            FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR,
            FAILURE_TARGETED_LOOP_NOT_COMPLETED,
            FAILURE_TARGETED_NO_PASS_ARTIFACTS,
            FAILURE_TARGETED_REVIEW_PACKET_MISSING,
            FAILURE_TARGETED_INSUFFICIENT_PASSES,
        ]
        for const in constants:
            assert isinstance(const, str)
            assert len(const) > 0

    def test_failure_constants_are_unique(self) -> None:
        """Test that all failure constants are unique."""
        constants = [
            FAILURE_TARGETED_INVOCATION_HTTP_ERROR,
            FAILURE_TARGETED_INVOCATION_INVALID_JSON,
            FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR,
            FAILURE_TARGETED_LOOP_NOT_COMPLETED,
            FAILURE_TARGETED_NO_PASS_ARTIFACTS,
            FAILURE_TARGETED_REVIEW_PACKET_MISSING,
            FAILURE_TARGETED_INSUFFICIENT_PASSES,
        ]
        assert len(constants) == len(set(constants))

    def test_failure_constants_follow_naming_convention(self) -> None:
        """Test failure constants follow naming convention."""
        expected_prefix = "targeted_"
        constants = [
            FAILURE_TARGETED_INVOCATION_HTTP_ERROR,
            FAILURE_TARGETED_INVOCATION_INVALID_JSON,
            FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR,
            FAILURE_TARGETED_LOOP_NOT_COMPLETED,
            FAILURE_TARGETED_NO_PASS_ARTIFACTS,
            FAILURE_TARGETED_REVIEW_PACKET_MISSING,
            FAILURE_TARGETED_INSUFFICIENT_PASSES,
        ]
        for const in constants:
            assert const.startswith(expected_prefix), (
                f"Constant {const} should start with '{expected_prefix}'"
            )
