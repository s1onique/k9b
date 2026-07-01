"""Unit tests for backend contracts - Artifact-related tests.

Tests artifact path/name/schema and evidence bundle contract tests.
"""

from __future__ import annotations

from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
    FAILURE_TARGETED_INVOCATION_HTTP_ERROR,
    FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR,
    FAILURE_TARGETED_LOOP_NOT_COMPLETED,
    TargetedDiagnosisInvocationResult,
    TargetedDiagnosisPollResult,
)


class TestTargetedDiagnosisInvocationResult:
    """Tests for TargetedDiagnosisInvocationResult."""

    def test_success_result(self) -> None:
        """Test successful invocation result."""
        result = TargetedDiagnosisInvocationResult(
            success=True,
            http_status=200,
            body='{"status": "ok"}',
            json_parsed=True,
            response_data={"status": "ok"},
        )

        assert result.success is True
        assert result.http_status == 200
        assert result.json_parsed is True
        assert result.error_class is None

    def test_http_error_result(self) -> None:
        """Test HTTP error classification."""
        result = TargetedDiagnosisInvocationResult(
            success=False,
            http_status=500,
            body="Internal Server Error",
            json_parsed=False,
            error_class=FAILURE_TARGETED_INVOCATION_HTTP_ERROR,
            error_detail="HTTP 500",
        )

        assert result.success is False
        assert result.error_class == FAILURE_TARGETED_INVOCATION_HTTP_ERROR

    def test_transport_error_result(self) -> None:
        """Test transport error classification."""
        result = TargetedDiagnosisInvocationResult(
            success=False,
            http_status=0,
            body="",
            json_parsed=False,
            error_class=FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR,
            error_detail="Transport error: curl_rc=7",
            curl_rc=7,
        )

        assert result.success is False
        assert result.error_class == FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR

    def test_to_dict(self) -> None:
        """Test dict conversion for evidence."""
        result = TargetedDiagnosisInvocationResult(
            success=True,
            http_status=200,
            body='{"test": true}',
            json_parsed=True,
        )
        d = result.to_dict()

        assert d["success"] is True
        assert d["http_status"] == 200
        assert d["json_parsed"] is True
        assert "response_data" not in d  # Not serialized to avoid large blobs

    def test_to_dict_with_error(self) -> None:
        """Test dict conversion includes error fields."""
        result = TargetedDiagnosisInvocationResult(
            success=False,
            http_status=500,
            body="error",
            json_parsed=False,
            error_class=FAILURE_TARGETED_INVOCATION_HTTP_ERROR,
            error_detail="HTTP 500",
            curl_rc=0,
        )
        d = result.to_dict()

        assert d["error_class"] == FAILURE_TARGETED_INVOCATION_HTTP_ERROR
        assert d["error_detail"] == "HTTP 500"
        assert d["curl_rc"] == 0


class TestTargetedDiagnosisPollResult:
    """Tests for TargetedDiagnosisPollResult."""

    def test_success_poll_result(self) -> None:
        """Test successful poll result."""
        result = TargetedDiagnosisPollResult(
            success=True,
            final_status="diagnosed",
            loop_summary_status="completed",
            review_available=True,
            attempts=5,
            max_attempts=12,
        )

        assert result.success is True
        assert result.final_status == "diagnosed"
        assert result.loop_summary_status == "completed"
        assert result.review_available is True
        assert result.attempts == 5
        assert result.max_attempts == 12
        assert result.failure_reason is None

    def test_timeout_poll_result(self) -> None:
        """Test polling timeout result."""
        result = TargetedDiagnosisPollResult(
            success=False,
            final_status="diagnosing",
            loop_summary_status="running",
            review_available=False,
            attempts=12,
            max_attempts=12,
            failure_reason=FAILURE_TARGETED_LOOP_NOT_COMPLETED,
            error_detail="Polling timeout after 12 attempts",
        )

        assert result.success is False
        assert result.failure_reason == FAILURE_TARGETED_LOOP_NOT_COMPLETED
        assert result.error_detail is not None

    def test_to_dict(self) -> None:
        """Test dict conversion for evidence."""
        result = TargetedDiagnosisPollResult(
            success=True,
            final_status="diagnosed",
            loop_summary_status="completed",
            review_available=True,
            attempts=3,
            max_attempts=12,
        )
        d = result.to_dict()

        assert d["success"] is True
        assert d["final_status"] == "diagnosed"
        assert d["attempts"] == 3
        assert d["max_attempts"] == 12

    def test_to_dict_with_failure(self) -> None:
        """Test dict conversion includes failure fields."""
        result = TargetedDiagnosisPollResult(
            success=False,
            final_status="diagnosing",
            loop_summary_status="running",
            review_available=False,
            attempts=12,
            max_attempts=12,
            failure_reason=FAILURE_TARGETED_LOOP_NOT_COMPLETED,
            error_detail="timeout",
        )
        d = result.to_dict()

        assert d["failure_reason"] == FAILURE_TARGETED_LOOP_NOT_COMPLETED
        assert d["error_detail"] == "timeout"
