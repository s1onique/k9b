"""Safety enforcement for incident diagnosis output.

Enforces safety constraints on diagnosis output using golden-case patterns:
- ImagePullBackOff, ErrImagePull (image pull failures)
- PVC, PersistentVolumeClaim (storage failures)
- FailedScheduling (scheduling failures)
- registry auth failures
- cnpg-operator failures

Also checks for mutation proposals (kubectl apply, helm install, etc.)
"""

from __future__ import annotations

import re
from typing import Any

from .golden_case_one_pass_patterns import (
    _FORBIDDEN_CONCLUSION_PATTERNS,
    _MUTATION_PATTERNS,
)


def enforce_diagnosis_safety(diagnosis: dict[str, Any]) -> tuple[bool, list[str]]:
    """Enforce safety constraints on diagnosis output.

    Args:
        diagnosis: The diagnosis result to validate

    Returns:
        Tuple of (is_safe, list of error messages)
    """
    errors: list[str] = []
    root_cause = str(diagnosis.get("root_cause", ""))
    description = str(diagnosis.get("description", ""))

    # Check forbidden conclusions in root cause
    for pattern_str, label in _FORBIDDEN_CONCLUSION_PATTERNS:
        pattern = re.compile(pattern_str, re.IGNORECASE)
        if pattern.search(root_cause):
            errors.append(f"Forbidden conclusion in root_cause: '{label}'")
        if pattern.search(description):
            errors.append(f"Forbidden conclusion in description: '{label}'")

    # Check mutation proposals in description
    for pattern_str in _MUTATION_PATTERNS:
        pattern = re.compile(pattern_str, re.IGNORECASE)
        if pattern.search(description):
            errors.append(f"Mutation proposal in description: '{pattern_str}'")

    # Check mutation proposals in next_checks methods
    next_checks = diagnosis.get("next_checks", [])
    if isinstance(next_checks, list):
        for i, check in enumerate(next_checks):
            if isinstance(check, dict):
                method = check.get("method", "")
                if method:
                    for pattern_str in _MUTATION_PATTERNS:
                        pattern = re.compile(pattern_str, re.IGNORECASE)
                        if pattern.search(method):
                            errors.append(f"Mutation proposal in next_check[{i}].method: '{pattern_str}'")

    # Check read_only flag
    if not diagnosis.get("read_only", False):
        errors.append("Diagnosis must have read_only=True")

    # Check allowed_actions is empty
    if diagnosis.get("allowed_actions") != []:
        errors.append("Diagnosis must have allowed_actions=[]")

    return len(errors) == 0, errors
