"""Constants for incident discovery gate."""

# Fixture-related failure constants
FAILURE_INCIDENT_FIXTURE_MISSING = "incident_fixture_missing"
FAILURE_INCIDENT_FIXTURE_HEALTHY_UNEXPECTEDLY = "incident_fixture_healthy_unexpectedly"
FAILURE_INCIDENT_FIXTURE_NAMESPACE_MISMATCH = "incident_fixture_namespace_mismatch"

# Candidate detection failure constants
FAILURE_INCIDENT_CANDIDATE_NOT_DETECTED = "incident_candidate_not_detected"
FAILURE_INCIDENT_CANDIDATE_NOT_PROMOTED = "incident_candidate_not_promoted"

# API/transport failure constants
FAILURE_INCIDENT_API_CONTRACT_MISMATCH = "incident_api_contract_mismatch"
FAILURE_INCIDENT_DISCOVERY_TIMEOUT = "incident_discovery_timeout"
FAILURE_INCIDENT_SCHEDULER_COMMUNICATION_ERROR = "incident_scheduler_communication_error"

# LLM enrichment failure constants (Phase 2d/2e)
FAILURE_LLM_ENRICHMENT_NOT_TRIGGERED_NO_INCIDENT = "llm_enrichment_not_triggered_no_incident"
FAILURE_LLM_ENRICHMENT_DISABLED = "llm_enrichment_disabled"
FAILURE_LLM_PROVIDER_NOT_CONFIGURED = "llm_provider_not_configured"
FAILURE_LLM_PROVIDER_SECRET_MISSING = "llm_provider_secret_missing"
FAILURE_LLM_PROVIDER_ENV_MISSING = "llm_provider_env_missing"
FAILURE_LLM_ENRICHMENT_NOT_TRIGGERED_POLICY_GATE = "llm_enrichment_not_triggered_policy_gate"
FAILURE_LLM_PROVIDER_CLIENT_NOT_INVOKED = "llm_provider_client_not_invoked"
FAILURE_LLM_PROVIDER_REQUEST_FAILED = "llm_provider_request_failed"
FAILURE_LLM_PROVIDER_RESPONSE_NOT_PERSISTED = "llm_provider_response_not_persisted"

# Snapshot/capture failure constants (Phase 2c)
FAILURE_SNAPSHOT_NOT_TRIGGERED = "snapshot_not_triggered"
FAILURE_SNAPSHOT_COMPLETED_NO_CANDIDATES = "snapshot_completed_no_candidates"
FAILURE_CANDIDATE_GENERATED_NOT_PROMOTED = "candidate_generated_not_promoted"
FAILURE_INCIDENT_PROMOTED_NOT_LISTED = "incident_promoted_not_listed"
FAILURE_WRONG_BACKEND_PROCESS = "wrong_backend_process"

# Backend pod discovery failure constants
FAILURE_BACKEND_POD_NOT_FOUND = "backend_pod_not_found"

# Default fixture name (from fixtures/lab/live/pod-failure/injected-change.yaml)
DEFAULT_FIXTURE_NAME = "cnpg-lab-failing-app"
