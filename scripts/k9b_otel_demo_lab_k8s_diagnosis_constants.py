#!/usr/bin/env python3
"""Constants for K8s multi-pass diagnosis verification.

This module contains configuration constants for the P4c diagnosis phase:
- Diagnosis artifact paths
- Multi-pass requirements
- Root-cause matching patterns
- Read-only check identifiers
"""

from __future__ import annotations

# =============================================================================
# Phase constants
# =============================================================================

# Diagnosis phase directory structure
PHASE_DIAGNOSIS = "phase4-diagnosis"
PHASE_NAME = "p4c-k8s-multipass-diagnosis"
ARTIFACT_DIR = "p4c-k8s-multipass-diagnosis"
ARTIFACT_FILENAME = "diagnosis-evidence.json"

# Minimum pass count required for multi-pass diagnosis
MIN_REQUIRED_PASSES = 2

# =============================================================================
# Root-cause matching patterns
# =============================================================================

# Required terms that final diagnosis must contain
REQUIRED_ROOT_CAUSE_TERMS = frozenset([
    "shipping",
    "shipping",  # deployment name
    "nodeSelector",  # scheduling constraint
    "k9b.dev/otel-lab-node",  # selector key
    "missing",  # selector value / no matching node
])

# Patterns indicating scheduling/unschedulable root cause
SCHEDULING_PATTERNS = [
    "unschedulable",
    "nodeSelector",
    "node selector",
    "no node",
    "no matching node",
    "cannot schedule",
    "FailedScheduling",
]

# Selector-related patterns
SELECTOR_KEY_PATTERNS = [
    "k9b.dev/otel-lab-node",
    "k9b.dev/otel-lab",
]

SELECTOR_VALUE_PATTERNS = [
    "missing",
    "no.*node",
    "unschedulable",
]

# =============================================================================
# Read-only check identifiers
# =============================================================================

# Expected read-only checks the diagnosis loop should be able to request
EXPECTED_READ_ONLY_CHECKS = frozenset([
    "kubectl_get_deployment",
    "kubectl_get_pods",
    "kubectl_get_events",
    "kubectl_get_nodes",
])

# Mutating action patterns that should NOT appear in diagnosis loop
FORBIDDEN_MUTATING_PATTERNS = [
    "kubectl apply",
    "kubectl delete",
    "kubectl patch",
    "kubectl scale",
    "kubectl rollout",
    "kubectl edit",
    "kubectl replace",
    "kubectl create",
    "helm install",
    "helm upgrade",
    "kubectl exec",
    "kubectl port-forward",
]

# =============================================================================
# Diagnosis loop configuration
# =============================================================================

# Default configuration for multi-pass diagnosis loop
DEFAULT_MAX_PASSES = 5  # Allow up to 5 passes for convergence
DEFAULT_MAX_CHECKS_PER_PASS = 5
DEFAULT_DIAGNOSIS_TIMEOUT_SECONDS = 300  # 5 minutes

# =============================================================================
# Simulation control (TEST ONLY)
# =============================================================================

# Environment variable to enable simulation mode for testing
# WARNING: This should NEVER be set in production/live-lab environments
SIMULATION_ENV_VAR = "K9B_OTEL_LAB_ALLOW_SIMULATED_DIAGNOSIS"

# Diagnosis source identifiers
DIAGNOSIS_SOURCE_REAL = "k9b_automatic_diagnosis_loop"
DIAGNOSIS_SOURCE_SIMULATED = "simulated_diagnosis_loop"

# Failure reasons for diagnosis loop
FAILURE_REASON_LOOP_DISABLED = "automatic_diagnosis_loop_disabled"
FAILURE_REASON_LOOP_IMPORT_FAILED = "automatic_diagnosis_import_failed"
FAILURE_REASON_LOOP_ERROR = "automatic_diagnosis_loop_error"
FAILURE_REASON_PASS_ARTIFACTS_MISSING = "diagnosis_pass_artifacts_missing"
FAILURE_REASON_SIMULATION_USED = "simulation_used_but_not_allowed"

# Failure reasons for deployment env read failures (RBAC/network errors)
# These distinguish between "loop is disabled" vs "can't verify loop config"
FAILURE_REASON_LOOP_ENV_RBAC_DENIED = "automatic_loop_env_rbac_denied"
FAILURE_REASON_LOOP_ENV_READ_FAILED = "automatic_loop_env_read_failed"

# =============================================================================
# Schema field names (for diagnosis-evidence.json)
# =============================================================================

SCHEMA_FIELDS = [
    "phase",
    "scenario",
    "incident_id",
    "candidate_class",
    "target_namespace",
    "target_deployment",
    "diagnosis_started",
    "diagnosis_completed",
    "loop_status",
    "pass_count",
    "pass_run_ids",
    "read_only",
    "allowed_actions",
    "requested_checks",
    "executed_checks",
    "root_cause_summary",
    "root_cause_matches",
    "mentions_shipping",
    "mentions_node_selector",
    "mentions_selector_key",
    "mentions_selector_value",
    "mentions_no_matching_node",
    "failure_reason",
    "raw_diagnosis_artifact_path",
    "review_packet_path",
]
