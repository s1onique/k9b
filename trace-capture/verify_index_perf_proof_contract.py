"""Contract types for index performance proof verification.

This module defines the data structures used for verifying content-index
performance proof artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# =============================================================================
# Schema Version
# =============================================================================

SCHEMA_VERSION = "k9b.index_perf_proof.v1"

# =============================================================================
# Indexed Endpoint Routes
# =============================================================================

INDEXED_ENDPOINT_ROUTES = {
    "GET /api/incidents",
    "GET /api/incidents/{incident_id}",
}

# =============================================================================
# Result Types
# =============================================================================


@dataclass
class LatencyDelta:
    """Latency delta for an endpoint."""

    disabled_p50_ms: float = 0.0
    enabled_p50_ms: float = 0.0
    disabled_p90_ms: float = 0.0
    enabled_p90_ms: float = 0.0
    disabled_p99_ms: float = 0.0
    enabled_p99_ms: float = 0.0
    p50_delta_ms: float = 0.0
    p50_improvement_percent: float = 0.0
    p90_delta_ms: float = 0.0
    p90_improvement_percent: float = 0.0
    p99_delta_ms: float = 0.0
    p99_improvement_percent: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "disabled_p50_ms": round(self.disabled_p50_ms, 2),
            "enabled_p50_ms": round(self.enabled_p50_ms, 2),
            "disabled_p90_ms": round(self.disabled_p90_ms, 2),
            "enabled_p90_ms": round(self.enabled_p90_ms, 2),
            "disabled_p99_ms": round(self.disabled_p99_ms, 2),
            "enabled_p99_ms": round(self.enabled_p99_ms, 2),
            "p50_delta_ms": round(self.p50_delta_ms, 2),
            "p50_improvement_percent": round(self.p50_improvement_percent, 2),
            "p90_delta_ms": round(self.p90_delta_ms, 2),
            "p90_improvement_percent": round(self.p90_improvement_percent, 2),
            "p99_delta_ms": round(self.p99_delta_ms, 2),
            "p99_improvement_percent": round(self.p99_improvement_percent, 2),
        }


@dataclass
class VerificationResult:
    """Result of verification checks."""

    index_db_valid: bool = False
    disabled_run_success: bool = False
    enabled_run_success: bool = False
    enabled_emits_content_index_spans: bool = False
    fallback_spans_for_indexed_endpoints: bool = True  # True = no fallback (good)
    api_shape_compatible: bool = False
    privacy_check_passed: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "index_db_valid": self.index_db_valid,
            "disabled_run_success": self.disabled_run_success,
            "enabled_run_success": self.enabled_run_success,
            "enabled_emits_content_index_spans": self.enabled_emits_content_index_spans,
            "fallback_spans_for_indexed_endpoints": self.fallback_spans_for_indexed_endpoints,
            "api_shape_compatible": self.api_shape_compatible,
            "privacy_check_passed": self.privacy_check_passed,
            "errors": self.errors,
            "warnings": self.warnings,
        }


@dataclass
class PerfProofSummary:
    """Summary of the index performance proof."""

    schema_version: str = SCHEMA_VERSION
    index_enabled_default: bool = False
    index_db_valid: bool = False
    endpoints_compared: list[str] = field(default_factory=list)
    disabled: dict[str, Any] = field(default_factory=dict)
    enabled: dict[str, Any] = field(default_factory=dict)
    latency_delta: dict[str, Any] = field(default_factory=dict)
    api_shape_compatible: bool = False
    privacy_check_passed: bool = False
    verification: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "schema_version": self.schema_version,
            "index_enabled_default": self.index_enabled_default,
            "index_db_valid": self.index_db_valid,
            "endpoints_compared": self.endpoints_compared,
            "disabled": self.disabled,
            "enabled": self.enabled,
            "latency_delta": self.latency_delta,
            "api_shape_compatible": self.api_shape_compatible,
            "privacy_check_passed": self.privacy_check_passed,
            "verification": self.verification,
        }
