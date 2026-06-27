#!/usr/bin/env python3
"""Tests for incident discovery gate.

Verifies:
- Failure class constants are properly defined
- API response shape classification
- Fixture failure classification
- Candidate detection logic
- Incident ID extraction
- Result dataclass serialization
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
from scripts.incident_discovery_gate.classify import (
    classify_api_contract_issue,
    classify_api_response_shape,
    classify_candidate_detection,
    classify_fixture_failure,
    classify_incident_promotion,
    extract_incident_id_from_response,
    sanitize_api_response_for_logging,
)
from scripts.incident_discovery_gate.enrich import (
    classify_enrichment_status,
    extract_enrichment_status_from_incident,
)
from scripts.incident_discovery_gate.render import sanitize_logs_for_artifacts
from scripts.incident_discovery_gate.types import IncidentDiscoveryResult


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


class TestWrapperImportMode:
    """Regression tests for CLI wrapper import mode."""

    def test_wrapper_imports_when_run_as_file(self) -> None:
        """Wrapper script imports correctly when executed as `python scripts/check_incident_discovery_gate.py`."""
        # Verify imports work
        from scripts.incident_discovery_gate import run_incident_discovery

        assert run_incident_discovery is not None


class TestArtifactPathConsistency:
    """Regression tests for artifact path consistency.

    Ensures that artifact_dir is used as-is without double-nesting.
    The workflow passes --artifact-dir ./lab-artifacts/live/provider-smoke/incident-discovery
    so main.py should NOT append additional path components.
    """

    def test_artifact_dir_used_directly(self) -> None:
        """Verify artifact_dir is used directly, not appended with provider-smoke/incident-discovery."""
        # This test verifies the contract: if artifact_dir is passed as-is,
        # no additional path components should be added.
        # The actual integration is tested via workflow runs.
        #
        # Contract: When workflow passes:
        #   --artifact-dir ./lab-artifacts/live/provider-smoke/incident-discovery
        # The artifacts should be written to that exact directory, not nested further.
        #
        # We verify this by checking the code doesn't append subdirectories.
        # The run_incident_discovery function should use artifact_dir directly.
        import inspect

        from scripts.incident_discovery_gate.main import run_incident_discovery

        source = inspect.getsource(run_incident_discovery)

        # Verify the pattern is artifact_dir / "provider-smoke" / "incident-discovery" NOT in source
        # After the fix, this pattern should not exist
        assert 'artifact_dir / "provider-smoke"' not in source, (
            "Artifact path double-nesting detected: main.py still appends 'provider-smoke/incident-discovery'"
        )
        assert "discovery_dir = artifact_dir" in source, (
            "main.py should use artifact_dir directly"
        )


class TestSanitizeLogsForArtifacts:
    """Test log sanitization for artifact writing."""

    def test_redacts_api_key_pattern(self) -> None:
        """API key patterns are redacted."""
        logs = 'api_key=sk-1234567890abcdefghijklmnopqrstuvwxyz'
        sanitized = sanitize_logs_for_artifacts(logs)
        assert "sk-1234567890abcdefghijklmnopqrstuvwxyz" not in sanitized
        assert "[REDACTED]" in sanitized

    def test_redacts_token_pattern(self) -> None:
        """Token patterns are redacted."""
        logs = 'token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9'
        sanitized = sanitize_logs_for_artifacts(logs)
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in sanitized
        assert "[REDACTED]" in sanitized

    def test_redacts_bearer_token(self) -> None:
        """Bearer tokens are redacted."""
        logs = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9"
        sanitized = sanitize_logs_for_artifacts(logs)
        assert "Bearer eyJhbGciOiJIUzI1NiJ9" not in sanitized
        assert "[REDACTED]" in sanitized

    def test_redacts_openai_api_key(self) -> None:
        """OpenAI API key patterns are redacted."""
        logs = 'OPENAI_API_KEY=sk-proj-1234567890abcdefghijklmnopqrstuvwxyz'
        sanitized = sanitize_logs_for_artifacts(logs)
        assert "sk-proj-1234567890abcdefghijklmnopqrstuvwxyz" not in sanitized
        assert "[REDACTED]" in sanitized

    def test_redacts_anthropic_api_key(self) -> None:
        """Anthropic API key patterns are redacted."""
        logs = 'anthropic_api_key=sk-ant-1234567890abcdefghijklmnopqrstuvwxyz'
        sanitized = sanitize_logs_for_artifacts(logs)
        assert "sk-ant-1234567890abcdefghijklmnopqrstuvwxyz" not in sanitized
        assert "[REDACTED]" in sanitized

    def test_redacts_url_with_credentials(self) -> None:
        """URLs with embedded credentials are redacted."""
        logs = "https://user:password@example.com/api"
        sanitized = sanitize_logs_for_artifacts(logs)
        assert "user:password" not in sanitized
        assert "[REDACTED_USER]" in sanitized
        assert "[REDACTED_PASS]" in sanitized

    def test_preserves_non_sensitive_content(self) -> None:
        """Non-sensitive content is preserved."""
        logs = 'INFO: Processing request for incident inc-123'
        sanitized = sanitize_logs_for_artifacts(logs)
        assert "Processing request" in sanitized
        assert "inc-123" in sanitized

    def test_handles_empty_logs(self) -> None:
        """Empty logs are handled gracefully."""
        assert sanitize_logs_for_artifacts("") == ""
        assert sanitize_logs_for_artifacts(None) is None

    def test_handles_multiline_logs(self) -> None:
        """Multiline logs are sanitized correctly."""
        logs = """2024-01-01 10:00:00 INFO Starting process
api_key=sk-1234567890abcdefghijklmnopqrstuvwxyz
2024-01-01 10:00:01 INFO Request completed
"""
        sanitized = sanitize_logs_for_artifacts(logs)
        assert "sk-1234567890abcdefghijklmnopqrstuvwxyz" not in sanitized
        assert "Starting process" in sanitized
        assert "Request completed" in sanitized


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
