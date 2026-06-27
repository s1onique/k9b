#!/usr/bin/env python3
"""Tests for incident discovery gate failure class constants.

Verifies that all failure class constants are properly defined with the correct values.
"""

import pytest

from scripts.incident_discovery_gate import (
    FAILURE_INCIDENT_API_CONTRACT_MISMATCH,
    FAILURE_INCIDENT_CANDIDATE_NOT_DETECTED,
    FAILURE_INCIDENT_CANDIDATE_NOT_PROMOTED,
    FAILURE_INCIDENT_DISCOVERY_TIMEOUT,
    FAILURE_INCIDENT_FIXTURE_HEALTHY_UNEXPECTEDLY,
    FAILURE_INCIDENT_FIXTURE_MISSING,
    FAILURE_INCIDENT_FIXTURE_NAMESPACE_MISMATCH,
    FAILURE_INCIDENT_SCHEDULER_COMMUNICATION_ERROR,
    # LLM enrichment failures (Phase 2d/2e)
    FAILURE_LLM_ENRICHMENT_DISABLED,
    FAILURE_LLM_ENRICHMENT_NOT_TRIGGERED_NO_INCIDENT,
    FAILURE_LLM_ENRICHMENT_NOT_TRIGGERED_POLICY_GATE,
    FAILURE_LLM_PROVIDER_CLIENT_NOT_INVOKED,
    FAILURE_LLM_PROVIDER_ENV_MISSING,
    FAILURE_LLM_PROVIDER_NOT_CONFIGURED,
    FAILURE_LLM_PROVIDER_REQUEST_FAILED,
    FAILURE_LLM_PROVIDER_RESPONSE_NOT_PERSISTED,
    FAILURE_LLM_PROVIDER_SECRET_MISSING,
)


class TestFailureClassConstants:
    """Test failure class constants are properly defined."""

    def test_fixture_missing_defined(self) -> None:
        """FAILURE_INCIDENT_FIXTURE_MISSING is defined correctly."""
        assert FAILURE_INCIDENT_FIXTURE_MISSING == "incident_fixture_missing"

    def test_fixture_healthy_unexpectedly_defined(self) -> None:
        """FAILURE_INCIDENT_FIXTURE_HEALTHY_UNEXPECTEDLY is defined correctly."""
        assert FAILURE_INCIDENT_FIXTURE_HEALTHY_UNEXPECTEDLY == "incident_fixture_healthy_unexpectedly"

    def test_fixture_namespace_mismatch_defined(self) -> None:
        """FAILURE_INCIDENT_FIXTURE_NAMESPACE_MISMATCH is defined correctly."""
        assert FAILURE_INCIDENT_FIXTURE_NAMESPACE_MISMATCH == "incident_fixture_namespace_mismatch"

    def test_candidate_not_detected_defined(self) -> None:
        """FAILURE_INCIDENT_CANDIDATE_NOT_DETECTED is defined correctly."""
        assert FAILURE_INCIDENT_CANDIDATE_NOT_DETECTED == "incident_candidate_not_detected"

    def test_candidate_not_promoted_defined(self) -> None:
        """FAILURE_INCIDENT_CANDIDATE_NOT_PROMOTED is defined correctly."""
        assert FAILURE_INCIDENT_CANDIDATE_NOT_PROMOTED == "incident_candidate_not_promoted"

    def test_api_contract_mismatch_defined(self) -> None:
        """FAILURE_INCIDENT_API_CONTRACT_MISMATCH is defined correctly."""
        assert FAILURE_INCIDENT_API_CONTRACT_MISMATCH == "incident_api_contract_mismatch"

    def test_discovery_timeout_defined(self) -> None:
        """FAILURE_INCIDENT_DISCOVERY_TIMEOUT is defined correctly."""
        assert FAILURE_INCIDENT_DISCOVERY_TIMEOUT == "incident_discovery_timeout"

    def test_scheduler_communication_error_defined(self) -> None:
        """FAILURE_INCIDENT_SCHEDULER_COMMUNICATION_ERROR is defined correctly."""
        assert FAILURE_INCIDENT_SCHEDULER_COMMUNICATION_ERROR == "incident_scheduler_communication_error"


class TestLlmEnrichmentFailureConstants:
    """Test LLM enrichment failure class constants (Phase 2d/2e)."""

    def test_llm_enrichment_not_triggered_no_incident_defined(self) -> None:
        """FAILURE_LLM_ENRICHMENT_NOT_TRIGGERED_NO_INCIDENT is defined correctly."""
        assert FAILURE_LLM_ENRICHMENT_NOT_TRIGGERED_NO_INCIDENT == "llm_enrichment_not_triggered_no_incident"

    def test_llm_enrichment_disabled_defined(self) -> None:
        """FAILURE_LLM_ENRICHMENT_DISABLED is defined correctly."""
        assert FAILURE_LLM_ENRICHMENT_DISABLED == "llm_enrichment_disabled"

    def test_llm_provider_not_configured_defined(self) -> None:
        """FAILURE_LLM_PROVIDER_NOT_CONFIGURED is defined correctly."""
        assert FAILURE_LLM_PROVIDER_NOT_CONFIGURED == "llm_provider_not_configured"

    def test_llm_provider_secret_missing_defined(self) -> None:
        """FAILURE_LLM_PROVIDER_SECRET_MISSING is defined correctly."""
        assert FAILURE_LLM_PROVIDER_SECRET_MISSING == "llm_provider_secret_missing"

    def test_llm_provider_env_missing_defined(self) -> None:
        """FAILURE_LLM_PROVIDER_ENV_MISSING is defined correctly."""
        assert FAILURE_LLM_PROVIDER_ENV_MISSING == "llm_provider_env_missing"

    def test_llm_enrichment_not_triggered_policy_gate_defined(self) -> None:
        """FAILURE_LLM_ENRICHMENT_NOT_TRIGGERED_POLICY_GATE is defined correctly."""
        assert FAILURE_LLM_ENRICHMENT_NOT_TRIGGERED_POLICY_GATE == "llm_enrichment_not_triggered_policy_gate"

    def test_llm_provider_client_not_invoked_defined(self) -> None:
        """FAILURE_LLM_PROVIDER_CLIENT_NOT_INVOKED is defined correctly."""
        assert FAILURE_LLM_PROVIDER_CLIENT_NOT_INVOKED == "llm_provider_client_not_invoked"

    def test_llm_provider_request_failed_defined(self) -> None:
        """FAILURE_LLM_PROVIDER_REQUEST_FAILED is defined correctly."""
        assert FAILURE_LLM_PROVIDER_REQUEST_FAILED == "llm_provider_request_failed"

    def test_llm_provider_response_not_persisted_defined(self) -> None:
        """FAILURE_LLM_PROVIDER_RESPONSE_NOT_PERSISTED is defined correctly."""
        assert FAILURE_LLM_PROVIDER_RESPONSE_NOT_PERSISTED == "llm_provider_response_not_persisted"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
