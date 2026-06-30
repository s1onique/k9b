#!/usr/bin/env python3
"""Verdict dataclasses for K8s-native OTel lab phases.

This module defines the split verdict types that distinguish:
- IncidentDiscoveryVerdict: P3c - incident discovery validation (scope check only)
- RootCauseEvidenceVerdict: P4c - root-cause evidence validation (scheduling markers)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# =============================================================================
# Scheduling Root-Cause Markers
# =============================================================================

# Markers that indicate scheduling-specific root cause evidence.
# These must be present in the diagnosis for P4c to pass.
SCHEDULING_ROOT_CAUSE_MARKERS: tuple[str, ...] = (
    "FailedScheduling",
    "Unschedulable",
    "didn't match Pod's node affinity/selector",
    "nodeSelector",
    "k9b.dev/otel-lab-node=missing",
)


# =============================================================================
# P3c: Incident Discovery Verdict
# =============================================================================

@dataclass(frozen=True)
class IncidentDiscoveryVerdict:
    """Verdict for P3c K8s incident discovery phase.
    
    P3c validates that k9b discovered an incident scoped to the injected
    workload. It does NOT validate root-cause evidence - that is P4c's job.
    
    Attributes:
        success: Whether discovery validation passed
        incident_id: Discovered incident ID, if any
        candidate_class: Candidate class of the discovered incident
        namespace: Namespace the incident is scoped to
        shipping_scoped: Whether the incident references the shipping workload
        reason: Failure reason if success is False
    """
    
    success: bool
    incident_id: str | None = None
    candidate_class: str | None = None
    namespace: str | None = None
    shipping_scoped: bool = False
    reason: str | None = None
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IncidentDiscoveryVerdict:
        """Create verdict from detection evidence dict.
        
        P3c discovery success depends ONLY on scope validations:
        - namespace matches
        - shipping reference found
        - candidate class is valid
        
        Note: validation_success is P4c's concern, not P3c's.
        """
        success = (
            data.get("discovery_success", False) and
            data.get("namespace_matches", False) and
            data.get("shipping_reference_found", False) and
            bool(data.get("candidate_class"))
        )
        return cls(
            success=success,
            incident_id=data.get("incident_id"),
            candidate_class=data.get("candidate_class"),
            namespace=data.get("target_namespace"),
            shipping_scoped=data.get("shipping_reference_found", False),
            reason=data.get("failure_reason"),
        )
    
    def to_dict(self) -> dict[str, Any]:
        """Convert verdict to dict for JSON serialization."""
        return {
            "success": self.success,
            "incident_id": self.incident_id,
            "candidate_class": self.candidate_class,
            "namespace": self.namespace,
            "shipping_scoped": self.shipping_scoped,
            "reason": self.reason,
            "phase": "p3c-k8s-discovery",
        }


# =============================================================================
# P4c: Root-Cause Evidence Verdict
# =============================================================================

@dataclass(frozen=True)
class RootCauseEvidenceVerdict:
    """Verdict for P4c root-cause evidence validation.
    
    P4c validates that the diagnosis evidence contains scheduling-specific
    root-cause markers. This is separate from P3c's discovery validation.
    
    Attributes:
        success: Whether root-cause evidence validation passed
        reason: Failure reason if success is False
        matched_evidence: List of scheduling markers found in evidence
        root_cause_summary: The diagnosis's root-cause summary text
    """
    
    success: bool
    reason: str | None = None
    matched_evidence: tuple[str, ...] = field(default_factory=tuple)
    root_cause_summary: str = ""
    
    @classmethod
    def from_diagnosis_evidence(cls, evidence: dict[str, Any]) -> RootCauseEvidenceVerdict:
        """Create verdict from diagnosis evidence dict.
        
        Args:
            evidence: Diagnosis evidence containing root_cause_summary and related fields
            
        Returns:
            RootCauseEvidenceVerdict with matched scheduling markers
        """
        matched = cls._find_scheduling_markers(evidence)
        
        if matched:
            return cls(
                success=True,
                matched_evidence=matched,
                root_cause_summary=evidence.get("root_cause_summary", ""),
            )
        
        return cls(
            success=False,
            reason="missing_scheduling_root_cause_evidence",
            matched_evidence=matched,
            root_cause_summary=evidence.get("root_cause_summary", ""),
        )
    
    @staticmethod
    def _find_scheduling_markers(evidence: dict[str, Any]) -> tuple[str, ...]:
        """Find scheduling root-cause markers in evidence.
        
        Args:
            evidence: Diagnosis evidence dict
            
        Returns:
            Tuple of marker strings that were found
        """
        markers = SCHEDULING_ROOT_CAUSE_MARKERS
        matched: list[str] = []
        
        # Check root_cause_summary
        summary = evidence.get("root_cause_summary", "")
        summary_lower = summary.lower()
        
        for marker in markers:
            if marker.lower() in summary_lower:
                if marker not in matched:
                    matched.append(marker)
        
        # Also check evidence/signals for raw evidence matching
        signals = evidence.get("signals", []) or evidence.get("evidence", [])
        for signal in signals:
            signal_str = str(signal).lower()
            for marker in markers:
                if marker.lower() in signal_str and marker not in matched:
                    matched.append(marker)
        
        return tuple(matched)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert verdict to dict for JSON serialization."""
        return {
            "success": self.success,
            "reason": self.reason,
            "matched_evidence": list(self.matched_evidence),
            "root_cause_summary": self.root_cause_summary,
            "phase": "p4c-root-cause-validation",
        }


# =============================================================================
# Validation Helpers
# =============================================================================

def validate_unschedulable_shipping_discovery(
    incident: dict[str, Any],
    namespace: str = "otel-demo",
) -> IncidentDiscoveryVerdict:
    """Validate incident discovery for unschedulable-shipping scenario.
    
    This validates ONLY the discovery phase (P3c), NOT root-cause evidence.
    
    Args:
        incident: Incident dict from k9b discovery
        namespace: Expected namespace (default: otel-demo)
        
    Returns:
        IncidentDiscoveryVerdict with discovery validation result
    """
    from scripts.k9b_otel_demo_lab_k8s_detection_constants import ACCEPTED_CANDIDATE_CLASSES
    from scripts.k9b_otel_demo_lab_k8s_detection_match import (
        _validate_namespace,
        _validate_shipping_reference,
    )
    
    # Check namespace
    namespace_matches = _validate_namespace(incident, namespace)
    if not namespace_matches:
        return IncidentDiscoveryVerdict(
            success=False,
            incident_id=incident.get("id") or incident.get("incident_id"),
            namespace=namespace,
            reason="namespace_mismatch",
        )
    
    # Check shipping scope
    shipping_scoped = _validate_shipping_reference(incident)
    if not shipping_scoped:
        return IncidentDiscoveryVerdict(
            success=False,
            incident_id=incident.get("id") or incident.get("incident_id"),
            namespace=namespace,
            shipping_scoped=False,
            reason="no_shipping_reference",
        )
    
    # Check candidate class
    candidate_class = incident.get("candidate_class") or incident.get("class", "")
    if candidate_class not in ACCEPTED_CANDIDATE_CLASSES:
        return IncidentDiscoveryVerdict(
            success=False,
            incident_id=incident.get("id") or incident.get("incident_id"),
            candidate_class=candidate_class,
            namespace=namespace,
            shipping_scoped=True,
            reason=f"candidate_class_rejected:{candidate_class}",
        )
    
    # Discovery validation passed
    return IncidentDiscoveryVerdict(
        success=True,
        incident_id=incident.get("id") or incident.get("incident_id"),
        candidate_class=candidate_class,
        namespace=namespace,
        shipping_scoped=True,
    )


def validate_unschedulable_shipping_root_cause(
    payload: dict[str, Any],
) -> RootCauseEvidenceVerdict:
    """Validate root-cause evidence for unschedulable-shipping scenario.
    
    This validates ONLY root-cause evidence (P4c), NOT discovery.
    
    Args:
        payload: Diagnosis evidence or review packet dict
        
    Returns:
        RootCauseEvidenceVerdict with root-cause validation result
    """
    verdict = RootCauseEvidenceVerdict.from_diagnosis_evidence(payload)
    return verdict
