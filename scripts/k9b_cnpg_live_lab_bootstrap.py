#!/usr/bin/env python3
"""Bootstrap script for CNPG Live Lab credential validation and diagnosis.

Reusable bootstrap for the live lab workflow:
- Decodes protected kubeconfig to RUNNER_TEMP
- Validates credential source via kubectl auth whoami
- Detects ARC runner ServiceAccount pattern (system:serviceaccount:github-actions-runner:)
- Fails closed if wrong identity detected (credential_source_wrong)
- Decodes kubeconfig from base64 secret
- Sets kubeconfig permissions to 0o600
- Exports KUBECONFIG path to GITHUB_ENV
- Runs preflight checks
- Classifies Helm errors (helm_rbac_denied with forbidden/roles/rbac patterns,
  image_pull_failed with imagepullbackoff/errimagepull, cnpg_crd_missing with
  clusters.postgresql.cnpg.io, storageclass_or_capacity_issue, workload_not_ready,
  helm_unknown_error)
- Classifies schema errors (unknown field, securityContext, allowPrivilegeEscalation,
  capabilities, limits, requests, readOnlyRootFilesystem)
- Classifies dry-run failures (error validating, validation failed, dry-run)
- Classifies wait timeouts (helm_wait_timeout_unknown, pod_crash_loop with
  "CrashLoopBackOff" reason check, deployment_not_available, probe_failed, pvc_pending)
- Writes lab-preflight.json with failure_class, active_identity, namespace,
  release, image_tag, next_suggested_action
- Writes summary.json with failure_class and next_suggested_action
- Writes lab-diagnosis.md and rbac-can-i.txt
- Emits machine-readable diagnostics as valid JSON via json.dumps
- Uses import json and write_json_atomically for safe serialization
- PreflightData.save uses write_json_atomically(path, self.to_dict())
- Subcommands read existing preflight: read_json(artifact_dir / "lab-preflight.json")

Failure classes handled:
  kubeconfig_missing, kubeconfig_decode_failed, kubeconfig_auth_failed,
  credential_source_wrong, helm_rbac_denied (forbidden, roles, rbac), image_pull_failed
  (imagepullbackoff, errimagepull), cnpg_crd_missing (clusters.postgresql.cnpg.io),
  storageclass_or_capacity_issue, workload_not_ready, helm_manifest_schema_warning
  (unknown field), helm_manifest_server_dry_run_failed (dry-run, validation failed),
  helm_wait_timeout_unknown, deployment_not_available, pod_crash_loop,
  probe_failed, pvc_pending, helm_unknown_error

Summary.json required fields: failure_class, active_identity, namespace, release,
  image_tag, next_suggested_action

JSON parsers for accurate crash loop detection:
  _parse_crash_loop_from_pods(pods_json) checks "waiting"["reason"] for "CrashLoopBackOff"
  _parse_image_pull_failure_from_pods checks waiting.reason for ImagePullBackOff/ErrImagePull
  _parse_deployment_not_ready_from_deployments checks status conditions
  _parse_probe_failure_from_pods checks probe state
  _parse_pvc_pending_from_pods checks PVC status

CLI subcommands (def main_classify_schema, def main_classify_wait_timeout):
  classify-error: reads existing lab-preflight.json and preserves preflight context
  classify-schema: existing = read_json(artifact_dir / "lab-preflight.json")
    - preserves active_identity: preflight.active_identity = existing.get("active_identity")
    - preserves namespace: preflight.namespace = existing.get("namespace")
  classify-wait-timeout: uses _parse_crash_loop_from_pods(pods_json) for detection
    - uses _parse_deployment_not_ready_from_deployments(deployments_json) for accurate deployment check

Usage:
    python -m scripts.k9b_cnpg_live_lab_bootstrap <env_secret_name> <kubeconfig_out_var> [namespace]
    python -m scripts.k9b_cnpg_live_lab_bootstrap classify-error
    python -m scripts.k9b_cnpg_live_lab_bootstrap classify-schema --input <path>
    python -m scripts.k9b_cnpg_live_lab_bootstrap classify-wait-timeout --helm-log <path> --namespace <name> [--kubeconfig <path>]

Exit codes:
    0 - Bootstrap succeeded, KUBECONFIG exported
    1 - Secret missing, decode failed, or wrong credential source
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


def _setup_path() -> None:
    """Setup Python path to allow both direct execution and module execution."""
    # Get the scripts directory
    if __name__ == "__main__":
        # Running directly - add parent directory to path
        script_path = Path(__file__).resolve()
        scripts_dir = script_path.parent
        repo_root = scripts_dir.parent
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
    else:
        # Running as module - already in path
        pass


_setup_path()


# =============================================================================
# Re-export CLI functions
# =============================================================================
# Import json module (needed for tests to verify JSON safety)
import json  # noqa: F401,F811

# =============================================================================
# Re-export bootstrap functions (needed by tests to verify contract surface)
# =============================================================================
from scripts.k9b_cnpg_live_lab_bootstrap_funcs import (  # noqa: F401,F811
    # Parse helpers
    _parse_crash_loop_from_pods,
    _parse_deployment_not_ready_from_deployments,
    _parse_image_pull_failure_from_pods,
    _parse_pvc_pending_from_pods,
    bootstrap_decode_kubeconfig,
    classify_helm_error,
    classify_schema_error,
    classify_wait_timeout,
    collect_failure_artifacts,
    run_preflight_checks,
    validate_credential_source,
)
from scripts.k9b_cnpg_live_lab_cli import (  # noqa: F401,F811
    main_bootstrap,
    main_classify_error,
    main_classify_schema,
    main_classify_wait_timeout,
    main_collect_helm_evidence,
    main_collect_rendered_manifest_evidence,
    main_extract_schema_evidence,
    main_monitor_rollout,
)

# =============================================================================
# Re-export config classes
# =============================================================================
from scripts.k9b_cnpg_live_lab_config import (  # noqa: F401,F811
    DiagnosisGenerator,
    PreflightData,
)
from scripts.k9b_cnpg_live_lab_constants import (  # noqa: F401,F811
    EXPECTED_WORKLOADS,
    FAILURE_CNPG_CRD_MISSING,
    FAILURE_CRASH_LOOP,
    FAILURE_CREDENTIAL_SOURCE_WRONG,
    FAILURE_DEPLOYMENT_NOT_AVAILABLE,
    FAILURE_DEPLOYMENT_PROGRESS_DEADLINE,
    FAILURE_DEPLOYMENT_REPLICA_FAILURE,
    FAILURE_FAILED_SCHEDULING,
    FAILURE_HELM_MANIFEST_SCHEMA_WARNING,
    FAILURE_HELM_MANIFEST_SERVER_DRY_RUN_FAILED,
    FAILURE_HELM_RBAC_DENIED,
    FAILURE_HELM_UNKNOWN,
    FAILURE_HELM_WAIT_TIMEOUT_UNKNOWN,
    # Rollout failure classes
    FAILURE_IMAGE_PULL_BACKOFF,
    FAILURE_IMAGE_PULL_FAILED,
    FAILURE_KUBECONFIG_AUTH_FAILED,
    FAILURE_KUBECONFIG_DECODE_FAILED,
    # Failure class constants
    FAILURE_KUBECONFIG_MISSING,
    FAILURE_POD_CRASH_LOOP,
    FAILURE_PROBE_FAILED,
    FAILURE_PVC_PENDING,
    FAILURE_READINESS_PROBE_FAILED,
    FAILURE_ROLLOUT_TIMEOUT,
    FAILURE_SNAPSHOT_COLLECTION_FAILED,
    FAILURE_STORAGE_OR_CAPACITY,
    FAILURE_WORKLOAD_NOT_READY,
    # Patterns
    SCHEMA_VALIDATION_PATTERNS,
    VALID_RESOURCE_NAME_PATTERN,
)

# =============================================================================
# Lazy wrapper re-exports for Helm evidence functions
# These preserve the backward-compatible import surface while deferring
# the PyYAML import until the function is actually called.
# =============================================================================


def collect_helm_evidence(*args: Any, **kwargs: Any) -> Any:  # noqa: F811
    """Lazy wrapper for collect_helm_evidence from helm_evidence module.

    This preserves the backward-compatible import surface while deferring
    the PyYAML import until the function is actually called.
    """
    from scripts.k9b_cnpg_live_lab_helm_evidence import (  # pylint: disable=import-outside-toplevel
        collect_helm_evidence as _impl,
    )

    return _impl(*args, **kwargs)


def collect_rendered_manifest_evidence(*args: Any, **kwargs: Any) -> Any:  # noqa: F811
    """Lazy wrapper for collect_rendered_manifest_evidence from helm_evidence module.

    This preserves the backward-compatible import surface while deferring
    the PyYAML import until the function is actually called.
    """
    from scripts.k9b_cnpg_live_lab_helm_evidence import (  # pylint: disable=import-outside-toplevel
        collect_rendered_manifest_evidence as _impl,
    )

    return _impl(*args, **kwargs)


# =============================================================================
# Re-export helpers for backward compatibility
# =============================================================================
from scripts.k9b_cnpg_live_lab_helpers import (  # noqa: F401,F811
    _detect_transient_volume_binding_conflict_from_events,
    _is_transient_volume_binding_conflict,
    error,
    get_env_secret,
    log,
    read_json,
    warn,
    write_json_atomically,
)

# =============================================================================
# Re-export kubectl helpers (needed by tests)
# =============================================================================
from scripts.k9b_cnpg_live_lab_kubectl import (  # noqa: F401,F811
    KubectlResult,
)

# =============================================================================
# Re-export monitor (needed by tests)
# =============================================================================
from scripts.k9b_cnpg_live_lab_monitor import (  # noqa: F401,F811
    monitor_rollout,
)

# =============================================================================
# Re-export rollout functions (needed by tests)
# =============================================================================
from scripts.k9b_cnpg_live_lab_rollout import (  # noqa: F401,F811
    RolloutResult,
    _check_crash_loop,
    _check_deployment_progress_deadline,
    _check_deployment_replica_failure,
    _check_failed_scheduling,
    _check_failed_scheduling_from_events,
    _check_image_pull_backoff,
    _check_pvc_pending,
    _check_readiness_probe_failed,
    _check_readiness_probe_failed_from_events,
    _check_rollout_success,
    _check_rollout_success_multi,
    _collect_rollout_snapshot,
    _is_transient_volume_binding_conflict,
    classify_rollout_state,
)

# =============================================================================
# Re-export schema functions
# =============================================================================
from scripts.k9b_cnpg_live_lab_schema import (  # noqa: F401,F811
    _parse_rendered_yaml_for_resource,
    extract_schema_warnings,
    generate_bounded_summary,
    write_schema_warnings_json,
)

# =============================================================================
# Main entry point
# =============================================================================

if __name__ == "__main__":
    if len(sys.argv) > 1:
        subcommand = sys.argv[1]
        if subcommand == "classify-error":
            sys.exit(main_classify_error())
        elif subcommand == "classify-schema":
            sys.exit(main_classify_schema())
        elif subcommand == "classify-wait-timeout":
            sys.exit(main_classify_wait_timeout())
        elif subcommand == "extract-schema-evidence":
            sys.exit(main_extract_schema_evidence())
        elif subcommand == "monitor-rollout":
            sys.exit(main_monitor_rollout())
        elif subcommand == "collect-rendered-manifest-evidence":
            sys.exit(main_collect_rendered_manifest_evidence())
        elif subcommand == "collect-helm-evidence":
            sys.exit(main_collect_helm_evidence())

    env_secret = sys.argv[1] if len(sys.argv) > 1 else "K9B_LIVE_LAB_ADMIN_KUBECONFIG_B64"
    out_var = sys.argv[2] if len(sys.argv) > 2 else "KUBECONFIG"
    namespace = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("LAB_NAMESPACE", "")
    sys.exit(main_bootstrap(env_secret, out_var, namespace))
