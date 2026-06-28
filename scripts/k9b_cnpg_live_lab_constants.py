#!/usr/bin/env python3
"""Configuration constants for CNPG Live Lab bootstrap script.

This module contains all configuration constants used across the bootstrap
and diagnosis workflow.
"""

from __future__ import annotations

# =============================================================================
# Failure class constants
# =============================================================================

# Bootstrap failure classes
FAILURE_KUBECONFIG_MISSING = "kubeconfig_missing"
FAILURE_KUBECONFIG_DECODE_FAILED = "kubeconfig_decode_failed"
FAILURE_KUBECONFIG_AUTH_FAILED = "kubeconfig_auth_failed"
FAILURE_CREDENTIAL_SOURCE_WRONG = "credential_source_wrong"
FAILURE_HELM_RBAC_DENIED = "helm_rbac_denied"
FAILURE_HELM_MANIFEST_SCHEMA_WARNING = "helm_manifest_schema_warning"
FAILURE_HELM_MANIFEST_SERVER_DRY_RUN_FAILED = "helm_manifest_server_dry_run_failed"
FAILURE_IMAGE_PULL_FAILED = "image_pull_failed"
FAILURE_CNPG_CRD_MISSING = "cnpg_crd_missing"
FAILURE_STORAGE_OR_CAPACITY = "storageclass_or_capacity_issue"
FAILURE_WORKLOAD_NOT_READY = "workload_not_ready"
FAILURE_DEPLOYMENT_NOT_AVAILABLE = "deployment_not_available"
FAILURE_POD_CRASH_LOOP = "pod_crash_loop"
FAILURE_PROBE_FAILED = "probe_failed"
FAILURE_PVC_PENDING = "pvc_pending"
FAILURE_HELM_WAIT_TIMEOUT_UNKNOWN = "helm_wait_timeout_unknown"
FAILURE_EXPECTED_WORKLOAD_MISSING = "expected_workload_missing"
# Sub-classifications for expected_workload_missing
FAILURE_WORKLOAD_RENDERED_MISSING_DEPLOYMENT = "rendered_manifest_missing_deployment"
FAILURE_WORKLOAD_RENDERED_BUT_CLUSTER_MISSING = "rendered_manifest_has_deployment_but_cluster_missing"
FAILURE_HELM_RELEASE_MISSING = "helm_release_missing_after_install"
FAILURE_HELM_RELEASE_FAILED_BEFORE_WORKLOAD = "helm_release_failed_before_workload_create"
FAILURE_CHART_VALUES_SUPPRESSED = "chart_values_suppressed_workload"
FAILURE_ADMISSION_OR_RBAC_REJECTED = "admission_or_rbac_rejected_workload"
# Deferred: requires rollout snapshot history integration
FAILURE_WORKLOAD_DISAPPEARED = "workload_created_then_disappeared"  # TODO: implement with rollout snapshots
FAILURE_EVIDENCE_COLLECTION_FAILED = "render_apply_evidence_collection_failed"
FAILURE_HELM_UNKNOWN = "helm_unknown_error"

# Rollout failure classes (proactive monitor)
FAILURE_IMAGE_PULL_BACKOFF = "image_pull_backoff"
FAILURE_CRASH_LOOP = "crash_loop"
FAILURE_FAILED_SCHEDULING = "failed_scheduling"
FAILURE_PVC_PENDING = "pvc_pending"
FAILURE_READINESS_PROBE_FAILED = "readiness_probe_failed"
FAILURE_DEPLOYMENT_REPLICA_FAILURE = "deployment_replica_failure"
FAILURE_DEPLOYMENT_PROGRESS_DEADLINE = "deployment_progress_deadline"
FAILURE_ROLLOUT_TIMEOUT = "rollout_timeout"
FAILURE_SNAPSHOT_COLLECTION_FAILED = "rollout_snapshot_collection_failed"

# Connectivity failure classes
FAILURE_CLUSTER_API_TIMEOUT = "cluster_api_timeout"
FAILURE_API_DISCOVERY_FAILED = "api_discovery_failed"
FAILURE_UNKNOWN_CLUSTER_CONNECTIVITY = "unknown_cluster_connectivity_failure"


# =============================================================================
# Schema validation patterns
# =============================================================================

# Schema validation patterns for precise detection (not generic "error")
SCHEMA_VALIDATION_PATTERNS = [
    r"unknown field",
    r"strict decoding error",
    r"ValidationError\b",
    r"error validating data",
    r"field not declared in schema",
]

# Valid resource name pattern (must start with alphanumeric, can contain dash/underscore)
VALID_RESOURCE_NAME_PATTERN = r'[a-zA-Z0-9][-a-zA-Z0-9_]*'


# =============================================================================
# Expected workloads
# =============================================================================

# Expected workloads for k9b CNPG lab
EXPECTED_WORKLOADS = frozenset([
    "k9b-backend",
    "k9b-frontend", 
    "k9b-scheduler",
])
