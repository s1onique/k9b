"""Types for incident discovery gate."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class IncidentDiscoveryResult:
    """Structured result from incident discovery check."""

    # Classification
    failure_class: str = ""
    passed: bool = False

    # Incident details
    incident_id: str = ""
    incident_found: bool = False

    # Timing
    poll_count: int = 0
    total_elapsed_seconds: float = 0.0

    # API response tracking
    api_response_shapes_seen: list[str] = field(default_factory=list)
    http_status_codes_seen: list[str] = field(default_factory=list)

    # Fixture details
    fixture_name: str = ""
    fixture_namespace: str = ""
    fixture_exists: bool = False
    fixture_phase: str = ""
    fixture_conditions: list[dict[str, Any]] = field(default_factory=list)
    fixture_is_healthy: bool = False
    fixture_container_states: list[dict[str, Any]] = field(default_factory=list)

    # Candidate details
    candidate_detected: bool = False
    candidate_type: str = ""

    # Provider/enrichment status (Phase 2d/2e)
    provider_enabled: bool = False
    provider_configured: bool = False
    provider_name: str = ""
    provider_model: str = ""
    provider_endpoint: str = ""
    provider_secret_refs: list[str] = field(default_factory=list)
    provider_env_vars: list[str] = field(default_factory=list)
    provider_invocation_count: int = 0
    provider_invocation_expected: bool = False
    enrichment_status: str = ""  # "not_triggered", "triggered", "completed", "failed", "skipped", "disabled"
    
    # Phase-level pass/fail tracking for clear separation
    discovery_status: str = ""  # "passed", "failed", "skipped"
    enrichment_gate_status: str = ""  # "passed", "failed", "skipped", "disabled"

    # Diagnostics for JSON artifact
    diagnostics: dict = field(default_factory=dict)

    # Raw API response for debugging (sanitized)
    last_api_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "failure_class": self.failure_class,
            "passed": self.passed,
            "incident_id": self.incident_id,
            "incident_found": self.incident_found,
            "poll_count": self.poll_count,
            "total_elapsed_seconds": self.total_elapsed_seconds,
            "api_response_shapes_seen": self.api_response_shapes_seen,
            "http_status_codes_seen": self.http_status_codes_seen,
            "fixture_name": self.fixture_name,
            "fixture_namespace": self.fixture_namespace,
            "fixture_exists": self.fixture_exists,
            "fixture_phase": self.fixture_phase,
            "fixture_conditions": self.fixture_conditions,
            "fixture_is_healthy": self.fixture_is_healthy,
            "fixture_container_states": self.fixture_container_states,
            "candidate_detected": self.candidate_detected,
            "candidate_type": self.candidate_type,
            "provider_enabled": self.provider_enabled,
            "provider_configured": self.provider_configured,
            "provider_name": self.provider_name,
            "provider_model": self.provider_model,
            "provider_endpoint": self._redact_endpoint(self.provider_endpoint),
            "provider_secret_refs": self.provider_secret_refs,
            "provider_env_vars": self.provider_env_vars,
            "provider_invocation_count": self.provider_invocation_count,
            "provider_invocation_expected": self.provider_invocation_expected,
            "enrichment_status": self.enrichment_status,
            "discovery_status": self.discovery_status,
            "enrichment_gate_status": self.enrichment_gate_status,
            "diagnostics": self.diagnostics,
            "last_api_response": self.last_api_response,
        }

    @staticmethod
    def _redact_endpoint(endpoint: str) -> str:
        """Redact sensitive parts of endpoint URL."""
        if not endpoint:
            return ""
        # Remove API keys and tokens from URL
        import re
        # Remove common secret patterns
        redacted = re.sub(r"([?&]api[_-]?key=)[^&]+", r"\1***", endpoint, flags=re.IGNORECASE)
        redacted = re.sub(r"([?&]token=)[^&]+", r"\1***", redacted, flags=re.IGNORECASE)
        redacted = re.sub(r"([?&]key=)[^&]+", r"\1***", redacted, flags=re.IGNORECASE)
        return redacted
