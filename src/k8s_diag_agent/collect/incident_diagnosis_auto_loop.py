"""Opt-in automatic read-only diagnosis loop evidence collector.

This module provides a bounded automatic collector that:
- Scans eligible open incidents
- Runs one deterministic read-only diagnosis pass per incident
- Writes a deterministic review packet for operator/ChatGPT review
- Preserves read-only safety: no mutation, no remediation, no kubectl

Design constraints:
- Opt-in via K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED=false by default
- Conservative eligibility: only active incidents with suggested checks
- Hard budget bounds: max 1 pass per incident, max 5 checks per pass
- No LLM calls, no Kubernetes calls, no subprocess/shell/kubectl
- No remediation, no mutation, no execution
- Idempotent: calling twice for same incident does not exceed budget

This module does NOT:
- Execute real Kubernetes collectors
- Call kubectl/helm/subprocess/shell
- Perform remediation or mutation
- Run unbounded loops
- Call external LLM providers
- Write action-control fields to artifacts

Implementation note:
    Functions have been moved to incident_diagnosis_auto_loop_evidence_collection.py
    (a leaf module) to avoid circular imports. This module re-exports for backwards
    compatibility.
"""

from __future__ import annotations

from .incident_diagnosis_auto_loop_config import (
    AutomaticDiagnosisLoopConfig,
    EligibilityResult,
    is_automatic_diagnosis_loop_enabled,
)

# Re-export everything from the leaf module for backwards compatibility
from .incident_diagnosis_auto_loop_evidence_collection import (
    collect_automatic_diagnosis_evidence,
    run_automatic_diagnosis_loop_evidence_collection,
)
from .incident_diagnosis_auto_loop_models import (
    AutoLoopCollectorResult,
    AutoLoopIncidentResult,
)

__all__ = [
    "is_automatic_diagnosis_loop_enabled",
    "AutomaticDiagnosisLoopConfig",
    "EligibilityResult",
    "AutoLoopIncidentResult",
    "AutoLoopCollectorResult",
    "run_automatic_diagnosis_loop_evidence_collection",
    "collect_automatic_diagnosis_evidence",
]
