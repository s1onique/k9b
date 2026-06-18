"""Read-only next-check policy registry and validation.

This module provides deterministic policy validation for next-check proposals:
- Defines a bounded read-only check registry
- Validates check IDs against the registry
- Rejects mutation/remediation check IDs
- Rejects direct command fields
- Enforces parameter constraints
- Bounds excessive check proposals

Design constraints:
- Pure functions only
- No store mutation
- No LLM calls
- No Kubernetes calls
- No execution, promotion, or remediation
- Deterministic validation
- Explicit safety metadata

This module does NOT:
- Execute checks
- Instantiate Kubernetes clients
- Call shell/subprocess
- Persist anything
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

__all__ = [
    "READ_ONLY_CHECK_REGISTRY",
    "FORBIDDEN_COMMAND_FIELDS",
    "CheckValidationResult",
    "NextCheckPolicy",
    "validate_next_check_proposal",
    "validate_next_check_proposals",
    "strip_forbidden_fields",
]


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


# =============================================================================
# Validation Result
# =============================================================================


@dataclass(frozen=True)
class CheckValidationResult:
    """Result of validating a single check proposal."""

    # Whether the check is accepted
    accepted: bool

    # The validated check (with forbidden fields stripped) if accepted
    validated_check: dict[str, Any] | None

    # Rejection reason if not accepted
    rejection_reason: str | None

    # Check ID that was validated/rejected
    check_id: str | None

    # Whether the check was rejected due to safety concerns
    safety_blocked: bool

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "accepted": self.accepted,
            "validated_check": self.validated_check,
            "rejection_reason": self.rejection_reason,
            "check_id": self.check_id,
            "safety_blocked": self.safety_blocked,
        }


# =============================================================================
# Validation Logic
# =============================================================================


def _has_forbidden_command_fields(proposal: Mapping[str, Any]) -> tuple[bool, str | None]:
    """Check if proposal contains forbidden command fields.

    Args:
        proposal: The check proposal to validate

    Returns:
        Tuple of (has_forbidden, reason_if_any)
    """
    for field in FORBIDDEN_COMMAND_FIELDS:
        if field in proposal:
            value = proposal.get(field)
            # Check direct value
            if value is not None and value != "":
                return True, f"Forbidden field '{field}' present with value"
            # Check nested values
            if isinstance(value, dict):
                for nested_val in value.values():
                    if nested_val is not None and nested_val != "":
                        return True, f"Forbidden field '{field}' contains non-empty nested value"
            if isinstance(value, list) and value:
                return True, f"Forbidden field '{field}' contains non-empty list"

    return False, None


def _is_mutation_check_id(check_id: str) -> bool:
    """Check if a check ID looks like a mutation action.

    Args:
        check_id: The check ID to validate

    Returns:
        True if the check ID appears to be mutation-like
    """
    check_id_lower = check_id.lower()

    # Check against explicit mutation IDs
    if check_id_lower in MUTATION_CHECK_IDS:
        return True

    # Check for kubectl prefix or mutation keywords
    mutation_patterns = (
        "kubectl_",
        "kubectl-",
        "_exec",
        "-exec",
        "restart",
        "scale",
        "rollout",
        "apply",
        "delete",
        "patch",
        "edit",
        "label",
        "annotate",
        "replace",
        "create",
        "run_script",
        "execute_command",
        "run_command",
    )

    for pattern in mutation_patterns:
        if pattern in check_id_lower:
            return True

    return False


def _validate_parameters(
    check_id: str,
    parameters: Mapping[str, Any] | None,
) -> tuple[bool, str | None, dict[str, Any]]:
    """Validate check parameters against registry.

    Args:
        check_id: The check ID
        parameters: The parameters to validate

    Returns:
        Tuple of (valid, reason_if_invalid, sanitized_parameters)
    """
    # If check_id not in registry, it's already rejected
    if check_id not in READ_ONLY_CHECK_REGISTRY:
        return False, f"Check ID '{check_id}' not in registry", {}

    registry_entry = READ_ONLY_CHECK_REGISTRY[check_id]
    allowed_params = registry_entry.get("allowed_parameters", frozenset())

    # If no parameters provided, that's fine
    if not parameters:
        return True, None, {}

    sanitized: dict[str, Any] = {}

    for key, value in parameters.items():
        # Skip None values
        if value is None:
            continue

        # Only allow known parameters
        if key not in allowed_params:
            # Strip unknown parameters instead of rejecting
            continue

        # Sanitize value types (no executable strings)
        if isinstance(value, str):
            # Strip any shell command patterns
            if any(cmd in value.lower() for cmd in (" && ", " || ", " | ", ";", "$(", "`")):
                continue
            sanitized[key] = value
        elif isinstance(value, (int, float, bool)):
            sanitized[key] = value
        elif isinstance(value, list):
            # Only keep lists of strings
            clean_list = [v for v in value if isinstance(v, str)]
            if clean_list:
                sanitized[key] = clean_list
        elif isinstance(value, dict):
            # Nested dicts are not allowed
            continue

    return True, None, sanitized


def strip_forbidden_fields(proposal: Mapping[str, Any]) -> dict[str, Any]:
    """Strip forbidden fields from a check proposal.

    Args:
        proposal: The check proposal to sanitize

    Returns:
        Sanitized dict without forbidden fields
    """
    result = {}
    for key, value in proposal.items():
        # Skip forbidden fields
        if key in FORBIDDEN_COMMAND_FIELDS:
            continue
        # Skip None values
        if value is None:
            continue
        # Skip mutation-like check IDs (strip completely)
        if key == "check_id" and isinstance(value, str):
            if _is_mutation_check_id(value):
                continue
        result[key] = value
    return result


# =============================================================================
# Main Validation Functions
# =============================================================================


def validate_next_check_proposal(
    proposal: Mapping[str, object],
) -> CheckValidationResult:
    """Validate a single next-check proposal against policy.

    This function performs deterministic validation:
    1. Checks for forbidden command fields
    2. Validates check_id is in registry
    3. Validates check_id is not mutation-like
    4. Validates and sanitizes parameters

    Args:
        proposal: The check proposal to validate

    Returns:
        CheckValidationResult with acceptance decision and details
    """
    check_id = proposal.get("check_id")

    # Check for forbidden command fields
    has_forbidden, forbidden_reason = _has_forbidden_command_fields(proposal)
    if has_forbidden:
        return CheckValidationResult(
            accepted=False,
            validated_check=None,
            rejection_reason=forbidden_reason,
            check_id=str(check_id) if check_id else None,
            safety_blocked=True,
        )

    # Must have a check_id
    if not check_id or not isinstance(check_id, str):
        return CheckValidationResult(
            accepted=False,
            validated_check=None,
            rejection_reason="Missing or invalid check_id",
            check_id=None,
            safety_blocked=False,
        )

    # Check if mutation-like check ID
    if _is_mutation_check_id(check_id):
        return CheckValidationResult(
            accepted=False,
            validated_check=None,
            rejection_reason=f"Check ID '{check_id}' appears to be mutation-like",
            check_id=check_id,
            safety_blocked=True,
        )

    # Check if in registry
    if check_id not in READ_ONLY_CHECK_REGISTRY:
        return CheckValidationResult(
            accepted=False,
            validated_check=None,
            rejection_reason=f"Check ID '{check_id}' not in read-only registry",
            check_id=check_id,
            safety_blocked=False,
        )

    # Validate and sanitize parameters
    parameters = proposal.get("parameters")
    if not isinstance(parameters, dict):
        parameters = {}

    valid, param_reason, sanitized_params = _validate_parameters(check_id, parameters)
    if not valid:
        return CheckValidationResult(
            accepted=False,
            validated_check=None,
            rejection_reason=param_reason,
            check_id=check_id,
            safety_blocked=True,
        )

    # Build validated check
    validated_check: dict[str, Any] = {
        "check_id": check_id,
        "title": str(proposal.get("title", check_id)),
        "read_only": True,
        "source": str(proposal.get("source", "llm-review")),
    }

    # Add rationale if present
    rationale = proposal.get("rationale")
    if isinstance(rationale, str) and rationale:
        # Bound length
        validated_check["rationale"] = rationale[:500] if len(rationale) > 500 else rationale

    # Add priority if present
    priority = proposal.get("priority")
    if isinstance(priority, int):
        validated_check["priority"] = priority

    # Add risk_level if present
    risk_level = proposal.get("risk_level")
    if isinstance(risk_level, str):
        validated_check["risk_level"] = risk_level

    # Add sanitized parameters
    if sanitized_params:
        validated_check["parameters"] = sanitized_params

    # Add expected_evidence if present
    expected = proposal.get("expected_evidence")
    if isinstance(expected, str) and expected:
        validated_check["expected_evidence"] = expected[:500] if len(expected) > 500 else expected

    return CheckValidationResult(
        accepted=True,
        validated_check=validated_check,
        rejection_reason=None,
        check_id=check_id,
        safety_blocked=False,
    )


def validate_next_check_proposals(
    proposals: Sequence[Mapping[str, object]],
    *,
    max_checks_per_pass: int = DEFAULT_MAX_CHECKS_PER_PASS,
) -> tuple[list[dict[str, Any]], list[CheckValidationResult]]:
    """Validate multiple next-check proposals with bounds.

    Args:
        proposals: Sequence of check proposals to validate
        max_checks_per_pass: Maximum checks to accept per pass

    Returns:
        Tuple of (accepted_checks, validation_results)
    """
    accepted: list[dict[str, Any]] = []
    results: list[CheckValidationResult] = []

    for proposal in proposals:
        # Stop accepting if max reached
        if len(accepted) >= max_checks_per_pass:
            results.append(
                CheckValidationResult(
                    accepted=False,
                    validated_check=None,
                    rejection_reason=f"Exceeds max_checks_per_pass ({max_checks_per_pass})",
                    check_id=str(proposal.get("check_id")) if proposal.get("check_id") else None,
                    safety_blocked=False,
                )
            )
            continue

        result = validate_next_check_proposal(proposal)
        results.append(result)

        if result.accepted and result.validated_check:
            accepted.append(result.validated_check)

    return accepted, results


# =============================================================================
# Policy Class (for convenience)
# =============================================================================


class NextCheckPolicy:
    """Policy validator for next-check proposals."""

    def __init__(
        self,
        max_checks_per_pass: int = DEFAULT_MAX_CHECKS_PER_PASS,
        max_total_checks: int = DEFAULT_MAX_TOTAL_CHECKS,
    ) -> None:
        """Initialize policy with bounds.

        Args:
            max_checks_per_pass: Maximum checks per pass
            max_total_checks: Maximum total checks across all passes
        """
        self.max_checks_per_pass = max_checks_per_pass
        self.max_total_checks = max_total_checks

    def validate(
        self,
        proposals: Sequence[Mapping[str, object]],
    ) -> tuple[list[dict[str, Any]], list[CheckValidationResult]]:
        """Validate proposals against this policy.

        Args:
            proposals: Proposals to validate

        Returns:
            Tuple of (accepted_checks, validation_results)
        """
        return validate_next_check_proposals(
            proposals,
            max_checks_per_pass=self.max_checks_per_pass,
        )

    @property
    def disallowed_actions(self) -> list[str]:
        """Return disallowed actions list."""
        return list(DISALLOWED_ACTIONS)

    @property
    def read_only(self) -> bool:
        """Return read-only flag."""
        return True

    @property
    def allowed_actions(self) -> list[str]:
        """Return allowed actions list (always empty)."""
        return []
