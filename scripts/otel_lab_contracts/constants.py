"""Constants for OTel demo lab contract verification."""

from __future__ import annotations

import re

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
VALID_P3C_REASONS = frozenset(
    [
        P3C_REASON_INCIDENT_DISCOVERED,
        P3C_REASON_INCIDENT_DISCOVERED_WITHOUT_RCA,
        "p3c_discovery_valid",
    ]
)

# Valid P4c reasons
VALID_P4C_REASONS = frozenset(
    [
        P4C_REASON_DIAGNOSIS_RCA_VALID,
    ]
)

# Accepted P3c candidate classes
ACCEPTED_P3C_CANDIDATE_CLASSES = frozenset(
    [
        "deployment_unavailable",
        "pending_pod",
        "warning_event_burst",
    ]
)

# Scheduling root-cause markers for P4c
SCHEDULING_ROOT_CAUSE_MARKERS = frozenset(
    [
        "FailedScheduling",
        "Unschedulable",
        "nodeSelector",
        "k9b.dev/otel-lab-node",
        "k9b.dev/otel-lab-node=missing",
        "missing node label",
        "no matching node",
        "0/8 nodes are available",
    ]
)

# Live-lab default bounded-loop policy
DEFAULT_MAX_PASSES = 2
DEFAULT_MAX_CHECKS_PER_PASS = 2
DEFAULT_MAX_TOTAL_CHECKS = 4

# Required pass artifact fields
REQUIRED_PASS_ARTIFACT_FIELDS = frozenset(
    [
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
    ]
)

# OTel trace span/event names
EXPECTED_OTEL_SPANS = frozenset(
    [
        "k9b.diagnosis_loop.budget",
        "k9b.diagnosis_loop.plan",
        "k9b.diagnosis_loop.gate",
        "k9b.diagnosis_loop.execute",
        "k9b.diagnosis_loop.artifact",
    ]
)

EXPECTED_OTEL_EVENTS = frozenset(
    [
        "k9b.diagnosis_loop.check_rejected",
        "k9b.diagnosis_loop.checks_executed",
        "k9b.diagnosis_loop.artifact_written",
        "k9b.diagnosis_loop.stop",
    ]
)

# Forbidden sensitive payload patterns (hard fail)
# Note: Patterns match keys in JSON serialization where field names are quoted
FORBIDDEN_SENSITIVE_PATTERNS: list[re.Pattern[str]] = [
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
ALLOWED_SAFE_PATTERNS = frozenset(
    [
        "sensitive_read_denied",
        "kubectl_get_secrets",
        "secret read rejected",
    ]
)

# RCA markers for P3c (should NOT appear in discovery)
RCA_MARKERS_IN_DISCOVERY = frozenset(
    [
        "FailedScheduling",
        "nodeSelector",
        "k9b.dev/otel-lab-node=missing",
    ]
)
