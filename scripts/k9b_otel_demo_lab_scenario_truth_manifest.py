#!/usr/bin/env python3
"""Scenario truth manifest for OTel demo lab K8s-native phases."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

# Typed literals for grade and root-cause kinds
DiagnosisGradeValue = Literal[
    "no_signal",
    "symptom_level",
    "scheduling_level",
    "causal_level",
    "exact_root_cause",
]

RootCauseKindValue = Literal[
    "node_selector_no_matching_node",
    "pod_crash_loop",
    "deployment_unavailable",
    "resource_quota_exceeded",
    "persistent_volume_pending",
]

SCENARIO_UNSCHEDULABLE_SHIPPING = "unschedulable-shipping"


# Literal root cause kinds
class RootCauseKind:
    NODE_SELECTOR_NO_MATCHING_NODE: RootCauseKindValue = "node_selector_no_matching_node"
    POD_CRASH_LOOP: RootCauseKindValue = "pod_crash_loop"
    DEPLOYMENT_UNAVAILABLE: RootCauseKindValue = "deployment_unavailable"
    RESOURCE_QUOTA_EXCEEDED: RootCauseKindValue = "resource_quota_exceeded"
    PERSISTENT_VOLUME_PENDING: RootCauseKindValue = "persistent_volume_pending"


# P2b (Injection): Ground truth exists in cluster
P2B_EXPECTED_MARKERS: tuple[str, ...] = (
    "shipping", "FailedScheduling", "Unschedulable", "nodeSelector",
    "k9b.dev/otel-lab-node=missing", "didn't match Pod's node affinity/selector",
)

# P3c (Discovery): Incident links causal evidence
P3C_EXPECTED_MARKERS: tuple[str, ...] = (
    "shipping", "FailedScheduling", "Unschedulable", "nodeSelector",
)

# P4c-input (Case file): Includes scheduling evidence
P4C_INPUT_EXPECTED_MARKERS: tuple[str, ...] = (
    "shipping", "FailedScheduling", "Unschedulable", "nodeSelector",
    "k9b.dev/otel-lab-node", "missing",
)

# P4c-output (Review packet): Names causal evidence
# NOTE: regex patterns use re.search(), literal markers use substring match
P4C_OUTPUT_REGEX_PATTERNS: tuple[str, ...] = (
    "no.*matching.*node",  # regex pattern
)
P4C_OUTPUT_LITERAL_MARKERS: tuple[str, ...] = (
    "shipping", "nodeSelector", "k9b.dev/otel-lab-node=missing", "FailedScheduling",
)

# P4c-final (Normalized outcome): Matches exact root cause
P4C_FINAL_EXPECTED_MARKERS: tuple[str, ...] = (
    "shipping", "nodeSelector", "k9b.dev/otel-lab-node", "missing",
)


# Diagnosis grade literals
class DiagnosisGrade:
    NO_SIGNAL: DiagnosisGradeValue = "no_signal"
    SYMPTOM_LEVEL: DiagnosisGradeValue = "symptom_level"
    SCHEDULING_LEVEL: DiagnosisGradeValue = "scheduling_level"
    CAUSAL_LEVEL: DiagnosisGradeValue = "causal_level"
    EXACT_ROOT_CAUSE: DiagnosisGradeValue = "exact_root_cause"
    GRADE_ORDER: tuple[DiagnosisGradeValue, ...] = (
        NO_SIGNAL, SYMPTOM_LEVEL, SCHEDULING_LEVEL, CAUSAL_LEVEL, EXACT_ROOT_CAUSE,
    )


# Evidence pipeline failure mode constants
class EvidencePipelineFailure:
    P0B_PROVIDER_PREFLIGHT_FAILED = "provider_preflight_failed_but_diagnosis_attempted"
    BACKEND_INCIDENT_MISSING_SCHEDULING = "backend_incident_missing_scheduling_evidence"
    CASE_FILE_MISSING_ROOT_CAUSE = "case_file_missing_root_cause_evidence"
    DIAGNOSIS_INPUT_STARVED = "diagnosis_input_starved"
    DIAGNOSIS_OUTPUT_IGNORED_ROOT_CAUSE = "diagnosis_output_ignored_available_root_cause"
    DUPLICATE_TERMINAL_PASSES = "duplicate_terminal_passes_without_incremental_evidence"
    TERMINAL_NO_CHECKS_NO_CLAIM = "terminal_no_checks_without_causal_claim"
    P0B_HEALTH_OUTPUT_CONTAMINATED = "provider_health_output_contaminated"
    VALIDATION_STEP_MISLEADING = "validation_step_misleading"
    EVIDENCE_PIPELINE_P2B_MISSING = "p2b_evidence_missing"
    EVIDENCE_PIPELINE_P3C_MISSING = "p3c_evidence_missing"
    EVIDENCE_PIPELINE_P4C_MISSING = "p4c_evidence_missing"


@dataclass(frozen=True)
class EvidenceMarkers:
    """Separated marker types for proper matching."""
    literals: tuple[str, ...] = ()
    regexes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScenarioTruthManifest:
    scenario: str
    workload: str
    expected_root_cause_kind: RootCauseKindValue
    expected_markers: tuple[str, ...]
    p2b_markers: tuple[str, ...] = ()
    p3c_markers: tuple[str, ...] = ()
    p4c_input_markers: EvidenceMarkers = field(default_factory=EvidenceMarkers)
    p4c_output_markers: EvidenceMarkers = field(default_factory=EvidenceMarkers)
    p4c_final_markers: EvidenceMarkers = field(default_factory=EvidenceMarkers)
    description: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario, "workload": self.workload,
            "expected_root_cause_kind": self.expected_root_cause_kind,
            "expected_markers": list(self.expected_markers),
            "description": self.description,
        }


SCENARIO_MANIFESTS: dict[str, ScenarioTruthManifest] = {
    SCENARIO_UNSCHEDULABLE_SHIPPING: ScenarioTruthManifest(
        scenario=SCENARIO_UNSCHEDULABLE_SHIPPING,
        workload="deployment/shipping",
        expected_root_cause_kind=RootCauseKind.NODE_SELECTOR_NO_MATCHING_NODE,
        expected_markers=P2B_EXPECTED_MARKERS,
        p2b_markers=P2B_EXPECTED_MARKERS,
        p3c_markers=P3C_EXPECTED_MARKERS,
        p4c_input_markers=EvidenceMarkers(literals=P4C_INPUT_EXPECTED_MARKERS),
        p4c_output_markers=EvidenceMarkers(
            literals=P4C_OUTPUT_LITERAL_MARKERS,
            regexes=P4C_OUTPUT_REGEX_PATTERNS,
        ),
        p4c_final_markers=EvidenceMarkers(literals=P4C_FINAL_EXPECTED_MARKERS),
        description="Shipping deployment patched with impossible nodeSelector (k9b.dev/otel-lab-node=missing).",
    ),
}


def get_scenario_manifest(scenario: str) -> ScenarioTruthManifest | None:
    return SCENARIO_MANIFESTS.get(scenario)


def check_markers_present(text: str, markers: EvidenceMarkers) -> tuple[list[str], list[str]]:
    """Check which markers are present in text, handling both literals and regexes."""
    text_lower = text.lower()
    found, missing = [], []
    
    # Check literals
    for marker in markers.literals:
        if marker.lower() in text_lower:
            found.append(marker)
        else:
            missing.append(marker)
    
    # Check regexes
    for pattern in markers.regexes:
        if re.search(pattern, text, flags=re.IGNORECASE):
            found.append(pattern)
        else:
            missing.append(pattern)
    
    return found, missing


def validate_evidence_pipeline(
    scenario: str,
    p2b_evidence: dict[str, Any] | None = None,
    p3c_evidence: dict[str, Any] | None = None,
    p4c_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate evidence pipeline for a scenario."""
    manifest = get_scenario_manifest(scenario)
    if manifest is None:
        return {"scenario": scenario, "error": f"Unknown scenario: {scenario}"}
    
    result: dict[str, Any] = {
        "scenario": scenario, "manifest": manifest.to_dict(),
        "p2b_valid": False, "p3c_valid": False, "p4c_valid": False,
        "p2b_missing": [], "p3c_missing": [], "p4c_missing": [], "failures": [],
    }
    
    if p2b_evidence:
        _, missing = _check_literal_markers(_evidence_to_text(p2b_evidence), manifest.p2b_markers)
        result["p2b_missing"], result["p2b_valid"] = missing, len(missing) == 0
    else:
        result["failures"].append(EvidencePipelineFailure.EVIDENCE_PIPELINE_P2B_MISSING)
    
    if p3c_evidence:
        _, missing = _check_literal_markers(_evidence_to_text(p3c_evidence), manifest.p3c_markers)
        result["p3c_missing"], result["p3c_valid"] = missing, len(missing) == 0
        if not result["p3c_valid"]:
            result["failures"].append(
                f"{EvidencePipelineFailure.BACKEND_INCIDENT_MISSING_SCHEDULING}: {missing}"
            )
    else:
        result["failures"].append(EvidencePipelineFailure.EVIDENCE_PIPELINE_P3C_MISSING)
    
    if p4c_evidence:
        _, missing = _check_output_markers(_evidence_to_text(p4c_evidence), manifest.p4c_final_markers)
        result["p4c_missing"], result["p4c_valid"] = missing, len(missing) == 0
        if not result["p4c_valid"]:
            result["failures"].append(
                f"{EvidencePipelineFailure.DIAGNOSIS_OUTPUT_IGNORED_ROOT_CAUSE}: {missing}"
            )
    else:
        result["failures"].append(EvidencePipelineFailure.EVIDENCE_PIPELINE_P4C_MISSING)
    
    return result


def _check_literal_markers(text: str, markers: tuple[str, ...]) -> tuple[list[str], list[str]]:
    """Check literal markers in text."""
    text_lower = text.lower()
    found: list[str] = []
    missing: list[str] = []
    for marker in markers:
        if marker.lower() in text_lower:
            found.append(marker)
        else:
            missing.append(marker)
    return found, missing


def _check_output_markers(text: str, markers: EvidenceMarkers) -> tuple[list[str], list[str]]:
    """Check EvidenceMarkers in text (literals + regexes)."""
    return check_markers_present(text, markers)


def _evidence_to_text(evidence: dict[str, Any]) -> str:
    parts: list[str] = []
    if rcs := evidence.get("root_cause_summary"):
        parts.append(str(rcs))
    if summary := evidence.get("summary"):
        parts.append(str(summary))
    parts.extend(str(s) for s in evidence.get("signals", []))
    parts.extend(str(e) for e in evidence.get("evidence", []))
    if verdict := evidence.get("p4c_verdict"):
        if isinstance(verdict, dict):
            parts.extend(str(m) for m in verdict.get("matched_evidence", []))
    parts.extend(str(evidence.get(k, "")) for k in ["candidate_class", "class", "failure_reason", "message"] if evidence.get(k))
    return " ".join(parts)


def evaluate_diagnosis_grade(
    evidence: dict[str, Any],
    manifest: ScenarioTruthManifest,
) -> DiagnosisGradeValue:
    """Evaluate the diagnosis grade based on evidence."""
    text_lower = _evidence_to_text(evidence).lower()
    
    if not evidence.get("incident_id"):
        return DiagnosisGrade.NO_SIGNAL
    
    has_shipping = "shipping" in text_lower
    if not has_shipping:
        return DiagnosisGrade.SYMPTOM_LEVEL
    
    has_deployment = "deployment" in text_lower and "unavailable" in text_lower
    if has_deployment and not _has_scheduling_indicators(text_lower):
        return DiagnosisGrade.SYMPTOM_LEVEL
    
    has_scheduling = _has_scheduling_indicators(text_lower)
    if has_scheduling and not _has_node_selector_specific(text_lower):
        return DiagnosisGrade.SCHEDULING_LEVEL
    
    has_causal = _has_node_selector_specific(text_lower)
    if has_causal and not _has_exact_root_cause(text_lower):
        return DiagnosisGrade.CAUSAL_LEVEL
    
    if _has_exact_root_cause(text_lower):
        return DiagnosisGrade.EXACT_ROOT_CAUSE
    
    return DiagnosisGrade.CAUSAL_LEVEL if has_causal else (
        DiagnosisGrade.SCHEDULING_LEVEL if has_scheduling else DiagnosisGrade.SYMPTOM_LEVEL
    )


def _has_scheduling_indicators(text_lower: str) -> bool:
    return any(ind in text_lower for ind in [
        "failedscheduling", "unschedulable", "node selector", "nodeselector", "cannot schedule",
    ])


def _has_node_selector_specific(text_lower: str) -> bool:
    """Check for nodeSelector-specific evidence: shipping + nodeSelector + selector key."""
    return (
        "shipping" in text_lower
        and ("nodeselector" in text_lower or "node selector" in text_lower)
        and "k9b.dev/otel-lab-node" in text_lower
    )


def _has_exact_root_cause(text_lower: str) -> bool:
    """Check for exact root cause: nodeSelector + key + value (missing).

    Requires either the full assignment literal k9b.dev/otel-lab-node=missing
    or the key with "missing" as a standalone word (e.g., "is missing").
    Does NOT match "missing evidence" or "missing data" (missing is a descriptor).
    """
    has_shipping = "shipping" in text_lower
    has_selector = "nodeselector" in text_lower or "node selector" in text_lower
    has_key = "k9b.dev/otel-lab-node" in text_lower
    
    # Check for the assignment literal first
    has_assignment = "k9b.dev/otel-lab-node=missing" in text_lower
    
    # Check for standalone "missing" after the key (e.g., "key is missing", "key: missing")
    # Must NOT be followed by another word (which would indicate "missing evidence")
    key_pos = text_lower.find("k9b.dev/otel-lab-node")
    has_missing_after_key = False
    if key_pos != -1:
        # Search for "missing" within window after key
        match = re.search(r"\bmissing\b", text_lower[key_pos:key_pos + 100])
        if match:
            missing_end = key_pos + match.end()
            after_missing = text_lower[missing_end:]
            # Check valid terminators: end of string
            if not after_missing:
                has_missing_after_key = True
            # Common punctuation as first character
            elif after_missing[0] in ",.-;:)]}":
                has_missing_after_key = True
            # Space followed by non-alphanumeric (e.g., "missing - no")
            elif after_missing.startswith(" ") and len(after_missing) > 1:
                has_missing_after_key = not after_missing[1].isalnum()
    
    has_exact_value = has_assignment or has_missing_after_key
    return has_shipping and has_selector and has_key and has_exact_value


__all__ = [
    "DiagnosisGradeValue", "RootCauseKindValue",
    "SCENARIO_UNSCHEDULABLE_SHIPPING", "RootCauseKind", "DiagnosisGrade",
    "EvidencePipelineFailure",
    "P2B_EXPECTED_MARKERS", "P3C_EXPECTED_MARKERS",
    "P4C_INPUT_EXPECTED_MARKERS", "P4C_OUTPUT_REGEX_PATTERNS",
    "P4C_OUTPUT_LITERAL_MARKERS", "P4C_FINAL_EXPECTED_MARKERS",
    "EvidenceMarkers", "ScenarioTruthManifest", "SCENARIO_MANIFESTS",
    "get_scenario_manifest", "check_markers_present", "validate_evidence_pipeline",
    "evaluate_diagnosis_grade",
]
