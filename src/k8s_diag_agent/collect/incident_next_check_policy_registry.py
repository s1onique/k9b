"""Read-only check registry for incident next-check policy.

This module contains constants and registry data.

Design constraints:
- Pure type definitions only
- No store mutation
- No LLM calls
- No Kubernetes calls
- No execution
"""

from __future__ import annotations

from typing import Any

# =============================================================================
# Constants
# =============================================================================

# Schema version for tracking structure evolution
POLICY_SCHEMA_VERSION = "1.0"

# Disallowed actions for safety boundary
DISALLOWED_ACTIONS: list[str] = [
    "execute_arbitrary_command",
    "promote",
    "apply",
    "remediate",
    "delete",
    "mutate_cluster",
    "execute",
]

# Fields that should NEVER appear in check proposals as executable commands
FORBIDDEN_COMMAND_FIELDS: frozenset[str] = frozenset({
    "command",
    "shell",
    "kubectl",
    "exec",
    "apply",
    "delete",
    "patch",
    "scale",
    "restart",
    "rollout",
    "run_command",
    "execute_command",
    "exec_command",
})

# Maximum number of checks per pass (bounded for safety)
DEFAULT_MAX_CHECKS_PER_PASS = 5

# Maximum total checks across all passes (bounded for safety)
DEFAULT_MAX_TOTAL_CHECKS = 15


# =============================================================================
# Read-Only Check Registry
# =============================================================================

# Registry of known read-only checks with their metadata
# Each entry contains:
#   - read_only: bool - must be True
#   - allowed_parameters: set[str] - parameters that are allowed
#   - description: str - human-readable description
READ_ONLY_CHECK_REGISTRY: dict[str, dict[str, Any]] = {
    "pod_logs": {
        "read_only": True,
        "allowed_parameters": frozenset({"namespace", "object_name", "container", "previous", "tail_lines"}),
        "description": "Read pod logs",
    },
    "pod_events": {
        "read_only": True,
        "allowed_parameters": frozenset({"namespace", "object_name", "object_kind"}),
        "description": "Read pod events",
    },
    "pod_describe": {
        "read_only": True,
        "allowed_parameters": frozenset({"namespace", "object_name"}),
        "description": "Read pod describe output",
    },
    "deployment_status": {
        "read_only": True,
        "allowed_parameters": frozenset({"namespace", "object_name"}),
        "description": "Read deployment status",
    },
    "deployment_events": {
        "read_only": True,
        "allowed_parameters": frozenset({"namespace", "object_name"}),
        "description": "Read deployment events",
    },
    "statefulset_status": {
        "read_only": True,
        "allowed_parameters": frozenset({"namespace", "object_name"}),
        "description": "Read statefulset status",
    },
    "daemonset_status": {
        "read_only": True,
        "allowed_parameters": frozenset({"namespace", "object_name"}),
        "description": "Read daemonset status",
    },
    "service_endpoints": {
        "read_only": True,
        "allowed_parameters": frozenset({"namespace", "object_name"}),
        "description": "Read service endpoints",
    },
    "ingress_status": {
        "read_only": True,
        "allowed_parameters": frozenset({"namespace", "object_name"}),
        "description": "Read ingress status",
    },
    "configmap_get": {
        "read_only": True,
        "allowed_parameters": frozenset({"namespace", "object_name"}),
        "description": "Read configmap",
    },
    "secret_list": {
        "read_only": True,
        "allowed_parameters": frozenset({"namespace"}),
        "description": "List secrets in namespace (names only)",
    },
    "node_status": {
        "read_only": True,
        "allowed_parameters": frozenset({"node_name"}),
        "description": "Read node status",
    },
    "node_events": {
        "read_only": True,
        "allowed_parameters": frozenset({"node_name"}),
        "description": "Read node events",
    },
    "persistentvolume_status": {
        "read_only": True,
        "allowed_parameters": frozenset({"name"}),
        "description": "Read persistentvolume status",
    },
    "resource_quota_status": {
        "read_only": True,
        "allowed_parameters": frozenset({"namespace"}),
        "description": "Read resource quota status",
    },
    "limit_range_status": {
        "read_only": True,
        "allowed_parameters": frozenset({"namespace"}),
        "description": "Read limit range status",
    },
    "hpa_status": {
        "read_only": True,
        "allowed_parameters": frozenset({"namespace", "object_name"}),
        "description": "Read HPA status",
    },
    "pod_metrics": {
        "read_only": True,
        "allowed_parameters": frozenset({"namespace", "object_name"}),
        "description": "Read pod metrics",
    },
    "node_metrics": {
        "read_only": True,
        "allowed_parameters": frozenset({"node_name"}),
        "description": "Read node metrics",
    },
}

# Mutation-like check IDs that should always be rejected
MUTATION_CHECK_IDS: frozenset[str] = frozenset({
    "kubectl_exec",
    "kubectl_apply",
    "kubectl_delete",
    "kubectl_patch",
    "kubectl_scale",
    "kubectl_rollout",
    "kubectl_run",
    "kubectl_create",
    "kubectl_replace",
    "kubectl_edit",
    "kubectl_label",
    "kubectl_annotate",
    "kubectl_logs_exec",  # exec into container is mutation
    "restart_pod",
    "restart_deployment",
    "scale_deployment",
    "apply_manifest",
    "delete_resource",
    "patch_resource",
    "execute_command",
    "run_script",
})


__all__ = [
    "POLICY_SCHEMA_VERSION",
    "DISALLOWED_ACTIONS",
    "FORBIDDEN_COMMAND_FIELDS",
    "DEFAULT_MAX_CHECKS_PER_PASS",
    "DEFAULT_MAX_TOTAL_CHECKS",
    "READ_ONLY_CHECK_REGISTRY",
    "MUTATION_CHECK_IDS",
]
