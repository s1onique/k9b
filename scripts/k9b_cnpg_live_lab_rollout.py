#!/usr/bin/env python3
"""Rollout functions re-exports for backward compatibility.

This module re-exports functions from split modules to maintain
backward compatibility for existing imports.
"""

# Re-export types
# Re-export classify and subprocess functions
from .k9b_cnpg_live_lab_rollout_classify import (  # noqa: F401,F811
    _format_bounded_summary,
    classify_rollout_state,
)

# Re-export deploy check functions
from .k9b_cnpg_live_lab_rollout_deploy import (  # noqa: F401,F811
    _check_deployment_progress_deadline_from_json,
    _check_deployment_replica_failure_from_json,
    _check_pvc_pending_from_json,
    _check_rollout_success_from_json,
)

# Re-export event-based check functions
from .k9b_cnpg_live_lab_rollout_events import (  # noqa: F401,F811
    _check_failed_scheduling_from_events,
    _check_readiness_probe_failed_from_events,
    _detect_transient_volume_binding_conflict,
    _is_transient_volume_binding_conflict,
)

# Re-export pod check functions
from .k9b_cnpg_live_lab_rollout_pods import (  # noqa: F401,F811
    _check_crash_loop_from_pods,
    _check_failed_scheduling_from_pods,
    _check_image_pull_backoff_from_pods,
    _check_readiness_probe_failed_from_pods,
)
from .k9b_cnpg_live_lab_rollout_subprocess import (  # noqa: F401,F811
    _check_crash_loop,
    _check_deployment_progress_deadline,
    _check_deployment_replica_failure,
    _check_failed_scheduling,
    _check_image_pull_backoff,
    _check_pvc_pending,
    _check_readiness_probe_failed,
    _check_rollout_success,
    _collect_rollout_snapshot,
)
from .k9b_cnpg_live_lab_rollout_types import (  # noqa: F401,F811
    RolloutResult,
)
