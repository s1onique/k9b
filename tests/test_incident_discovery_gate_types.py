#!/usr/bin/env python3
"""Tests for incident discovery gate result types.

Verifies the IncidentDiscoveryResult dataclass serialization.
"""

import pytest

from scripts.incident_discovery_gate.types import IncidentDiscoveryResult
from tests.incident_discovery_gate_test_utils import (
    FAILURE_INCIDENT_FIXTURE_MISSING,
)


class TestIncidentDiscoveryResult:
    """Test IncidentDiscoveryResult dataclass."""

    def test_to_dict_includes_failure_class(self) -> None:
        """to_dict includes failure_class."""
        result = IncidentDiscoveryResult()
        result.failure_class = FAILURE_INCIDENT_FIXTURE_MISSING

        data = result.to_dict()

        assert "failure_class" in data
        assert data["failure_class"] == FAILURE_INCIDENT_FIXTURE_MISSING

    def test_to_dict_includes_incident_id(self) -> None:
        """to_dict includes incident_id."""
        result = IncidentDiscoveryResult()
        result.incident_id = "inc-123"

        data = result.to_dict()

        assert "incident_id" in data
        assert data["incident_id"] == "inc-123"

    def test_to_dict_includes_fixture_details(self) -> None:
        """to_dict includes fixture details."""
        result = IncidentDiscoveryResult()
        result.fixture_name = "test-pod"
        result.fixture_namespace = "test-ns"
        result.fixture_exists = True
        result.fixture_phase = "Running"
        result.fixture_is_healthy = False

        data = result.to_dict()

        assert data["fixture_name"] == "test-pod"
        assert data["fixture_namespace"] == "test-ns"
        assert data["fixture_exists"] is True
        assert data["fixture_phase"] == "Running"
        assert data["fixture_is_healthy"] is False

    def test_to_dict_includes_candidate_details(self) -> None:
        """to_dict includes candidate details."""
        result = IncidentDiscoveryResult()
        result.candidate_detected = True
        result.candidate_type = "readiness_failure"

        data = result.to_dict()

        assert data["candidate_detected"] is True
        assert data["candidate_type"] == "readiness_failure"

    def test_to_dict_includes_poll_count(self) -> None:
        """to_dict includes poll_count."""
        result = IncidentDiscoveryResult()
        result.poll_count = 5
        result.total_elapsed_seconds = 50.0

        data = result.to_dict()

        assert data["poll_count"] == 5
        assert data["total_elapsed_seconds"] == 50.0

    def test_to_dict_includes_api_tracking(self) -> None:
        """to_dict includes API response tracking."""
        result = IncidentDiscoveryResult()
        result.http_status_codes_seen = ["200", "200", "500"]
        result.api_response_shapes_seen = ["valid_but_empty", "valid_but_empty", "valid_but_empty"]
        result.last_api_response = '{"incidents": []}'

        data = result.to_dict()

        assert data["http_status_codes_seen"] == ["200", "200", "500"]
        assert data["api_response_shapes_seen"] == ["valid_but_empty", "valid_but_empty", "valid_but_empty"]
        assert data["last_api_response"] == '{"incidents": []}'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
