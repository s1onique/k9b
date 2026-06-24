"""Safety enforcement for golden-case diagnosis outputs.

This module provides safety checks for diagnosis output:
- Checks for forbidden conclusions
- Checks for mutation proposals
- Ensures read-only behavior
"""

from __future__ import annotations

import re
from typing import Any

from .golden_case_one_pass_patterns import (
    _FORBIDDEN_CONCLUSION_PATTERNS,
    _MUTATION_PATTERNS,
)


def enforce_safety(diagnosis: dict[str, Any]) -> tuple[bool, list[str]]:
    """Enforce safety constraints on diagnosis output.

    Checks:
    - Forbidden conclusions should not appear in root cause or description
    - Mutation proposals should not appear in description or next_checks
    - read_only must be True
    - forbidden_actions_observed and mutation_proposals_observed must be empty

    Args:
        diagnosis: The diagnosis output to check

    Returns:
        Tuple of (is_safe, list of errors)
    """
    errors: list[str] = []
    root_cause = diagnosis.get("root_cause", "")
    description = diagnosis.get("description", "")

    for pattern, label in _FORBIDDEN_CONCLUSION_PATTERNS:
        if re.search(pattern, root_cause, re.IGNORECASE):
            errors.append(f"Forbidden conclusion in root_cause: {label}")
        if re.search(pattern, description, re.IGNORECASE):
            errors.append(f"Forbidden conclusion in description: {label}")

    for pattern in _MUTATION_PATTERNS:
        if re.search(pattern, description, re.IGNORECASE):
            errors.append(f"Mutation proposal in description: {pattern}")

    next_checks = diagnosis.get("next_checks", [])
    for i, check in enumerate(next_checks):
        if isinstance(check, dict):
            method = check.get("method", "")
            if method:
                for pattern in _MUTATION_PATTERNS:
                    if re.search(pattern, method, re.IGNORECASE):
                        errors.append(f"Mutation proposal in next_check[{i}].method: {pattern}")

    if not diagnosis.get("read_only", False):
        errors.append("read_only is not True")

    forbidden_observed = diagnosis.get("forbidden_actions_observed", [])
    if forbidden_observed:
        errors.append(f"forbidden_actions_observed is non-empty: {forbidden_observed}")

    mutation_observed = diagnosis.get("mutation_proposals_observed", [])
    if mutation_observed:
        errors.append(f"mutation_proposals_observed is non-empty: {mutation_observed}")

    return len(errors) == 0, errors
