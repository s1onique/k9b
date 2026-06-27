#!/usr/bin/env python3
"""Tests for incident discovery gate parse and detection logic.

Verifies:
- API response shape classification
- Fixture failure classification
- Candidate detection logic
- API contract issue classification
- Incident ID extraction
- API response sanitization
"""

import pytest

from scripts.incident_discovery_gate.classify import (
    classify_api_contract_issue,
    classify_api_response_shape,
    classify_candidate_detection,
    classify_fixture_failure,
    extract_incident_id_from_response,
    sanitize_api_response_for_logging,
)
from tests.incident_discovery_gate_test_utils import (
    FAILURE_INCIDENT_API_CONTRACT_MISMATCH,
    FAILURE_INCIDENT_FIXTURE_HEALTHY_UNEXPECTEDLY,
    FAILURE_INCIDENT_FIXTURE_MISSING,
    FAILURE_INCIDENT_FIXTURE_NAMESPACE_MISMATCH,
)


class TestApiResponseShapeClassification:
    """Test API response shape classification."""

    def test_valid_response_with_incidents(self) -> None:
        """Valid response with incidents returns 'valid'."""
        response = '{"incidents": [{"incident_id": "inc-123"}]}'
        assert classify_api_response_shape(response) == "valid"

    def test_valid_response_empty(self) -> None:
        """Valid response with empty incidents returns 'valid_but_empty'."""
        response = '{"incidents": []}'
        assert classify_api_response_shape(response) == "valid_but_empty"

    def test_invalid_json(self) -> None:
        """Invalid JSON returns 'invalid_json'."""
        response = "not valid json"
        assert classify_api_response_shape(response) == "invalid_json"

    def test_empty_response(self) -> None:
        """Empty response returns 'empty'."""
        assert classify_api_response_shape("") == "empty"

    def test_items_key_response(self) -> None:
        """Response with 'items' key returns 'items_key'."""
        response = '{"items": []}'
        assert classify_api_response_shape(response) == "items_key"

    def test_data_key_response(self) -> None:
        """Response with 'data' key returns 'data_key'."""
        response = '{"data": []}'
        assert classify_api_response_shape(response) == "data_key"

    def test_top_level_array(self) -> None:
        """Top-level array returns 'top_level_array'."""
        response = "[]"
        assert classify_api_response_shape(response) == "top_level_array"

    def test_malformed_incidents_type(self) -> None:
        """Response with non-list incidents returns 'malformed'."""
        response = '{"incidents": "not a list"}'
        assert classify_api_response_shape(response) == "malformed"


class TestFixtureFailureClassification:
    """Test fixture failure classification."""

    def test_fixture_missing(self) -> None:
        """Pod not found returns fixture_missing."""
        pod_status = {"found": False}
        result = classify_fixture_failure(pod_status, "test-pod", "test-ns")
        assert result == FAILURE_INCIDENT_FIXTURE_MISSING

    def test_fixture_namespace_mismatch(self) -> None:
        """Pod in wrong namespace returns namespace_mismatch."""
        pod_status = {"found": True, "namespace": "wrong-ns", "container_statuses": []}
        result = classify_fixture_failure(pod_status, "test-pod", "test-ns")
        assert result == FAILURE_INCIDENT_FIXTURE_NAMESPACE_MISMATCH

    def test_fixture_healthy_unexpectedly(self) -> None:
        """Pod with all containers ready returns healthy_unexpectedly."""
        pod_status = {
            "found": True,
            "namespace": "test-ns",
            "container_statuses": [{"ready": True}, {"ready": True}],
        }
        result = classify_fixture_failure(pod_status, "test-pod", "test-ns")
        assert result == FAILURE_INCIDENT_FIXTURE_HEALTHY_UNEXPECTEDLY

    def test_fixture_failing_correctly(self) -> None:
        """Pod with containers not ready returns None (fixture is correct)."""
        pod_status = {
            "found": True,
            "namespace": "test-ns",
            "container_statuses": [{"ready": False}],
        }
        result = classify_fixture_failure(pod_status, "test-pod", "test-ns")
        assert result is None


class TestCandidateDetection:
    """Test candidate detection logic."""

    def test_detects_readiness_failure(self) -> None:
        """Pod with containers not ready is detected as readiness_failure."""
        pod_status = {
            "found": True,
            "phase": "Running",
            "container_statuses": [{"ready": False}],
            "conditions": [],
        }
        detected, ctype = classify_candidate_detection(pod_status, [])
        assert detected is True
        assert ctype == "readiness_failure"

    def test_detects_pending_phase(self) -> None:
        """Pod in Pending phase is detected as pending."""
        pod_status = {
            "found": True,
            "phase": "Pending",
            "container_statuses": [],
            "conditions": [],
        }
        detected, ctype = classify_candidate_detection(pod_status, [])
        assert detected is True
        assert ctype == "pending"

    def test_detects_failed_phase(self) -> None:
        """Pod in Failed phase is detected as failed."""
        pod_status = {
            "found": True,
            "phase": "Failed",
            "container_statuses": [],
            "conditions": [],
        }
        detected, ctype = classify_candidate_detection(pod_status, [])
        assert detected is True
        assert ctype == "failed"

    def test_detects_crash_loop(self) -> None:
        """Pod with many restarts is detected as restart_loop when containers are ready."""
        pod_status = {
            "found": True,
            "phase": "Running",
            "container_statuses": [{"ready": True, "restartCount": 10}],
            "conditions": [{"type": "Ready", "status": "True"}],
        }
        detected, ctype = classify_candidate_detection(pod_status, [])
        assert detected is True
        assert ctype == "restart_loop"

    def test_no_candidate_when_healthy(self) -> None:
        """Healthy pod with all containers ready returns no candidate."""
        pod_status = {
            "found": True,
            "phase": "Running",
            "container_statuses": [{"ready": True}],
            "conditions": [{"type": "Ready", "status": "True"}],
        }
        detected, ctype = classify_candidate_detection(pod_status, [])
        assert detected is False
        assert ctype == ""

    def test_no_candidate_when_not_found(self) -> None:
        """Pod not found returns no candidate."""
        pod_status = {"found": False}
        detected, ctype = classify_candidate_detection(pod_status, [])
        assert detected is False
        assert ctype == ""


class TestApiContractIssueClassification:
    """Test API contract issue classification."""

    def test_non_200_status_not_contract_issue(self) -> None:
        """Non-200 HTTP status is not a contract issue."""
        result = classify_api_contract_issue('{"error": "bad"}', 500)
        assert result is None

    def test_invalid_json_is_contract_issue(self) -> None:
        """Invalid JSON with 200 is a contract issue."""
        result = classify_api_contract_issue("not json", 200)
        assert result == FAILURE_INCIDENT_API_CONTRACT_MISMATCH

    def test_wrong_shape_is_contract_issue(self) -> None:
        """Response with wrong shape is a contract issue."""
        result = classify_api_contract_issue('{"items": []}', 200)
        assert result == FAILURE_INCIDENT_API_CONTRACT_MISMATCH

    def test_valid_response_not_contract_issue(self) -> None:
        """Valid response is not a contract issue."""
        result = classify_api_contract_issue('{"incidents": []}', 200)
        assert result is None


class TestIncidentIdExtraction:
    """Test incident ID extraction."""

    def test_extracts_from_valid_response(self) -> None:
        """Extracts incident_id from valid response."""
        response = '{"incidents": [{"incident_id": "inc-123"}]}'
        assert extract_incident_id_from_response(response) == "inc-123"

    def test_empty_when_no_incidents(self) -> None:
        """Returns empty when no incidents."""
        response = '{"incidents": []}'
        assert extract_incident_id_from_response(response) == ""

    def test_empty_when_invalid_json(self) -> None:
        """Returns empty when invalid JSON."""
        assert extract_incident_id_from_response("not json") == ""

    def test_empty_when_empty_response(self) -> None:
        """Returns empty when empty response."""
        assert extract_incident_id_from_response("") == ""

    def test_empty_when_missing_key(self) -> None:
        """Returns empty when incidents key missing."""
        response = '{"data": []}'
        assert extract_incident_id_from_response(response) == ""


class TestSanitizeApiResponse:
    """Test API response sanitization."""

    def test_preserves_structure(self) -> None:
        """Sanitized response preserves structure."""
        response = '{"incidents": [{"incident_id": "inc-123"}]}'
        sanitized = sanitize_api_response_for_logging(response)
        assert "incidents" in sanitized
        assert "1" in sanitized  # One item

    def test_truncates_long_responses(self) -> None:
        """Long responses are truncated."""
        response = "x" * 1000
        sanitized = sanitize_api_response_for_logging(response, max_length=100)
        assert len(sanitized) < 1000
        assert "(truncated)" in sanitized

    def test_handles_empty_response(self) -> None:
        """Empty response returns empty marker."""
        assert sanitize_api_response_for_logging("") == "(empty)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
