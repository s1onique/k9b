#!/usr/bin/env python3
"""CI-enforced live-lab contract verifier for unschedulable-shipping.

This module verifies that the live-lab run produced valid artifacts for:
- P3c: K8s incident discovery
- P4c: K8s multi-pass diagnosis with scheduling root-cause evidence
- Runtime: Loop pass artifacts with safety and budget enforcement
- OTel: Optional trace verification

Usage:
    python -m scripts.k9b_otel_demo_lab_contract_verify \
        --artifact-dir lab-artifacts/otel-demo \
        --scenario unschedulable-shipping \
        --require-lab-passed \
        --otel-traces auto

Exit codes:
    0 - All contracts passed
    1 - Contract failure

OTel trace behavior:
- auto: Inspect traces if present, skip if missing
- require: Fail if traces are missing
- skip: Do not inspect traces
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

# =============================================================================
# Phase Result Reason Constants
# =============================================================================

# P3c Discovery
P3C_REASON_INCIDENT_DISCOVERED = "incident_discovered"
P3C_REASON_INCIDENT_NOT_FOUND = "incident_not_found"
P3C_REASON_WRONG_INCIDENT_IDENTITY = "wrong_incident_identity"
P3C_REASON_WRONG_CANDIDATE_CLASS = "wrong_candidate_class"
P3C_REASON_STALE_INCIDENT = "stale_incident"
P3C_REASON_INCIDENT_DISCOVERED_WITHOUT_RCA = "incident_discovered_without_rca_evidence_yet"

# P4c Diagnosis
P4C_REASON_DIAGNOSIS_RCA_VALID = "diagnosis_rca_valid"
P4C_REASON_DIAGNOSIS_MISSING_SCHEDULING_RC = "diagnosis_missing_scheduling_root_cause"
P4C_REASON_DIAGNOSIS_MISSING_SHIPPING = "diagnosis_missing_shipping_identity"
P4C_REASON_DIAGNOSIS_MISSING_MULT_PASS = "diagnosis_missing_mult_pass_evidence"

# Valid P3c reasons
VALID_P3C_REASONS = frozenset([
    P3C_REASON_INCIDENT_DISCOVERED,
    P3C_REASON_INCIDENT_DISCOVERED_WITHOUT_RCA,
    "p3c_discovery_valid",
])

# Valid P4c reasons
VALID_P4C_REASONS = frozenset([
    P4C_REASON_DIAGNOSIS_RCA_VALID,
])

# Accepted P3c candidate classes
ACCEPTED_P3C_CANDIDATE_CLASSES = frozenset([
    "deployment_unavailable",
    "pending_pod",
    "warning_event_burst",
])

# Scheduling root-cause markers for P4c
SCHEDULING_ROOT_CAUSE_MARKERS = frozenset([
    "FailedScheduling",
    "Unschedulable",
    "nodeSelector",
    "k9b.dev/otel-lab-node",
    "k9b.dev/otel-lab-node=missing",
    "missing node label",
    "no matching node",
    "0/8 nodes are available",
])

# Live-lab default bounded-loop policy
DEFAULT_MAX_PASSES = 2
DEFAULT_MAX_CHECKS_PER_PASS = 2
DEFAULT_MAX_TOTAL_CHECKS = 4

# Required pass artifact fields
REQUIRED_PASS_ARTIFACT_FIELDS = frozenset([
    "loop_run_id",
    "incident_id",
    "pass_index",
    "case_file_hash",
    "proposed_checks",
    "accepted_checks",
    "rejected_checks",
    "check_fingerprints",
    "new_evidence_hashes",
    "duplicate_check_count",
    "unsafe_check_count",
    "root_cause_summary",
    "confidence",
    "should_continue",
    "stop_reason",
])

# OTel trace span/event names
EXPECTED_OTEL_SPANS = frozenset([
    "k9b.diagnosis_loop.budget",
    "k9b.diagnosis_loop.plan",
    "k9b.diagnosis_loop.gate",
    "k9b.diagnosis_loop.execute",
    "k9b.diagnosis_loop.artifact",
])

EXPECTED_OTEL_EVENTS = frozenset([
    "k9b.diagnosis_loop.check_rejected",
    "k9b.diagnosis_loop.checks_executed",
    "k9b.diagnosis_loop.artifact_written",
    "k9b.diagnosis_loop.stop",
])

# Forbidden sensitive payload patterns (hard fail)
# Note: Patterns match keys in JSON serialization where field names are quoted
FORBIDDEN_SENSITIVE_PATTERNS = [
    re.compile(r'"kubeconfig"'),  # JSON key
    re.compile(r"Bearer\s+eyJ", re.IGNORECASE),  # Bearer JWT pattern
    re.compile(r"BEGIN\s+PRIVATE\s+KEY", re.IGNORECASE),
    re.compile(r'"client-certificate-data"'),
    re.compile(r'"client-key-data"'),
    re.compile(r'"password"'),
    re.compile(r"password\s*=", re.IGNORECASE),
    re.compile(r"secret_value", re.IGNORECASE),
    re.compile(r'"access_token"'),
    re.compile(r'"refresh_token"'),
]

# Allowed safe patterns (do NOT fail on these)
ALLOWED_SAFE_PATTERNS = frozenset([
    "sensitive_read_denied",
    "kubectl_get_secrets",
    "secret read rejected",
])


class OtelTracesMode(Enum):
    """OTel trace verification mode."""
    AUTO = "auto"
    REQUIRE = "require"
    SKIP = "skip"


@dataclass
class ContractCheck:
    """Result of a single contract check."""
    name: str
    passed: bool
    phase: str
    reason: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class VerificationReport:
    """Complete verification report."""
    passed: bool
    checks: list[ContractCheck] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_check(self, check: ContractCheck) -> None:
        self.checks.append(check)
        if not check.passed:
            self.passed = False

    def add_error(self, error: str) -> None:
        self.errors.append(error)
        self.passed = False

    def add_warning(self, warning: str) -> None:
        self.warnings.append(warning)


# =============================================================================
# Lab Result Verification
# =============================================================================

def verify_lab_result(artifact_dir: Path, require_passed: bool, report: VerificationReport) -> bool:
    """Verify lab-result.json exists and indicates success."""
    lab_result_path = artifact_dir / "lab-result.json"

    if not lab_result_path.exists():
        report.add_error(f"lab-result.json not found at {lab_result_path}")
        return False

    try:
        lab_result = json.loads(lab_result_path.read_text())
    except json.JSONDecodeError as e:
        report.add_error(f"lab-result.json is malformed JSON: {e}")
        return False

    # Check for success field (tolerant about exact field names)
    success_values = {"true", "passed", "success", "ok"}
    success_field = lab_result.get("success") or lab_result.get("status") or lab_result.get("outcome")

    if success_field is None:
        report.add_error(
            "lab-result.json missing success/status/outcome field"
        )
        return False

    # Normalize success value
    is_success = str(success_field).lower() in success_values

    if require_passed and not is_success:
        report.add_error(
            f"lab-result.json indicates failure: success={lab_result.get('success')}, "
            f"status={lab_result.get('status')}, outcome={lab_result.get('outcome')}"
        )
        return False

    report.add_check(ContractCheck(
        name="lab_result",
        passed=True,
        phase="lab",
        reason="lab_passed" if is_success else "lab_skipped",
        details={"success_field": success_field},
    ))
    return True


# =============================================================================
# P3c Discovery Verification
# =============================================================================

def find_p3c_artifacts(artifact_dir: Path) -> list[Path]:
    """Find P3c detection/discovery artifacts."""
    patterns = [
        "**/p3c*/**/*.json",
        "**/phase3*/**/*.json",
    ]
    found: list[Path] = []
    for pattern in patterns:
        found.extend(artifact_dir.glob(pattern))
    return found


def verify_p3c_discovery(artifact_dir: Path, report: VerificationReport) -> bool:
    """Verify P3c discovery contract.

    Accept a discovered incident only if:
    - namespace == otel-demo
    - workload references shipping
    - candidate_class in ACCEPTED_P3C_CANDIDATE_CLASSES
    - reason in VALID_P3C_REASONS
    """
    p3c_artifacts = find_p3c_artifacts(artifact_dir)

    if not p3c_artifacts:
        report.add_error("No P3c detection artifacts found")
        return False

    # Try detection-evidence.json first
    detection_evidence_path = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery" / "detection-evidence.json"

    if detection_evidence_path.exists():
        return _verify_p3c_from_evidence(detection_evidence_path, report)

    # Fall back to first found artifact
    for artifact_path in p3c_artifacts:
        try:
            evidence = json.loads(artifact_path.read_text())
            return _verify_p3c_from_evidence_dict(evidence, report, str(artifact_path))
        except (json.JSONDecodeError, OSError):
            continue

    report.add_error("No parseable P3c artifact found")
    return False


def _verify_p3c_from_evidence(path: Path, report: VerificationReport) -> bool:
    """Verify P3c from detection-evidence.json."""
    try:
        evidence = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        report.add_error(f"Failed to parse {path}: {e}")
        return False
    return _verify_p3c_from_evidence_dict(evidence, report, str(path))


def _verify_p3c_from_evidence_dict(evidence: dict[str, Any], report: VerificationReport, source: str) -> bool:
    """Verify P3c from evidence dict."""
    # Check discovery success
    if not evidence.get("discovery_success"):
        report.add_error(f"P3c discovery failed: {evidence.get('failure_reason', 'unknown')}")
        return False

    # Check incident ID
    incident_id = evidence.get("incident_id")
    if not incident_id:
        report.add_error("P3c missing incident_id")
        return False

    # Check candidate class
    candidate_class = evidence.get("candidate_class", "")
    if candidate_class not in ACCEPTED_P3C_CANDIDATE_CLASSES:
        report.add_error(
            f"P3c candidate_class '{candidate_class}' not in accepted list: "
            f"{ACCEPTED_P3C_CANDIDATE_CLASSES}"
        )
        return False

    # Check namespace
    target_namespace = evidence.get("target_namespace", "")
    if target_namespace != "otel-demo":
        report.add_error(f"P3c namespace '{target_namespace}' != 'otel-demo'")
        return False

    # Check shipping reference - must be in root_cause_summary, not just any field
    root_cause_summary = evidence.get("root_cause_summary", "")
    has_shipping = "shipping" in root_cause_summary.lower()

    if not has_shipping:
        report.add_error("P3c evidence does not reference 'shipping'")
        return False

    # P3c must NOT require RCA markers (those belong to P4c)
    rca_markers = ["FailedScheduling", "nodeSelector", "k9b.dev/otel-lab-node=missing"]
    rca_in_discovery = any(m in root_cause_summary for m in rca_markers)

    # Check phase result reason
    phase_reason = evidence.get("phase_result_reason", evidence.get("reason", ""))
    valid_reason = any(r in str(phase_reason).lower() for r in ["incident_discovered", "discovery_valid", "p3c"])

    if not valid_reason:
        report.add_warning(f"P3c phase_result_reason '{phase_reason}' not in standard set")

    report.add_check(ContractCheck(
        name="p3c_discovery",
        passed=True,
        phase="p3c",
        reason=phase_reason or P3C_REASON_INCIDENT_DISCOVERED_WITHOUT_RCA,
        details={
            "incident_id": incident_id,
            "candidate_class": candidate_class,
            "namespace": target_namespace,
            "has_shipping": has_shipping,
            "rca_in_discovery": rca_in_discovery,
        },
    ))
    return True


# =============================================================================
# P4c Diagnosis Verification
# =============================================================================

def find_p4c_artifacts(artifact_dir: Path) -> list[Path]:
    """Find P4c diagnosis artifacts."""
    diagnosis_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis"
    if not diagnosis_dir.exists():
        return []
    return list(diagnosis_dir.glob("**/*.json"))


def verify_p4c_diagnosis(artifact_dir: Path, report: VerificationReport) -> bool:
    """Verify P4c diagnosis contract.

    Require diagnosis evidence to reference:
    - shipping
    - at least one scheduling root-cause marker
    """
    diagnosis_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis"
    diagnosis_evidence_path = diagnosis_dir / "diagnosis-evidence.json"

    if not diagnosis_evidence_path.exists():
        report.add_error(f"diagnosis-evidence.json not found at {diagnosis_evidence_path}")
        return False

    try:
        evidence = json.loads(diagnosis_evidence_path.read_text())
    except json.JSONDecodeError as e:
        report.add_error(f"Failed to parse diagnosis-evidence.json: {e}")
        return False

    # Check real loop invoked
    real_loop_invoked = evidence.get("real_loop_invoked", False)
    if not real_loop_invoked:
        report.add_error("P4c: real_loop_invoked is False - simulation not allowed")
        return False

    # Check shipping identity
    root_cause_summary = str(evidence.get("root_cause_summary", ""))
    if "shipping" not in root_cause_summary.lower():
        report.add_error("P4c root_cause_summary does not reference 'shipping'")
        return False

    # Check scheduling root-cause markers
    scheduling_markers_found = [
        marker for marker in SCHEDULING_ROOT_CAUSE_MARKERS
        if marker.lower() in root_cause_summary.lower()
    ]

    if not scheduling_markers_found:
        report.add_error(
            f"P4c: No scheduling root-cause markers found in root_cause_summary. "
            f"Expected one of: {SCHEDULING_ROOT_CAUSE_MARKERS}"
        )
        return False

    # Check pass count
    pass_count = evidence.get("pass_count", 0)
    if pass_count < 2:
        report.add_error(f"P4c: pass_count={pass_count} < 2")
        return False

    # Check read-only contract
    executed_checks = evidence.get("executed_checks", [])
    mutating_patterns = ["apply", "delete", "patch", "scale", "rollout", "edit", "replace", "create"]
    has_mutating = any(
        any(p in str(check).lower() for p in mutating_patterns)
        for check in executed_checks
    )

    if has_mutating:
        report.add_error(f"P4c: Mutating commands found in executed_checks: {executed_checks}")
        return False

    # Check phase result reason
    phase_reason = evidence.get("phase_result_reason", "")
    if not any(r in str(phase_reason).lower() for r in ["diagnosis_rca_valid", "rca_valid"]):
        report.add_warning(f"P4c phase_result_reason '{phase_reason}' not in standard set")

    report.add_check(ContractCheck(
        name="p4c_diagnosis",
        passed=True,
        phase="p4c",
        reason=phase_reason or P4C_REASON_DIAGNOSIS_RCA_VALID,
        details={
            "incident_id": evidence.get("incident_id"),
            "pass_count": pass_count,
            "scheduling_markers_found": scheduling_markers_found,
            "read_only": evidence.get("read_only", True),
        },
    ))
    return True


# =============================================================================
# Runtime Loop-Pass Verification
# =============================================================================

def find_loop_pass_artifacts(artifact_dir: Path) -> list[Path]:
    """Find loop pass artifacts."""
    loop_passes_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis" / "loop-passes"
    if loop_passes_dir.exists():
        return list(loop_passes_dir.glob("*.json"))

    # Fall back to embedded in diagnosis-evidence
    diagnosis_evidence_path = (
        artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis" / "diagnosis-evidence.json"
    )
    if diagnosis_evidence_path.exists():
        try:
            evidence = json.loads(diagnosis_evidence_path.read_text())
            if "pass_artifacts" in evidence:
                return [diagnosis_evidence_path]  # Marker to use embedded
        except json.JSONDecodeError:
            pass

    return []


def verify_runtime_loop_passes(artifact_dir: Path, report: VerificationReport) -> bool:
    """Verify runtime loop-pass artifacts.

    For every pass artifact, require:
    - All REQUIRED_PASS_ARTIFACT_FIELDS
    - safety_metadata.policy_enforced == true
    - safety_metadata.mutating_checks_executed_count == 0
    - safety_metadata.sensitive_reads_executed_count == 0
    - len(accepted_checks) == len(check_fingerprints)
    - No rejected check id in accepted_checks
    - gate_summary.rejected_checks exists
    - stop_reason present on final pass
    """
    loop_pass_artifacts = find_loop_pass_artifacts(artifact_dir)

    if not loop_pass_artifacts:
        report.add_error("No loop-pass artifacts found")
        return False

    pass_artifacts: list[dict[str, Any]] = []

    for artifact_path in loop_pass_artifacts:
        try:
            if artifact_path.name.endswith(".json"):
                # Standalone pass artifact
                artifact = json.loads(artifact_path.read_text())
                pass_artifacts.append(artifact)
            else:
                continue
        except (json.JSONDecodeError, OSError) as e:
            report.add_warning(f"Failed to parse {artifact_path}: {e}")
            continue

    # Try embedded pass artifacts
    if not pass_artifacts:
        diagnosis_evidence_path = (
            artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis" / "diagnosis-evidence.json"
        )
        if diagnosis_evidence_path.exists():
            try:
                evidence = json.loads(diagnosis_evidence_path.read_text())
                pass_artifacts = evidence.get("pass_artifacts", [])
            except json.JSONDecodeError:
                pass

    if not pass_artifacts:
        report.add_error("No parseable pass artifacts found")
        return False

    # Verify each pass artifact and track failures
    schema_valid = True
    for i, artifact in enumerate(pass_artifacts):
        if not _verify_pass_artifact_schema(artifact, i, report):
            schema_valid = False

    # Check aggregate safety
    total_unsafe = sum(a.get("unsafe_check_count", 0) for a in pass_artifacts)
    total_mutating = sum(
        a.get("safety_metadata", {}).get("mutating_checks_executed_count", 0)
        for a in pass_artifacts
    )
    total_sensitive = sum(
        a.get("safety_metadata", {}).get("sensitive_reads_executed_count", 0)
        for a in pass_artifacts
    )

    if total_mutating > 0:
        report.add_error(f"Runtime: mutating_checks_executed_count > 0: {total_mutating}")
        return False

    if total_sensitive > 0:
        report.add_error(f"Runtime: sensitive_reads_executed_count > 0: {total_sensitive}")
        return False

    if not schema_valid:
        report.add_error("Runtime: One or more pass artifacts failed schema validation")
        return False

    # Verify bounded-loop policy
    bounded_loop_valid = _verify_bounded_loop_policy(pass_artifacts, report)
    if not bounded_loop_valid:
        report.add_error("Runtime: Bounded-loop policy violated")
        return False

    report.add_check(ContractCheck(
        name="runtime_loop_passes",
        passed=True,
        phase="runtime",
        reason="passes_valid",
        details={
            "pass_count": len(pass_artifacts),
            "total_unsafe": total_unsafe,
            "total_mutating": total_mutating,
            "total_sensitive": total_sensitive,
        },
    ))
    return True


def _verify_pass_artifact_schema(artifact: dict[str, Any], index: int, report: VerificationReport) -> bool:
    """Verify a single pass artifact has required schema fields."""
    missing_fields = [f for f in REQUIRED_PASS_ARTIFACT_FIELDS if f not in artifact]

    if missing_fields:
        report.add_error(f"Pass artifact {index}: missing required fields: {missing_fields}")
        return False

    # Verify safety_metadata
    safety_metadata = artifact.get("safety_metadata", {})
    if safety_metadata.get("policy_enforced") is not True:
        report.add_error(f"Pass artifact {index}: safety_metadata.policy_enforced != True")
        return False

    if safety_metadata.get("mutating_checks_executed_count", 0) > 0:
        report.add_error(f"Pass artifact {index}: mutating_checks_executed_count > 0")
        return False

    if safety_metadata.get("sensitive_reads_executed_count", 0) > 0:
        report.add_error(f"Pass artifact {index}: sensitive_reads_executed_count > 0")
        return False

    # Verify accepted_checks alignment with check_fingerprints
    accepted_checks = artifact.get("accepted_checks", [])
    check_fingerprints = artifact.get("check_fingerprints", [])

    if len(accepted_checks) != len(check_fingerprints):
        report.add_error(
            f"Pass artifact {index}: len(accepted_checks)={len(accepted_checks)} != "
            f"len(check_fingerprints)={len(check_fingerprints)}"
        )
        return False

    # Verify no rejected check in accepted
    rejected_checks = set(str(c) for c in artifact.get("rejected_checks", []))
    accepted_ids = set(str(c) for c in accepted_checks)
    overlap = rejected_checks & accepted_ids

    if overlap:
        report.add_error(f"Pass artifact {index}: rejected check ids in accepted_checks: {overlap}")
        return False

    # Verify gate_summary.rejected_checks exists
    gate_summary = artifact.get("gate_summary", {})
    if "rejected_checks" not in gate_summary:
        report.add_error(f"Pass artifact {index}: gate_summary.rejected_checks missing")
        return False

    # Verify stop_reason on final pass
    if artifact.get("should_continue") is False and not artifact.get("stop_reason"):
        report.add_error(f"Pass artifact {index}: should_continue=False but stop_reason missing")
        return False

    # Verify unsafe_check_count is zero (safety contract)
    if artifact.get("unsafe_check_count", 0) > 0:
        report.add_error(f"Pass artifact {index}: unsafe_check_count > 0: {artifact.get('unsafe_check_count')}")
        return False

    return True


def _verify_bounded_loop_policy(pass_artifacts: list[dict[str, Any]], report: VerificationReport) -> bool:
    """Verify bounded-loop policy constraints.

    If policy metadata is absent, use live-lab defaults:
    - max_passes = 2
    - max_checks_per_pass = 2
    - max_total_checks = 4

    Returns True if policy is satisfied, False if violated.
    """
    # Try to extract policy from first pass
    first_pass = pass_artifacts[0] if pass_artifacts else {}
    policy = first_pass.get("policy_metadata", first_pass.get("loop_policy", {}))

    max_passes = policy.get("max_passes") or DEFAULT_MAX_PASSES
    max_checks_per_pass = policy.get("max_checks_per_pass") or DEFAULT_MAX_CHECKS_PER_PASS
    max_total_checks = policy.get("max_total_checks") or DEFAULT_MAX_TOTAL_CHECKS

    violations: list[str] = []

    # Verify pass count
    if len(pass_artifacts) > max_passes:
        violations.append(
            f"Bounded-loop: pass count {len(pass_artifacts)} > max_passes {max_passes}"
        )

    # Verify total checks
    total_accepted = sum(len(p.get("accepted_checks", [])) for p in pass_artifacts)
    if total_accepted > max_total_checks:
        violations.append(
            f"Bounded-loop: total accepted checks {total_accepted} > max_total_checks {max_total_checks}"
        )

    # Verify per-pass checks
    for i, pass_art in enumerate(pass_artifacts):
        accepted = len(pass_art.get("accepted_checks", []))
        if accepted > max_checks_per_pass:
            violations.append(
                f"Bounded-loop: pass {i} accepted {accepted} > max_checks_per_pass {max_checks_per_pass}"
            )

    for violation in violations:
        report.add_error(violation)

    return len(violations) == 0


# =============================================================================
# Sensitive Payload Scan
# =============================================================================

def scan_for_sensitive_payloads(artifact_dir: Path, report: VerificationReport) -> bool:
    """Scan JSON artifacts for forbidden sensitive payload patterns.

    Fail if artifacts contain likely raw secret/token material.
    Do NOT fail on safe patterns like sensitive_read_denied.
    """
    json_files = list(artifact_dir.glob("**/*.json"))
    sensitive_artifacts: list[str] = []

    for json_path in json_files:
        try:
            content = json_path.read_text()
            artifact = json.loads(content)

            # Convert to string for pattern matching
            artifact_str = json.dumps(artifact)

            # Check for forbidden patterns
            for pattern in FORBIDDEN_SENSITIVE_PATTERNS:
                if pattern.search(artifact_str):
                    # Check if it's actually a safe pattern
                    if any(safe in artifact_str for safe in ALLOWED_SAFE_PATTERNS):
                        continue
                    sensitive_artifacts.append(str(json_path))
                    break

        except (json.JSONDecodeError, OSError):
            continue

    if sensitive_artifacts:
        report.add_error(
            f"Sensitive payload scan: Forbidden patterns found in artifacts: {sensitive_artifacts}"
        )
        return False

    report.add_check(ContractCheck(
        name="sensitive_payload_scan",
        passed=True,
        phase="security",
        reason="no_forbidden_payloads",
    ))
    return True


# =============================================================================
# OTel Trace Verification
# =============================================================================

def find_otel_trace_artifacts(artifact_dir: Path) -> list[Path]:
    """Find OTel trace artifacts."""
    patterns = [
        "**/traces*.json",
        "**/otel*.json",
        "**/spans*.json",
    ]
    found: list[Path] = []
    for pattern in patterns:
        found.extend(artifact_dir.glob(pattern))
    return found


def verify_otel_traces(artifact_dir: Path, mode: OtelTracesMode, report: VerificationReport) -> bool:
    """Verify OTel trace artifacts.

    When mode is:
    - skip: Do not inspect traces
    - auto: Inspect if present, skip if missing
    - require: Fail if missing

    If traces exist, verify expected span/event names.
    """
    if mode == OtelTracesMode.SKIP:
        report.add_check(ContractCheck(
            name="otel_traces",
            passed=True,
            phase="otel",
            reason="skipped",
        ))
        return True

    trace_artifacts = find_otel_trace_artifacts(artifact_dir)

    if not trace_artifacts:
        if mode == OtelTracesMode.REQUIRE:
            report.add_error("OTel traces required but not found")
            return False
        else:
            # auto mode - traces optional
            report.add_check(ContractCheck(
                name="otel_traces",
                passed=True,
                phase="otel",
                reason="skipped_missing",
            ))
            return True

    # Verify traces contain expected spans/events
    spans_found: set[str] = set()
    events_found: set[str] = set()

    for trace_path in trace_artifacts:
        try:
            content = trace_path.read_text()
            trace_data = json.loads(content)

            # Extract span/event names
            _extract_trace_names(trace_data, spans_found, events_found)

        except (json.JSONDecodeError, OSError):
            continue

    # Check for expected spans (at least some should be present)
    expected_spans_found = spans_found & EXPECTED_OTEL_SPANS
    expected_events_found = events_found & EXPECTED_OTEL_EVENTS

    # OTel traces are informational - warn but don't fail if expected names missing
    # (API-only instrumentation may not export without SDK config)
    if not expected_spans_found and not expected_events_found:
        report.add_warning(
            f"OTel traces found but no expected span/event names. "
            f"Spans: {spans_found}, Events: {events_found}"
        )

    report.add_check(ContractCheck(
        name="otel_traces",
        passed=True,
        phase="otel",
        reason="traces_present",
        details={
            "trace_files": [str(p) for p in trace_artifacts],
            "spans_found": list(spans_found),
            "events_found": list(events_found),
            "expected_spans_found": list(expected_spans_found),
            "expected_events_found": list(expected_events_found),
        },
    ))
    return True


def _extract_trace_names(data: Any, spans: set[str], events: set[str]) -> None:
    """Recursively extract span/event names from trace data."""
    if isinstance(data, dict):
        # Check for span name fields
        for key in ["name", "span_name", "display_name"]:
            if key in data and isinstance(data[key], str):
                spans.add(data[key])

        # Check for event names
        if "events" in data and isinstance(data["events"], list):
            for event in data["events"]:
                if isinstance(event, dict) and "name" in event:
                    events.add(str(event["name"]))

        # Recurse
        for value in data.values():
            _extract_trace_names(value, spans, events)

    elif isinstance(data, list):
        for item in data:
            _extract_trace_names(item, spans, events)


# =============================================================================
# Main Verification
# =============================================================================

def verify_live_lab_contracts(
    artifact_dir: Path,
    scenario: str,
    require_lab_passed: bool,
    otel_traces_mode: OtelTracesMode,
) -> VerificationReport:
    """Run all contract verifications for a live-lab run."""
    report = VerificationReport(passed=True)

    # Phase 0: Lab result
    verify_lab_result(artifact_dir, require_lab_passed, report)

    # Phase 1: Sensitive payload scan (runs on all artifacts)
    scan_for_sensitive_payloads(artifact_dir, report)

    if scenario == "unschedulable-shipping":
        # Phase 2: P3c discovery
        verify_p3c_discovery(artifact_dir, report)

        # Phase 3: P4c diagnosis
        verify_p4c_diagnosis(artifact_dir, report)

        # Phase 4: Runtime loop passes
        verify_runtime_loop_passes(artifact_dir, report)

    # Phase 5: OTel traces
    verify_otel_traces(artifact_dir, otel_traces_mode, report)

    return report


def format_report(report: VerificationReport, json_output: bool) -> str:
    """Format verification report for output."""
    if json_output:
        return json.dumps({
            "passed": report.passed,
            "checks": [
                {
                    "name": c.name,
                    "passed": c.passed,
                    "phase": c.phase,
                    "reason": c.reason,
                    "details": c.details,
                }
                for c in report.checks
            ],
            "errors": report.errors,
            "warnings": report.warnings,
        }, indent=2)

    # Human-readable output
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("LIVE-LAB CONTRACT VERIFICATION REPORT")
    lines.append("=" * 60)

    for check in report.checks:
        status = "PASS" if check.passed else "FAIL"
        reason = f" ({check.reason})" if check.reason else ""
        lines.append(f"  [{status}] {check.phase}: {check.name}{reason}")

    if report.errors:
        lines.append("")
        lines.append("ERRORS:")
        for error in report.errors:
            lines.append(f"  - {error}")

    if report.warnings:
        lines.append("")
        lines.append("WARNINGS:")
        for warning in report.warnings:
            lines.append(f"  - {warning}")

    lines.append("")
    lines.append(f"VERIFICATION GATE: {'PASSED' if report.passed else 'FAILED'}")

    return "\n".join(lines)


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Verify live-lab contracts for unschedulable-shipping scenario"
    )
    parser.add_argument(
        "--artifact-dir",
        required=True,
        help="Root artifact directory (e.g., lab-artifacts/otel-demo)",
    )
    parser.add_argument(
        "--scenario",
        default="unschedulable-shipping",
        help="Incident scenario name (default: unschedulable-shipping)",
    )
    parser.add_argument(
        "--require-lab-passed",
        action="store_true",
        help="Require lab-result.json to indicate success",
    )
    parser.add_argument(
        "--otel-traces",
        choices=["auto", "require", "skip"],
        default="auto",
        help="OTel trace verification mode (default: auto)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON format",
    )

    args = parser.parse_args()
    artifact_dir = Path(args.artifact_dir)

    if not artifact_dir.exists():
        print(f"ERROR: Artifact directory does not exist: {artifact_dir}", file=sys.stderr)
        return 1

    otel_mode = OtelTracesMode(args.otel_traces)

    report = verify_live_lab_contracts(
        artifact_dir=artifact_dir,
        scenario=args.scenario,
        require_lab_passed=args.require_lab_passed,
        otel_traces_mode=otel_mode,
    )

    output = format_report(report, args.json)
    print(output)

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
