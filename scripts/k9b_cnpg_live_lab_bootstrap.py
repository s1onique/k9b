#!/usr/bin/env python3
"""Bootstrap script for CNPG Live Lab credential validation and diagnosis.

Reusable bootstrap for the live lab workflow:
- Decodes protected kubeconfig to RUNNER_TEMP
- Validates credential source and fails closed if wrong identity detected
- Runs preflight checks
- Classifies Helm errors
- Emits machine-readable diagnostics as valid JSON

Usage:
    python -m scripts.k9b_cnpg_live_lab_bootstrap <env_secret_name> <kubeconfig_out_var> [namespace]
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
# Re-export all constants for backward compatibility
# =============================================================================
# These are re-exported so consumers can import from this module
# =============================================================================
# Re-export CLI functions
# =============================================================================
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
from scripts.k9b_cnpg_live_lab_helm_evidence import (  # noqa: F401,F811
    collect_helm_evidence,
    collect_rendered_manifest_evidence,
)

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
    _check_failed_scheduling_from_events,
    _check_readiness_probe_failed_from_events,
    _collect_rollout_snapshot,
    _is_transient_volume_binding_conflict,
    classify_rollout_state,
)

# =============================================================================
# Re-export schema functions
# =============================================================================
# =============================================================================
# Re-export schema helper (needed by tests)
# =============================================================================
from scripts.k9b_cnpg_live_lab_schema import (  # noqa: F401,F811  # noqa: F401,F811
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
