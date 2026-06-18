"""Read-only next-check policy registry and validation.

This module is a facade that re-exports the public API from split modules.

For the full implementation, see:
- incident_next_check_policy_registry: Constants and registry data
- incident_next_check_policy_validation: Validation functions

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

from .incident_next_check_policy_registry import (
    DEFAULT_MAX_CHECKS_PER_PASS,
    DEFAULT_MAX_TOTAL_CHECKS,
    DISALLOWED_ACTIONS,
    FORBIDDEN_COMMAND_FIELDS,
    MUTATION_CHECK_IDS,
    POLICY_SCHEMA_VERSION,
    READ_ONLY_CHECK_REGISTRY,
)
from .incident_next_check_policy_validation import (
    CheckValidationResult,
    NextCheckPolicy,
    strip_forbidden_fields,
    validate_next_check_proposal,
    validate_next_check_proposals,
)

__all__ = [
    "POLICY_SCHEMA_VERSION",
    "DISALLOWED_ACTIONS",
    "FORBIDDEN_COMMAND_FIELDS",
    "DEFAULT_MAX_CHECKS_PER_PASS",
    "DEFAULT_MAX_TOTAL_CHECKS",
    "READ_ONLY_CHECK_REGISTRY",
    "MUTATION_CHECK_IDS",
    "CheckValidationResult",
    "NextCheckPolicy",
    "validate_next_check_proposal",
    "validate_next_check_proposals",
    "strip_forbidden_fields",
]
