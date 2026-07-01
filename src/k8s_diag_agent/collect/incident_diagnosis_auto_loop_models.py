"""Result models for automatic diagnosis loop collector.

This module provides:
- AutoLoopIncidentResult for single incident processing
- AutoLoopCollectorResult for complete collector run
- _COLLECTOR_SAFETY_METADATA constant
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .incident_diagnosis_auto_loop_config import DiagnosisBudgetDiagnostic

__all__ = [
    "AutoLoopIncidentResult",
    "AutoLoopCollectorResult",
    "_COLLECTOR_SAFETY_METADATA",
]


# =============================================================================
# Safety Metadata
# =============================================================================

_COLLECTOR_SAFETY_METADATA: dict[str, Any] = {
    "read_only": True,
    "allowed_actions": [],
    "no_kubernetes_client": True,
    "no_shell": True,
    "no_subprocess": True,
    "no_kubectl": True,
    "no_mutation": True,
    "no_remediation": True,
    "automatic_evidence_collection_only": True,
    "no_llm_calls": True,
    "no_execution": True,
}


# =============================================================================
# Incident Result
# =============================================================================


@dataclass
class AutoLoopIncidentResult:
    """Result of processing a single incident in automatic loop."""

    incident_id: str
    eligible: bool
    eligibility_reason: str
    run_id: str | None = None
    decision: str | None = None
    checks_requested: int = 0
    checks_run: int = 0
    checks_skipped: int = 0
    checks_rejected: int = 0
    review_packet_written: bool = False
    review_packet_name: str | None = None
    read_only_check_artifact_written: bool = False
    loop_pass_artifact_written: bool = False
    error: str | None = None
    skipped: bool = False
    skip_reason: str | None = None
    budget_diagnostics: tuple[DiagnosisBudgetDiagnostic, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "incident_id": self.incident_id,
            "eligible": self.eligible,
            "eligibility_reason": self.eligibility_reason,
        }
        if self.run_id is not None:
            result["run_id"] = self.run_id
        if self.decision is not None:
            result["decision"] = self.decision
        result["checks_requested"] = self.checks_requested
        result["checks_run"] = self.checks_run
        result["checks_skipped"] = self.checks_skipped
        result["checks_rejected"] = self.checks_rejected
        result["review_packet_written"] = self.review_packet_written
        if self.review_packet_name is not None:
            result["review_packet_name"] = self.review_packet_name
        result["read_only_check_artifact_written"] = self.read_only_check_artifact_written
        result["loop_pass_artifact_written"] = self.loop_pass_artifact_written
        if self.error is not None:
            result["error"] = self.error
        if self.skipped:
            result["skipped"] = True
            if self.skip_reason is not None:
                result["skip_reason"] = self.skip_reason
        if self.budget_diagnostics:
            result["budget_diagnostics"] = [d.to_dict() for d in self.budget_diagnostics]
        return result


# =============================================================================
# Collector Result
# =============================================================================


@dataclass
class AutoLoopCollectorResult:
    """Result of a complete automatic diagnosis loop collector run."""

    run_id: str
    generated_at: str
    enabled: bool
    config: dict[str, Any]
    incidents_processed: int = 0
    incidents_eligible: int = 0
    incidents_ineligible: int = 0
    incidents_skipped: int = 0
    incidents_with_errors: int = 0
    total_checks_run: int = 0
    total_review_packets_written: int = 0
    incident_results: list[dict[str, Any]] = field(default_factory=list)
    safety_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "enabled": self.enabled,
            "config": self.config,
            "incidents_processed": self.incidents_processed,
            "incidents_eligible": self.incidents_eligible,
            "incidents_ineligible": self.incidents_ineligible,
            "incidents_skipped": self.incidents_skipped,
            "incidents_with_errors": self.incidents_with_errors,
            "total_checks_run": self.total_checks_run,
            "total_review_packets_written": self.total_review_packets_written,
            "incident_results": self.incident_results,
            "safety_metadata": self.safety_metadata,
        }
