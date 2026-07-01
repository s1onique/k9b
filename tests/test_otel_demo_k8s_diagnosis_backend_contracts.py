"""Unit tests for k9b_otel_demo_lab_k8s_diagnosis_backend_contracts.py.

These tests validate the data contracts (dataclasses and constants) used by
the backend-targeted diagnosis helpers.
"""

from __future__ import annotations

# Import from the module under test
from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
    FAILURE_BACKEND_INCIDENT_FETCH_CONTRACT_ERROR,
    FAILURE_BACKEND_INCIDENT_FETCH_FAILED,
    FAILURE_BACKEND_INCIDENT_FETCH_HTTP_ERROR,
    FAILURE_BACKEND_INCIDENT_FETCH_INVALID_JSON,
    FAILURE_BACKEND_INCIDENT_FETCH_NOT_FOUND,
    FAILURE_BACKEND_INCIDENT_FETCH_TRANSPORT_ERROR,
    FAILURE_TARGETED_INSUFFICIENT_PASSES,
    FAILURE_TARGETED_INVOCATION_HTTP_ERROR,
    FAILURE_TARGETED_INVOCATION_INVALID_JSON,
    FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR,
    FAILURE_TARGETED_LOOP_NOT_COMPLETED,
    FAILURE_TARGETED_NO_PASS_ARTIFACTS,
    FAILURE_TARGETED_REVIEW_PACKET_MISSING,
    BackendIncidentDetail,
    BackendIncidentFetchResult,
    TargetedDiagnosisInvocationResult,
    TargetedDiagnosisPollResult,
)

# =============================================================================
# Test Failure Reason Constants
# =============================================================================


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


# =============================================================================
# Test BackendIncidentDetail
# =============================================================================


class TestBackendIncidentDetail:
    """Tests for BackendIncidentDetail parsing."""

    def test_from_dict_complete(self) -> None:
        """Test parsing a complete incident response."""
        data = {
            "status": "collecting_evidence",
            "evidence_count": 5,
            "review_packet": {"status": "ready"},
            "automatic_diagnosis_loop_summary": {"status": "completed"},
            "automatic_diagnosis_review": {"available": True},
        }
        detail = BackendIncidentDetail.from_dict("inc-123", data)

        assert detail.incident_id == "inc-123"
        assert detail.status == "collecting_evidence"
        assert detail.evidence_count == 5
        assert detail.review_packet_status == "ready"
        assert detail.loop_summary_status == "completed"
        assert detail.review_available is True
        assert detail.raw == data

    def test_from_dict_minimal(self) -> None:
        """Test parsing minimal incident response."""
        data: dict = {}
        detail = BackendIncidentDetail.from_dict("inc-456", data)

        assert detail.incident_id == "inc-456"
        assert detail.status == "unknown"
        assert detail.evidence_count == 0
        assert detail.review_packet_status is None
        assert detail.loop_summary_status is None
        assert detail.review_available is False

    def test_from_dict_null_review_packet(self) -> None:
        """Test parsing with null review_packet."""
        data = {"review_packet": None}
        detail = BackendIncidentDetail.from_dict("inc-789", data)

        assert detail.review_packet_status is None

    def test_from_dict_null_loop_summary(self) -> None:
        """Test parsing with null loop_summary."""
        data = {"automatic_diagnosis_loop_summary": None}
        detail = BackendIncidentDetail.from_dict("inc-abc", data)

        assert detail.loop_summary_status is None

    def test_from_dict_null_review(self) -> None:
        """Test parsing with null review."""
        data = {"automatic_diagnosis_review": None}
        detail = BackendIncidentDetail.from_dict("inc-def", data)

        assert detail.review_available is False

    def test_from_dict_non_dict_nested(self) -> None:
        """Test parsing with non-dict nested values."""
        data = {
            "review_packet": "not a dict",
            "automatic_diagnosis_loop_summary": 123,
            "automatic_diagnosis_review": [1, 2, 3],
        }
        detail = BackendIncidentDetail.from_dict("inc-ghi", data)

        assert detail.review_packet_status is None
        assert detail.loop_summary_status is None
        assert detail.review_available is False

    def test_to_compact_log(self) -> None:
        """Test compact log formatting."""
        data = {
            "status": "diagnosing",
            "evidence_count": 3,
            "review_packet": {"status": "pending"},
            "automatic_diagnosis_loop_summary": {"status": "running"},
            "automatic_diagnosis_review": {"available": False},
        }
        detail = BackendIncidentDetail.from_dict("inc-test", data)
        log = detail.to_compact_log()

        assert "incident_id=inc-test" in log
        assert "status=diagnosing" in log
        assert "evidence_count=3" in log
        assert "review_packet.status=pending" in log
        assert "loop_summary.status=running" in log
        assert "review_available=False" in log

    def test_to_compact_log_null_values(self) -> None:
        """Test compact log with null values."""
        data: dict = {}
        detail = BackendIncidentDetail.from_dict("inc-null", data)
        log = detail.to_compact_log()

        assert "incident_id=inc-null" in log
        assert "review_packet.status=null" in log
        assert "loop_summary.status=null" in log


# =============================================================================
# Test TargetedDiagnosisInvocationResult
# =============================================================================


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

    def test_invalid_json_result(self) -> None:
        """Test JSON parse error classification."""
        result = TargetedDiagnosisInvocationResult(
            success=False,
            http_status=200,
            body="not valid json",
            json_parsed=False,
            error_class=FAILURE_TARGETED_INVOCATION_INVALID_JSON,
            error_detail="JSON parse error: Expecting value",
        )

        assert result.success is False
        assert result.error_class == FAILURE_TARGETED_INVOCATION_INVALID_JSON

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


# =============================================================================
# Test TargetedDiagnosisPollResult
# =============================================================================


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


# =============================================================================
# Test BackendIncidentFetchResult
# =============================================================================


class TestBackendIncidentFetchResult:
    """Tests for BackendIncidentFetchResult dataclass."""

    def test_success_result(self) -> None:
        """Test successful fetch result."""
        result = BackendIncidentFetchResult(
            success=True,
            incident=BackendIncidentDetail.from_dict("inc-123", {"status": "ok"}),
            http_status=200,
            curl_rc=0,
            url="http://localhost:8080/api/incidents/inc-123",
            api_path="/api/incidents/inc-123",
            encoded_incident_id="inc-123",
        )

        assert result.success is True
        assert result.incident is not None
        assert result.incident.incident_id == "inc-123"
        assert result.error_class is None

    def test_transport_error_result(self) -> None:
        """Test transport error result."""
        result = BackendIncidentFetchResult(
            success=False,
            error_class=FAILURE_BACKEND_INCIDENT_FETCH_TRANSPORT_ERROR,
            error_detail="Transport error: curl_rc=7",
            http_status=0,
            curl_rc=7,
            url="http://localhost:8080/api/incidents/inc-123",
            api_path="/api/incidents/inc-123",
            encoded_incident_id="inc-123",
            stderr_prefix="Connection refused",
        )

        assert result.success is False
        assert result.error_class == FAILURE_BACKEND_INCIDENT_FETCH_TRANSPORT_ERROR
        assert result.incident is None

    def test_not_found_result(self) -> None:
        """Test 404 not found result."""
        result = BackendIncidentFetchResult(
            success=False,
            error_class=FAILURE_BACKEND_INCIDENT_FETCH_NOT_FOUND,
            error_detail="Incident not found: HTTP 404",
            http_status=404,
            curl_rc=0,
            url="http://localhost:8080/api/incidents/inc-missing",
            api_path="/api/incidents/inc-missing",
            encoded_incident_id="inc-missing",
            body_prefix='{"error": "not found"}',
        )

        assert result.success is False
        assert result.error_class == FAILURE_BACKEND_INCIDENT_FETCH_NOT_FOUND

    def test_invalid_json_result(self) -> None:
        """Test invalid JSON result."""
        result = BackendIncidentFetchResult(
            success=False,
            error_class=FAILURE_BACKEND_INCIDENT_FETCH_INVALID_JSON,
            error_detail="JSON parse error: Expecting value",
            http_status=200,
            curl_rc=0,
            url="http://localhost:8080/api/incidents/inc-123",
            api_path="/api/incidents/inc-123",
            encoded_incident_id="inc-123",
            body_prefix="<!doctype html>",
            json_error="Expecting value",
        )

        assert result.success is False
        assert result.error_class == FAILURE_BACKEND_INCIDENT_FETCH_INVALID_JSON
        assert result.json_error == "Expecting value"

    def test_to_dict_success_compact(self) -> None:
        """Test to_dict is compact on success."""
        result = BackendIncidentFetchResult(
            success=True,
            incident=BackendIncidentDetail.from_dict("inc-123", {"status": "ok"}),
            http_status=200,
            curl_rc=0,
            url="http://localhost:8080/api/incidents/inc-123",
            api_path="/api/incidents/inc-123",
            encoded_incident_id="inc-123",
        )

        d = result.to_dict()

        assert d["success"] is True
        assert d["http_status"] == 200
        assert d["curl_rc"] == 0
        assert d["url"] == "http://localhost:8080/api/incidents/inc-123"
        # Error fields should NOT be present on success
        assert "error_class" not in d
        assert "body_prefix" not in d
        assert "error_detail" not in d

    def test_to_dict_failure_includes_all_fields(self) -> None:
        """Test to_dict includes error fields on failure."""
        result = BackendIncidentFetchResult(
            success=False,
            error_class=FAILURE_BACKEND_INCIDENT_FETCH_INVALID_JSON,
            error_detail="JSON parse error",
            http_status=200,
            curl_rc=0,
            url="http://localhost:8080/api/incidents/inc-123",
            api_path="/api/incidents/inc-123",
            encoded_incident_id="inc-123",
            body_prefix="<html>",
            stderr_prefix="",
            json_error="Expecting value",
        )

        d = result.to_dict()

        assert d["success"] is False
        assert d["error_class"] == FAILURE_BACKEND_INCIDENT_FETCH_INVALID_JSON
        assert d["error_detail"] == "JSON parse error"
        assert d["http_status"] == 200
        assert d["curl_rc"] == 0
        assert d["body_prefix"] == "<html>"
        assert d["json_error"] == "Expecting value"

    def test_to_log_lines(self) -> None:
        """Test to_log_lines generates structured log output."""
        result = BackendIncidentFetchResult(
            success=False,
            error_class=FAILURE_BACKEND_INCIDENT_FETCH_TRANSPORT_ERROR,
            error_detail="Connection refused",
            http_status=0,
            curl_rc=7,
            url="http://localhost:8080/api/incidents/inc-123",
            api_path="/api/incidents/inc-123",
            encoded_incident_id="inc-123",
            stderr_prefix="Connection refused",
        )

        lines = result.to_log_lines()

        assert "backend_incident_fetch: success=False" in lines[0]
        assert f"error_class={FAILURE_BACKEND_INCIDENT_FETCH_TRANSPORT_ERROR}" in lines[1]
        assert "curl_rc=7" in lines[4]


class TestIncidentFetchFailureConstants:
    """Tests for incident fetch failure constants."""

    def test_incident_fetch_constants_exist(self) -> None:
        """Test that all incident fetch constants are defined."""
        constants = [
            FAILURE_BACKEND_INCIDENT_FETCH_TRANSPORT_ERROR,
            FAILURE_BACKEND_INCIDENT_FETCH_HTTP_ERROR,
            FAILURE_BACKEND_INCIDENT_FETCH_NOT_FOUND,
            FAILURE_BACKEND_INCIDENT_FETCH_INVALID_JSON,
            FAILURE_BACKEND_INCIDENT_FETCH_CONTRACT_ERROR,
            FAILURE_BACKEND_INCIDENT_FETCH_FAILED,
        ]
        for const in constants:
            assert isinstance(const, str)
            assert len(const) > 0

    def test_incident_fetch_constants_are_unique(self) -> None:
        """Test that incident fetch constants are unique."""
        constants = [
            FAILURE_BACKEND_INCIDENT_FETCH_TRANSPORT_ERROR,
            FAILURE_BACKEND_INCIDENT_FETCH_HTTP_ERROR,
            FAILURE_BACKEND_INCIDENT_FETCH_NOT_FOUND,
            FAILURE_BACKEND_INCIDENT_FETCH_INVALID_JSON,
            FAILURE_BACKEND_INCIDENT_FETCH_CONTRACT_ERROR,
            FAILURE_BACKEND_INCIDENT_FETCH_FAILED,
        ]
        assert len(constants) == len(set(constants))

    def test_constants_follow_naming_convention(self) -> None:
        """Test constants follow the naming convention."""
        for const in [
            FAILURE_BACKEND_INCIDENT_FETCH_TRANSPORT_ERROR,
            FAILURE_BACKEND_INCIDENT_FETCH_HTTP_ERROR,
            FAILURE_BACKEND_INCIDENT_FETCH_NOT_FOUND,
            FAILURE_BACKEND_INCIDENT_FETCH_INVALID_JSON,
            FAILURE_BACKEND_INCIDENT_FETCH_CONTRACT_ERROR,
            FAILURE_BACKEND_INCIDENT_FETCH_FAILED,
        ]:
            assert const.startswith("backend_incident_fetch_"), f"Constant {const} should start with 'backend_incident_fetch_'"
