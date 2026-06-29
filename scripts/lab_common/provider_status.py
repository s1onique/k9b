"""Provider status parser for k9b live-lab gates.

This module provides the canonical parser for /api/health/details provider status.
It supports both:
- Legacy flattened format: provider_enabled, provider_configured, provider_status
- New dependencies[] format: dependencies[].diagnosis_provider.status, phase, reason_code

Both CNPG and OTel labs should use parse_provider_status_from_health_details()
instead of implementing their own parsing logic.

The contract:
- If top-level flattened fields are present, they take precedence.
- If top-level fields are absent/null, derive from dependencies[].
- Healthy status values: "available", "configured", "healthy"
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Healthy provider status values that indicate the provider is enabled/configured
_HEALTHY_STATUSES = frozenset({"available", "configured", "healthy"})


@dataclass
class ProviderStatus:
    """Parsed provider status from /api/health/details.
    
    Attributes:
        provider_enabled: True if provider is enabled (can be derived from dependency status).
        provider_configured: True if provider is configured (can be derived from dependency status).
        provider_invocation_attempted: True if provider invocation was attempted.
        provider_name: Name of the provider (e.g., "openai").
        provider_status: Raw status string from API (e.g., "available", "unavailable").
        provider_phase: Phase of provider initialization (e.g., "models_list_ok", "not_initialized").
        diagnosis_provider_enabled: Alias for provider_enabled (for backward compatibility).
        reason_code: Provider reason code (e.g., "provider_available", "provider_connection_failed").
        failure_class: Failure class if provider is unavailable.
        healthy: Overall health status from API.
    """

    provider_enabled: bool = False
    provider_configured: bool = False
    provider_invocation_attempted: bool = False
    provider_name: str = ""
    provider_status: str = ""
    provider_phase: str = ""
    diagnosis_provider_enabled: bool = False
    reason_code: str = ""
    failure_class: str = ""
    healthy: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "provider_enabled": self.provider_enabled,
            "provider_configured": self.provider_configured,
            "provider_invocation_attempted": self.provider_invocation_attempted,
            "provider_name": self.provider_name,
            "provider_status": self.provider_status,
            "provider_phase": self.provider_phase,
            "diagnosis_provider_enabled": self.diagnosis_provider_enabled,
            "reason_code": self.reason_code,
            "failure_class": self.failure_class,
            "healthy": self.healthy,
        }


def _find_dependency_by_name(health_details: dict, name: str) -> dict:
    """Find a dependency by name in health_details.
    
    Supports both legacy flattened format and new dependencies[] format.
    
    Args:
        health_details: Parsed JSON from /api/health/details
        name: Dependency name to find (e.g., "diagnosis_provider")
    
    Returns:
        Matching dependency dict, or empty dict if not found.
    """
    dependencies = health_details.get("dependencies")
    if not isinstance(dependencies, list):
        return {}
    for dep in dependencies:
        if isinstance(dep, dict) and dep.get("dependency_name") == name:
            return dep
    return {}


def parse_provider_status_from_health_details(health_details: dict) -> ProviderStatus:
    """Parse provider status from /api/health/details response.
    
    Supports both:
    - Legacy flattened format: provider_enabled, provider_configured, provider_status
    - New dependencies[] format: dependencies[].diagnosis_provider
    
    When both formats are present, flattened fields take precedence.
    
    Args:
        health_details: Parsed JSON from /api/health/details endpoint.
        
    Returns:
        ProviderStatus with all provider fields populated.
    """
    # Find diagnosis_provider dependency if present
    provider_dep = _find_dependency_by_name(health_details, "diagnosis_provider")
    
    # Parse flattened fields first (they take precedence)
    provider_enabled = health_details.get("provider_enabled")
    provider_configured = health_details.get("provider_configured")
    provider_status = health_details.get("provider_status")
    provider_phase = health_details.get("phase")
    
    # Derive from dependency if flattened fields are absent
    if provider_enabled is None:
        provider_enabled = provider_dep.get("status") in _HEALTHY_STATUSES
    
    if provider_configured is None:
        provider_configured = provider_dep.get("status") in _HEALTHY_STATUSES
    
    if not provider_status or provider_status == "unknown":
        provider_status = provider_dep.get("status", "unknown")
    
    if not provider_phase or provider_phase == "unknown":
        provider_phase = provider_dep.get("phase", "unknown")
    
    return ProviderStatus(
        provider_enabled=bool(provider_enabled),
        provider_configured=bool(provider_configured),
        provider_invocation_attempted=bool(health_details.get("provider_invocation_attempted", False)),
        provider_name=health_details.get("provider_name", ""),
        provider_status=provider_status,
        provider_phase=provider_phase,
        diagnosis_provider_enabled=bool(provider_enabled),
        reason_code=provider_dep.get("reason_code", ""),
        failure_class=provider_dep.get("failure_class", ""),
        healthy=bool(health_details.get("healthy", False)),
    )


def is_provider_healthy(provider_status: ProviderStatus) -> bool:
    """Check if provider is in a healthy/available state.
    
    Args:
        provider_status: Parsed provider status.
        
    Returns:
        True if provider is enabled, configured, and in a healthy status.
    """
    return (
        provider_status.provider_enabled
        and provider_status.provider_configured
        and provider_status.provider_status in _HEALTHY_STATUSES
    )
