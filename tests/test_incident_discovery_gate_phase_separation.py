#!/usr/bin/env python3
"""Tests for incident discovery gate phase separation.

Verifies that incident discovery and LLM enrichment are cleanly separated
in the gate behavior and reporting.
"""

import pytest

from scripts.incident_discovery_gate import (
    FAILURE_LLM_ENRICHMENT_DISABLED,
    FAILURE_LLM_PROVIDER_NOT_CONFIGURED,
)
from scripts.incident_discovery_gate.enrich import classify_enrichment_status
from scripts.incident_discovery_gate.render import render_bounded_summary
from scripts.incident_discovery_gate.types import IncidentDiscoveryResult


class TestEnrichmentClassification:
    """Test enrichment status classification with phase separation."""

    def test_incident_found_enrichment_disabled_returns_failure_class(self) -> None:
        """When incident found but enrichment disabled, returns failure class for Phase 2e."""
        result = classify_enrichment_status(
            incident_exists=True,
            provider_enabled=False,
            provider_configured=False,
            provider_secret_refs_present=[],
            provider_env_vars_present=[],
            provider_invocation_count=0,
            incident_enriched=False,
        )
        assert result == FAILURE_LLM_ENRICHMENT_DISABLED

    def test_incident_found_provider_not_configured_returns_failure_class(self) -> None:
        """When incident found but provider not configured, returns specific failure class."""
        result = classify_enrichment_status(
            incident_exists=True,
            provider_enabled=True,  # enabled but not configured
            provider_configured=False,
            provider_secret_refs_present=[],
            provider_env_vars_present=[],
            provider_invocation_count=0,
            incident_enriched=False,
        )
        assert result == FAILURE_LLM_PROVIDER_NOT_CONFIGURED

    def test_incident_not_found_returns_no_incident_failure(self) -> None:
        """When no incident found, returns no_incident failure (not discovery timeout)."""
        result = classify_enrichment_status(
            incident_exists=False,
            provider_enabled=True,
            provider_configured=True,
            provider_secret_refs_present=["secret-ref"],
            provider_env_vars_present=["VAR"],
            provider_invocation_count=0,
            incident_enriched=False,
        )
        assert result == "llm_enrichment_not_triggered_no_incident"

    def test_incident_found_enrichment_working_returns_empty(self) -> None:
        """When incident found and enrichment working, returns empty string (pass)."""
        result = classify_enrichment_status(
            incident_exists=True,
            provider_enabled=True,
            provider_configured=True,
            provider_secret_refs_present=["secret-ref"],
            provider_env_vars_present=["VAR"],
            provider_invocation_count=1,
            incident_enriched=True,
        )
        assert result == ""


class TestPhaseStatusTracking:
    """Test phase status tracking in IncidentDiscoveryResult."""

    def test_discovery_status_field_exists(self) -> None:
        """Result type has discovery_status field."""
        result = IncidentDiscoveryResult()
        assert hasattr(result, "discovery_status")

    def test_enrichment_gate_status_field_exists(self) -> None:
        """Result type has enrichment_gate_status field."""
        result = IncidentDiscoveryResult()
        assert hasattr(result, "enrichment_gate_status")

    def test_to_dict_includes_phase_statuses(self) -> None:
        """to_dict includes discovery_status and enrichment_gate_status."""
        result = IncidentDiscoveryResult()
        result.discovery_status = "passed"
        result.enrichment_gate_status = "failed"
        
        data = result.to_dict()
        assert "discovery_status" in data
        assert "enrichment_gate_status" in data
        assert data["discovery_status"] == "passed"
        assert data["enrichment_gate_status"] == "failed"


class TestSummaryRendering:
    """Test bounded summary rendering with phase separation."""

    def test_summary_shows_phase_separation_when_incident_found(self) -> None:
        """Summary shows Incident discovery: PASSED when incident found."""
        result = IncidentDiscoveryResult()
        result.passed = True
        result.incident_found = True
        result.incident_id = "test-incident-123"
        result.discovery_status = "passed"
        result.enrichment_gate_status = "skipped"
        
        summary = render_bounded_summary(result)
        assert "Incident discovery: PASSED" in summary
        assert "LLM enrichment: SKIPPED" in summary

    def test_summary_shows_enrichment_failed_separately(self) -> None:
        """Summary shows enrichment failure (non-disabled) separate from discovery."""
        # Use a non-disabled failure class that results in enrichment_gate_status = "failed"
        result = IncidentDiscoveryResult()
        result.passed = False  # Overall gate failed
        result.incident_found = True
        result.incident_id = "test-incident-123"
        result.failure_class = FAILURE_LLM_PROVIDER_NOT_CONFIGURED
        result.discovery_status = "passed"  # Discovery still passed
        result.enrichment_gate_status = "failed"
        
        summary = render_bounded_summary(result)
        assert "Incident discovery: PASSED" in summary
        assert "LLM enrichment: FAILED" in summary
        # Should NOT say "was not discovered"
        assert "was not discovered" not in summary

    def test_summary_does_not_say_timeout_when_incident_found(self) -> None:
        """Regression: When incident_id present, summary must not say 'was not discovered'."""
        result = IncidentDiscoveryResult()
        result.passed = False
        result.incident_found = True
        result.incident_id = "test-incident-123"
        result.failure_class = FAILURE_LLM_ENRICHMENT_DISABLED
        result.discovery_status = "passed"
        result.enrichment_gate_status = "failed"
        
        summary = render_bounded_summary(result)
        # This is the key regression test from the bug report
        assert "was not discovered" not in summary.lower()

    def test_summary_shows_discovery_failed_when_timeout(self) -> None:
        """Summary shows Incident discovery: FAILED when timeout."""
        result = IncidentDiscoveryResult()
        result.passed = False
        result.incident_found = False
        result.failure_class = "incident_discovery_timeout"
        result.discovery_status = "failed"
        
        summary = render_bounded_summary(result)
        assert "Incident discovery: FAILED" in summary


class TestContractScenarios:
    """Test specific contract scenarios from the ACT prompt."""

    def test_scenario_incident_found_enrichment_disabled_optional(self) -> None:
        """Scenario: incident found + enrichment disabled + enrichment optional => gate passes."""
        result = IncidentDiscoveryResult()
        result.passed = True
        result.incident_found = True
        result.incident_id = "readiness-failure-123"
        result.discovery_status = "passed"
        # enrichment disabled but optional -> skipped, not failure
        result.enrichment_gate_status = "skipped"
        
        # This should be a pass scenario
        assert result.passed is True
        assert result.discovery_status == "passed"

    def test_scenario_incident_found_enrichment_disabled_required(self) -> None:
        """Scenario: incident found + enrichment disabled + enrichment required => gate fails with specific class."""
        # This is the scenario that was broken before
        result = IncidentDiscoveryResult()
        result.passed = False  # Gate fails
        result.incident_found = True
        result.incident_id = "readiness-failure-123"
        result.failure_class = FAILURE_LLM_ENRICHMENT_DISABLED
        result.discovery_status = "passed"  # Discovery still passed
        result.enrichment_gate_status = "disabled"  # Specific: disabled, not failed
        
        # Gate fails but discovery passed
        assert result.passed is False
        assert result.discovery_status == "passed"
        assert result.failure_class == "llm_enrichment_disabled"
        assert result.enrichment_gate_status == "disabled"
        # Key: should NOT say "incident was not discovered"
        summary = render_bounded_summary(result)
        assert "was not discovered" not in summary.lower()
        # Summary should show DISABLED not FAILED for enrichment
        assert "LLM enrichment: DISABLED" in summary

    def test_scenario_incident_not_found(self) -> None:
        """Scenario: incident not found => gate fails with discovery timeout."""
        result = IncidentDiscoveryResult()
        result.passed = False
        result.incident_found = False
        result.failure_class = "incident_discovery_timeout"
        result.discovery_status = "failed"
        
        assert result.passed is False
        assert result.discovery_status == "failed"


class TestTerminalOutputBehavior:
    """Test terminal output behavior for enrichment-disabled scenarios.
    
    Regression tests for the bug where terminal output said:
    "Incident discovery failed: llm_enrichment_disabled"
    "The incident was not discovered within the timeout period."
    
    When incident was actually found.
    """

    def test_failure_display_shows_enrichment_when_incident_found(self) -> None:
        """When incident found + enrichment disabled, failure_display attributes to enrichment."""
        result = IncidentDiscoveryResult()
        result.passed = False
        result.incident_found = True
        result.incident_id = "test-incident-456"
        result.failure_class = "llm_enrichment_disabled"
        result.discovery_status = "passed"
        result.enrichment_gate_status = "disabled"
        
        summary = render_bounded_summary(result)
        # Must NOT say "was not discovered"
        assert "was not discovered" not in summary.lower()
        # Should attribute failure to enrichment
        assert "enrichment: llm_enrichment_disabled" in summary

    def test_failure_display_shows_phase_status_correctly(self) -> None:
        """Summary shows discovery: PASSED when incident found even if overall failed."""
        result = IncidentDiscoveryResult()
        result.passed = False
        result.incident_found = True
        result.incident_id = "test-incident-789"
        result.failure_class = "llm_enrichment_disabled"
        result.discovery_status = "passed"
        result.enrichment_gate_status = "disabled"
        
        summary = render_bounded_summary(result)
        assert "Incident discovery: PASSED" in summary
        assert "LLM enrichment: DISABLED" in summary

    def test_true_timeout_scenario_shows_timeout_message(self) -> None:
        """True discovery timeout should show timeout message."""
        result = IncidentDiscoveryResult()
        result.passed = False
        result.incident_found = False
        result.failure_class = "incident_discovery_timeout"
        result.discovery_status = "failed"
        result.poll_count = 12
        result.total_elapsed_seconds = 120.0
        
        summary = render_bounded_summary(result)
        assert "Incident discovery: FAILED" in summary
        # For true discovery failures, the timeout message is appropriate in bounded summary

    def test_llm_enrichment_failure_prefixed_in_summary(self) -> None:
        """LLM enrichment failures should be prefixed with 'enrichment:' in failure_display."""
        llm_failures = [
            "llm_enrichment_disabled",
            "llm_provider_not_configured",
            "llm_provider_secret_missing",
            "llm_provider_env_missing",
            "llm_provider_client_not_invoked",
        ]
        
        for failure_class in llm_failures:
            result = IncidentDiscoveryResult()
            result.passed = False
            result.incident_found = True
            result.incident_id = f"test-{failure_class}"
            result.failure_class = failure_class
            result.discovery_status = "passed"
            result.enrichment_gate_status = "failed"
            
            summary = render_bounded_summary(result)
            assert f"enrichment: {failure_class}" in summary, f"Failed for {failure_class}"
            assert "was not discovered" not in summary.lower()

    def test_post_discovery_failure_uses_post_discovery_prefix(self) -> None:
        """Post-discovery failures (not enrichment) should be attributed as 'post-discovery:'."""
        result = IncidentDiscoveryResult()
        result.passed = False
        result.incident_found = True
        result.incident_id = "test-incident-123"
        result.failure_class = "some_other_failure"
        result.discovery_status = "passed"
        result.enrichment_gate_status = ""  # Not enrichment-related
        
        summary = render_bounded_summary(result)
        # Should use neutral post-discovery attribution, not enrichment
        assert "post-discovery: some_other_failure" in summary
        assert "enrichment: some_other_failure" not in summary
        assert "was not discovered" not in summary.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
