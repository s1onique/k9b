#!/usr/bin/env python3
"""Tests for incident discovery gate promotion and enrichment logic.

Verifies:
- Incident promotion classification
- LLM enrichment status classification
- Enrichment status extraction from incidents
"""

import pytest

from scripts.incident_discovery_gate.classify import classify_incident_promotion
from scripts.incident_discovery_gate.enrich import (
    classify_enrichment_status,
    extract_enrichment_status_from_incident,
)
from tests.incident_discovery_gate_test_utils import (
    FAILURE_INCIDENT_CANDIDATE_NOT_DETECTED,
    FAILURE_INCIDENT_CANDIDATE_NOT_PROMOTED,
    FAILURE_LLM_ENRICHMENT_DISABLED,
    FAILURE_LLM_ENRICHMENT_NOT_TRIGGERED_NO_INCIDENT,
    FAILURE_LLM_PROVIDER_CLIENT_NOT_INVOKED,
    FAILURE_LLM_PROVIDER_ENV_MISSING,
    FAILURE_LLM_PROVIDER_NOT_CONFIGURED,
    FAILURE_LLM_PROVIDER_RESPONSE_NOT_PERSISTED,
    FAILURE_LLM_PROVIDER_SECRET_MISSING,
)


class TestIncidentPromotionClassification:
    """Test incident promotion classification."""

    def test_candidate_not_detected(self) -> None:
        """When no candidate detected, returns candidate_not_detected."""
        result = classify_incident_promotion(
            candidate_detected=False,
            candidate_type="",
            api_has_incidents=False,
        )
        assert result == FAILURE_INCIDENT_CANDIDATE_NOT_DETECTED

    def test_candidate_not_promoted(self) -> None:
        """When candidate detected but no incidents, returns candidate_not_promoted."""
        result = classify_incident_promotion(
            candidate_detected=True,
            candidate_type="readiness_failure",
            api_has_incidents=False,
        )
        assert result == FAILURE_INCIDENT_CANDIDATE_NOT_PROMOTED

    def test_promotion_working(self) -> None:
        """When incidents present, returns None (promotion is working)."""
        result = classify_incident_promotion(
            candidate_detected=True,
            candidate_type="readiness_failure",
            api_has_incidents=True,
        )
        assert result is None


class TestClassifyEnrichmentStatus:
    """Test classify_enrichment_status function."""

    def test_no_incident_returns_not_triggered_no_incident(self) -> None:
        """When no incident exists, returns not_triggered_no_incident."""
        result = classify_enrichment_status(
            incident_exists=False,
            provider_enabled=True,
            provider_configured=True,
            provider_secret_refs_present=["api-key"],
            provider_env_vars_present=["LLM_PROVIDER"],
            provider_invocation_count=1,
            incident_enriched=True,
        )
        assert result == FAILURE_LLM_ENRICHMENT_NOT_TRIGGERED_NO_INCIDENT

    def test_provider_disabled_returns_disabled(self) -> None:
        """When provider is disabled, returns disabled."""
        result = classify_enrichment_status(
            incident_exists=True,
            provider_enabled=False,
            provider_configured=True,
            provider_secret_refs_present=["api-key"],
            provider_env_vars_present=["LLM_PROVIDER"],
            provider_invocation_count=0,
            incident_enriched=False,
        )
        assert result == FAILURE_LLM_ENRICHMENT_DISABLED

    def test_provider_not_configured_returns_not_configured(self) -> None:
        """When provider is not configured, returns not_configured."""
        result = classify_enrichment_status(
            incident_exists=True,
            provider_enabled=True,
            provider_configured=False,
            provider_secret_refs_present=[],
            provider_env_vars_present=[],
            provider_invocation_count=0,
            incident_enriched=False,
        )
        assert result == FAILURE_LLM_PROVIDER_NOT_CONFIGURED

    def test_missing_secrets_returns_secret_missing(self) -> None:
        """When required secrets are missing, returns secret_missing."""
        result = classify_enrichment_status(
            incident_exists=True,
            provider_enabled=True,
            provider_configured=True,
            provider_secret_refs_present=[],  # Empty = missing
            provider_env_vars_present=["LLM_PROVIDER"],
            provider_invocation_count=0,
            incident_enriched=False,
        )
        assert result == FAILURE_LLM_PROVIDER_SECRET_MISSING

    def test_missing_env_vars_returns_env_missing(self) -> None:
        """When required env vars are missing, returns env_missing."""
        result = classify_enrichment_status(
            incident_exists=True,
            provider_enabled=True,
            provider_configured=True,
            provider_secret_refs_present=["api-key"],
            provider_env_vars_present=[],  # Empty = missing
            provider_invocation_count=0,
            incident_enriched=False,
        )
        assert result == FAILURE_LLM_PROVIDER_ENV_MISSING

    def test_provider_not_invoked_returns_client_not_invoked(self) -> None:
        """When provider is configured but never invoked, returns client_not_invoked."""
        result = classify_enrichment_status(
            incident_exists=True,
            provider_enabled=True,
            provider_configured=True,
            provider_secret_refs_present=["api-key"],
            provider_env_vars_present=["LLM_PROVIDER"],
            provider_invocation_count=0,
            incident_enriched=False,
        )
        assert result == FAILURE_LLM_PROVIDER_CLIENT_NOT_INVOKED

    def test_incident_not_enriched_returns_response_not_persisted(self) -> None:
        """When provider invoked but incident not enriched, returns response_not_persisted."""
        result = classify_enrichment_status(
            incident_exists=True,
            provider_enabled=True,
            provider_configured=True,
            provider_secret_refs_present=["api-key"],
            provider_env_vars_present=["LLM_PROVIDER"],
            provider_invocation_count=1,
            incident_enriched=False,  # Invoked but not enriched
        )
        assert result == FAILURE_LLM_PROVIDER_RESPONSE_NOT_PERSISTED

    def test_enrichment_working_returns_empty(self) -> None:
        """When enrichment is working, returns empty string."""
        result = classify_enrichment_status(
            incident_exists=True,
            provider_enabled=True,
            provider_configured=True,
            provider_secret_refs_present=["api-key"],
            provider_env_vars_present=["LLM_PROVIDER"],
            provider_invocation_count=1,
            incident_enriched=True,  # Incident is enriched
        )
        assert result == ""


class TestExtractEnrichmentStatusFromIncident:
    """Test extract_enrichment_status_from_incident function."""

    def test_empty_incident_returns_false(self) -> None:
        """Empty incident data returns False."""
        assert extract_enrichment_status_from_incident({}) is False
        assert extract_enrichment_status_from_incident(None) is False

    def test_detects_enriched_field(self) -> None:
        """Detects 'enriched' field when True."""
        incident = {"enriched": True}
        assert extract_enrichment_status_from_incident(incident) is True

    def test_detects_triage_status(self) -> None:
        """Detects 'triage_status' field."""
        incident = {"triage_status": "completed"}
        assert extract_enrichment_status_from_incident(incident) is True

    def test_detects_llm_enriched_field(self) -> None:
        """Detects 'llm_enriched' field."""
        incident = {"llm_enriched": True}
        assert extract_enrichment_status_from_incident(incident) is True

    def test_detects_nested_metadata(self) -> None:
        """Detects enrichment in nested metadata."""
        incident = {"metadata": {"enriched": True}}
        assert extract_enrichment_status_from_incident(incident) is True

    def test_detects_diagnostic_summary(self) -> None:
        """Detects 'diagnostic_summary' field."""
        incident = {"diagnostic_summary": "Some analysis"}
        assert extract_enrichment_status_from_incident(incident) is True

    def test_no_enrichment_returns_false(self) -> None:
        """Plain incident without enrichment indicators returns False."""
        incident = {"incident_id": "inc-123", "status": "new"}
        assert extract_enrichment_status_from_incident(incident) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
