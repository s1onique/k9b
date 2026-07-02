"""Provider preflight models for k9b live labs.

This module provides the result types and serialization helpers for provider preflight.
It is split from provider_preflight.py to keep file sizes under LLM-friendly limits.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderPreflightResult:
    """Result of provider preflight check."""

    passed: bool = False
    failure_class: str | None = None
    message: str = ""
    provider_enabled: bool = False
    provider_configured: bool = False
    provider_invocation_attempted: bool = False
    provider_name: str = ""
    provider_status: str = ""
    provider_phase: str = ""
    diagnosis_provider_enabled: bool = False
    requires_diagnosis: bool = False
    duration_seconds: float = 0.0
    check_method: str = ""  # "service" or "exec-local"
    parsed_status: Any = field(default=None)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "passed": self.passed,
            "failure_class": self.failure_class,
            "message": self.message,
            "provider_enabled": self.provider_enabled,
            "provider_configured": self.provider_configured,
            "provider_invocation_attempted": self.provider_invocation_attempted,
            "provider_name": self.provider_name,
            "provider_status": self.provider_status,
            "provider_phase": self.provider_phase,
            "diagnosis_provider_enabled": self.diagnosis_provider_enabled,
            "requires_diagnosis": self.requires_diagnosis,
            "duration_seconds": self.duration_seconds,
            "check_method": self.check_method,
        }
