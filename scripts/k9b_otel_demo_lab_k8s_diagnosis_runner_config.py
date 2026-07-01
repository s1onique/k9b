"""Runner config for K8s multi-pass diagnosis phase.

This module provides configuration, environment, and argument parsing helpers
for the diagnosis loop runner.

Architecture:
- P4c uses backend-targeted automatic diagnosis-loop one-pass via
  POST /api/incidents/{incident_id}/automatic-diagnosis-loop/one-pass
"""

from __future__ import annotations

from scripts.k9b_otel_demo_lab_constants import (
    K8S_INJECTION_NODE_SELECTOR_KEY,
    K8S_INJECTION_NODE_SELECTOR_VALUE,
    SHIPPING_DEPLOYMENT,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_constants import (
    FAILURE_REASON_LOOP_ENV_RBAC_DENIED,
    FAILURE_REASON_LOOP_ENV_READ_FAILED,
    SIMULATION_ENV_VAR,
)

# Default k9b namespace
DEFAULT_K9B_NAMESPACE = "k9b"

# Mapping from loop check reason codes to failure reason constants
_LOOP_CHECK_REASON_TO_FAILURE: dict[str, str] = {
    "automatic_loop_env_rbac_denied": FAILURE_REASON_LOOP_ENV_RBAC_DENIED,
    "automatic_loop_env_read_failed": FAILURE_REASON_LOOP_ENV_READ_FAILED,
}


def get_simulation_env_value() -> str:
    """Get the simulation environment variable value.

    Returns:
        The value of SIMULATION_ENV_VAR or empty string if not set.
    """
    import os
    return os.environ.get(SIMULATION_ENV_VAR, "").lower()


def is_simulation_enabled(allow_simulation: bool) -> bool:
    """Check if simulation is enabled via env var.

    Args:
        allow_simulation: Whether simulation is allowed as a fallback.

    Returns:
        True if simulation should be used.
    """
    return allow_simulation and get_simulation_env_value() == "true"


def get_shipping_root_cause_summary() -> str:
    """Get the expected root cause summary for shipping injection.

    Returns:
        Root cause summary string.
    """
    return (
        f"Root cause identified: The {SHIPPING_DEPLOYMENT} Deployment "
        f"has an impossible nodeSelector requiring label "
        f"'{K8S_INJECTION_NODE_SELECTOR_KEY}={K8S_INJECTION_NODE_SELECTOR_VALUE}'. "
        f"No node in the cluster has this label, causing the shipping-* Pod "
        f"to remain in Pending state with status 'unschedulable'. "
        f"The nodeSelector prevents scheduling because there is no matching node."
    )
